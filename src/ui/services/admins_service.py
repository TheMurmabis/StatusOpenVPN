from src.ui.constants import CLIENT_MAPPING_KEY
from src.ui.services.settings_service import read_settings


def read_admin_info():
    data = read_settings().get("telegram_admins", {})
    if not isinstance(data, dict):
        return {}
    return data


def parse_admin_ids(admin_id_value):
    placeholder = "<Enter your user ID>"
    admin_ids = []
    for item in admin_id_value.split(","):
        item = item.strip()
        if not item:
            continue
        if item == placeholder:
            continue
        admin_ids.append(item)
    return admin_ids


def format_admin_ids(admin_ids):
    return ",".join(admin_ids)


def format_admin_display(admin_id, admin_info):
    info = admin_info.get(admin_id, {})
    display_name = (info.get("display_name") or "").strip()
    username = (info.get("username") or "").strip()

    if display_name and username:
        return f"{display_name} (@{username})"
    if display_name:
        return display_name
    if username:
        return f"@{username}"
    return f"ID: {admin_id}"


def build_admin_display_list(admin_id_value, admin_info):
    admin_ids = parse_admin_ids(admin_id_value)
    return [
        {"id": admin_id, "display": format_admin_display(admin_id, admin_info)}
        for admin_id in admin_ids
    ]


def parse_client_mapping(env_values):
    settings_data = read_settings()
    clients = settings_data.get("telegram_clients", {})
    mapping = {}
    if isinstance(clients, dict):
        for telegram_id, client_data in clients.items():
            tid = str(telegram_id).strip()
            if not tid:
                continue
            names = []
            if isinstance(client_data, dict):
                raw_names = client_data.get("client_names", [])
                if isinstance(raw_names, list):
                    for name in raw_names:
                        clean_name = str(name).strip()
                        if clean_name and clean_name not in names:
                            names.append(clean_name)
                elif isinstance(client_data.get("client_name"), str):
                    clean_name = client_data.get("client_name", "").strip()
                    if clean_name:
                        names.append(clean_name)
            elif isinstance(client_data, str):
                clean_name = client_data.strip()
                if clean_name:
                    names.append(clean_name)
            if names:
                mapping[tid] = names
    if mapping:
        return mapping

    raw_value = (env_values.get(CLIENT_MAPPING_KEY) or "").strip()
    if not raw_value:
        return {}
    legacy_mapping = {}
    for item in raw_value.split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        telegram_id, client_name = item.split(":", 1)
        telegram_id = telegram_id.strip()
        client_name = client_name.strip()
        if not telegram_id or not client_name:
            continue
        names = legacy_mapping.setdefault(telegram_id, [])
        if client_name not in names:
            names.append(client_name)
    return legacy_mapping


def build_client_mapping_list(env_values, admin_info):
    mapping = parse_client_mapping(env_values)
    mapping_list = []
    for telegram_id, client_names in mapping.items():
        display = format_admin_display(telegram_id, admin_info)
        mapping_list.append(
            {
                "telegram_id": telegram_id,
                "display": display,
                "client_names": client_names,
                "clients_count": len(client_names),
            }
        )
    mapping_list.sort(
        key=lambda item: (
            (item["client_names"][0].lower() if item["client_names"] else ""),
            item["display"].lower(),
        )
    )
    return mapping_list


def build_available_admin_candidates(admin_info, admin_ids):
    available = []
    admin_id_set = set(admin_ids)
    for admin_id in admin_info.keys():
        if admin_id in admin_id_set:
            continue
        available.append(
            {"id": admin_id, "display": format_admin_display(admin_id, admin_info)}
        )
    available.sort(key=lambda item: item["display"].lower())
    return available
