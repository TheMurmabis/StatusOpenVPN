import os
import subprocess
import time
from threading import Lock

import requests
from packaging.version import InvalidVersion, Version

from src.ui.constants import BASE_DIR, GITHUB_REPO, UPDATE_LOG_PATH, UPDATE_SCRIPT
from src.ui.services.system_info_service import get_git_version

UPDATE_CHECK_TTL = 900
UPDATE_LOCK_PATH = "/tmp/statusopenvpn-update.lock"

_update_cache = {"at": 0.0, "latest": None, "error": None}
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


def _fetch_github_tags():
    url = f"https://api.github.com/repos/{GITHUB_REPO}/tags"
    response = requests.get(url, params={"per_page": 100}, timeout=15)
    response.raise_for_status()
    return response.json()


def get_latest_github_version():
    with _update_cache_lock:
        if time.time() - _update_cache["at"] < UPDATE_CHECK_TTL:
            if _update_cache["error"]:
                return None, _update_cache["error"]
            return _update_cache["latest"], None

    try:
        tags = _fetch_github_tags()
        best_tag = None
        best_version = None
        for item in tags:
            name = item.get("name", "")
            parsed = normalize_version_tag(name)
            if parsed is None:
                continue
            if best_version is None or parsed > best_version:
                best_version = parsed
                best_tag = name
        with _update_cache_lock:
            _update_cache["at"] = time.time()
            _update_cache["latest"] = best_tag
            _update_cache["error"] = None
        return best_tag, None
    except Exception as exc:
        with _update_cache_lock:
            _update_cache["at"] = time.time()
            _update_cache["latest"] = None
            _update_cache["error"] = str(exc)
        return None, str(exc)


def is_update_available():
    current = get_current_version()
    latest, _error = get_latest_github_version()
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
        _update_cache["error"] = None
