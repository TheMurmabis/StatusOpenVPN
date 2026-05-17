from datetime import datetime, timedelta

from flask import request
from tzlocal import get_localzone
from zoneinfo import ZoneInfo
from zoneinfo._common import ZoneInfoNotFoundError


def parse_date_yyyy_mm_dd(raw_value):
    value = (raw_value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


def resolve_client_timezone():
    tz_name = (request.args.get("tz") or "").strip()
    if tz_name:
        try:
            return ZoneInfo(tz_name), tz_name
        except ZoneInfoNotFoundError:
            pass

    server_tz = get_localzone()
    server_tz_name = getattr(server_tz, "key", None) or str(server_tz)
    return server_tz, server_tz_name


def floor_to_hour(dt_value):
    return dt_value.replace(minute=0, second=0, microsecond=0)


def ceil_to_hour(dt_value):
    floored = floor_to_hour(dt_value)
    if dt_value == floored:
        return floored
    return floored + timedelta(hours=1)


def get_server_hour_window_for_client_day(day_ymd, client_tz):
    """Возвращает [start, end) в серверной зоне для клиентского дня."""
    server_tz = get_localzone()
    day_dt = datetime.strptime(day_ymd, "%Y-%m-%d")
    start_client = day_dt.replace(tzinfo=client_tz)
    end_client = start_client + timedelta(days=1)

    start_server = floor_to_hour(start_client.astimezone(server_tz))
    end_server = ceil_to_hour(end_client.astimezone(server_tz))

    return (
        start_server.strftime("%Y-%m-%d %H:00"),
        end_server.strftime("%Y-%m-%d %H:00"),
    )


def parse_relative_time(relative_time):
    """Преобразует строку с днями, часами, минутами и секундами в абсолютное время."""
    now = datetime.now()
    time_deltas = {"days": 0, "hours": 0, "minutes": 0, "seconds": 0}

    parts = relative_time.split()
    i = 0
    while i < len(parts):
        try:
            value = int(parts[i])
            unit = parts[i + 1]
            if "д" in unit or "day" in unit:
                time_deltas["days"] += value
            elif "ч" in unit or "hour" in unit:
                time_deltas["hours"] += value
            elif "мин" in unit or "minute" in unit:
                time_deltas["minutes"] += value
            elif "сек" in unit or "second" in unit:
                time_deltas["seconds"] += value
            i += 2
        except (ValueError, IndexError):
            break

    delta = timedelta(
        days=time_deltas["days"],
        hours=time_deltas["hours"],
        minutes=time_deltas["minutes"],
        seconds=time_deltas["seconds"],
    )

    return now - delta


def is_peer_online(last_handshake):
    if not last_handshake:
        return False
    return datetime.now() - last_handshake < timedelta(minutes=3)
