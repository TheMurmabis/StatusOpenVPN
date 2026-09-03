import os
import re
import subprocess
import time
from threading import Lock

import bleach
import markdown
import requests
from bleach import callbacks
from packaging.version import InvalidVersion, Version

from src.ui.constants import BASE_DIR, GITHUB_REPO, UPDATE_LOG_PATH, UPDATE_SCRIPT
from src.ui.services.system_info_service import get_git_version

UPDATE_CHECK_TTL = 900
UPDATE_LOCK_PATH = "/tmp/statusopenvpn-update.lock"
GITHUB_RELEASES_LATEST_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

_update_cache = {
    "at": 0.0,
    "latest": None,
    "changelog_md": None,
    "changelog_html": None,
    "changelog_url": None,
    "published_at": None,
    "etag": None,
    "error": None,
}
_update_cache_lock = Lock()
_update_process_lock = Lock()


def normalize_version_tag(tag):
    if not tag:
        return None
    value = str(tag).strip()
    if value.startswith("v"):
        value = value[1:]
    try:
        return Version(value)
    except InvalidVersion:
        return None


def get_current_version():
    return get_git_version()


def render_changelog_html(markdown_text):
    if not markdown_text:
        return ""
    lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    normalized = []
    for line in lines:
        if line.startswith("  - ") or line.startswith("  * "):
            line = "    " + line[2:]
        elif re.match(r"^  \d+\.\s+", line):
            line = "    " + line[2:]
        is_top_list = bool(line) and (
            line.startswith("- ")
            or line.startswith("* ")
            or re.match(r"^\d+\.\s+", line)
        )
        if is_top_list:
            prev = normalized[-1] if normalized else ""
            if prev.strip():
                normalized.append("")
        normalized.append(line)
    html = markdown.markdown(
        "\n".join(normalized), extensions=["extra", "sane_lists", "tables"]
    )
    allowed_tags = [
        "p",
        "ul",
        "ol",
        "li",
        "strong",
        "em",
        "code",
        "pre",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "blockquote",
        "a",
        "br",
        "hr",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
    ]
    allowed_attrs = {
        "a": ["href", "title", "rel", "target"],
    }
    cleaned = bleach.clean(
        html,
        tags=allowed_tags,
        attributes=allowed_attrs,
        protocols=["http", "https"],
        strip=True,
    )
    return bleach.linkify(
        cleaned,
        callbacks=[callbacks.nofollow, callbacks.target_blank],
    )


_CHANGE_SECTION_PATTERNS = [
    re.compile(r"(?i)добавлен|added|новое"),
    re.compile(r"(?i)исправлен|fixed|bug"),
    re.compile(r"(?i)изменен|changed|улучшен|improved"),
    re.compile(r"(?i)удален|removed|deprecated"),
]

_CHANGELOG_HEADING_RE = re.compile(
    r"^\s{0,3}(?:#{1,6}\s+|\*\*|__)(.+?)(?:\*\*|__)?\s*$"
)


def _is_change_section_title(title):
    value = (title or "").strip().rstrip(":")
    if not value:
        return False
    return any(pattern.search(value) for pattern in _CHANGE_SECTION_PATTERNS)


def split_changelog_markdown(markdown_text):
    """Split release notes into change sections and overview (e.g. Основные функции)."""
    if not markdown_text:
        return "", ""

    lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    change_start = None
    for index, raw_line in enumerate(lines):
        heading = _CHANGELOG_HEADING_RE.match(raw_line.rstrip())
        if not heading:
            continue
        if _is_change_section_title(heading.group(1)):
            change_start = index
            break

    if change_start is None:
        return markdown_text.strip(), ""

    changes = "\n".join(lines[change_start:]).strip()
    overview = "\n".join(lines[:change_start]).strip()
    return changes, overview


def summarize_changelog_changes(markdown_text):
    if not markdown_text:
        return []

    section_patterns = [
        (re.compile(r"(?i)добавлен|added|новое"), "добавления"),
        (re.compile(r"(?i)исправлен|fixed|bug"), "исправления"),
        (re.compile(r"(?i)изменен|changed|улучшен|improved"), "изменения"),
        (re.compile(r"(?i)удален|removed|deprecated"), "удаления"),
    ]
    item_re = re.compile(r"^[-*+]\s+\S")

    counts = {}
    current_label = None
    for raw_line in markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.rstrip()
        heading = _CHANGELOG_HEADING_RE.match(line)
        if heading:
            title = heading.group(1).strip().rstrip(":")
            current_label = None
            for pattern, label in section_patterns:
                if pattern.search(title):
                    current_label = label
                    counts.setdefault(label, 0)
                    break
            continue
        if current_label and item_re.match(line):
            counts[current_label] += 1

    summary = []
    for label in ("добавления", "исправления", "изменения", "удаления"):
        count = counts.get(label, 0)
        if count:
            summary.append({"label": label, "count": count})
    return summary


def _cache_snapshot():
    with _update_cache_lock:
        return {
            "latest": _update_cache["latest"],
            "changelog_md": _update_cache["changelog_md"],
            "changelog_html": _update_cache["changelog_html"] or "",
            "changelog_url": _update_cache["changelog_url"],
            "published_at": _update_cache["published_at"],
            "at": _update_cache["at"],
            "etag": _update_cache["etag"],
            "error": _update_cache["error"],
        }


def get_release_info(force=False):
    with _update_cache_lock:
        cached_at = _update_cache["at"]
        etag = _update_cache["etag"]
        if (
            not force
            and cached_at
            and time.time() - cached_at < UPDATE_CHECK_TTL
        ):
            return {
                "latest": _update_cache["latest"],
                "changelog_md": _update_cache["changelog_md"],
                "changelog_html": _update_cache["changelog_html"] or "",
                "changelog_url": _update_cache["changelog_url"],
                "published_at": _update_cache["published_at"],
                "at": _update_cache["at"],
                "etag": _update_cache["etag"],
                "error": _update_cache["error"],
            }

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "StatusOpenVPN",
    }
    if etag:
        headers["If-None-Match"] = etag

    try:
        response = requests.get(
            GITHUB_RELEASES_LATEST_URL,
            headers=headers,
            timeout=15,
        )
        if response.status_code == 304:
            with _update_cache_lock:
                _update_cache["at"] = time.time()
                _update_cache["error"] = None
                if response.headers.get("ETag"):
                    _update_cache["etag"] = response.headers.get("ETag")
            return _cache_snapshot()

        response.raise_for_status()
        data = response.json()
        tag_name = data.get("tag_name")
        body = (data.get("body") or "").strip()
        html_url = data.get("html_url")
        published_at = data.get("published_at")
        changelog_html = render_changelog_html(body)

        with _update_cache_lock:
            _update_cache["at"] = time.time()
            _update_cache["latest"] = tag_name
            _update_cache["changelog_md"] = body
            _update_cache["changelog_html"] = changelog_html
            _update_cache["changelog_url"] = html_url
            _update_cache["published_at"] = published_at
            _update_cache["etag"] = response.headers.get("ETag")
            _update_cache["error"] = None
        return _cache_snapshot()
    except Exception as exc:
        with _update_cache_lock:
            _update_cache["at"] = time.time()
            _update_cache["error"] = str(exc)
        return _cache_snapshot()


def get_latest_github_version(force=False):
    info = get_release_info(force=force)
    return info["latest"], info["error"]


def get_update_check_time():
    with _update_cache_lock:
        return _update_cache["at"]


def is_update_available():
    current = get_current_version()
    info = get_release_info()
    latest = info["latest"]
    if not latest or current == "unknown":
        return False, current, latest
    current_v = normalize_version_tag(current)
    latest_v = normalize_version_tag(latest)
    if current_v is None or latest_v is None:
        return False, current, latest
    return latest_v > current_v, current, latest


def is_update_running():
    if not os.path.isfile(UPDATE_LOCK_PATH):
        return False
    try:
        with open(UPDATE_LOCK_PATH, encoding="utf-8") as lock_file:
            pid = int(lock_file.read().strip() or "0")
    except (OSError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def read_update_log_tail(max_lines=80):
    if not os.path.isfile(UPDATE_LOG_PATH):
        return ""
    try:
        with open(UPDATE_LOG_PATH, encoding="utf-8", errors="replace") as log_file:
            lines = log_file.readlines()
        return "".join(lines[-max_lines:])
    except OSError:
        return ""


def start_silent_update(tag):
    if not tag:
        return False, "Тег обновления не указан."
    if not os.path.isfile(UPDATE_SCRIPT):
        return False, "Скрипт обновления не найден."
    if is_update_running():
        return False, "Обновление уже выполняется."

    with _update_process_lock:
        if is_update_running():
            return False, "Обновление уже выполняется."
        try:
            os.makedirs(os.path.dirname(UPDATE_LOG_PATH), exist_ok=True)
            log_file = open(UPDATE_LOG_PATH, "w", encoding="utf-8")
        except OSError as exc:
            return False, f"Не удалось создать журнал: {exc}"

        try:
            process = subprocess.Popen(
                ["/bin/bash", UPDATE_SCRIPT, tag],
                cwd=BASE_DIR,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            with open(UPDATE_LOCK_PATH, "w", encoding="utf-8") as lock_file:
                lock_file.write(str(process.pid))
        except OSError as exc:
            log_file.close()
            return False, f"Не удалось запустить обновление: {exc}"
        finally:
            log_file.close()

    return True, None


def clear_update_cache():
    with _update_cache_lock:
        _update_cache["at"] = 0.0
        _update_cache["latest"] = None
        _update_cache["changelog_md"] = None
        _update_cache["changelog_html"] = None
        _update_cache["changelog_url"] = None
        _update_cache["published_at"] = None
        _update_cache["etag"] = None
        _update_cache["error"] = None
