import io
import os
import shutil
import subprocess

from flask import jsonify, request, send_file
from flask_login import current_user, login_required

from src.ui.constants import CLIENT_NAME_PATTERN, CLIENT_SH_PATH
from src.ui.extensions import app
from src.ui.services.openvpn_service import (
    ensure_client_connect_ban_check_block,
    kick_openvpn_client,
    read_banned_clients,
    run_openvpn_add_or_renew_client,
    write_banned_clients,
)
from src.ui.services.settings_service import read_settings
from src.ui.utils.openvpn_naming import (
    list_openvpn_ovpn_paths_for_client,
    ovpn_profile_label,
)
from src.ui.utils.wireguard_naming import (
    list_wg_conf_paths_for_client,
    wg_client_name_param_ok,
    wg_conf_path_is_allowed,
    wg_conf_profile_label,
    wg_conf_short_filename,
)
from src.tg_bot.audit import log_action


@app.route("/api/openvpn/client-cert", methods=["POST"])
@login_required
def api_openvpn_client_cert():
    client_name = request.form.get("client_name", "").strip()
    days_raw = request.form.get("days", "").strip()

    if not days_raw.isdigit() or not (1 <= int(days_raw) <= 3650):
        return jsonify({"success": False, "message": "Укажите срок от 1 до 3650 дней."}), 400

    result = run_openvpn_add_or_renew_client(client_name, int(days_raw))
    if not result.get("success"):
        return jsonify(result), 400

    action = "client_cert_renew" if result.get("renewed") else "client_create"
    detail = f"{client_name} (до {result.get('cert_expiry_label', '—')})"
    if result.get("was_expired"):
        detail += ", истёкший сертификат"
    log_action(
        "web",
        getattr(current_user, "id", 0),
        getattr(current_user, "username", "admin"),
        action,
        detail,
    )
    return jsonify(result)


@app.route("/api/openvpn/client-block", methods=["POST"])
@login_required
def api_openvpn_client_block():
    client_name = request.form.get("client_name", "").strip()
    blocked_raw = request.form.get("blocked", "").strip().lower()

    if not CLIENT_NAME_PATTERN.fullmatch(client_name):
        return jsonify({"success": False, "message": "Некорректное имя клиента."}), 400

    should_block = blocked_raw in {"1", "true", "yes", "on"}

    try:
        ensure_client_connect_ban_check_block()
        banned_clients = read_banned_clients()

        if should_block:
            banned_clients.add(client_name)
        else:
            banned_clients.discard(client_name)

        write_banned_clients(banned_clients)
        return jsonify(
            {
                "success": True,
                "client_name": client_name,
                "blocked": should_block,
                "message": (
                    "Клиент заблокирован." if should_block else "Блокировка снята."
                ),
            }
        )
    except PermissionError:
        return (
            jsonify(
                {"success": False, "message": "Нет прав на запись banned_clients."}
            ),
            500,
        )
    except OSError as e:
        return (
            jsonify(
                {"success": False, "message": f"Ошибка работы с banned_clients: {e}"}
            ),
            500,
        )


@app.route("/api/openvpn/client-kick", methods=["POST"])
@login_required
def api_openvpn_client_kick():
    client_name = request.form.get("client_name", "").strip()
    protocol = request.form.get("protocol", "").strip() or None

    if not CLIENT_NAME_PATTERN.fullmatch(client_name):
        return jsonify({"success": False, "message": "Некорректное имя клиента."}), 400

    try:
        ensure_client_connect_ban_check_block()
        banned_clients = read_banned_clients()
        banned_clients.add(client_name)
        write_banned_clients(banned_clients)

        kicked, errors = kick_openvpn_client(client_name, protocol)

        if kicked:
            return jsonify(
                {
                    "success": True,
                    "client_name": client_name,
                    "kicked": True,
                    "blocked": True,
                    "message": "Клиент отключён и заблокирован.",
                }
            )
        return jsonify(
            {
                "success": True,
                "client_name": client_name,
                "kicked": False,
                "blocked": True,
                "message": "Клиент заблокирован. Отключение не удалось (возможно, уже оффлайн).",
                "errors": errors,
            }
        )

    except PermissionError:
        return (
            jsonify(
                {"success": False, "message": "Нет прав на запись banned_clients."}
            ),
            500,
        )
    except OSError as e:
        return jsonify({"success": False, "message": f"Ошибка: {e}"}), 500


@app.route("/api/openvpn/client-delete", methods=["POST"])
@login_required
def api_openvpn_client_delete():
    client_name = request.form.get("client_name", "").strip()
    if not CLIENT_NAME_PATTERN.fullmatch(client_name):
        return jsonify({"success": False, "message": "Некорректное имя клиента."}), 400

    if not os.path.isfile(CLIENT_SH_PATH):
        return jsonify({"success": False, "message": "Не найден скрипт client.sh"}), 500

    env = {
        **os.environ,
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    }
    try:
        proc = subprocess.run(
            [CLIENT_SH_PATH, "2", client_name],
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return (
            jsonify({"success": False, "message": "Превышено время ожидания client.sh"}),
            500,
        )
    except OSError as e:
        return jsonify({"success": False, "message": str(e)}), 500

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return (
            jsonify(
                {
                    "success": False,
                    "message": err or f"client.sh завершился с кодом {proc.returncode}",
                }
            ),
            500,
        )

    try:
        banned_clients = read_banned_clients()
        if client_name in banned_clients:
            banned_clients.discard(client_name)
            write_banned_clients(banned_clients)
    except OSError:
        pass

    log_action(
        "web",
        getattr(current_user, "id", 0),
        getattr(current_user, "username", "admin"),
        "client_delete",
        f"{client_name} (OpenVPN)",
    )
    return jsonify(
        {
            "success": True,
            "client_name": client_name,
            "message": f"Клиент <b>{client_name}</b> удалён.",
        }
    )


@app.route("/api/openvpn/client-config", methods=["GET"])
@login_required
def api_openvpn_client_config():
    """Список профилей .ovpn или содержимое по index."""
    client_name = request.args.get("client_name", "").strip()
    idx_raw = request.args.get("index", "").strip()

    if not CLIENT_NAME_PATTERN.fullmatch(client_name):
        return jsonify({"success": False, "message": "Некорректное имя клиента."}), 400

    paths = list_openvpn_ovpn_paths_for_client(client_name)
    if idx_raw == "":
        items = [
            {"index": i, "label": ovpn_profile_label(p)} for i, p in enumerate(paths)
        ]
        return jsonify({"success": True, "items": items})

    try:
        idx = int(idx_raw)
    except ValueError:
        return jsonify({"success": False, "message": "Некорректный index."}), 400

    if idx < 0 or idx >= len(paths):
        return jsonify({"success": False, "message": "Профиль не найден."}), 404

    path = paths[idx]
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        return jsonify({"success": False, "message": str(e)}), 500

    return jsonify(
        {
            "success": True,
            "config_text": text,
            "label": ovpn_profile_label(path),
            "filename": os.path.basename(path),
        }
    )


@app.route("/api/openvpn/client-config/download", methods=["GET"])
@login_required
def api_openvpn_client_config_download():
    """Скачивание .ovpn по имени клиента и индексу профиля."""
    client_name = request.args.get("client_name", "").strip()
    idx_raw = request.args.get("index", "0").strip()

    if not CLIENT_NAME_PATTERN.fullmatch(client_name):
        return jsonify({"success": False, "message": "Некорректное имя клиента."}), 400

    try:
        idx = int(idx_raw)
    except ValueError:
        return jsonify({"success": False, "message": "Некорректный index."}), 400

    paths = list_openvpn_ovpn_paths_for_client(client_name)
    if idx < 0 or idx >= len(paths):
        return jsonify({"success": False, "message": "Профиль не найден."}), 404

    path = paths[idx]
    if not os.path.isfile(path):
        return jsonify({"success": False, "message": "Файл не найден."}), 404

    return send_file(
        path,
        as_attachment=True,
        download_name=os.path.basename(path),
        mimetype="application/x-openvpn-profile",
    )


@app.route("/api/wireguard/client-config", methods=["GET"])
@login_required
def api_wireguard_client_config():
    """Список .conf профилей или содержимое по index."""
    client_name = request.args.get("client_name", "").strip()
    idx_raw = request.args.get("index", "").strip()

    if not wg_client_name_param_ok(client_name):
        return jsonify({"success": False, "message": "Некорректное имя клиента."}), 400

    paths = list_wg_conf_paths_for_client(client_name)
    shorten = bool(read_settings().get("shorten_wg_filenames", False))
    if idx_raw == "":
        items = [
            {
                "index": i,
                "label": wg_conf_profile_label(p),
                "filename": wg_conf_short_filename(p) if shorten else os.path.basename(p),
            }
            for i, p in enumerate(paths)
        ]
        return jsonify({"success": True, "items": items})

    try:
        idx = int(idx_raw)
    except ValueError:
        return jsonify({"success": False, "message": "Некорректный index."}), 400

    if idx < 0 or idx >= len(paths):
        return jsonify({"success": False, "message": "Профиль не найден."}), 404

    path = paths[idx]
    if not wg_conf_path_is_allowed(path):
        return jsonify({"success": False, "message": "Недопустимый путь."}), 403

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        return jsonify({"success": False, "message": str(e)}), 500

    return jsonify(
        {
            "success": True,
            "config_text": text,
            "label": wg_conf_profile_label(path),
            "filename": wg_conf_short_filename(path) if shorten else os.path.basename(path),
        }
    )


@app.route("/api/wireguard/client-config/download", methods=["GET"])
@login_required
def api_wireguard_client_config_download():
    """Скачивание .conf по имени клиента и индексу профиля."""
    client_name = request.args.get("client_name", "").strip()
    idx_raw = request.args.get("index", "0").strip()

    if not wg_client_name_param_ok(client_name):
        return jsonify({"success": False, "message": "Некорректное имя клиента."}), 400

    try:
        idx = int(idx_raw)
    except ValueError:
        return jsonify({"success": False, "message": "Некорректный index."}), 400

    paths = list_wg_conf_paths_for_client(client_name)
    if idx < 0 or idx >= len(paths):
        return jsonify({"success": False, "message": "Профиль не найден."}), 404

    path = paths[idx]
    if not wg_conf_path_is_allowed(path):
        return jsonify({"success": False, "message": "Недопустимый путь."}), 403

    if not os.path.isfile(path):
        return jsonify({"success": False, "message": "Файл не найден."}), 404

    shorten = bool(read_settings().get("shorten_wg_filenames", False))
    download_name = wg_conf_short_filename(path) if shorten else os.path.basename(path)

    return send_file(
        path,
        as_attachment=True,
        download_name=download_name,
        mimetype="text/plain",
    )


def _wg_qr_png_for_conf_path(path: str) -> bytes:
    qrencode_bin = shutil.which("qrencode") or "/usr/bin/qrencode"
    if not os.path.isfile(qrencode_bin):
        raise FileNotFoundError("qrencode не найден. Установите пакет qrencode.")

    with open(path, "rb") as f:
        config_data = f.read()

    proc = subprocess.run(
        [qrencode_bin, "-t", "PNG", "-o", "-"],
        input=config_data,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode(errors="replace").strip()
        raise RuntimeError(stderr or f"qrencode завершился с кодом {proc.returncode}")

    if not proc.stdout:
        raise RuntimeError("qrencode не вернул изображение")

    return proc.stdout


@app.route("/api/wireguard/client-config/qr", methods=["GET"])
@login_required
def api_wireguard_client_config_qr():
    """PNG QR-код конфигурации WireGuard (qrencode)."""
    client_name = request.args.get("client_name", "").strip()
    idx_raw = request.args.get("index", "0").strip()

    if not wg_client_name_param_ok(client_name):
        return jsonify({"success": False, "message": "Некорректное имя клиента."}), 400

    try:
        idx = int(idx_raw)
    except ValueError:
        return jsonify({"success": False, "message": "Некорректный index."}), 400

    paths = list_wg_conf_paths_for_client(client_name)
    if idx < 0 or idx >= len(paths):
        return jsonify({"success": False, "message": "Профиль не найден."}), 404

    path = paths[idx]
    if not wg_conf_path_is_allowed(path):
        return jsonify({"success": False, "message": "Недопустимый путь."}), 403

    if not os.path.isfile(path):
        return jsonify({"success": False, "message": "Файл не найден."}), 404

    try:
        png_data = _wg_qr_png_for_conf_path(path)
    except FileNotFoundError as e:
        return jsonify({"success": False, "message": str(e)}), 503
    except OSError as e:
        return jsonify({"success": False, "message": str(e)}), 500
    except RuntimeError as e:
        return jsonify({"success": False, "message": str(e)}), 500

    return send_file(
        io.BytesIO(png_data),
        mimetype="image/png",
        download_name="wireguard-qr.png",
    )
