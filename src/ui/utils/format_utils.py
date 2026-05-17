import base64
import re
from datetime import datetime, timezone

from tzlocal import get_localzone


def humanize_bytes(num, suffix="B"):
    for unit in ["", "K", "M", "G", "T"]:
        if abs(num) < 1024.0:
            return f"{num:.1f} {unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f} P{suffix}"


def format_bytes(size):
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"


def parse_bytes(value):
    """Преобразует строку с размером данных в байты."""
    size, unit = value.split(" ")
    size = float(size)
    unit = unit.lower()
    if unit == "kb":
        return size * 1024
    elif unit == "mb":
        return size * 1024**2
    elif unit == "gb":
        return size * 1024**3
    elif unit == "tb":
        return size * 1024**4
    return size


def pluralize_clients(count):
    if 11 <= count % 100 <= 19:
        return f"{count} клиентов"
    elif count % 10 == 1:
        return f"{count} клиент"
    elif 2 <= count % 10 <= 4:
        return f"{count} клиента"
    else:
        return f"{count} клиентов"


def mask_ip(ip_address, hide=True):
    if not ip_address:
        return "0.0.0.0"

    port = ""
    if ":" in ip_address:
        ip, port = ip_address.rsplit(":", 1)
        port = f":{port}"
    else:
        ip = ip_address

    parts = ip.split(".")

    if len(parts) == 4:
        try:
            parts = [str(int(part)) for part in parts]
            if hide:
                return f"{parts[0]}.***.***.{parts[3]}"
            return f"{parts[0]}.{parts[1]}.{parts[2]}.{parts[3]}"
        except ValueError:
            return ip_address

    return ip_address


def format_uptime(uptime_string):
    pattern = r"(?:(\d+)\s*years?|(\d+)\s*months?|(\d+)\s*weeks?|(\d+)\s*days?|(\d+)\s*hours?|(\d+)\s*minutes?)"

    years = months = weeks = days = hours = minutes = 0
    matches = re.findall(pattern, uptime_string)

    for match in matches:
        if match[0]:
            years = int(match[0])
        elif match[1]:
            months = int(match[1])
        elif match[2]:
            weeks = int(match[2])
        elif match[3]:
            days = int(match[3])
        elif match[4]:
            hours = int(match[4])
        elif match[5]:
            minutes = int(match[5])

    result = []
    if years > 0:
        result.append(f"{years} г.")
    if months > 0:
        result.append(f"{months} мес.")
    if weeks > 0:
        result.append(f"{weeks} нед.")
    if days > 0:
        result.append(f"{days} дн.")
    if hours > 0:
        result.append(f"{hours} ч.")
    if minutes > 0:
        result.append(f"{minutes} мин.")

    return " ".join(result)


def format_duration(start_time):
    now = datetime.now()
    delta = now - start_time

    days = delta.days
    seconds = delta.seconds
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if days >= 30:
        months = days // 30
        days %= 30
        return f"{months} мес. {days} дн. {hours} ч. {minutes} мин."
    elif days > 0:
        return f"{days} дн. {hours} ч. {minutes} мин."
    elif hours > 0:
        return f"{hours} ч. {minutes} мин."
    elif minutes > 0:
        return f"{minutes} мин."
    else:
        return f"{seconds} сек."


def format_date(date_string):
    date_obj = datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S")
    server_timezone = get_localzone()
    localized_date = date_obj.replace(tzinfo=server_timezone)
    utc_date = localized_date.astimezone(timezone.utc)
    return utc_date.isoformat()


def format_handshake_time(handshake_string):
    time_units = re.findall(r"(\d+)\s+(\w+)", handshake_string)

    abbreviations = {
        "year": "г.",
        "years": "г.",
        "month": "мес.",
        "months": "мес.",
        "week": "нед.",
        "weeks": "нед.",
        "day": "дн.",
        "days": "дн.",
        "hour": "ч.",
        "hours": "ч.",
        "minute": "мин.",
        "minutes": "мин.",
        "second": "сек.",
        "seconds": "сек.",
    }

    return " ".join(
        f"{value} {abbreviations[unit]}" for value, unit in time_units
    )


def normalize_real_address(addr):
    if addr.startswith(("udp4:", "tcp4:", "tcp4-server:", "udp6:", "tcp6:")):
        addr = addr.split(":", 1)[1]
    return addr


def ovpn_session_row_key(name, protocol):
    raw = f"{name}\x1f{protocol}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
