import fcntl
import os
import shutil
import subprocess
import tempfile
import time


STATUS_SOCAT_CACHE_TTL = 15
_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
STATUS_CACHE_DIR = os.path.join(_BASE_DIR, "ovpn-status")

OPENVPN_STATUS_SOURCES = (
    (
        "UDP",
        (
            "/etc/openvpn/server/logs/antizapret-udp-status.log",
            "/run/openvpn-server/status-antizapret-udp.log",
        ),
        "/run/openvpn-server/antizapret-udp.sock",
    ),
    (
        "TCP",
        (
            "/etc/openvpn/server/logs/antizapret-tcp-status.log",
            "/run/openvpn-server/status-antizapret-tcp.log",
        ),
        "/run/openvpn-server/antizapret-tcp.sock",
    ),
    (
        "VPN-UDP",
        (
            "/etc/openvpn/server/logs/vpn-udp-status.log",
            "/run/openvpn-server/status-vpn-udp.log",
        ),
        "/run/openvpn-server/vpn-udp.sock",
    ),
    (
        "VPN-TCP",
        (
            "/etc/openvpn/server/logs/vpn-tcp-status.log",
            "/run/openvpn-server/status-vpn-tcp.log",
        ),
        "/run/openvpn-server/vpn-tcp.sock",
    ),
)

OPENVPN_STATUS_LABELS = {
    "UDP": "Antizapret UDP",
    "TCP": "Antizapret TCP",
    "VPN-UDP": "VPN UDP",
    "VPN-TCP": "VPN TCP",
}

_SOURCES_BY_PROTOCOL = {item[0]: item for item in OPENVPN_STATUS_SOURCES}


def iter_openvpn_status_sources():
    for protocol, files, socket_path in OPENVPN_STATUS_SOURCES:
        yield protocol, files, socket_path


def _read_nonempty_file(path):
    try:
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            return None
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return None


def _cache_paths(socket_path):
    name = os.path.basename(socket_path).removesuffix(".sock")
    base = os.path.join(STATUS_CACHE_DIR, name)
    return f"{base}.cache", f"{base}.lock"


def _ensure_cache_dir():
    try:
        os.makedirs(STATUS_CACHE_DIR, mode=0o755, exist_ok=True)
        return True
    except OSError:
        return False


def _read_shared_cache(cache_path):
    try:
        stat = os.stat(cache_path)
        if stat.st_size == 0:
            return None
        if time.time() - stat.st_mtime > STATUS_SOCAT_CACHE_TTL:
            return None
        with open(cache_path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        return text if text.strip() else None
    except OSError:
        return None


def _write_shared_cache(cache_path, text):
    directory = os.path.dirname(cache_path)
    try:
        fd, tmp_path = tempfile.mkstemp(prefix=".cache-", dir=directory)
    except OSError:
        return
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, cache_path)
    except OSError:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _fetch_status_via_socat(socket_path):
    if not os.path.exists(socket_path):
        return None, None

    socat_bin = shutil.which("socat") or "/usr/bin/socat"
    if not os.path.isfile(socat_bin):
        return None, "socat не найден"

    try:
        proc = subprocess.run(
            [socat_bin, "-t", "2", "-", f"UNIX-CONNECT:{socket_path}"],
            input="status 2\n",
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, f"Таймаут socat: {socket_path}"
    except OSError as exc:
        return None, str(exc)

    text = proc.stdout or ""
    if not text.strip():
        err = (proc.stderr or "").strip() or f"Пустой ответ socat: {socket_path}"
        return None, err
    return text, None


def _fetch_status_shared(socket_path):
    if not os.path.exists(socket_path):
        return None, None

    if not _ensure_cache_dir():
        return _fetch_status_via_socat(socket_path)

    cache_path, lock_path = _cache_paths(socket_path)
    cached = _read_shared_cache(cache_path)
    if cached is not None:
        return cached, None

    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    except OSError:
        return _fetch_status_via_socat(socket_path)

    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        cached = _read_shared_cache(cache_path)
        if cached is not None:
            return cached, None

        text, error = _fetch_status_via_socat(socket_path)
        if text is not None:
            _write_shared_cache(cache_path, text)
        return text, error
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(lock_fd)


def get_openvpn_status_text(protocol):
    source = _SOURCES_BY_PROTOCOL.get(protocol)
    if not source:
        return None, f"Неизвестный протокол: {protocol}"

    _, files, socket_path = source
    for path in files:
        text = _read_nonempty_file(path)
        if text is not None:
            return text, None

    return _fetch_status_shared(socket_path)


def iter_client_list_rows(status_text):
    if not status_text:
        return
    for raw_line in status_text.splitlines():
        line = raw_line.strip()
        if not line.startswith("CLIENT_LIST"):
            continue
        parts = line.split(",")
        if len(parts) < 8:
            continue
        yield parts


def count_openvpn_online_from_status():
    total = 0
    for protocol, _, _ in OPENVPN_STATUS_SOURCES:
        text, _ = get_openvpn_status_text(protocol)
        if not text:
            continue
        for parts in iter_client_list_rows(text):
            name = parts[1].strip() if len(parts) > 1 else ""
            if name and name != "UNDEF":
                total += 1
    return total
