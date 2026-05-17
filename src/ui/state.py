from collections import defaultdict
from threading import Lock


cached_system_info = None
last_fetch_time = 0
last_db_save = 0
last_collect = 0

cpu_history = []

BOT_RESTART_LOCK = Lock()

client_cache = defaultdict(lambda: {"received": 0, "sent": 0, "timestamp": None})
