import os

db_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "databases")
os.makedirs(db_dir, exist_ok=True)
