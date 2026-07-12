import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from typing import BinaryIO

from src.tg_bot.config import load_settings, normalize_settings_data, save_settings
from src.tg_bot.settings_report import settings_are_equal
from src.ui.constants import BASE_DIR, CLIENT_SH_PATH, SETTINGS_PATH
from src.ui.utils.network_utils import get_external_ip

DATABASES_DIR = os.path.join(BASE_DIR, "src", "databases")
STATUSOPENVPN_BACKUP_DIR = "/root/StatusOpenVPN-backup"
SETTINGS_RESTORE_PHRASE = "settings.json"
MAX_RESTORE_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_SETTINGS_RESTORE_BYTES = 1_000_000
SETTINGS_KEY_TYPES = {
    "app_name": str,
    "telegram_admins": dict,
    "telegram_clients": dict,
    "tg_bot_banned_user_ids": list,
    "tg_bot_pending_requests": dict,
    "bot_enabled": bool,
    "show_ovpn_menu": bool,
    "show_wg_menu": bool,
    "hide_ovpn_ip": bool,
    "hide_wg_ip": bool,
    "hide_wg_warp_interface": bool,
    "shorten_wg_filenames": bool,
    "stats_retention_days": int,
    "history_max_records": int,
    "load_thresholds": dict,
    "vpn_service_monitoring_enabled": bool,
    "vpn_monitored_services": dict,
    "tg_bot_profile_seeded": bool,
}


def get_statusopenvpn_backup_sources() -> list[tuple[str, str]]:
    src_dir = os.path.join(BASE_DIR, "src")
    candidates = [
        DATABASES_DIR,
        src_dir,
        STATUSOPENVPN_BACKUP_DIR,
    ]
    sources: list[tuple[str, str]] = []
    seen = set()

    for candidate in candidates:
        if os.path.isdir(candidate):
            for root, _, files in os.walk(candidate):
                for name in files:
                    path = os.path.join(root, name)
                    if candidate.endswith(os.path.join("src", "databases")):
                        archive_name = os.path.join(
                            "src",
                            "databases",
                            os.path.relpath(path, candidate),
                        )
                    elif candidate.endswith("src"):
                        if not name.endswith(".db"):
                            continue
                        archive_name = os.path.join(
                            "src", os.path.relpath(path, candidate)
                        )
                    else:
                        archive_name = os.path.join(
                            os.path.basename(candidate),
                            os.path.relpath(path, candidate),
                        )
                    real_path = os.path.realpath(path)
                    if real_path not in seen:
                        seen.add(real_path)
                        sources.append((path, archive_name))
        elif os.path.isfile(candidate):
            real_path = os.path.realpath(candidate)
            if real_path not in seen:
                seen.add(real_path)
                sources.append((candidate, os.path.basename(candidate)))

    return sources


def build_statusopenvpn_backup_archive(dest_path: str) -> tuple[bool, str]:
    sources = get_statusopenvpn_backup_sources()
    if not sources:
        return False, "Файлы для бэкапа StatusOpenVPN не найдены."

    try:
        with tarfile.open(dest_path, "w:gz") as archive:
            for source_path, archive_name in sources:
                archive.add(source_path, arcname=archive_name)
        return True, ""
    except OSError as e:
        return False, str(e)


def find_vpn_clients_backup_path() -> str | None:
    server_ip = get_external_ip() or ""
    paths_to_check = []
    if server_ip and " " not in server_ip and "Ошибка" not in server_ip:
        paths_to_check.append(f"/root/antizapret/backup-{server_ip}.tar.gz")
    paths_to_check.append("/root/antizapret/backup.tar.gz")

    for backup_path in paths_to_check:
        if os.path.isfile(backup_path):
            return backup_path
    return None


def create_vpn_clients_backup() -> tuple[bool, str, str | None]:
    if not os.path.isfile(CLIENT_SH_PATH):
        return False, "Не найден скрипт client.sh", None

    env = os.environ.copy()
    env["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    try:
        proc = subprocess.run(
            [CLIENT_SH_PATH, "8"],
            capture_output=True,
            text=True,
            env=env,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return False, "Превышено время ожидания client.sh", None
    except OSError as e:
        return False, str(e), None

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return False, err or f"client.sh завершился с кодом {proc.returncode}", None

    path = find_vpn_clients_backup_path()
    if not path:
        return False, "Файл бэкапа клиентов не найден после создания.", None
    return True, "", path


def settings_file_path() -> str | None:
    if os.path.isfile(SETTINGS_PATH):
        return SETTINGS_PATH
    return None


def _is_safe_archive_member(member: tarfile.TarInfo) -> bool:
    name = member.name.replace("\\", "/")
    if name.startswith("/") or name.startswith("..") or "/../" in f"/{name}/":
        return False
    if member.islnk() or member.issym():
        return False
    return member.isfile() or member.isdir()


def _collect_db_files_from_extract(extract_dir: str) -> list[tuple[str, str]]:
    preferred = os.path.join(extract_dir, "src", "databases")
    search_roots = []
    if os.path.isdir(preferred):
        search_roots.append(preferred)
    else:
        search_roots.append(extract_dir)

    found: list[tuple[str, str]] = []
    for root in search_roots:
        for dirpath, _, filenames in os.walk(root):
            for name in filenames:
                if not name.endswith(".db"):
                    continue
                path = os.path.join(dirpath, name)
                found.append((path, name))
    return found


def restore_statusopenvpn_from_archive(file_storage: BinaryIO, filename: str) -> tuple[bool, str]:
    name = (filename or "").strip().lower()
    if not (name.endswith(".tar.gz") or name.endswith(".tgz")):
        return False, "Нужен архив .tar.gz (как в бэкапе StatusOpenVPN)."

    file_storage.seek(0, os.SEEK_END)
    size = file_storage.tell()
    file_storage.seek(0)
    if size <= 0:
        return False, "Пустой файл."
    if size > MAX_RESTORE_ARCHIVE_BYTES:
        return False, "Архив слишком большой (максимум 512 МБ)."

    with tempfile.TemporaryDirectory(prefix="sovpn-restore-") as tmpdir:
        archive_path = os.path.join(tmpdir, "upload.tar.gz")
        with open(archive_path, "wb") as out:
            shutil.copyfileobj(file_storage, out)

        extract_dir = os.path.join(tmpdir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)

        try:
            with tarfile.open(archive_path, "r:gz") as archive:
                members = [m for m in archive.getmembers() if _is_safe_archive_member(m)]
                if not members:
                    return False, "В архиве нет безопасных файлов для восстановления."
                archive.extractall(extract_dir, members=members)
        except tarfile.TarError:
            return False, "Не удалось прочитать архив. Проверьте, что это корректный .tar.gz."
        except OSError as e:
            return False, str(e)

        db_files = _collect_db_files_from_extract(extract_dir)
        if not db_files:
            return False, "В архиве не найдены файлы .db."

        os.makedirs(DATABASES_DIR, exist_ok=True)
        restored = []
        try:
            for src_path, dest_name in db_files:
                dest_path = os.path.join(DATABASES_DIR, dest_name)
                shutil.copy2(src_path, dest_path)
                restored.append(dest_name)
        except OSError as e:
            return False, f"Ошибка записи баз данных: {e}"

        return True, f"Восстановлено файлов: {len(restored)} ({', '.join(sorted(restored))})."


def _has_settings_structure(data: dict) -> bool:
    return any(
        key in data and isinstance(data.get(key), expected_type)
        for key, expected_type in SETTINGS_KEY_TYPES.items()
    )


def restore_settings_from_file(file_storage: BinaryIO, filename: str) -> tuple[bool, str]:
    name = (filename or "").strip().lower()
    if not name.endswith(".json"):
        return False, "Нужен файл settings.json."

    file_storage.seek(0, os.SEEK_END)
    size = file_storage.tell()
    file_storage.seek(0)
    if size <= 0:
        return False, "Пустой файл."
    if size > MAX_SETTINGS_RESTORE_BYTES:
        return False, "Файл слишком большой (максимум 1 МБ)."

    try:
        raw = file_storage.read().decode("utf-8")
        parsed = json.loads(raw)
    except UnicodeDecodeError:
        return False, "Файл должен быть в кодировке UTF-8."
    except json.JSONDecodeError:
        return False, "Некорректный JSON в settings.json."

    if not isinstance(parsed, dict):
        return False, "Корневой элемент settings.json должен быть объектом JSON."
    if not _has_settings_structure(parsed):
        return False, "Структура файла не похожа на settings.json."

    imported = normalize_settings_data(parsed)
    current = normalize_settings_data(load_settings())
    if settings_are_equal(current, imported):
        return True, "Файл совпадает с текущими настройками. Изменений не было."

    try:
        save_settings(imported)
    except OSError as e:
        return False, f"Ошибка записи settings.json: {e}"

    return True, "Файл settings.json восстановлен."
