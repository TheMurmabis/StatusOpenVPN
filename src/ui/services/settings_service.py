import json
import os
import sqlite3
from datetime import datetime

from src.ui.constants import DEFAULT_SETTINGS, LEGACY_ADMIN_INFO_PATH, SETTINGS_PATH


def get_display_app_name():
    raw = read_settings().get("app_name", DEFAULT_SETTINGS.get("app_name", "StatusOpenVPN"))
    if not isinstance(raw, str):
        return DEFAULT_SETTINGS.get("app_name", "StatusOpenVPN")
    name = raw.strip()
    return name or DEFAULT_SETTINGS.get("app_name", "StatusOpenVPN")


def write_settings_data(settings_data):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as settings_file:
        json.dump(settings_data, settings_file, ensure_ascii=False, indent=4)
        settings_file.write("\n")


def read_settings():
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as settings_file:
            data = json.load(settings_file)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}

    if not isinstance(data, dict):
        data = {}

    merged = DEFAULT_SETTINGS.copy()
    merged.update(data)

    telegram_admins = merged.get("telegram_admins")
    if not isinstance(telegram_admins, dict):
        telegram_admins = {}
        merged["telegram_admins"] = telegram_admins

    if not telegram_admins and os.path.exists(LEGACY_ADMIN_INFO_PATH):
        try:
            with open(LEGACY_ADMIN_INFO_PATH, "r", encoding="utf-8") as legacy_file:
                legacy_data = json.load(legacy_file)
            if isinstance(legacy_data, dict):
                merged["telegram_admins"] = legacy_data
                write_settings_data(merged)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    return merged


def write_settings(updated_settings):
    current_settings = read_settings()
    current_settings.update(updated_settings)
    write_settings_data(current_settings)


def parse_stats_retention_days(raw_value):
    try:
        days = int(str(raw_value).strip())
    except (TypeError, ValueError):
        return 365
    return max(30, min(days, 3650))


def get_stats_retention_days():
    return parse_stats_retention_days(read_settings().get("stats_retention_days", 365))


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
