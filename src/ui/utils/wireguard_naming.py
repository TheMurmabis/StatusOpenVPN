import os
import re

from src.ui.constants import WG_CLIENT_CONFIG_DIRS


def wg_conf_name_core(client_name: str) -> str:
    return (client_name or "").strip().replace("antizapret-", "").replace("vpn-", "")


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
    name_core = wg_conf_name_core(raw)
    if not name_core:
        return []
    matches = []
    for dir_path, iface, suffix in WG_CLIENT_CONFIG_DIRS:
        if not os.path.isdir(dir_path):
            continue
        pat = re.compile(
            rf"^{re.escape(iface)}-{re.escape(name_core)}-\([^)]+\)-{re.escape(suffix)}\.conf$"
        )
        try:
            for fn in os.listdir(dir_path):
                if pat.match(fn):
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
