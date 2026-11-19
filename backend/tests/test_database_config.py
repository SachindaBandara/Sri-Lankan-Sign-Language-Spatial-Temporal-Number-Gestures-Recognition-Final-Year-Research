import os
import unittest
from unittest.mock import patch

from sqlalchemy.engine import make_url

from app import _database_url_from_fields, create_app


class DatabaseConfigurationTests(unittest.TestCase):
    def test_db_fields_build_mysql_url_and_encode_password(self):
        environment = {
            "DB_HOST": "127.0.0.1",
            "DB_PORT": "3306",
            "DB_NAME": "learning_analytics",
            "DB_USER": "root",
            "DB_PASSWORD": "p@ss:/#word",
        }

        with patch.dict(os.environ, environment, clear=True):
            database_url = make_url(_database_url_from_fields())

        self.assertEqual(database_url.drivername, "mysql+pymysql")
        self.assertEqual(database_url.host, "127.0.0.1")
        self.assertEqual(database_url.port, 3306)
        self.assertEqual(database_url.database, "learning_analytics")
        self.assertEqual(database_url.username, "root")
        self.assertEqual(database_url.password, "p@ss:/#word")
        self.assertEqual(database_url.query["charset"], "utf8mb4")

    def test_production_requires_secure_cookies_redis_rate_limits_and_explicit_origins(self):
        environment = {
            "APP_ENV": "production",
            "SECRET_KEY": "s" * 64,
            "FLASK_DEBUG": "false",
            "SESSION_COOKIE_SECURE": "true",
            "RATELIMIT_STORAGE_URI": "redis://localhost:6379/0",
            "CORS_ORIGINS": "https://app.example",
        }
        cases = (
            ({"SESSION_COOKIE_SECURE": "false"}, "SESSION_COOKIE_SECURE"),
            ({"SESSION_COOKIE_SAMESITE": "None", "SESSION_COOKIE_SECURE": "false"}, "SESSION_COOKIE_SECURE"),
            ({"RATELIMIT_STORAGE_URI": "memory://"}, "RATELIMIT_STORAGE_URI"),
            ({"CORS_ORIGINS": ""}, "CORS_ORIGINS"),
            ({"FLASK_DEBUG": "true"}, "FLASK_DEBUG"),
        )
        for overrides, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                configuration = {**environment, **overrides}
                with patch.dict(os.environ, configuration, clear=True):
                    with self.assertRaisesRegex(RuntimeError, expected_error):
                        create_app({"SQLALCHEMY_DATABASE_URI": "sqlite://"})


if __name__ == "__main__":
    unittest.main()
