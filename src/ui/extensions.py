import os

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    request,
    url_for as flask_url_for,
)
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_wtf.csrf import CSRFError, CSRFProtect

from src.config import Config
from src.ui.middleware import ScriptNameMiddleware


app = Flask(
    __name__,
    template_folder="../../templates",
    static_folder="../../static",
)
app.config.from_object(Config)

app.wsgi_app = ScriptNameMiddleware(app.wsgi_app)

bcrypt = Bcrypt(app)
loginManager = LoginManager(app)
loginManager.login_view = "login"
loginManager.login_message = "Для доступа к этой странице необходимо войти."
loginManager.login_message_category = "warning"
csrf = CSRFProtect(app)


def _request_retry_url():
    """Return the current request path including an nginx URL prefix."""
    script_root = request.script_root.rstrip("/")
    request_path = request.full_path.rstrip("?")
    return f"{script_root}{request_path}"


@app.errorhandler(CSRFError)
def _handle_csrf_error(error):
    message = "Сессия формы устарела. Обновите страницу и повторите действие."
    if request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json":
        return jsonify({"success": False, "error": "csrf_failed", "message": message}), 400

    if request.endpoint != "login":
        flash(message, "danger")
        retry_url = _request_retry_url() or flask_url_for("home")
        return redirect(retry_url, code=303)

    flash("Форма входа устарела. Введите данные ещё раз.", "warning")
    return redirect(flask_url_for("login"), code=303)


@app.context_processor
def _static_cache_bust():
    def url_for(endpoint, **values):
        if endpoint == "static":
            filename = values.get("filename")
            if filename and app.static_folder:
                file_path = os.path.join(app.static_folder, filename)
                try:
                    values["v"] = int(os.path.getmtime(file_path))
                except OSError:
                    pass
        return flask_url_for(endpoint, **values)

    return {"url_for": url_for}


@app.after_request
def _html_no_store(response):
    content_type = response.content_type or ""
    if content_type.startswith("text/html"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response
