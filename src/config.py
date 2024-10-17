import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "supersecretkey"
    DATABASE_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "db.db")
class DevelopmentConfig(Config):
    DEBUG = True
class ProductionConfig(Config):
    DEBUG = False
