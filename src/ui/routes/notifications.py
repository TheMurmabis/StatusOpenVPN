from flask import jsonify, request
from flask_login import current_user, login_required

from src.ui.extensions import app
from src.ui.services.notification_service import (
    get_notifications,
    get_read_notification_keys,
    mark_notifications_read,
)


@app.route("/api/notifications", methods=["GET", "POST"])
@login_required
def api_notifications():
    items = get_notifications(limit=20)
    available_keys = {item["key"] for item in items}

    if request.method == "POST":
        payload = request.get_json(silent=True) or request.form
        if payload.get("all") is True or payload.get("all") == "true":
            keys = available_keys
        else:
            raw_keys = payload.get("keys", [])
            if not isinstance(raw_keys, list):
                raw_keys = [raw_keys]
            keys = available_keys.intersection(str(key) for key in raw_keys)
        marked = mark_notifications_read(current_user.id, keys)
        return jsonify({"success": True, "marked": marked})

    read_keys = get_read_notification_keys(
        current_user.id, [item["key"] for item in items]
    )
    for item in items:
        item["read"] = item["key"] in read_keys
    return jsonify(
        {
            "success": True,
            "items": items,
            "unread_count": sum(not item["read"] for item in items),
        }
    )
