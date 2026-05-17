import os
import shutil
import sqlite3
import subprocess
from datetime import datetime, timedelta

from flask import jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from tzlocal import get_localzone

from src.tg_bot.audit import log_action
from src.ui.constants import MONTH_OPTIONS_RU
from src.ui.extensions import app
from src.ui.services.settings_service import read_settings
from src.ui.services.wireguard_service import (
    get_disabled_wg_peers,
    get_wireguard_stats,
    parse_wireguard_output,
    toggle_peer_config,
)
from src.ui.utils.format_utils import format_bytes
from src.ui.utils.time_utils import (
    get_server_hour_window_for_client_day,
    parse_date_yyyy_mm_dd,
    resolve_client_timezone,
)


@app.route("/wg")
@login_required
def wg():
    """Маршрут клиентов WireGuard."""
    settings_data = read_settings()
    hide_wg_ip = settings_data.get("hide_wg_ip", True)
    hide_warp = bool(settings_data.get("hide_wg_warp_interface", False))
    shorten_wg_filenames = bool(settings_data.get("shorten_wg_filenames", False))
    stats = parse_wireguard_output(
        get_wireguard_stats(), hide_ip=hide_wg_ip, hide_warp=hide_warp
    )
    disabled_peers = get_disabled_wg_peers()
    for interface_data in stats:
        for peer in interface_data.get("peers", []):
            peer["enabled"] = True
        iface = interface_data.get("interface")
        if iface in disabled_peers:
            interface_data.setdefault("peers", []).extend(disabled_peers[iface])

    return render_template(
        "wg/wg.html",
        stats=stats,
        shorten_wg_filenames=shorten_wg_filenames,
        active_section="wg",
        active_page="wg_clients",
    )


@app.route("/wg/client-status")
@login_required
def wg_client_status():
    """Старая страница статуса объединена с разделом «Клиенты»."""
    return redirect(url_for("wg"))


@app.route("/api/wg/stats")
@login_required
def api_wg_stats():
    try:
        settings_data = read_settings()
        hide_wg_ip = settings_data.get("hide_wg_ip", True)
        hide_warp = bool(settings_data.get("hide_wg_warp_interface", False))
        stats = parse_wireguard_output(
            get_wireguard_stats(), hide_ip=hide_wg_ip, hide_warp=hide_warp
        )
        disabled_peers = get_disabled_wg_peers()
        for interface_data in stats:
            for peer in interface_data.get("peers", []):
                peer["enabled"] = True
            iface = interface_data.get("interface")
            if iface in disabled_peers:
                interface_data.setdefault("peers", []).extend(disabled_peers[iface])
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/wg/peer/toggle", methods=["POST"])
@login_required
def toggle_wg_peer():
    data = request.get_json()
    peer = data.get("peer")
    interface = data.get("interface")
    enable = data.get("enable")

    if not peer or not interface or enable is None:
        return jsonify({"error": "Отсутствуют обязательные параметры"}), 400

    config_path = f"/etc/wireguard/{interface}.conf"

    if not os.path.exists(config_path):
        return jsonify({"error": "Конфигурация не найдена"}), 404

    try:
        success = toggle_peer_config(config_path, peer, enable)
        if not success:
            return jsonify({"error": "Пир не найден в конфигурации"}), 404

        wg_quick = shutil.which("wg-quick") or "/usr/bin/wg-quick"
        wg_bin = shutil.which("wg") or "/usr/bin/wg"
        if not os.path.isfile(wg_quick):
            return (
                jsonify({"error": "wg-quick не найден. Установите wireguard-tools."}),
                500,
            )
        if not os.path.isfile(wg_bin):
            return (
                jsonify({"error": "wg не найден. Установите wireguard-tools."}),
                500,
            )

        subprocess.run(
            [
                "/bin/bash",
                "-c",
                f"{wg_bin} syncconf {interface} <({wg_quick} strip {interface})",
            ],
            check=True,
            env={**os.environ, "PATH": "/usr/bin:/bin"},
        )

        client_name = data.get("client_name", peer[:8] + "...")
        action_str = "включён" if enable else "отключён"
        log_action(
            "web",
            current_user.username,
            current_user.username,
            "peer_toggle",
            f"{client_name} ({action_str})",
        )

        return jsonify({"success": True, "enabled": enable})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/wg/stats")
@login_required
def wg_stats():
    try:
        sort_by = request.args.get("sort", "client")
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
            "client": "client",
            "total_sent": "SUM(sent)",
            "total_received": "SUM(received)",
        }

        sort_column = allowed_sorts.get(sort_by, "client")
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

        with sqlite3.connect(app.config["WG_STATS_PATH"]) as conn:
            if is_single_day:
                target_date = date_from
                start_hour, end_hour = get_server_hour_window_for_client_day(
                    target_date, client_tz
                )
                query = f"""
                    SELECT client,
                           SUM(received) as total_received,
                           SUM(sent) as total_sent
                    FROM wg_hourly_stats
                    WHERE hour >= ? AND hour < ?
                      AND interface != 'warp'
                    GROUP BY client
                    HAVING SUM(received) > 0 OR SUM(sent) > 0
                    ORDER BY {sort_column} {order_sql}
                """
                rows = conn.execute(query, (start_hour, end_hour)).fetchall()
            elif period == "year":
                year_month_from = year_start.strftime("%Y-%m")
                query = f"""
                    SELECT client,
                           SUM(received) as total_received,
                           SUM(sent) as total_sent
                    FROM wg_monthly_stats
                    WHERE month >= ?
                      AND interface != 'warp'
                    GROUP BY client
                    HAVING SUM(received) > 0 OR SUM(sent) > 0
                    ORDER BY {sort_column} {order_sql}
                """
                rows = conn.execute(query, (year_month_from,)).fetchall()
            elif date_to:
                query = f"""
                    SELECT client,
                           SUM(received) as total_received,
                           SUM(sent) as total_sent
                    FROM wg_daily_stats
                    WHERE date >= ? AND date < ?
                      AND interface != 'warp'
                    GROUP BY client
                    HAVING SUM(received) > 0 OR SUM(sent) > 0
                    ORDER BY {sort_column} {order_sql}
                """
                rows = conn.execute(query, (date_from, date_to)).fetchall()
            else:
                query = f"""
                    SELECT client,
                           SUM(received) as total_received,
                           SUM(sent) as total_sent
                    FROM wg_daily_stats
                    WHERE date >= ?
                      AND interface != 'warp'
                    GROUP BY client
                    HAVING SUM(received) > 0 OR SUM(sent) > 0
                    ORDER BY {sort_column} {order_sql}
                """
                rows = conn.execute(query, (date_from,)).fetchall()

            for row in rows:
                client, received, sent = row
                received = received or 0
                sent = sent or 0
                total_received += received
                total_sent += sent
                stats_list.append(
                    {
                        "client": client,
                        "total_received": format_bytes(received),
                        "total_sent": format_bytes(sent),
                        "total_received_raw": received,
                        "total_sent_raw": sent,
                    }
                )

        return render_template(
            "wg/wg_stats.html",
            total_received=format_bytes(total_received),
            total_sent=format_bytes(total_sent),
            active_section="wg",
            active_page="wg_stats",
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
                "wg/wg_stats.html",
                error_message=error_message,
                active_section="wg",
                active_page="wg_stats",
            ),
            500,
        )


@app.route("/api/wg/client_chart")
@login_required
def api_wg_client_chart():
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
        with sqlite3.connect(app.config["WG_STATS_PATH"]) as conn:
            if is_single_day:
                start_hour, end_hour = get_server_hour_window_for_client_day(
                    target_date, client_tz
                )
                rows = conn.execute(
                    """
                    SELECT hour,
                           SUM(received) as rx,
                           SUM(sent) as tx
                    FROM wg_hourly_stats
                    WHERE client = ? AND hour >= ? AND hour < ?
                      AND interface != 'warp'
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
                           SUM(received) as rx,
                           SUM(sent) as tx
                    FROM wg_monthly_stats
                    WHERE client = ? AND month >= ?
                      AND interface != 'warp'
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
                    SELECT date,
                           SUM(received) as rx,
                           SUM(sent) as tx
                    FROM wg_daily_stats
                    WHERE client = ? AND date >= ? AND date < ?
                      AND interface != 'warp'
                    GROUP BY date
                    ORDER BY date ASC
                    """,
                    (client_name, date_from, date_to),
                ).fetchall()
                labels = [r[0] for r in rows]
                rx_data = [r[1] or 0 for r in rows]
                tx_data = [r[2] or 0 for r in rows]
            else:
                rows = conn.execute(
                    """
                    SELECT date,
                           SUM(received) as rx,
                           SUM(sent) as tx
                    FROM wg_daily_stats
                    WHERE client = ? AND date >= ?
                      AND interface != 'warp'
                    GROUP BY date
                    ORDER BY date ASC
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
