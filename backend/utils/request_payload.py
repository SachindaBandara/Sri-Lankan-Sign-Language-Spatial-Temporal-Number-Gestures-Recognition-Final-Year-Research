from flask import request


def json_object() -> dict:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}
