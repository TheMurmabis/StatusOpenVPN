import os
import sqlite3
from datetime import datetime

from src.ui.constants import DEFAULT_SETTINGS


def get_display_app_name():
    raw = read_settings().get("app_name", DEFAULT_SETTINGS.get("app_name", "StatusOpenVPN"))
    if not isinstance(raw, str):
        return DEFAULT_SETTINGS.get("app_name", "StatusOpenVPN")
    name = raw.strip()
    return name or DEFAULT_SETTINGS.get("app_name", "StatusOpenVPN")


def write_settings_data(settings_data):
    from src.tg_bot.config import save_settings

    save_settings(settings_data)


def read_settings():
    from src.tg_bot.config import load_settings

    data = load_settings()
    merged = DEFAULT_SETTINGS.copy()
    merged.update(data)

    profiles = merged.get("telegram_profiles")
    if not isinstance(profiles, dict):
        profiles = {}
        merged["telegram_profiles"] = profiles

    return merged


def write_settings(updated_settings):
    current_settings = read_settings()
    current_settings.update(updated_settings)
    write_settings_data(current_settings)


def get_vpn_client_protocols(client_name):
    from src.tg_bot.config import get_client_allowed_protocols

    defaults = get_client_allowed_protocols("")
    saved = (read_settings().get("vpn_client_protocols") or {}).get(client_name, {})
    if not isinstance(saved, dict):
        return defaults
    return {key: bool(saved.get(key, default)) for key, default in defaults.items()}


def get_available_vpn_client_protocol_keys(client_name):
    """Ключи настроек, для которых у клиента реально есть файлы конфигураций."""
    from src.ui.utils.openvpn_naming import list_openvpn_profile_choices
    from src.ui.utils.wireguard_naming import list_wireguard_profile_choices

    keys = set()
    openvpn_choices = list_openvpn_profile_choices(client_name)
    if openvpn_choices:
        profiles = {choice.get("profile") for choice in openvpn_choices}
        transports = {choice.get("protocol") for choice in openvpn_choices}
        if "vpn" in profiles or "other" in profiles:
            keys.add("openvpn_vpn")
        if "antizapret" in profiles or "other" in profiles:
            keys.add("openvpn_antizapret")
        for transport, key in (
            ("auto", "openvpn_default"),
            ("tcp", "openvpn_tcp"),
            ("udp", "openvpn_udp"),
        ):
            if transport in transports:
                keys.add(key)

    wireguard_choices = list_wireguard_profile_choices(client_name)
    if wireguard_choices:
        profiles = {choice.get("profile") for choice in wireguard_choices}
        kinds = {choice.get("kind") for choice in wireguard_choices}
        if "vpn" in profiles or "other" in profiles:
            keys.add("wireguard_vpn")
        if "antizapret" in profiles or "other" in profiles:
            keys.add("wireguard_antizapret")
        if "wireguard" in kinds:
            keys.add("wireguard_wg")
        if "amnezia" in kinds:
            keys.add("wireguard_am")

    return keys


def set_vpn_client_protocols(client_name, protocols):
    set_vpn_clients_protocols({client_name: protocols})


def set_vpn_clients_protocols(client_protocols):
    data = read_settings()
    clients = data.get("vpn_client_protocols") or {}
    if not isinstance(clients, dict):
        clients = {}
    for client_name, protocols in client_protocols.items():
        clients[client_name] = {key: bool(value) for key, value in protocols.items()}
    data["vpn_client_protocols"] = clients
    write_settings_data(data)


def parse_stats_retention_days(raw_value):
    try:
        days = int(str(raw_value).strip())
    except (TypeError, ValueError):
        return 365
    return max(30, min(days, 3650))


def get_stats_retention_days():
    return parse_stats_retention_days(read_settings().get("stats_retention_days", 365))


def parse_subscription_link_lifetime_minutes(raw_value):
    try:
        minutes = int(str(raw_value).strip())
    except (TypeError, ValueError):
        return 15
    return max(1, min(minutes, 1440))


def get_subscription_link_lifetime_minutes():
    return parse_subscription_link_lifetime_minutes(
        read_settings().get("subscription_link_lifetime_minutes", 15)
    )


def parse_history_max_records(raw_value):
    try:
        value = int(str(raw_value).strip())
    except (TypeError, ValueError):
        return 1000
    return max(100, min(value, 100000))


def get_available_stat_years(db_path, table_name, date_column):
    years = []
    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                f"""
                SELECT DISTINCT substr({date_column}, 1, 4) AS y
                FROM {table_name}
                WHERE substr({date_column}, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
                ORDER BY y DESC
                """
            ).fetchall()
            years = [int(row[0]) for row in rows if row and row[0].isdigit()]
    except sqlite3.Error:
        years = []

    current_year = datetime.now().year
    if current_year not in years:
        years.append(current_year)
    years = sorted(set(years), reverse=True)
    return years
