import os
import tempfile
from datetime import datetime

from flask import abort, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from src.tg_bot.audit import format_log_details, get_logs, get_logs_count, log_action
from src.ui.services.notification_service import sync_subscription_expiration_logs
from src.tg_bot.config import get_client_allowed_protocols, set_client_allowed_protocols
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
    get_telegram_bot_identity,
    get_telegram_bot_status,
    restart_telegram_bot,
    stop_telegram_bot,
)
from src.ui.services.env_service import (
    read_env_values,
    read_setup_key_value_file,
    update_env_values,
)
from src.ui.services.ovpn_subscription_service import (
    is_subscription_https_ready,
    list_public_link_clients,
    resolve_subscriptions_enabled,
    subscriptions_preference_enabled,
)
from src.ui.services.notification_service import mark_all_current_notifications_read
from src.ui.services.settings_service import (
    get_subscription_link_lifetime_minutes,
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
    set_wireguard_stats_service_enabled,
)
from src.ui.services.update_service import (
    get_release_info,
    is_update_available,
    is_update_running,
    read_update_log_tail,
    render_changelog_html,
    split_changelog_markdown,
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
            previous_settings = read_settings()
            app_name = request.form.get("app_name", "").strip()
            show_ovpn_menu = request.form.get("show_ovpn_menu") == "on"
            show_wg_menu = request.form.get("show_wg_menu") == "on"
            wg_stats_enabled = (
                show_wg_menu and request.form.get("wg_stats_enabled") == "on"
            )
            hide_ovpn_ip = request.form.get("hide_ovpn_ip") == "on"
            group_ovpn_history = request.form.get("group_ovpn_history") == "on"
            hide_wg_ip = request.form.get("hide_wg_ip") == "on"
            shorten_wg_filenames = request.form.get("shorten_wg_filenames") == "on"
            hide_wg_warp_interface = request.form.get("hide_wg_warp_interface") == "on"
            retention_days = parse_stats_retention_days(
                request.form.get("stats_retention_days", "365")
            )
            history_max_records = parse_history_max_records(
                request.form.get("history_max_records", "1000")
            )
            previous_wg_stats_enabled = bool(
                previous_settings.get("wg_stats_enabled", True)
            )
            if wg_stats_enabled != previous_wg_stats_enabled:
                service_ok, service_error = set_wireguard_stats_service_enabled(
                    wg_stats_enabled
                )
                if not service_ok:
                    action = "включить" if wg_stats_enabled else "отключить"
                    settings_error = (
                        f"Не удалось {action} службу wg_stats: {service_error}"
                    )

            if settings_error is None:
                write_settings(
                    {
                        "app_name": app_name,
                        "show_ovpn_menu": show_ovpn_menu,
                        "show_wg_menu": show_wg_menu,
                        "wg_stats_enabled": wg_stats_enabled,
                        "hide_ovpn_ip": hide_ovpn_ip,
                        "group_ovpn_history": group_ovpn_history,
                        "hide_wg_ip": hide_wg_ip,
                        "shorten_wg_filenames": shorten_wg_filenames,
                        "hide_wg_warp_interface": hide_wg_warp_interface,
                        "stats_retention_days": retention_days,
                        "history_max_records": history_max_records,
                    }
                )
                settings_message = "Настройки сохранены."
                if wg_stats_enabled != previous_wg_stats_enabled:
                    log_action(
                        "web",
                        current_user.username,
                        current_user.username,
                        "wg_stats_toggle",
                        "включена" if wg_stats_enabled else "отключена",
                        _get_client_ip(),
                    )

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
    wg_stats_enabled = show_wg_menu and bool(
        settings_data.get("wg_stats_enabled", True)
    )
    hide_ovpn_ip = settings_data.get("hide_ovpn_ip", True)
    group_ovpn_history = bool(settings_data.get("group_ovpn_history", False))
    hide_wg_ip = settings_data.get("hide_wg_ip", True)
    shorten_wg_filenames = bool(settings_data.get("shorten_wg_filenames", False))
    hide_wg_warp_interface = bool(settings_data.get("hide_wg_warp_interface", True))
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
        wg_stats_enabled=wg_stats_enabled,
        hide_ovpn_ip=hide_ovpn_ip,
        group_ovpn_history=group_ovpn_history,
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


@app.route("/settings/links", methods=["GET", "POST"])
@login_required
def settings_links():
    links_message = None
    links_error = None
    if request.method == "POST" and request.form.get("form_type") == "public_links":
        raw_lifetime = (
            request.form.get("subscription_link_lifetime_minutes") or ""
        ).strip()
        if not raw_lifetime:
            raw_lifetime = str(get_subscription_link_lifetime_minutes())
        https_ready = is_subscription_https_ready()
        enabled = resolve_subscriptions_enabled(
            request.form.get("subscriptions_enabled") == "on",
            https_ready,
        )
        if (
            not https_ready
            and request.form.get("subscriptions_enabled") == "on"
            and not subscriptions_preference_enabled()
        ):
            links_error = (
                "Ссылки можно включить только при домене "
                "и действующем HTTPS-сертификате."
            )
        try:
            lifetime = int(raw_lifetime)
        except ValueError:
            links_error = "Укажите срок временной ссылки в минутах."
            lifetime = None
        else:
            if not 1 <= lifetime <= 1440:
                links_error = "Срок временной ссылки должен быть от 1 до 1440 минут."
        if links_error is None:
            write_settings(
                {
                    "subscription_link_lifetime_minutes": lifetime,
                    "subscriptions_enabled": enabled,
                }
            )
            links_message = "Настройки сохранены."
    subscriptions_enabled = subscriptions_preference_enabled()
    return render_template(
        "settings/links.html",
        links_message=links_message,
        links_error=links_error,
        clients=list_public_link_clients() if subscriptions_enabled else [],
        subscription_link_lifetime_minutes=get_subscription_link_lifetime_minutes(),
        subscriptions_enabled=subscriptions_enabled,
        subscription_https_ready=is_subscription_https_ready(),
        active_page="settings_links",
    )


@app.route("/settings/telegram", methods=["GET", "POST"])
@login_required
def settings_telegram():
    bot_message = None
    bot_error = None
    access_message = None
    access_error = None
    selected_protocol_user = None

    protocol_keys = (
        "openvpn_vpn",
        "openvpn_antizapret",
        "openvpn_default",
        "openvpn_tcp",
        "openvpn_udp",
        "wireguard_vpn",
        "wireguard_antizapret",
        "wireguard_wg",
        "wireguard_am",
    )

    if request.method == "POST":
        form_type = request.form.get("form_type")

        if form_type == "bot":
            old_env = read_env_values()
            old_token = old_env.get("BOT_TOKEN", "")
            old_admin_id = old_env.get("ADMIN_ID", "")
            old_settings = read_settings()
            old_bot_enabled = bool(old_settings.get("bot_enabled", False))

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
                        bot_message = "Настройки бота сохранены. API токен бота пустой, бот остановлен."
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

        elif form_type == "client_protocols":
            telegram_id = (request.form.get("telegram_id") or "").strip()
            selected_protocol_user = telegram_id
            mapping = build_client_mapping_list(read_env_values(), read_admin_info())
            if not telegram_id.isdigit() or telegram_id not in {
                item["telegram_id"] for item in mapping
            }:
                access_error = "Привязка пользователя не найдена. Обновите страницу."
            else:
                protocols = {
                    key: request.form.get(key) == "on" for key in protocol_keys
                }
                try:
                    previous = get_client_allowed_protocols(telegram_id)
                    set_client_allowed_protocols(telegram_id, **protocols)
                except OSError:
                    access_error = "Не удалось сохранить доступ к конфигурациям."
                else:
                    changed = [
                        key for key in protocol_keys if previous[key] != protocols[key]
                    ]
                    if changed:
                        log_action(
                            "web",
                            current_user.username,
                            current_user.username,
                            "client_protocols_change",
                            f"Telegram ID {telegram_id}: {', '.join(changed)}",
                            _get_client_ip(),
                        )
                    access_message = "Доступ к конфигурациям сохранён."

    env_values = read_env_values()
    bot_token_value = env_values.get("BOT_TOKEN", "")
    admin_id_value = env_values.get("ADMIN_ID", "")
    settings_data = read_settings()
    admin_info = settings_data.get("telegram_profiles", {})
    admin_display_list = build_admin_display_list(admin_id_value, admin_info)
    available_admins = build_available_admin_candidates(
        admin_info, parse_admin_ids(admin_id_value)
    )
    client_mapping_list = build_client_mapping_list(env_values, admin_info)
    for item in client_mapping_list:
        item["allowed_protocols"] = get_client_allowed_protocols(item["telegram_id"])
    bot_service_active = get_telegram_bot_status()
    bot_identity = get_telegram_bot_identity(bot_token_value)
    bot_enabled = bool(settings_data.get("bot_enabled", False))

    return render_template(
        "settings/telegram.html",
        bot_token=bot_token_value,
        admin_id=admin_id_value,
        admin_display_list=admin_display_list,
        available_admins=available_admins,
        client_mapping_list=client_mapping_list,
        bot_service_active=bot_service_active,
        bot_identity=bot_identity,
        bot_enabled=bot_enabled,
        bot_message=bot_message,
        bot_error=bot_error,
        access_message=access_message,
        access_error=access_error,
        selected_protocol_user=selected_protocol_user,
        active_page="settings_telegram",
    )


@app.route("/settings/access", methods=["GET", "POST"])
@login_required
def settings_access():
    return redirect(url_for("settings_links"))


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
    sync_subscription_expiration_logs()
    mark_all_current_notifications_read(current_user.id)
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
    for row in logs:
        row["details"] = format_log_details(row)

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
        "wg_stats_toggle": "Вкл/выкл статистики WireGuard",
        "request_approve": "Привязка клиента",
        "request_reject": "Отклонение запроса",
        "client_broadcast": "Рассылка клиентам",
        "settings_import": "Импорт settings.json",
        "user_ban": "Блокировка пользователя",
        "user_ban_scheduled": "Планирование блокировки пользователя",
        "user_ban_schedule_cancelled": "Отмена запланированной блокировки",
        "user_unban": "Разблокировка пользователя",
        "peer_disable_scheduled": "Планирование отключения WireGuard",
        "peer_disable_schedule_cancelled": "Отмена отключения WireGuard",
        "stats_db_clear_ovpn": "Очистка БД OpenVPN",
        "stats_db_clear_wg": "Очистка БД WireGuard",
        "app_update": "Обновление приложения",
        "backup_download_vpn": "Скачивание бэкапа VPN",
        "backup_download_statusopenvpn": "Скачивание бэкапа StatusOpenVPN",
        "backup_download_settings": "Скачивание settings.json",
        "backup_restore_statusopenvpn": "Восстановление БД StatusOpenVPN",
        "backup_restore_settings": "Восстановление settings.json",
        "subscription_opened": "Открытие публичной ссылки",
        "subscription_expired": "Истечение публичной ссылки",
        "client_protocols_change": "Изменение доступных конфигураций",
        "client_subscription_rotate": "Новая публичная ссылка",
        "client_subscription_revoke": "Отзыв публичной ссылки",
        "subscription_lifetime_change": "Изменение срока ссылки",
    }
    action_badges = {
        "client_create": ("Создание", "success"),
        "client_delete": ("Удаление", "danger"),
        "files_recreate": ("Пересоздание", "warning"),
        "server_reboot": ("Перезагрузка", "danger"),
        "web_login": ("Вход", "primary"),
        "peer_toggle": ("Клиент WG", "secondary"),
        "bot_toggle": ("Телеграм", "info"),
        "wg_stats_toggle": ("Статистика WG", "info"),
        "request_approve": ("Одобрено", "success"),
        "request_reject": ("Отклонено", "danger"),
        "client_broadcast": ("Рассылка", "info"),
        "stats_db_clear_ovpn": ("Очистка OpenVPN", "warning"),
        "stats_db_clear_wg": ("Очистка WireGuard", "warning"),
        "bot_token_change": ("Токен бота", "secondary"),
        "bot_admins_change": ("Админ Telegram", "primary"),
        "app_update": ("Обновление", "primary"),
        "settings_import": ("Импорт настроек", "info"),
        "wg_client_create": ("Создание WG", "success"),
        "wg_client_delete": ("Удаление WG", "danger"),
        "client_cert_renew": ("Продление сертификата", "warning"),
        "subscription_opened": ("Ссылка открыта", "primary"),
        "subscription_expired": ("Ссылка истекла", "warning"),
        "client_protocols_change": ("Профили", "primary"),
        "client_subscription_rotate": ("Новая ссылка", "primary"),
        "client_subscription_revoke": ("Отзыв ссылки", "warning"),
        "subscription_lifetime_change": ("Срок ссылки", "primary"),
        "user_ban": ("Блокировка", "danger"),
        "user_ban_scheduled": ("Запланировано", "warning"),
        "user_ban_schedule_cancelled": ("Расписание отменено", "secondary"),
        "user_unban": ("Разблокировка", "success"),
        "peer_disable_scheduled": ("Отключение WG запланировано", "warning"),
        "peer_disable_schedule_cancelled": ("Отключение WG отменено", "secondary"),
        "wg_client_rename": ("Переименование", "success"),
        "backup_download_vpn": ("Бэкап VPN", "primary"),
        "backup_download_statusopenvpn": ("Бэкап StatusOpenVPN", "primary"),
        "backup_download_settings": ("Бэкап настроек", "primary"),
        "backup_restore_statusopenvpn": ("Восстановление БД", "warning"),
        "backup_restore_settings": ("Восстановление настроек", "warning"),
    }

    return render_template(
        "settings/audit.html",
        logs=logs,
        page=page,
        total_pages=total_pages,
        action_filter=action_filter or "all",
        action_labels=action_labels,
        action_badges=action_badges,
        active_page="settings_audit",
    )


@app.route("/settings/update", methods=["GET", "POST"])
@login_required
def settings_update():
    update_message = None
    update_error = None
    update_available, current_version, latest_version = is_update_available()
    release_info = get_release_info()
    latest_version = latest_version or release_info.get("latest")
    github_error = release_info.get("error")
    changelog_url = release_info.get("changelog_url")
    changelog_md = release_info.get("changelog_md") or ""
    changes_md, overview_md = split_changelog_markdown(changelog_md)
    changelog_html = render_changelog_html(changes_md or changelog_md)
    changelog_overview_html = render_changelog_html(overview_md) if overview_md else ""
    check_time = release_info.get("at") or 0
    last_check = None
    if check_time:
        last_check = datetime.fromtimestamp(check_time).strftime("%d.%m.%Y %H:%M")
    published_at = None
    published_raw = release_info.get("published_at")
    if published_raw:
        try:
            published_at = datetime.fromisoformat(
                published_raw.replace("Z", "+00:00")
            ).strftime("%d.%m.%Y")
        except ValueError:
            published_at = None

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
        last_check=last_check,
        published_at=published_at,
        changelog_url=changelog_url,
        changelog_html=changelog_html,
        changelog_overview_html=changelog_overview_html,
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
    antizapret_pairs, antizapret_error = read_setup_key_value_file(
        ANTIZAPRET_SETUP_PATH
    )
    antizapret_keys = {key for key, _value in antizapret_pairs}
    antizapret_setup_schema = (
        "current"
        if antizapret_keys & {"WARP_MTU", "DNS_WARP", "WARP_PROTECTION"}
        else "legacy"
    )
    antizapret_rows = [
        (key, value, ANTIZAPRET_SETUP_DESCRIPTIONS.get(key, ""))
        for key, value in antizapret_pairs
    ]
    web_pairs, web_error = read_setup_key_value_file(STATUSOPENVPN_SETUP_PATH)
    web_rows = [
        (key, value, WEB_SETUP_DESCRIPTIONS.get(key, "")) for key, value in web_pairs
    ]
    return render_template(
        "settings/install.html",
        antizapret_rows=antizapret_rows,
        antizapret_error=antizapret_error,
        antizapret_path=ANTIZAPRET_SETUP_PATH,
        antizapret_setup_schema=antizapret_setup_schema,
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
