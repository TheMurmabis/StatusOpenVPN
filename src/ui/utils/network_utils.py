import subprocess
import time

import psutil
import requests


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


def get_external_ip():
    try:
        response = requests.get("https://api.ipify.org", timeout=10)
        if response.status_code == 200:
            return response.text
        return "IP не найден"
    except requests.Timeout:
        return "Ошибка: запрос превысил время ожидания."
    except requests.ConnectionError:
        return "Ошибка: нет подключения к интернету."
    except requests.RequestException as e:
        return f"Ошибка при запросе: {e}"
