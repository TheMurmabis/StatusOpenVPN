import json
import os
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta, timezone

from flask import jsonify, request
from flask_login import login_required

from src.ui.constants import LIVE_POINTS, VPN_SYSTEMD_UNIT_SET
from src.ui.extensions import app
from src.ui.services.stats_service import group_rows, resample_to_n
from src.ui.services.system_info_service import get_system_info, get_vnstat_interfaces
from src.ui.services.vpn_service import restart_vpn_systemd_unit
from src.ui.state import cpu_history


@app.route("/api/system_info")
@login_required
def api_system_info():
    system_info = get_system_info()
    return jsonify(system_info)


@app.route("/api/vpn-service/restart", methods=["POST"])
@login_required
def api_restart_vpn_service():
    data = request.get_json(silent=True) or {}
    unit = data.get("unit")
    if not unit or not isinstance(unit, str) or unit not in VPN_SYSTEMD_UNIT_SET:
        return jsonify({"ok": False, "error": "Недопустимый unit"}), 400
    ok, detail = restart_vpn_systemd_unit(unit)
    if ok:
        return jsonify({"ok": True, "detail": detail})
    return jsonify({"ok": False, "error": detail}), 500


@app.route("/api/ovpn/next_update")
@login_required
def api_ovpn_next_update():
    """Оценка времени следующего обновления логов OpenVPN."""
    file_paths = [
        ("/etc/openvpn/server/logs/antizapret-udp-status.log", "UDP"),
        ("/etc/openvpn/server/logs/antizapret-tcp-status.log", "TCP"),
        ("/etc/openvpn/server/logs/vpn-udp-status.log", "VPN-UDP"),
        ("/etc/openvpn/server/logs/vpn-tcp-status.log", "VPN-TCP"),
    ]

    mtimes = []
    for path, _ in file_paths:
        try:
            if os.path.exists(path):
                mtimes.append(os.path.getmtime(path))
        except OSError:
            continue

    now_ts = time.time()

    if not mtimes:
        next_update_ts = now_ts + 30
    else:
        last_mtime = max(mtimes)
        next_update_ts = last_mtime + 30
        if next_update_ts <= now_ts:
            next_update_ts = now_ts + 30

    return jsonify(
        {
            "server_time": int(now_ts),
            "next_update_ts": int(next_update_ts),
            "interval_seconds": 30,
        }
    )


@app.route("/api/bw")
@login_required
def api_bw():
    q_iface = request.args.get("iface")
    period = request.args.get("period", "day")
    vnstat_bin = os.environ.get("VNSTAT_BIN", "/usr/bin/vnstat")

    try:
        proc = subprocess.run(
            [vnstat_bin, "--json"], check=True, capture_output=True, text=True
        )
        data = json.loads(proc.stdout)
        interfaces = [iface["name"] for iface in data.get("interfaces", [])]
    except subprocess.CalledProcessError:
        interfaces = []
    except json.JSONDecodeError:
        interfaces = []

    if not interfaces:
        return jsonify({"error": "Нет интерфейсов vnstat", "iface": None}), 500

    iface = q_iface if q_iface in interfaces else interfaces[0]

    if period == "hour":
        vnstat_option = "f"
        points = 12
        interval_seconds = 300
    elif period == "day":
        vnstat_option = "h"
        points = 24
        interval_seconds = 3600
    elif period == "week":
        vnstat_option = "d"
        points = 7
        interval_seconds = 86400
    elif period == "month":
        vnstat_option = "d"
        points = 30
        interval_seconds = 86400
    else:
        vnstat_option = "h"
        points = 24
        interval_seconds = 3600

    try:
        proc = subprocess.run(
            [vnstat_bin, "--json", vnstat_option, "-i", iface],
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(proc.stdout)
    except subprocess.CalledProcessError as e:
        return (
            jsonify(
                {"error": f"vnstat вернул код ошибки: {e.returncode}", "iface": iface}
            ),
            500,
        )
    except Exception as e:
        return jsonify({"error": str(e), "iface": iface}), 500

    traffic_data = []
    for it in data.get("interfaces", []):
        if it.get("name") == iface:
            traffic = it.get("traffic") or {}
            if vnstat_option == "f":
                traffic_data = traffic.get("fiveminute") or []
            elif vnstat_option == "h":
                traffic_data = traffic.get("hour") or []
            elif vnstat_option == "d":
                traffic_data = traffic.get("day") or []
            break

    def sort_key(h):
        d = h.get("date") or {}
        t = h.get("time") or {}
        return (
            d.get("year", 0),
            d.get("month", 0),
            d.get("day", 0),
            t.get("hour", 0),
            t.get("minute", 0),
        )

    sorted_data = sorted(traffic_data, key=sort_key)
    if points:
        sorted_data = sorted_data[-points:]

    labels, utc_labels, rx_mbps, tx_mbps = [], [], [], []

    server_tz = datetime.now().astimezone().tzinfo

    for m in sorted_data:
        d = m.get("date") or {}
        t = m.get("time") or {}

        year = int(d.get("year", 0))
        month = int(d.get("month", 0))
        day = int(d.get("day", 0))
        hour = int(t.get("hour", 0))
        minute = int(t.get("minute", 0))

        if vnstat_option == "f":
            labels.append(f"{hour:02d}:{minute:02d}")
        elif vnstat_option == "h":
            labels.append(f"{hour:02d}:00")
        else:
            labels.append(f"{day:02d}.{month:02d}")

        try:
            local_dt = datetime(year, month, day, hour, minute, tzinfo=server_tz)
        except Exception:
            local_dt = datetime.now().astimezone(server_tz)

        utc_iso = local_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        utc_labels.append(utc_iso)

        rx = int(m.get("rx", 0))
        tx = int(m.get("tx", 0))
        rx_mbps.append(round((rx * 8) / (interval_seconds * 1_000_000), 3))
        tx_mbps.append(round((tx * 8) / (interval_seconds * 1_000_000), 3))

    server_time_utc = datetime.now(timezone.utc).isoformat()

    return jsonify(
        {
            "iface": iface,
            "labels": labels,
            "utc_labels": utc_labels,
            "rx_mbps": rx_mbps,
            "tx_mbps": tx_mbps,
            "server_time": server_time_utc,
        }
    )


@app.route("/api/interfaces")
def api_interfaces():
    interfaces = get_vnstat_interfaces()
    return jsonify({"interfaces": interfaces})


@app.route("/api/cpu")
def api_cpu():
    period = request.args.get("period", "live")
    now = datetime.now()

    targets = {
        "live": LIVE_POINTS,
        "hour": 60,
        "day": 24,
        "week": 7,
        "month": 30,
    }
    max_points = targets.get(period, LIVE_POINTS)

    mem_rows = list(cpu_history)

    if period == "live":
        last = mem_rows[-LIVE_POINTS:] if len(mem_rows) > LIVE_POINTS else mem_rows

        data = [
            {"timestamp": r["timestamp"], "cpu": r["cpu"], "ram": r["ram"]}
            for r in last
        ]

    else:
        if period == "hour":
            bucket = "minute"
            cutoff = now - timedelta(hours=1)
        elif period == "day":
            bucket = "hour"
            cutoff = now - timedelta(days=1)
        elif period == "week":
            bucket = "day"
            cutoff = now - timedelta(days=7)
        elif period == "month":
            bucket = "day"
            cutoff = now - timedelta(days=30)
        else:
            bucket = "minute"
            cutoff = now - timedelta(hours=1)

        mem_candidates = [r for r in mem_rows if r["timestamp"] >= cutoff]
        need_db = True
        if need_db:
            try:
                conn = sqlite3.connect(app.config["SYSTEM_STATS_PATH"])
                cur = conn.cursor()

                cur.execute(
                    """
                    SELECT timestamp, cpu_percent, ram_percent
                    FROM system_stats
                    WHERE timestamp >= ?
                    ORDER BY timestamp ASC
                """,
                    (cutoff.strftime("%Y-%m-%d %H:%M:%S"),),
                )

                rows = cur.fetchall()
                conn.close()

                source_rows = [
                    {
                        "timestamp": datetime.strptime(ts, "%Y-%m-%d %H:%M:%S"),
                        "cpu": cpu,
                        "ram": ram,
                    }
                    for ts, cpu, ram in rows
                ]

            except Exception as e:
                print("[DB ERROR] api_cpu:", e)
                source_rows = mem_candidates
        else:
            source_rows = mem_candidates

        grouped = group_rows(source_rows, interval=bucket)
        data = resample_to_n(grouped, max_points)

    utc_labels = [
        d["timestamp"].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for d in data
    ]

    return jsonify(
        {
            "utc_labels": utc_labels,
            "cpu_percent": [round(d["cpu"], 2) for d in data],
            "ram_percent": [round(d["ram"], 2) for d in data],
            "period": period,
        }
    )
