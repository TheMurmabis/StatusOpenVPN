import os
import tempfile

from flask import abort, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from src.tg_bot.audit import get_logs, get_logs_count, log_action
from src.ui.constants import (
    ANTIZAPRET_SETUP_DESCRIPTIONS,
    ANTIZAPRET_SETUP_PATH,
    STATS_DB_CLEAR_OVPN_PHRASE,
    STATS_DB_CLEAR_WG_PHRASE,
    STATUSOPENVPN_SETUP_PATH,
    WEB_SETUP_DESCRIPTIONS,
)
from src.ui.extensions import app
from src.ui.services.admins_service import (
    build_admin_display_list,
    build_available_admin_candidates,
    build_client_mapping_list,
    format_admin_ids,
    parse_admin_ids,
    read_admin_info,
)
from src.ui.services.backup_service import (
    SETTINGS_RESTORE_PHRASE,
    build_statusopenvpn_backup_archive,
    create_vpn_clients_backup,
    restore_settings_from_file,
    restore_statusopenvpn_from_archive,
    settings_file_path,
)
from src.ui.services.bot_service import (
    get_telegram_bot_status,
    restart_telegram_bot,
    stop_telegram_bot,
)
from src.ui.services.env_service import (
    read_env_values,
    read_setup_key_value_file,
    update_env_values,
)
from src.ui.services.settings_service import (
    get_display_app_name,
    parse_history_max_records,
    parse_stats_retention_days,
    read_settings,
    write_settings,
)
from src.ui.services.stats_service import (
    clear_openvpn_stats_database,
    clear_wireguard_stats_database,
    get_ovpn_wg_database_sizes,
)
from src.ui.services.update_service import (
    get_latest_github_version,
    is_update_available,
    is_update_running,
    read_update_log_tail,
    start_silent_update,
)
from src.ui.utils.format_utils import format_bytes


def _get_client_ip():
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if client_ip and "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()
    return client_ip or ""


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    settings_message = None
    settings_error = None
    stats_db_message = None
    stats_db_error = None

    if request.method == "POST":
        form_type = request.form.get("form_type")

        if form_type == "settings_all":
            app_name = request.form.get("app_name", "").strip()
            show_ovpn_menu = request.form.get("show_ovpn_menu") == "on"
            show_wg_menu = request.form.get("show_wg_menu") == "on"
            hide_ovpn_ip = request.form.get("hide_ovpn_ip") == "on"
            hide_wg_ip = request.form.get("hide_wg_ip") == "on"
            shorten_wg_filenames = request.form.get("shorten_wg_filenames") == "on"
            hide_wg_warp_interface = request.form.get("hide_wg_warp_interface") == "on"
            retention_days = parse_stats_retention_days(
                request.form.get("stats_retention_days", "365")
            )
            history_max_records = parse_history_max_records(
                request.form.get("history_max_records", "1000")
            )
            write_settings(
                {
                    "app_name": app_name,
                    "show_ovpn_menu": show_ovpn_menu,
                    "show_wg_menu": show_wg_menu,
                    "hide_ovpn_ip": hide_ovpn_ip,
                    "hide_wg_ip": hide_wg_ip,
                    "shorten_wg_filenames": shorten_wg_filenames,
                    "hide_wg_warp_interface": hide_wg_warp_interface,
                    "stats_retention_days": retention_days,
                    "history_max_records": history_max_records,
                }
            )
            settings_message = "Настройки сохранены."

        elif form_type == "stats_db_clear_ovpn":
            phrase = (request.form.get("confirm_phrase") or "").strip()
            if phrase != STATS_DB_CLEAR_OVPN_PHRASE:
                stats_db_error = "Неверная фраза. Введите: OpenVPN"
            else:
                ok, err = clear_openvpn_stats_database()
                if ok:
                    stats_db_message = "База статистики OpenVPN очищена."
                    log_action(
                        "web",
                        current_user.username,
                        current_user.username,
                        "stats_db_clear_ovpn",
                        "",
                        _get_client_ip(),
                    )
                else:
                    stats_db_error = f"Ошибка очистки OpenVPN: {err}"

        elif form_type == "stats_db_clear_wg":
            phrase = (request.form.get("confirm_phrase") or "").strip()
            if phrase != STATS_DB_CLEAR_WG_PHRASE:
                stats_db_error = "Неверная фраза. Введите: WireGuard"
            else:
                ok, err = clear_wireguard_stats_database()
                if ok:
                    stats_db_message = "База статистики WireGuard очищена."
                    log_action(
                        "web",
                        current_user.username,
                        current_user.username,
                        "stats_db_clear_wg",
                        "",
                        _get_client_ip(),
                    )
                else:
                    stats_db_error = f"Ошибка очистки WireGuard: {err}"

    settings_data = read_settings()
    current_app_name = settings_data.get("app_name", "StatusOpenVPN")
    show_ovpn_menu = bool(settings_data.get("show_ovpn_menu", True))
    show_wg_menu = bool(settings_data.get("show_wg_menu", True))
    hide_ovpn_ip = settings_data.get("hide_ovpn_ip", True)
    hide_wg_ip = settings_data.get("hide_wg_ip", True)
    shorten_wg_filenames = bool(settings_data.get("shorten_wg_filenames", False))
    hide_wg_warp_interface = bool(settings_data.get("hide_wg_warp_interface", False))
    stats_retention_days = parse_stats_retention_days(
        settings_data.get("stats_retention_days", 365)
    )
    history_max_records = parse_history_max_records(
        settings_data.get("history_max_records", 1000)
    )

    stats_db_items, stats_db_total_bytes = get_ovpn_wg_database_sizes()

    return render_template(
        "settings/settings.html",
        app_name=current_app_name,
        show_ovpn_menu=show_ovpn_menu,
        show_wg_menu=show_wg_menu,
        hide_ovpn_ip=hide_ovpn_ip,
        hide_wg_ip=hide_wg_ip,
        shorten_wg_filenames=shorten_wg_filenames,
        hide_wg_warp_interface=hide_wg_warp_interface,
        settings_message=settings_message,
        settings_error=settings_error,
        stats_retention_days=stats_retention_days,
        history_max_records=history_max_records,
        stats_db_items=stats_db_items,
        stats_db_total_fmt=format_bytes(stats_db_total_bytes),
        stats_db_message=stats_db_message,
        stats_db_error=stats_db_error,
        stats_clear_ovpn_phrase=STATS_DB_CLEAR_OVPN_PHRASE,
        stats_clear_wg_phrase=STATS_DB_CLEAR_WG_PHRASE,
        active_page="settings",
    )


@app.route("/settings/telegram", methods=["GET", "POST"])
@login_required
def settings_telegram():
    bot_message = None
    bot_error = None

    if request.method == "POST":
        form_type = request.form.get("form_type")

        if form_type == "bot":
            old_env = read_env_values()
            old_token = old_env.get("BOT_TOKEN", "")
            old_admin_id = old_env.get("ADMIN_ID", "")
            old_settings = read_settings()
            old_bot_enabled = (
                bool(old_settings.get("bot_enabled", False))
                or get_telegram_bot_status()
            )

            bot_token = request.form.get("bot_token", "").strip()
            admin_id = request.form.get("admin_id")
            if admin_id is None:
                admin_id = old_admin_id
            admin_id = admin_id.strip()
            bot_enabled = request.form.get("bot_enabled") == "on"
            update_env_values({"BOT_TOKEN": bot_token, "ADMIN_ID": admin_id})
            write_settings({"bot_enabled": bot_enabled})

            client_ip = _get_client_ip()

            if bot_token != old_token:
                token_changed = "изменён" if bot_token else "удалён"
                log_action(
                    "web",
                    current_user.username,
                    current_user.username,
                    "bot_token_change",
                    token_changed,
                    client_ip,
                )

            if admin_id != old_admin_id:
                log_action(
                    "web",
                    current_user.username,
                    current_user.username,
                    "bot_admins_change",
                    f"{old_admin_id} → {admin_id}",
                    client_ip,
                )

            should_start = bool(bot_enabled and bot_token)

            if should_start:
                restart_ok, restart_error = restart_telegram_bot()
                if restart_ok:
                    bot_message = "Настройки бота сохранены. Бот перезапущен."
                    if not old_bot_enabled:
                        log_action(
                            "web",
                            current_user.username,
                            current_user.username,
                            "bot_toggle",
                            "включён",
                            client_ip,
                        )
                else:
                    bot_error = (
                        "Настройки бота сохранены, но перезапуск не удался: "
                        f"{restart_error}"
                    )
            else:
                restart_ok, restart_error = stop_telegram_bot()
                if restart_ok:
                    if not bot_token:
                        bot_message = (
                            "Настройки бота сохранены. API токен бота пустой, бот остановлен."
                        )
                    else:
                        bot_message = "Настройки бота сохранены. Бот остановлен."
                    if old_bot_enabled:
                        log_action(
                            "web",
                            current_user.username,
                            current_user.username,
                            "bot_toggle",
                            "отключён",
                            client_ip,
                        )
                else:
                    bot_error = (
                        "Настройки бота сохранены, но остановка не удалась: "
                        f"{restart_error}"
                    )

    env_values = read_env_values()
    bot_token_value = env_values.get("BOT_TOKEN", "")
    admin_id_value = env_values.get("ADMIN_ID", "")
    settings_data = read_settings()
    admin_info = settings_data.get("telegram_admins", {})
    admin_display_list = build_admin_display_list(admin_id_value, admin_info)
    available_admins = build_available_admin_candidates(
        admin_info, parse_admin_ids(admin_id_value)
    )
    client_mapping_list = build_client_mapping_list(env_values, admin_info)
    bot_service_active = get_telegram_bot_status()
    bot_enabled = bool(settings_data.get("bot_enabled", False)) or bot_service_active

    return render_template(
        "settings/telegram.html",
        bot_token=bot_token_value,
        admin_id=admin_id_value,
        admin_display_list=admin_display_list,
        available_admins=available_admins,
        client_mapping_list=client_mapping_list,
        bot_service_active=bot_service_active,
        bot_enabled=bot_enabled,
        bot_message=bot_message,
        bot_error=bot_error,
        active_page="settings_telegram",
    )


@app.route("/settings/backups", methods=["GET", "POST"])
@login_required
def settings_backups():
    backup_message = None
    backup_error = None
    app_display_name = get_display_app_name()
    restore_phrase = app_display_name

    if request.method == "GET":
        q_error = (request.args.get("error") or "").strip()
        q_message = (request.args.get("message") or "").strip()
        if q_message:
            backup_error = q_message
        elif q_error == "vpn":
            backup_error = "Не удалось создать бэкап клиентов VPN."
        elif q_error == "statusopenvpn":
            backup_error = f"Не удалось создать бэкап {app_display_name}."

    if request.method == "POST":
        form_type = request.form.get("form_type")
        if form_type == "restore_statusopenvpn":
            phrase = (request.form.get("confirm_phrase") or "").strip()
            if phrase != restore_phrase:
                backup_error = f"Неверная фраза. Введите: {restore_phrase}"
            else:
                archive = request.files.get("archive")
                if not archive or not archive.filename:
                    backup_error = "Выберите архив для восстановления."
                else:
                    ok, msg = restore_statusopenvpn_from_archive(
                        archive.stream, archive.filename
                    )
                    if ok:
                        backup_message = msg
                        log_action(
                            "web",
                            current_user.username,
                            current_user.username,
                            "backup_restore_statusopenvpn",
                            archive.filename,
                            _get_client_ip(),
                        )
                    else:
                        backup_error = msg

        elif form_type == "restore_settings":
            phrase = (request.form.get("confirm_phrase") or "").strip()
            if phrase != SETTINGS_RESTORE_PHRASE:
                backup_error = f"Неверная фраза. Введите: {SETTINGS_RESTORE_PHRASE}"
            else:
                settings_file = request.files.get("settings_file")
                if not settings_file or not settings_file.filename:
                    backup_error = "Выберите файл settings.json для восстановления."
                else:
                    ok, msg = restore_settings_from_file(
                        settings_file.stream, settings_file.filename
                    )
                    if ok:
                        backup_message = msg
                        log_action(
                            "web",
                            current_user.username,
                            current_user.username,
                            "backup_restore_settings",
                            settings_file.filename,
                            _get_client_ip(),
                        )
                    else:
                        backup_error = msg

    return render_template(
        "settings/backups.html",
        backup_message=backup_message,
        backup_error=backup_error,
        settings_available=bool(settings_file_path()),
        app_display_name=app_display_name,
        restore_phrase=restore_phrase,
        settings_restore_phrase=SETTINGS_RESTORE_PHRASE,
        active_page="settings_backups",
    )


@app.route("/settings/backups/download/vpn")
@login_required
def settings_backups_download_vpn():
    ok, err, path = create_vpn_clients_backup()
    if not ok or not path:
        return redirect(
            url_for("settings_backups", error="vpn", message=err or "Ошибка бэкапа")
        )
    log_action(
        "web",
        current_user.username,
        current_user.username,
        "backup_download_vpn",
        os.path.basename(path),
        _get_client_ip(),
    )
    return send_file(
        path,
        as_attachment=True,
        download_name=os.path.basename(path),
        mimetype="application/gzip",
    )


@app.route("/settings/backups/download/statusopenvpn")
@login_required
def settings_backups_download_statusopenvpn():
    tmp = tempfile.NamedTemporaryFile(
        prefix="StatusOpenVPN-backup-",
        suffix=".tar.gz",
        delete=False,
    )
    tmp_path = tmp.name
    tmp.close()
    ok, err = build_statusopenvpn_backup_archive(tmp_path)
    if not ok:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return redirect(
            url_for(
                "settings_backups",
                error="statusopenvpn",
                message=err or "Ошибка бэкапа",
            )
        )
    log_action(
        "web",
        current_user.username,
        current_user.username,
        "backup_download_statusopenvpn",
        "StatusOpenVPN-backup.tar.gz",
        _get_client_ip(),
    )

    def _cleanup():
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    response = send_file(
        tmp_path,
        as_attachment=True,
        download_name="StatusOpenVPN-backup.tar.gz",
        mimetype="application/gzip",
    )
    response.call_on_close(_cleanup)
    return response


@app.route("/settings/backups/download/settings")
@login_required
def settings_backups_download_settings():
    path = settings_file_path()
    if not path:
        abort(404)
    log_action(
        "web",
        current_user.username,
        current_user.username,
        "backup_download_settings",
        "settings.json",
        _get_client_ip(),
    )
    return send_file(
        path,
        as_attachment=True,
        download_name="settings.json",
        mimetype="application/json",
    )


@app.route("/settings/audit")
@login_required
def settings_audit():
    page = request.args.get("page", 1, type=int)
    action_filter = request.args.get("action", None)
    per_page = 20

    if action_filter == "all":
        action_filter = None

    total = get_logs_count(action_filter)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    offset = (page - 1) * per_page

    logs = get_logs(limit=per_page, offset=offset, action_filter=action_filter)

    action_labels = {
        "client_create": "Создание клиента",
        "client_cert_renew": "Продление сертификата OpenVPN",
        "client_delete": "Удаление клиента",
        "files_recreate": "Пересоздание файлов",
        "server_reboot": "Перезагрузка сервера",
        "web_login": "Вход в панель",
        "peer_toggle": "Переключение WG пира",
        "wg_client_create": "Создание клиента WireGuard",
        "wg_client_delete": "Удаление клиента WireGuard",
        "wg_client_rename": "Переименование клиента WireGuard",
        "bot_token_change": "Изменение токена бота",
        "bot_admins_change": "Изменение админов бота",
        "bot_toggle": "Вкл/выкл бота",
        "request_approve": "Привязка клиента",
        "request_reject": "Отклонение запроса",
        "settings_import": "Импорт settings.json",
        "user_ban": "Блокировка пользователя",
        "user_unban": "Разблокировка пользователя",
        "stats_db_clear_ovpn": "Очистка БД OpenVPN",
        "stats_db_clear_wg": "Очистка БД WireGuard",
        "app_update": "Обновление приложения",
        "backup_download_vpn": "Скачивание бэкапа VPN",
        "backup_download_statusopenvpn": "Скачивание бэкапа StatusOpenVPN",
        "backup_download_settings": "Скачивание settings.json",
        "backup_restore_statusopenvpn": "Восстановление БД StatusOpenVPN",
        "backup_restore_settings": "Восстановление settings.json",
    }

    return render_template(
        "settings/audit.html",
        logs=logs,
        page=page,
        total_pages=total_pages,
        action_filter=action_filter or "all",
        action_labels=action_labels,
        active_page="settings_audit",
    )


@app.route("/settings/update", methods=["GET", "POST"])
@login_required
def settings_update():
    update_message = None
    update_error = None
    update_available, current_version, latest_version = is_update_available()
    github_error = None
    if not latest_version:
        latest_version, github_error = get_latest_github_version()

    if request.method == "POST":
        if is_update_running():
            update_error = "Обновление уже выполняется."
        elif not update_available or not latest_version:
            update_error = "Нет доступного обновления."
        else:
            ok, err = start_silent_update(latest_version)
            if ok:
                update_message = (
                    "Обновление запущено. Сервис перезапустится автоматически. "
                    "Обновите страницу через несколько минут."
                )
                log_action(
                    "web",
                    current_user.username,
                    current_user.username,
                    "app_update",
                    f"{current_version} → {latest_version}",
                    _get_client_ip(),
                )
            else:
                update_error = err or "Не удалось запустить обновление."

    return render_template(
        "settings/update.html",
        current_version=current_version,
        latest_version=latest_version,
        update_available=update_available,
        update_running=is_update_running(),
        update_log=read_update_log_tail(),
        update_message=update_message,
        update_error=update_error,
        github_error=github_error,
        active_page="settings_update",
    )


@app.route("/api/settings/update/status")
@login_required
def api_settings_update_status():
    update_available, current_version, latest_version = is_update_available()
    return jsonify(
        {
            "update_available": update_available,
            "current_version": current_version,
            "latest_version": latest_version,
            "running": is_update_running(),
            "log": read_update_log_tail(),
        }
    )


@app.route("/settings/install")
@login_required
def settings_install():
    antizapret_pairs, antizapret_error = read_setup_key_value_file(ANTIZAPRET_SETUP_PATH)
    antizapret_rows = [
        (key, value, ANTIZAPRET_SETUP_DESCRIPTIONS.get(key, ""))
        for key, value in antizapret_pairs
    ]
    web_pairs, web_error = read_setup_key_value_file(STATUSOPENVPN_SETUP_PATH)
    web_rows = [
        (key, value, WEB_SETUP_DESCRIPTIONS.get(key, ""))
        for key, value in web_pairs
    ]
    return render_template(
        "settings/install.html",
        antizapret_rows=antizapret_rows,
        antizapret_error=antizapret_error,
        antizapret_path=ANTIZAPRET_SETUP_PATH,
        web_rows=web_rows,
        web_error=web_error,
        web_path=STATUSOPENVPN_SETUP_PATH,
        active_page="settings_install",
    )


@app.route("/settings/install/download")
@login_required
def settings_install_download():
    """Скачивание файла параметров установки Antizapret с сервера."""
    path = ANTIZAPRET_SETUP_PATH
    if not os.path.isfile(path):
        abort(404)
    return send_file(
        path,
        as_attachment=True,
        download_name=os.path.basename(path),
        mimetype="text/plain",
    )


@app.route("/settings/install/download/statusopenvpn")
@login_required
def settings_install_download_statusopenvpn():
    """Скачивание файла параметров установки StatusOpenVPN."""
    path = STATUSOPENVPN_SETUP_PATH
    if not os.path.isfile(path):
        abort(404)
    return send_file(
        path,
        as_attachment=True,
        download_name=os.path.basename(path),
        mimetype="text/plain",
    )


@app.route("/api/admins/add", methods=["POST"])
@login_required
def api_admins_add():
    payload = request.get_json(silent=True) or {}
    telegram_id = str(payload.get("telegram_id", "")).strip()
    if not telegram_id:
        return jsonify({"success": False, "message": "ID не указан."}), 400

    admin_info = read_admin_info()

    env_values = read_env_values()
    admin_id_value = env_values.get("ADMIN_ID", "")
    admin_ids = parse_admin_ids(admin_id_value)
    if telegram_id in admin_ids:
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Администратор уже в списке.",
                    "admins": build_admin_display_list(admin_id_value, admin_info),
                    "available_admins": build_available_admin_candidates(
                        admin_info, admin_ids
                    ),
                    "admin_id_value": admin_id_value,
                    "bot_service_active": get_telegram_bot_status(),
                }
            ),
            400,
        )

    admin_ids.append(telegram_id)
    updated_admin_id_value = format_admin_ids(admin_ids)
    update_env_values({"ADMIN_ID": updated_admin_id_value})

    admin_display_list = build_admin_display_list(updated_admin_id_value, admin_info)
    available_admins = build_available_admin_candidates(admin_info, admin_ids)
    response = {
        "success": True,
        "message": "Администратор добавлен. Нажмите «Сохранить», чтобы применить изменения.",
        "admins": admin_display_list,
        "available_admins": available_admins,
        "admin_id_value": updated_admin_id_value,
        "bot_service_active": get_telegram_bot_status(),
    }
    return jsonify(response), 200


@app.route("/api/admins/remove", methods=["POST"])
@login_required
def api_admins_remove():
    payload = request.get_json(silent=True) or {}
    telegram_id = str(payload.get("telegram_id", "")).strip()
    if not telegram_id:
        return jsonify({"success": False, "message": "ID не указан."}), 400

    admin_info = read_admin_info()
    env_values = read_env_values()
    admin_id_value = env_values.get("ADMIN_ID", "")
    admin_ids = parse_admin_ids(admin_id_value)
    if telegram_id not in admin_ids:
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Администратор не найден в списке.",
                    "admins": build_admin_display_list(admin_id_value, admin_info),
                    "available_admins": build_available_admin_candidates(
                        admin_info, admin_ids
                    ),
                    "admin_id_value": admin_id_value,
                    "bot_service_active": get_telegram_bot_status(),
                }
            ),
            400,
        )

    if len(admin_ids) <= 1:
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Нельзя удалить последнего администратора.",
                    "admins": build_admin_display_list(admin_id_value, admin_info),
                    "available_admins": build_available_admin_candidates(
                        admin_info, admin_ids
                    ),
                    "admin_id_value": admin_id_value,
                    "bot_service_active": get_telegram_bot_status(),
                }
            ),
            400,
        )

    admin_ids = [admin_id for admin_id in admin_ids if admin_id != telegram_id]
    updated_admin_id_value = format_admin_ids(admin_ids)
    update_env_values({"ADMIN_ID": updated_admin_id_value})

    admin_display_list = build_admin_display_list(updated_admin_id_value, admin_info)
    available_admins = build_available_admin_candidates(admin_info, admin_ids)
    response = {
        "success": True,
        "message": "Администратор удалён. Нажмите «Сохранить», чтобы применить изменения.",
        "admins": admin_display_list,
        "available_admins": available_admins,
        "admin_id_value": updated_admin_id_value,
        "bot_service_active": get_telegram_bot_status(),
    }
    return jsonify(response), 200
