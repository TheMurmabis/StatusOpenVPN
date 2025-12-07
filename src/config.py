from datetime import timedelta
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "supersecretkey"
    DATABASE_PATH = os.path.join(BASE_DIR, "databases", "db.db")
    LOGS_DATABASE_PATH = os.path.join(BASE_DIR, "databases", "openvpn_logs.db")
    WG_STATS_PATH = os.path.join(BASE_DIR, "databases", "wireguard_stats.db")
    SYSTEM_STATS_PATH = os.path.join(BASE_DIR, "databases", "system_stats.db")
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=5)
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    SESSION_REFRESH_EACH_REQUEST = False

class DevelopmentConfig(Config):
    DEBUG = True
class ProductionConfig(Config):
    DEBUG = False
