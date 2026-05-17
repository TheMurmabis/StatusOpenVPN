import socket

from flask import render_template, request
from flask_login import login_required

from src.ui.constants import HOST_STATIC_INFO
from src.ui.extensions import app
from src.ui.services.settings_service import read_settings
from src.ui.services.system_info_service import get_git_version, get_system_info
from src.ui.utils.network_utils import get_external_ip


@app.context_processor
def inject_info():
    settings_data = read_settings()
    app_name = settings_data.get("app_name", "StatusOpenVPN")
    show_ovpn_menu = bool(settings_data.get("show_ovpn_menu", True))
    show_wg_menu = bool(settings_data.get("show_wg_menu", True))
    return {
        "hostname": socket.gethostname(),
        "server_ip": get_external_ip(),
        "version": get_git_version(),
        "base_path": request.script_root or "",
        "app_name": app_name,
        "show_ovpn_menu": show_ovpn_menu,
        "show_wg_menu": show_wg_menu,
        "host_os_label": HOST_STATIC_INFO["os_label"],
    }


@app.route("/")
@login_required
def home():
    server_ip = get_external_ip()
    system_info = get_system_info() or {**HOST_STATIC_INFO}
    hostname = socket.gethostname()

    return render_template(
        "index.html",
        server_ip=server_ip,
        system_info=system_info,
        hostname=hostname,
        active_page="home",
    )
