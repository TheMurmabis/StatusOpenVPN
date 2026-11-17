import os
import re
import shutil
import subprocess

from src.ui.constants import WG_CLIENT_CONFIG_DIRS


WG_SERVER_CONFIG_PATHS = (
    "/etc/wireguard/vpn.conf",
    "/etc/wireguard/antizapret.conf",
)


def _configured_wireguard_client_names():
    names = set()
    config_read = False
    for path in WG_SERVER_CONFIG_PATHS:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                config_read = True
                for line in handle:
                    stripped = line.strip()
                    if stripped.startswith("# Client ="):
                        name = stripped.split("=", 1)[1].strip()
                        if name:
                            names.add(name)
        except OSError:
            continue
    return names, config_read


def _wireguard_client_names_from_files():
    names = set()
    for directory, interface, suffix in WG_CLIENT_CONFIG_DIRS:
        try:
            filenames = os.listdir(directory)
        except OSError:
            continue
        pattern = re.compile(
            rf"^{re.escape(interface)}-(.+)-\([^)]+\)-{re.escape(suffix)}\.conf$"
        )
        for filename in filenames:
            match = pattern.fullmatch(filename)
            if match and os.path.isfile(os.path.join(directory, filename)):
                names.add(match.group(1))
    return names


def list_wireguard_client_names():
    """Точные имена клиентов из серверного WireGuard-конфига.

    client.sh удаляет префиксы ``antizapret-`` и ``vpn-`` только из имени
    выдаваемого файла. Идентичность клиента при этом остаётся в строке
    ``# Client = ...`` и должна браться именно оттуда.
    """
    configured, config_read = _configured_wireguard_client_names()
    if not config_read:
        return _wireguard_client_names_from_files()
    return {name for name in configured if list_wg_conf_paths_for_client(name)}


def wg_conf_name_core(client_name: str) -> str:
    name = (client_name or "").strip()
    lowered = name.lower()
    for prefix in ("antizapret-", "vpn-"):
        if lowered.startswith(prefix):
            return name[len(prefix):]
    return name


def wg_client_name_param_ok(name: str) -> bool:
    """Имя клиента из UI/запроса: без path traversal, до 128 символов (не только ASCII)."""
    raw = (name or "").strip()
    if not raw or len(raw) > 128:
        return False
    if "\x00" in raw or "/" in raw or "\\" in raw:
        return False
    return True


def list_wg_conf_paths_for_client(client_name: str):
    """Пути к .conf клиента (шаблон интерфейс-имя-(…)-wg|am.conf)."""
    raw = (client_name or "").strip()
    if not raw or not wg_client_name_param_ok(raw):
        return []
    configured, config_read = _configured_wireguard_client_names()
    if config_read and raw not in configured:
        return []

    lookup_names = {raw}
    core = wg_conf_name_core(raw)
    if core:
        lookup_names.add(core)
    without_note = re.sub(r"\s*\([^)]*\)\s*$", "", raw).strip()
    if without_note:
        lookup_names.add(without_note)
    matches = []
    for dir_path, iface, suffix in WG_CLIENT_CONFIG_DIRS:
        if not os.path.isdir(dir_path):
            continue
        patterns = [
            re.compile(
                rf"^{re.escape(iface)}-{re.escape(name)}-\([^)]+\)-{re.escape(suffix)}\.conf$"
            )
            for name in lookup_names
        ]
        try:
            for fn in os.listdir(dir_path):
                if any(pat.match(fn) for pat in patterns):
                    matches.append(os.path.join(dir_path, fn))
        except OSError:
            continue
    matches.sort()
    return matches


def wg_conf_short_filename(full_path: str) -> str:
    basename = os.path.basename(full_path)
    return re.sub(r"-\([^)]+\)-", "-", basename, count=1)


def wg_conf_profile_label(full_path: str) -> str:
    basename = os.path.basename(full_path)
    parent = os.path.basename(os.path.dirname(full_path))
    if "amneziawg" in full_path:
        kind = "AmneziaWG"
    else:
        kind = "WireGuard"
    return f"{parent} · {kind} · {basename}"


def wg_conf_path_is_allowed(abs_path: str) -> bool:
    abs_path = os.path.realpath(abs_path)
    roots = [
        os.path.realpath("/root/antizapret/client/wireguard"),
        os.path.realpath("/root/antizapret/client/amneziawg"),
    ]
    for root in roots:
        if abs_path.startswith(root + os.sep) and abs_path.endswith(".conf"):
            return os.path.isfile(abs_path)
    return False


def wg_choice_from_path(full_path: str):
    basename = os.path.basename(full_path)
    parent = os.path.basename(os.path.dirname(full_path)).lower()
    path_lower = (full_path or "").lower()
    name_lower = basename.lower()

    if parent == "antizapret" or name_lower.startswith("antizapret-"):
        profile = "antizapret"
    elif parent == "vpn" or name_lower.startswith("vpn-"):
        profile = "vpn"
    else:
        profile = "other"

    if "amneziawg" in path_lower or name_lower.endswith("-am.conf"):
        kind = "amnezia"
        kind_slug = "am"
    else:
        kind = "wireguard"
        kind_slug = "wg"

    return {
        "family": "wireguard",
        "profile": profile,
        "kind": kind,
        "slug": f"{profile}-{kind_slug}",
        "filename": basename,
        "label": wg_conf_profile_label(full_path),
        "path": full_path,
        "ext": "conf",
    }


def list_wireguard_profile_choices(client_name: str):
    choices = []
    seen_slugs = set()
    for path in list_wg_conf_paths_for_client(client_name):
        item = wg_choice_from_path(path)
        if item["slug"] in seen_slugs:
            continue
        seen_slugs.add(item["slug"])
        choices.append(item)
    profile_order = {"antizapret": 0, "vpn": 1, "other": 2}
    kind_order = {"wireguard": 0, "amnezia": 1}
    choices.sort(
        key=lambda item: (
            profile_order.get(item["profile"], 9),
            kind_order.get(item["kind"], 9),
            item["slug"],
        )
    )
    return choices


def wg_qr_png_for_conf_path(path: str) -> bytes:
    qrencode_bin = shutil.which("qrencode") or "/usr/bin/qrencode"
    if not os.path.isfile(qrencode_bin):
        raise FileNotFoundError("qrencode не найден. Установите пакет qrencode.")

    with open(path, "rb") as handle:
        config_data = handle.read()

    proc = subprocess.run(
        [qrencode_bin, "-t", "PNG", "-s", "10", "-m", "2", "-o", "-"],
        input=config_data,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode(errors="replace").strip()
        raise RuntimeError(stderr or f"qrencode завершился с кодом {proc.returncode}")
    if not proc.stdout:
        raise RuntimeError("qrencode не вернул изображение")
    return proc.stdout
