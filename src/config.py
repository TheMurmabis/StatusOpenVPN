from datetime import timedelta
import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "supersecretkey"
    DATABASE_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "db.db")
    LOGS_DATABASE_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "openvpn_logs.db")
    WG_STATS_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "wireguard_stats.db")
    PERMANENT_SESSION_LIFETIME=timedelta(days=30)
class DevelopmentConfig(Config):
    DEBUG = True
class ProductionConfig(Config):
    DEBUG = False
