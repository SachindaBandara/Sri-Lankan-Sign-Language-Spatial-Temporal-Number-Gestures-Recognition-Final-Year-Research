from functools import wraps

from flask import g, jsonify, session

from extensions import db
from models import User

VALID_ROLES = {"student", "teacher"}


def authenticated_user() -> User | None:
    user_id = session.get("user_id")
    cached_user = getattr(g, "authenticated_user", None)
    if (
        user_id is not None
        and cached_user is not None
        and cached_user.id == user_id
        and cached_user.is_active
        and cached_user.role in VALID_ROLES
    ):
        return cached_user

    user = db.session.get(User, user_id) if user_id else None
    if user is None or not user.is_active or user.role not in VALID_ROLES:
        if user_id:
            session.clear()
        user = None

    g.authenticated_user = user
    return user


def require_student():
    user = authenticated_user()
    if user is None:
        return None, (jsonify({"error": "Authentication required"}), 401)
    if user.role != "student":
        return None, (jsonify({"error": "Student account required"}), 403)
    return user, None


def student_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user, error = require_student()
        if error:
            return error
        return view(*args, **kwargs)

    return wrapped
