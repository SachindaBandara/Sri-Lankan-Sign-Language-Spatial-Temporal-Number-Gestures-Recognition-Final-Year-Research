import unittest

from app import create_app


class MigrationHistoryTests(unittest.TestCase):
    def test_migrations_upgrade_to_head_without_model_schema_drift(self):
        app = create_app({
            "TESTING": True,
            "SECRET_KEY": "migration-test-secret",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        })
        runner = app.test_cli_runner()

        upgrade = runner.invoke(args=["db", "upgrade"])
        self.assertEqual(upgrade.exit_code, 0, upgrade.output)

        downgrade = runner.invoke(args=["db", "downgrade", "base"])
        self.assertEqual(downgrade.exit_code, 0, downgrade.output)

        upgrade_again = runner.invoke(args=["db", "upgrade"])
        self.assertEqual(upgrade_again.exit_code, 0, upgrade_again.output)

        schema_check = runner.invoke(args=["db", "check"])
        self.assertEqual(schema_check.exit_code, 0, schema_check.output)
