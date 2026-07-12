import sqlite3
from collections import OrderedDict
from datetime import datetime, timedelta

from flask import jsonify, render_template, request
from flask_login import login_required
from tzlocal import get_localzone
from zoneinfo._common import ZoneInfoNotFoundError

from src.ui.constants import MONTH_OPTIONS_RU
from src.ui.extensions import app
from src.ui.services.env_service import get_openvpn_server_ports
from src.ui.services.openvpn_service import (
    cert_days_left_fields,
    get_all_openvpn_clients,
    get_openvpn_cert_renew_state,
    get_openvpn_client_cert_expiry,
    read_banned_clients,
    read_csv,
)
from src.ui.services.settings_service import read_settings
from src.ui.utils.format_utils import (
    format_bytes,
    mask_ip,
    normalize_real_address,
    ovpn_session_row_key,
    parse_bytes,
    pluralize_clients,
)
from src.ui.utils.network_utils import get_external_ip
from src.ui.utils.openvpn_naming import clean_client_display_name
from src.ui.utils.time_utils import (
    get_server_hour_window_for_client_day,
    parse_date_yyyy_mm_dd,
    resolve_client_timezone,
)


def _collect_openvpn_clients_unsorted():
    """Собирает список клиентов OpenVPN без сортировки.
    Возвращает (all_clients_list, total_received, total_sent, errors,
    total_dl_speed, total_ul_speed)."""
    file_paths = [
        ("/etc/openvpn/server/logs/antizapret-udp-status.log", "UDP"),
        ("/etc/openvpn/server/logs/antizapret-tcp-status.log", "TCP"),
        ("/etc/openvpn/server/logs/vpn-udp-status.log", "VPN-UDP"),
        ("/etc/openvpn/server/logs/vpn-tcp-status.log", "VPN-TCP"),
    ]
    server_ports = get_openvpn_server_ports()

    online_clients_raw = []
    total_received, total_sent = 0, 0
    total_download_speed_raw, total_upload_speed_raw = 0.0, 0.0
    errors = []
    online_client_names = set()

    for file_path, protocol in file_paths:
        file_data, received, sent, error = read_csv(file_path, protocol)
        if error:
            errors.append(f"Ошибка в файле {file_path}: {error}")
        else:
            online_clients_raw.extend(file_data)
            total_received += received
            total_sent += sent
            for client_row in file_data:
                if client_row[0] != "UNDEF":
                    online_client_names.add(client_row[0])
                    total_download_speed_raw += client_row[10]
                    total_upload_speed_raw += client_row[11]

    all_clients = get_all_openvpn_clients()
    banned_clients = read_banned_clients()
    server_ip = get_external_ip()

    all_clients_list = []

    for client_row in online_clients_raw:
        client_name = client_row[0]
        if client_name == "UNDEF":
            continue
        is_blocked = client_name in banned_clients
        all_clients_list.append(
            {
                "name": client_name,
                "display_name": clean_client_display_name(client_name, server_ip),
                "online": True,
                "blocked": is_blocked,
                "real_ip": client_row[1],
                "local_ip": client_row[2],
                "received": client_row[3],
                "sent": client_row[4],
                "download_speed": client_row[5],
                "upload_speed": client_row[6],
                "connected_since": client_row[7],
                "duration": client_row[8],
                "protocol": client_row[9],
                "server_port": server_ports.get(client_row[9], ""),
            }
        )

    for client_name in sorted(all_clients):
        if client_name not in online_client_names:
            is_blocked = client_name in banned_clients
            all_clients_list.append(
                {
                    "name": client_name,
                    "display_name": clean_client_display_name(client_name, server_ip),
                    "online": False,
                    "blocked": is_blocked,
                    "real_ip": "-",
                    "local_ip": "-",
                    "received": "-",
                    "sent": "-",
                    "download_speed": "-",
                    "upload_speed": "-",
                    "connected_since": "-",
                    "duration": "-",
                    "protocol": "-",
                    "server_port": "",
                }
            )

    return (
        all_clients_list,
        total_received,
        total_sent,
        errors,
        total_download_speed_raw,
        total_upload_speed_raw,
    )


def _dedupe_openvpn_client_status_rows(rows):
    """Одна строка на уникальное имя клиента."""
    groups = OrderedDict()
    for row in rows:
        name = row["name"]
        if name not in groups:
            groups[name] = []
        groups[name].append(row)

    out = []
    for grp in groups.values():
        if len(grp) == 1:
            out.append(grp[0])
            continue
        merged = dict(grp[0])
        merged["online"] = any(r["online"] for r in grp)
        merged["blocked"] = any(r["blocked"] for r in grp)
        online_protocols = [
            r["protocol"]
            for r in grp
            if r["online"] and r.get("protocol") not in (None, "-", "")
        ]
        if len(online_protocols) > 1:
            merged["protocol"] = ""
        elif len(online_protocols) == 1:
            merged["protocol"] = online_protocols[0]
        else:
            merged["protocol"] = grp[0]["protocol"]
        out.append(merged)
    return out


def _build_openvpn_client_status_sorted(sort_by, order):
    """Список клиентов для страницы статуса: сертификат, сортировка client/status/cert."""
    all_clients_list, _, _, errors, _, _ = _collect_openvpn_clients_unsorted()
    for row in all_clients_list:
        exp_dt, exp_label = get_openvpn_client_cert_expiry(row["name"])
        row["cert_expiry_dt"] = exp_dt
        row["cert_expiry_label"] = exp_label
        days_left, days_label = cert_days_left_fields(exp_dt)
        row["cert_days_left"] = days_left
        row["cert_days_left_label"] = days_label
        row["cert_renew_state"] = get_openvpn_cert_renew_state(exp_dt)

    all_clients_list = _dedupe_openvpn_client_status_rows(all_clients_list)

    if sort_by == "cert":
        valid = [x for x in all_clients_list if x["cert_expiry_dt"] is not None]
        missing = [x for x in all_clients_list if x["cert_expiry_dt"] is None]
        valid.sort(key=lambda x: x["cert_expiry_dt"], reverse=(order == "desc"))
        all_clients_list = valid + missing
    else:
        reverse_order = order == "desc"

        def sort_key(x):
            if sort_by == "client":
                return (x["name"].lower(),)
            if sort_by == "status":
                return (0 if x["online"] else 1, 0 if not x["blocked"] else 1)
            online_priority = 0 if x["online"] else 1
            return (online_priority, x["name"].lower())

        all_clients_list.sort(key=sort_key, reverse=reverse_order)

    total_online = len([c for c in all_clients_list if c["online"]])
    return all_clients_list, errors, total_online


def _build_openvpn_clients_sorted(sort_by, order):
    """Собирает список клиентов OpenVPN и сортирует."""
    (
        all_clients_list,
        total_received,
        total_sent,
        errors,
        total_dl_speed,
        total_ul_speed,
    ) = _collect_openvpn_clients_unsorted()

    reverse_order = order == "desc"

    def sort_key(x):
        online_priority = 0 if x["online"] else 1
        if sort_by == "client":
            return (online_priority, x["name"].lower())
        elif sort_by == "realIp":
            return (online_priority, x["real_ip"])
        elif sort_by == "localIp":
            return (online_priority, x["local_ip"])
        elif sort_by == "sent":
            return (
                online_priority,
                parse_bytes(x["sent"]) if x["sent"] != "-" else -1,
            )
        elif sort_by == "received":
            return (
                online_priority,
                parse_bytes(x["received"]) if x["received"] != "-" else -1,
            )
        elif sort_by == "connection-time":
            return (
                online_priority,
                x["connected_since"] if x["connected_since"] != "-" else "",
            )
        elif sort_by == "duration":
            return (
                online_priority,
                x["connected_since"] if x["connected_since"] != "-" else "",
            )
        elif sort_by == "protocol":
            return (online_priority, x["protocol"])
        elif sort_by == "status":
            return (0 if x["online"] else 1, 0 if not x["blocked"] else 1)
        return (online_priority, x["name"].lower())

    all_clients_list.sort(key=sort_key, reverse=reverse_order)

    total_online = len([c for c in all_clients_list if c["online"]])
    for c in all_clients_list:
        c["row_key"] = ovpn_session_row_key(c["name"], c["protocol"])
    return (
        all_clients_list,
        total_received,
        total_sent,
        errors,
        total_online,
        total_dl_speed,
        total_ul_speed,
    )


@app.route("/api/ovpn/clients")
@login_required
def api_ovpn_clients():
    """JSON-снимок списка OpenVPN."""
    sort_by = request.args.get("sort", "client")
    order = request.args.get("order", "asc")
    try:
        (
            all_clients_list,
            total_received,
            total_sent,
            errors,
            total_online,
            total_dl_speed,
            total_ul_speed,
        ) = _build_openvpn_clients_sorted(sort_by, order)
        online = [c for c in all_clients_list if c["online"]]
        return jsonify(
            {
                "ok": True,
                "online": online,
                "total_received": format_bytes(total_received),
                "total_sent": format_bytes(total_sent),
                "total_clients_str": pluralize_clients(total_online),
                "total_online": total_online,
                "total_download_speed": f"{format_bytes(total_dl_speed)}/s",
                "total_upload_speed": f"{format_bytes(total_ul_speed)}/s",
                "errors": errors,
            }
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/ovpn")
@login_required
def ovpn():
    try:
        sort_by = request.args.get("sort", "client")
        order = request.args.get("order", "asc")
        (
            all_clients_list,
            total_received,
            total_sent,
            errors,
            total_online,
            total_dl_speed,
            total_ul_speed,
        ) = _build_openvpn_clients_sorted(sort_by, order)
        return render_template(
            "ovpn/ovpn.html",
            clients=all_clients_list,
            total_clients_str=pluralize_clients(total_online),
            total_received=format_bytes(total_received),
            total_sent=format_bytes(total_sent),
            total_download_speed=f"{format_bytes(total_dl_speed)}/s",
            total_upload_speed=f"{format_bytes(total_ul_speed)}/s",
            active_section="ovpn",
            active_page="clients",
            errors=errors,
            sort_by=sort_by,
            order=order,
        )

    except ZoneInfoNotFoundError:
        error_message = (
            "Обнаружены конфликтующие настройки часового пояса "
            "в файлах /etc/timezone и /etc/localtime. "
            "Попробуйте установить правильный часовой пояс "
            "с помощью команды: sudo dpkg-reconfigure tzdata"
        )
        return (
            render_template(
                "ovpn/ovpn.html",
                error_message=error_message,
                active_section="ovpn",
                active_page="clients",
            ),
            500,
        )

    except Exception as e:
        error_message = f"Произошла непредвиденная ошибка: {str(e)}"
        return (
            render_template(
                "ovpn/ovpn.html",
                error_message=error_message,
                active_section="ovpn",
                active_page="clients",
            ),
            500,
        )


@app.route("/ovpn/client-status")
@login_required
def ovpn_client_status():
    try:
        sort_by = request.args.get("sort", "client")
        order = request.args.get("order", "asc")
        all_clients_list, errors, total_online = _build_openvpn_client_status_sorted(
            sort_by, order
        )
        return render_template(
            "ovpn/ovpn_client_status.html",
            clients=all_clients_list,
            total_clients_str=pluralize_clients(total_online),
            active_section="ovpn",
            active_page="client_status",
            errors=errors,
            sort_by=sort_by,
            order=order,
        )

    except ZoneInfoNotFoundError:
        error_message = (
            "Обнаружены конфликтующие настройки часового пояса "
            "в файлах /etc/timezone и /etc/localtime. "
            "Попробуйте установить правильный часовой пояс "
            "с помощью команды: sudo dpkg-reconfigure tzdata"
        )
        return (
            render_template(
                "ovpn/ovpn_client_status.html",
                error_message=error_message,
                active_section="ovpn",
                active_page="client_status",
            ),
            500,
        )

    except Exception as e:
        error_message = f"Произошла непредвиденная ошибка: {str(e)}"
        return (
            render_template(
                "ovpn/ovpn_client_status.html",
                error_message=error_message,
                active_section="ovpn",
                active_page="client_status",
            ),
            500,
        )


@app.route("/ovpn/history")
@login_required
def ovpn_history():
    q = (request.args.get("q") or "").strip()
    try:
        page = request.args.get("page", 1, type=int)
        per_page = 20

        conn_logs = sqlite3.connect(app.config["LOGS_DATABASE_PATH"])

        filter_clause = "client_name != 'UNDEF'"
        filter_params = []
        if q:
            like_value = f"%{q.lower()}%"
            filter_clause += (
                " AND (lower(client_name) LIKE ? OR lower(real_ip) LIKE ? "
                "OR lower(local_ip) LIKE ? OR lower(protocol) LIKE ?)"
            )
            filter_params.extend([like_value, like_value, like_value, like_value])

        total_count = conn_logs.execute(
            f"SELECT COUNT(*) FROM connection_logs WHERE {filter_clause}",
            filter_params,
        ).fetchone()[0]

        total_pages = max(1, (total_count + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        offset = (page - 1) * per_page

        logs_reader = conn_logs.execute(
            f"""SELECT * FROM connection_logs
               WHERE {filter_clause}
               ORDER BY connected_since DESC
               LIMIT ? OFFSET ?""",
            (*filter_params, per_page, offset),
        ).fetchall()
        conn_logs.close()

        hide_ovpn_ip = read_settings().get("hide_ovpn_ip", True)

        def format_ip(ip):
            real_ip = normalize_real_address(ip)
            return mask_ip(real_ip, hide=hide_ovpn_ip)

        logs = [
            {
                "client_name": row[1],
                "real_ip": format_ip(row[3]),
                "local_ip": row[2],
                "connection_since": row[4],
                "protocol": row[7],
            }
            for row in logs_reader
        ]

        return render_template(
            "ovpn/ovpn_history.html",
            active_section="ovpn",
            active_page="history",
            logs=logs,
            page=page,
            total_pages=total_pages,
            q=q,
        )

    except Exception as e:
        error_message = f"Произошла непредвиденная ошибка: {str(e)}"
        return (
            render_template(
                "ovpn/ovpn_history.html",
                error_message=error_message,
                active_section="ovpn",
                active_page="history",
                q=q,
            ),
            500,
        )


@app.route("/ovpn/stats")
@login_required
def ovpn_stats():
    try:
        sort_by = request.args.get("sort", "client_name")
        sort_by = {
            "total_bytes_sent": "client_bytes_sent",
            "total_bytes_received": "client_bytes_received",
        }.get(sort_by, sort_by)
        order = request.args.get("order", "asc").lower()
        period = request.args.get("period", "day")
        client_tz, selected_tz = resolve_client_timezone()
        now = datetime.now(client_tz)
        today = now.date()
        selected_date_from = (request.args.get("date_from") or "").strip()
        selected_date_to = (request.args.get("date_to") or "").strip()

        def format_period_date(dt_value):
            label = dt_value.strftime("%d.%m.%Y")
            if dt_value.date() == today:
                return f"{label} (сегодня)"
            return label

        allowed_sorts = {
            "client_name": "client_name",
            "client_bytes_sent": "SUM(total_bytes_received)",
            "client_bytes_received": "SUM(total_bytes_sent)",
            "last_connected": "MAX(last_connected)",
        }

        sort_column = allowed_sorts.get(sort_by, "client_name")
        order_sql = "DESC" if order == "desc" else "ASC"
        if period == "day":
            date_from = now.strftime("%Y-%m-%d")
            date_to = None
            selected_date_from = date_from
            selected_date_to = date_from
            interval_label = f"за {format_period_date(now)}"
        elif period == "week":
            week_start = now - timedelta(days=now.weekday())
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            date_from = week_start.strftime("%Y-%m-%d")
            date_to = None
            selected_date_from = date_from
            selected_date_to = now.strftime("%Y-%m-%d")
            interval_label = (
                f"с {format_period_date(week_start)} по {format_period_date(now)}"
            )
        elif period == "month":
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            date_from = month_start.strftime("%Y-%m-%d")
            date_to = None
            selected_date_from = date_from
            selected_date_to = now.strftime("%Y-%m-%d")
            month_name = dict(MONTH_OPTIONS_RU).get(
                month_start.month, month_start.strftime("%m")
            )
            interval_label = f"{month_name} {month_start.year}"
        elif period == "year":
            year_start = now.replace(
                month=1, day=1, hour=0, minute=0, second=0, microsecond=0
            )
            date_from = year_start.strftime("%Y-%m-%d")
            date_to = None
            selected_date_from = date_from
            selected_date_to = now.strftime("%Y-%m-%d")
            interval_label = str(year_start.year)
        elif period == "custom":
            date_from_dt = parse_date_yyyy_mm_dd(selected_date_from)
            date_to_dt = parse_date_yyyy_mm_dd(selected_date_to)
            if date_from_dt and date_to_dt:
                if date_from_dt > date_to_dt:
                    date_from_dt, date_to_dt = date_to_dt, date_from_dt
                selected_date_from = date_from_dt.strftime("%Y-%m-%d")
                selected_date_to = date_to_dt.strftime("%Y-%m-%d")
                date_from = selected_date_from
                date_to = (date_to_dt + timedelta(days=1)).strftime("%Y-%m-%d")
                if date_from_dt.date() == date_to_dt.date():
                    interval_label = f"за {format_period_date(date_from_dt)}"
                else:
                    interval_label = (
                        f"с {format_period_date(date_from_dt)}"
                        f" по {format_period_date(date_to_dt)}"
                    )
            else:
                period = "day"
                date_from = now.strftime("%Y-%m-%d")
                date_to = None
                selected_date_from = date_from
                selected_date_to = date_from
                interval_label = f"за {format_period_date(now)}"
        else:
            period = "day"
            date_from = now.strftime("%Y-%m-%d")
            date_to = None
            selected_date_from = date_from
            selected_date_to = date_from
            interval_label = f"за {format_period_date(now)}"

        is_single_day = period == "day" or (
            period == "custom"
            and selected_date_from
            and selected_date_from == selected_date_to
        )

        stats_list = []
        total_received, total_sent = 0, 0

        with sqlite3.connect(app.config["LOGS_DATABASE_PATH"]) as conn:
            if is_single_day:
                target_date = date_from
                start_hour, end_hour = get_server_hour_window_for_client_day(
                    target_date, client_tz
                )
                query = f"""
                    SELECT client_name,
                           SUM(total_bytes_received),
                           SUM(total_bytes_sent),
                           MAX(last_connected)
                    FROM daily_stats
                    WHERE hour >= ? AND hour < ?
                    GROUP BY client_name
                    ORDER BY {sort_column} {order_sql}
                """
                rows = conn.execute(query, (start_hour, end_hour)).fetchall()
            elif period == "year":
                year_month_from = year_start.strftime("%Y-%m")
                query = f"""
                    SELECT client_name,
                           SUM(total_bytes_received),
                           SUM(total_bytes_sent),
                           MAX(last_connected)
                    FROM yearly_stats
                    WHERE month >= ?
                    GROUP BY client_name
                    ORDER BY {sort_column} {order_sql}
                """
                rows = conn.execute(query, (year_month_from,)).fetchall()
            elif date_to:
                query = f"""
                    SELECT client_name,
                           SUM(total_bytes_received),
                           SUM(total_bytes_sent),
                           MAX(last_connected)
                    FROM monthly_stats
                    WHERE month >= ? AND month < ?
                    GROUP BY client_name
                    ORDER BY {sort_column} {order_sql}
                """
                rows = conn.execute(query, (date_from, date_to)).fetchall()
            else:
                query = f"""
                    SELECT client_name,
                           SUM(total_bytes_received),
                           SUM(total_bytes_sent),
                           MAX(last_connected)
                    FROM monthly_stats
                    WHERE month >= ?
                    GROUP BY client_name
                    ORDER BY {sort_column} {order_sql}
                """
                rows = conn.execute(query, (date_from,)).fetchall()

            for client_name, received, sent, last_connected in rows:
                total_received += received or 0
                total_sent += sent or 0
                stats_list.append(
                    {
                        "client_name": client_name,
                        "client_bytes_sent": format_bytes(received),
                        "client_bytes_received": format_bytes(sent),
                        "total_bytes_sent": format_bytes(sent),
                        "total_bytes_received": format_bytes(received),
                        "client_bytes_sent_raw": received or 0,
                        "client_bytes_received_raw": sent or 0,
                        "total_bytes_sent_raw": sent or 0,
                        "total_bytes_received_raw": received or 0,
                        "last_connected": last_connected,
                    }
                )

        return render_template(
            "ovpn/ovpn_stats.html",
            total_client_received=format_bytes(total_sent),
            total_client_sent=format_bytes(total_received),
            total_received=format_bytes(total_received),
            total_sent=format_bytes(total_sent),
            active_section="ovpn",
            active_page="stats",
            stats=stats_list,
            period=period,
            sort_by=sort_by,
            order=order_sql.lower(),
            selected_date_from=selected_date_from,
            selected_date_to=selected_date_to,
            selected_tz=selected_tz,
            interval_label=interval_label,
        )

    except Exception as e:
        error_message = f"Произошла непредвиденная ошибка: {e}"
        return (
            render_template(
                "ovpn/ovpn_stats.html",
                error_message=error_message,
                active_section="ovpn",
                active_page="stats",
            ),
            500,
        )


@app.route("/api/ovpn/client_chart")
@login_required
def api_ovpn_client_chart():
    client_name = request.args.get("client")
    period = request.args.get("period", "day")
    client_tz, _ = resolve_client_timezone()
    now = datetime.now(client_tz)
    selected_date_from = (request.args.get("date_from") or "").strip()
    selected_date_to = (request.args.get("date_to") or "").strip()
    if not client_name:
        return jsonify({"error": "client parameter required"}), 400

    is_single_day = False

    if period == "day":
        target_date = now.strftime("%Y-%m-%d")
        selected_date_from = target_date
        selected_date_to = target_date
        is_single_day = True
    elif period == "week":
        week_start = now - timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        date_from = week_start.strftime("%Y-%m-%d")
        date_to = None
    elif period == "month":
        date_from = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ).strftime("%Y-%m-%d")
        date_to = None
    elif period == "year":
        year_month_from = now.replace(month=1, day=1).strftime("%Y-%m")
    elif period == "custom":
        date_from_dt = parse_date_yyyy_mm_dd(selected_date_from)
        date_to_dt = parse_date_yyyy_mm_dd(selected_date_to)
        if date_from_dt and date_to_dt:
            if date_from_dt > date_to_dt:
                date_from_dt, date_to_dt = date_to_dt, date_from_dt
            if date_from_dt == date_to_dt:
                target_date = date_from_dt.strftime("%Y-%m-%d")
                selected_date_from = target_date
                selected_date_to = target_date
                is_single_day = True
            else:
                date_from = date_from_dt.strftime("%Y-%m-%d")
                date_to = (date_to_dt + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            target_date = now.strftime("%Y-%m-%d")
            selected_date_from = target_date
            selected_date_to = target_date
            is_single_day = True
    else:
        target_date = now.strftime("%Y-%m-%d")
        selected_date_from = target_date
        selected_date_to = target_date
        is_single_day = True

    try:
        with sqlite3.connect(app.config["LOGS_DATABASE_PATH"]) as conn:
            if is_single_day:
                start_hour, end_hour = get_server_hour_window_for_client_day(
                    target_date, client_tz
                )
                rows = conn.execute(
                    """
                    SELECT hour,
                           SUM(total_bytes_received) as rx,
                           SUM(total_bytes_sent) as tx
                    FROM daily_stats
                    WHERE client_name = ? AND hour >= ? AND hour < ?
                    GROUP BY hour
                    ORDER BY hour ASC
                    """,
                    (client_name, start_hour, end_hour),
                ).fetchall()
                hour_data = {h: (rx or 0, tx or 0) for h, rx, tx in rows}
                day_start_client = datetime.strptime(
                    target_date, "%Y-%m-%d"
                ).replace(tzinfo=client_tz)
                day_end_client = day_start_client + timedelta(days=1)
                now_hour_client = now.replace(
                    minute=0, second=0, microsecond=0
                ) + timedelta(hours=1)
                display_end_client = min(day_end_client, now_hour_client)
                labels = []
                rx_data = []
                tx_data = []

                point_dt_client = day_start_client
                while point_dt_client < display_end_client:
                    point_dt_server = point_dt_client.astimezone(get_localzone())
                    server_hour_key = point_dt_server.strftime("%Y-%m-%d %H:00")
                    labels.append(point_dt_client.strftime("%Y-%m-%d %H:00"))
                    rx, tx = hour_data.get(server_hour_key, (0, 0))
                    rx_data.append(rx or 0)
                    tx_data.append(tx or 0)
                    point_dt_client += timedelta(hours=1)
            elif period == "year":
                rows = conn.execute(
                    """
                    SELECT month,
                           SUM(total_bytes_received) as rx,
                           SUM(total_bytes_sent) as tx
                    FROM yearly_stats
                    WHERE client_name = ? AND month >= ?
                    GROUP BY month
                    ORDER BY month ASC
                    """,
                    (client_name, year_month_from),
                ).fetchall()
                labels = [r[0] for r in rows]
                rx_data = [r[1] or 0 for r in rows]
                tx_data = [r[2] or 0 for r in rows]
            elif date_to:
                rows = conn.execute(
                    """
                    SELECT month,
                           SUM(total_bytes_received) as rx,
                           SUM(total_bytes_sent) as tx
                    FROM monthly_stats
                    WHERE client_name = ? AND month >= ? AND month < ?
                    GROUP BY month
                    ORDER BY month ASC
                    """,
                    (client_name, date_from, date_to),
                ).fetchall()
                labels = [r[0] for r in rows]
                rx_data = [r[1] or 0 for r in rows]
                tx_data = [r[2] or 0 for r in rows]
            else:
                rows = conn.execute(
                    """
                    SELECT month,
                           SUM(total_bytes_received) as rx,
                           SUM(total_bytes_sent) as tx
                    FROM monthly_stats
                    WHERE client_name = ? AND month >= ?
                    GROUP BY month
                    ORDER BY month ASC
                    """,
                    (client_name, date_from),
                ).fetchall()
                labels = [r[0] for r in rows]
                rx_data = [r[1] or 0 for r in rows]
                tx_data = [r[2] or 0 for r in rows]

        return jsonify(
            {
                "client": client_name,
                "labels": labels,
                "rx_bytes": rx_data,
                "tx_bytes": tx_data,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
