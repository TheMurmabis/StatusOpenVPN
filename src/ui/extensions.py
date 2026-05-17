from flask import Flask
from flask_bcrypt import Bcrypt
from flask_login import LoginManager

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
