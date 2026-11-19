import os
import secrets
from datetime import timedelta
from pathlib import Path

import click
from dotenv import dotenv_values, load_dotenv
from flask import Flask, g, jsonify, request, session
from flask_cors import CORS
from sqlalchemy.engine import URL
from werkzeug.exceptions import RequestEntityTooLarge

from extensions import db, limiter, migrate
from models import User
from routes.auth_routes import auth_bp
from routes.activity_routes import activity_bp
from routes.learning_routes import learning_bp
from routes.personalized_learning_routes import personalized_learning_bp
from routes.prediction_routes import prediction_bp
from security import authenticated_user


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_BACKEND_ENV = Path(__file__).resolve().with_name(".env")
_PROCESS_ENV = dict(os.environ)
_ROOT_ENV_SETTINGS = dotenv_values(_PROJECT_ROOT / ".env")
_BACKEND_ENV_SETTINGS = dotenv_values(_BACKEND_ENV)
_ROOT_DATABASE_KEYS = ("DATABASE_URL", "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")
_ROOT_HAS_DATABASE_SETTINGS = any(
    _ROOT_ENV_SETTINGS.get(key) is not None for key in _ROOT_DATABASE_KEYS
)
load_dotenv(_PROJECT_ROOT / ".env", override=False)
if _ROOT_HAS_DATABASE_SETTINGS:
    for key, value in _ROOT_ENV_SETTINGS.items():
        if value is not None and _PROCESS_ENV.get(key) == _BACKEND_ENV_SETTINGS.get(key):
            os.environ[key] = value
    if (
        _ROOT_ENV_SETTINGS.get("DATABASE_URL") is None
        and _PROCESS_ENV.get("DATABASE_URL") == _BACKEND_ENV_SETTINGS.get("DATABASE_URL")
    ):
        os.environ.pop("DATABASE_URL", None)
else:
    load_dotenv(_BACKEND_ENV, override=False)


def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith("mysql://"):
        return database_url.replace("mysql://", "mysql+pymysql://", 1)
    return database_url


def _database_url_from_fields() -> str:
    required_keys = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER")
    missing_keys = [key for key in required_keys if not os.environ.get(key)]
    if missing_keys:
        raise RuntimeError(f"Set the following MySQL settings: {', '.join(missing_keys)}.")

    try:
        port = int(os.environ["DB_PORT"])
    except ValueError as error:
        raise RuntimeError("DB_PORT must be an integer.") from error

    return URL.create(
        drivername="mysql+pymysql",
        username=os.environ["DB_USER"],
        password=os.environ.get("DB_PASSWORD", ""),
        host=os.environ["DB_HOST"],
        port=port,
        database=os.environ["DB_NAME"],
        query={"charset": "utf8mb4"},
    ).render_as_string(hide_password=False)


def _database_url_from_environment() -> str | None:
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return _normalize_database_url(database_url)

    if any(key in os.environ for key in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")):
        return _database_url_from_fields()
    return None


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
    app.config["APP_ENV"] = os.environ.get("APP_ENV", "development").lower()
    app.config["FLASK_DEBUG"] = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
    database_url = _database_url_from_environment()
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax").strip().capitalize()
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "").lower() in {"1", "true", "yes"}
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=12)
    app.config["RATELIMIT_STORAGE_URI"] = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    app.config["RATELIMIT_HEADERS_ENABLED"] = True
    app.config["PERSONALIZATION_MIN_ATTEMPTS"] = int(
        os.environ.get("PERSONALIZATION_MIN_ATTEMPTS", "8")
    )
    app.config["PERSONALIZATION_RECENT_WINDOW"] = int(
        os.environ.get("PERSONALIZATION_RECENT_WINDOW", "10")
    )
    app.config["PERSONALIZATION_PROMOTION_ACCURACY"] = float(
        os.environ.get("PERSONALIZATION_PROMOTION_ACCURACY", "0.85")
    )
    app.config["PERSONALIZATION_PROMOTION_HISTORY_ACCURACY"] = float(
        os.environ.get("PERSONALIZATION_PROMOTION_HISTORY_ACCURACY", "0.75")
    )
    app.config["PERSONALIZATION_PROMOTION_STREAK"] = int(
        os.environ.get("PERSONALIZATION_PROMOTION_STREAK", "5")
    )
    app.config["PERSONALIZATION_DEMOTION_ACCURACY"] = float(
        os.environ.get("PERSONALIZATION_DEMOTION_ACCURACY", "0.60")
    )
    app.config["PERSONALIZATION_DEMOTION_HISTORY_ACCURACY"] = float(
        os.environ.get("PERSONALIZATION_DEMOTION_HISTORY_ACCURACY", "0.70")
    )
    app.config["PERSONALIZATION_DEMOTION_STREAK"] = int(
        os.environ.get("PERSONALIZATION_DEMOTION_STREAK", "3")
    )
    app.config["PERSONALIZATION_WEAK_TREND_DECLINE"] = float(
        os.environ.get("PERSONALIZATION_WEAK_TREND_DECLINE", "0.15")
    )
    app.config["PERSONALIZATION_WEAK_HINT_RATE"] = float(
        os.environ.get("PERSONALIZATION_WEAK_HINT_RATE", "0.5")
    )
    app.config["PERSONALIZATION_WEAK_SKIP_RATE"] = float(
        os.environ.get("PERSONALIZATION_WEAK_SKIP_RATE", "0.25")
    )
    if any(
        app.config[key] < 1
        for key in (
            "PERSONALIZATION_MIN_ATTEMPTS",
            "PERSONALIZATION_RECENT_WINDOW",
            "PERSONALIZATION_PROMOTION_STREAK",
            "PERSONALIZATION_DEMOTION_STREAK",
        )
    ):
        raise RuntimeError("Personalization attempt counts and streaks must be positive integers.")
    if any(
        not 0 <= app.config[key] <= 1
        for key in (
            "PERSONALIZATION_PROMOTION_ACCURACY",
            "PERSONALIZATION_PROMOTION_HISTORY_ACCURACY",
            "PERSONALIZATION_DEMOTION_ACCURACY",
            "PERSONALIZATION_DEMOTION_HISTORY_ACCURACY",
            "PERSONALIZATION_WEAK_TREND_DECLINE",
            "PERSONALIZATION_WEAK_HINT_RATE",
            "PERSONALIZATION_WEAK_SKIP_RATE",
        )
    ):
        raise RuntimeError(
            "Personalization accuracy and weak-signal thresholds must be between 0 and 1."
        )
    if test_config:
        app.config.update(test_config)
    if app.config["SESSION_COOKIE_SAMESITE"] not in {"Lax", "Strict", "None"}:
        raise RuntimeError("SESSION_COOKIE_SAMESITE must be Lax, Strict, or None.")
    if app.config["SESSION_COOKIE_SAMESITE"] == "None" and not app.config["SESSION_COOKIE_SECURE"]:
        raise RuntimeError("SESSION_COOKIE_SECURE=true is required when SESSION_COOKIE_SAMESITE=None.")
    if not app.config.get("TESTING"):
        if not app.config.get("SECRET_KEY") or len(app.config["SECRET_KEY"]) < 32:
            raise RuntimeError("Set SECRET_KEY to a unique random value of at least 32 characters.")
        if not app.config.get("SQLALCHEMY_DATABASE_URI"):
            raise RuntimeError(
                "Set either DATABASE_URL or DB_HOST, DB_PORT, DB_NAME, and DB_USER "
                "before starting the backend."
            )
        if app.config["APP_ENV"] == "production":
            if app.config["FLASK_DEBUG"]:
                raise RuntimeError("Disable FLASK_DEBUG when APP_ENV=production.")
            if not app.config["SESSION_COOKIE_SECURE"]:
                raise RuntimeError("Set SESSION_COOKIE_SECURE=true when APP_ENV=production.")
            if app.config["RATELIMIT_STORAGE_URI"].startswith("memory://"):
                raise RuntimeError(
                    "Configure a shared RATELIMIT_STORAGE_URI (such as Redis) when APP_ENV=production."
                )
            if not os.environ.get("CORS_ORIGINS"):
                raise RuntimeError("Set CORS_ORIGINS to the exact frontend origin(s) when APP_ENV=production.")

    cors_origins = [
        origin.strip()
        for origin in os.environ.get(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ]
    if "*" in cors_origins:
        raise RuntimeError("CORS_ORIGINS must list explicit browser origins; wildcard origins are not allowed.")
    CORS(app, supports_credentials=True, resources={r"/*": {"origins": cors_origins}})

    db.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)

    @app.before_request
    def require_authenticated_account():
        if request.method == "OPTIONS" or request.endpoint is None:
            return None
        if request.endpoint in {"health", "static", "auth.login", "auth.register", "auth.current_user"}:
            return None
        user = authenticated_user()
        if user is None:
            return jsonify({"error": "Authentication required"}), 401
        g.current_user = user
        return None

    @app.before_request
    def protect_cookie_authenticated_requests():
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"} or request.endpoint is None:
            return None
        expected = session.get("csrf_token")
        supplied = request.headers.get("X-CSRF-Token", "")
        if not expected or not secrets.compare_digest(expected, supplied):
            return jsonify({"error": "CSRF token is missing or invalid"}), 403
        return None

    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.endpoint not in {"health", "static", None}:
            response.headers["Cache-Control"] = "no-store"
        return response

    app.register_blueprint(prediction_bp)
    app.register_blueprint(activity_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(learning_bp)
    app.register_blueprint(personalized_learning_bp)

    @app.cli.command("create-teacher")
    @click.argument("username")
    def create_teacher(username):
        if User.query.filter_by(username=username).first():
            raise click.ClickException("That username already exists.")
        password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
        if len(password) < 12:
            raise click.ClickException("Teacher passwords must be at least 12 characters.")
        teacher = User(username=username, role="teacher")
        teacher.set_password(password)
        db.session.add(teacher)
        db.session.commit()
        click.echo(f"Teacher account '{username}' created.")

    @app.cli.command("assign-student")
    @click.argument("teacher_username")
    @click.argument("student_username")
    def assign_student(teacher_username, student_username):
        teacher = User.query.filter_by(username=teacher_username, role="teacher").first()
        student = User.query.filter_by(username=student_username, role="student").first()
        if teacher is None or student is None:
            raise click.ClickException("A valid teacher and student username are required.")
        if student not in teacher.students:
            teacher.students.append(student)
            db.session.commit()
        click.echo(f"Assigned '{student_username}' to '{teacher_username}'.")

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.errorhandler(RequestEntityTooLarge)
    def handle_request_too_large(_error):
        return jsonify({"error": "Request payload exceeds the 32 MB limit"}), 413

    @app.errorhandler(429)
    def handle_rate_limit(_error):
        return jsonify({"error": "Too many authentication attempts. Try again later."}), 429

    @app.errorhandler(500)
    def handle_internal_error(_error):
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred"}), 500

    return app
