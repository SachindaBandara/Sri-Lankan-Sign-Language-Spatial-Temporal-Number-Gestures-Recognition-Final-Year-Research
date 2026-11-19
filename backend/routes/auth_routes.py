import re
import secrets

from flask import Blueprint, jsonify, request, session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db, limiter
from models import LearningSession, User, utcnow
from utils.request_payload import json_object

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,80}$")
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 256
_DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_urlsafe(32), method="scrypt")


def login_rate_limit_key():
    payload = request.get_json(silent=True)
    username = payload.get("username", "") if isinstance(payload, dict) else ""
    identity = username[:80].strip().casefold() if isinstance(username, str) else ""
    return f"{request.remote_addr or 'unknown'}:{identity}"


@auth_bp.post("/register")
@limiter.limit("10 per hour")
def register():
    payload = json_object()
    username = payload.get("username")
    password = payload.get("password")
    grade = payload.get("grade")

    if (
        not isinstance(username, str)
        or len(username) > 80
        or not USERNAME_PATTERN.fullmatch(username.strip())
    ):
        return jsonify({"error": "Username must be 3-80 characters using letters, numbers, '.', '_' or '-'"}), 400
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH or len(password) > MAX_PASSWORD_LENGTH:
        return jsonify({"error": "Password must be between 12 and 256 characters"}), 400
    if grade is not None and (isinstance(grade, bool) or not isinstance(grade, int) or not 1 <= grade <= 13):
        return jsonify({"error": "grade must be an integer from 1 to 13"}), 400

    user = User(username=username.strip(), role="student", grade=grade)
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "That username is already registered"}), 409

    session.clear()
    session["user_id"] = user.id
    session["csrf_token"] = secrets.token_urlsafe(32)
    session.permanent = True
    return jsonify({"user": user.public_data(), "csrf_token": session["csrf_token"]}), 201


@auth_bp.post("/login")
@limiter.limit("5 per minute", key_func=login_rate_limit_key)
@limiter.limit("50 per minute")
def login():
    payload = json_object()
    username = payload.get("username")
    password = payload.get("password")
    if (
        not isinstance(username, str)
        or not isinstance(password, str)
        or not username.strip()
        or len(username) > 80
        or not password
        or len(password) > MAX_PASSWORD_LENGTH
    ):
        return jsonify({"error": "username and password are required"}), 400

    user = db.session.scalar(select(User).where(User.username == username.strip(), User.is_active.is_(True)))
    password_matches = (
        user.check_password(password)
        if user is not None
        else check_password_hash(_DUMMY_PASSWORD_HASH, password)
    )
    if user is None or not password_matches:
        return jsonify({"error": "Invalid username or password"}), 401

    session.clear()
    session["user_id"] = user.id
    session["csrf_token"] = secrets.token_urlsafe(32)
    session.permanent = True
    return jsonify({"user": user.public_data(), "csrf_token": session["csrf_token"]})


@auth_bp.post("/logout")
def logout():
    user_id = session.get("user_id")
    if user_id:
        now = utcnow()
        active_sessions = db.session.scalars(
            select(LearningSession).where(
                LearningSession.student_id == user_id,
                LearningSession.status == "in_progress",
            ).with_for_update()
        ).all()
        for learning_session in active_sessions:
            learning_session.ended_at = now
            learning_session.total_duration_ms = max(
                0, int((now - learning_session.started_at).total_seconds() * 1000)
            )
            learning_session.status = "abandoned"
            for activity in learning_session.activities:
                if activity.status == "in_progress":
                    activity.status = "abandoned"
                    activity.completed_at = now
        db.session.commit()
    session.clear()
    return jsonify({"status": "ok"})


@auth_bp.get("/me")
def current_user():
    user_id = session.get("user_id")
    user = db.session.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        if user_id:
            session.clear()
        csrf_token = session.get("csrf_token")
        if not csrf_token:
            csrf_token = secrets.token_urlsafe(32)
            session["csrf_token"] = csrf_token
        return jsonify({"user": None, "csrf_token": csrf_token})
    csrf_token = session.get("csrf_token")
    if not csrf_token:
        csrf_token = secrets.token_urlsafe(32)
        session["csrf_token"] = csrf_token
    return jsonify({"user": user.public_data(), "csrf_token": csrf_token})
