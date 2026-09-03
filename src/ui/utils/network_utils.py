import ipaddress
import subprocess
import time
from threading import Lock

import psutil
import requests

_IP_CACHE_TTL = 300
_IP_FAIL_TTL = 30
_ip_cache = {"value": None, "at": 0.0, "ok": False}
_ip_cache_lock = Lock()


def _parse_ip(value):
    try:
        return ipaddress.ip_address(str(value or "").strip())
    except ValueError:
        return None


def is_public_ip(value):
    parsed = _parse_ip(value)
    return bool(parsed and parsed.is_global)


def get_default_interface():
    try:
        result = subprocess.run(
            ["/usr/bin/ip", "route"], capture_output=True, text=True, check=True
        )
        for line in result.stdout.splitlines():
            if "default" in line:
                return line.split()[4]
    except Exception as e:
        print(f"Ошибка: {e}")
    return None


def get_network_stats(interface):
    try:
        with open(
            f"/sys/class/net/{interface}/statistics/rx_bytes", "r", encoding="utf-8"
        ) as f:
            rx_bytes = int(f.read().strip())
        with open(
            f"/sys/class/net/{interface}/statistics/tx_bytes", "r", encoding="utf-8"
        ) as f:
            tx_bytes = int(f.read().strip())
        return {"interface": interface, "rx": rx_bytes, "tx": tx_bytes}
    except FileNotFoundError:
        return None


def get_network_load():
    net_io_start = psutil.net_io_counters(pernic=True)
    time.sleep(1)
    net_io_end = psutil.net_io_counters(pernic=True)

    network_data = {}
    for interface in net_io_start:
        if interface == "lo":
            continue

        sent_start, recv_start = (
            net_io_start[interface].bytes_sent,
            net_io_start[interface].bytes_recv,
        )
        sent_end, recv_end = (
            net_io_end[interface].bytes_sent,
            net_io_end[interface].bytes_recv,
        )

        sent_speed = (sent_end - sent_start) * 8 / 1e6
        recv_speed = (recv_end - recv_start) * 8 / 1e6

        if sent_speed > 0 or recv_speed > 0:
            network_data[interface] = {
                "sent_speed": round(sent_speed, 2),
                "recv_speed": round(recv_speed, 2),
            }

    return network_data


def get_uptime():
    try:
        uptime = (
            subprocess.check_output("/usr/bin/uptime -p", shell=True).decode().strip()
        )
    except subprocess.CalledProcessError:
        uptime = "Не удалось получить время работы"
    return uptime


def _default_route_src_ip():
    try:
        result = subprocess.run(
            ["/usr/bin/ip", "-4", "route", "get", "1.1.1.1"],
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
        parts = result.stdout.split()
        if "src" in parts:
            return parts[parts.index("src") + 1]
    except Exception:
        pass
    iface = get_default_interface()
    if not iface:
        return None
    try:
        result = subprocess.run(
            ["/usr/bin/ip", "-4", "-o", "addr", "show", "dev", iface],
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
        for token in result.stdout.split():
            if "/" in token and token[0].isdigit():
                return token.split("/", 1)[0]
    except Exception:
        pass
    return None


def get_external_ip():
    now = time.time()
    with _ip_cache_lock:
        cached = _ip_cache["value"]
        cached_at = _ip_cache["at"]
        if cached is not None and cached_at:
            ttl = _IP_CACHE_TTL if _ip_cache["ok"] else _IP_FAIL_TTL
            if now - cached_at < ttl:
                return cached

    public_ip = None
    for url in (
        "https://api.ipify.org",
        "https://icanhazip.com",
        "https://ifconfig.me/ip",
    ):
        try:
            response = requests.get(url, timeout=2)
            if response.status_code != 200:
                continue
            ip = response.text.strip()
            if is_public_ip(ip):
                public_ip = str(_parse_ip(ip))
                break
        except requests.RequestException:
            continue

    if public_ip:
        with _ip_cache_lock:
            _ip_cache["value"] = public_ip
            _ip_cache["at"] = time.time()
            _ip_cache["ok"] = True
        return public_ip

    fallback = _default_route_src_ip() or "IP не найден"
    with _ip_cache_lock:
        _ip_cache["value"] = fallback
        _ip_cache["at"] = time.time()
        _ip_cache["ok"] = False
    return fallback
