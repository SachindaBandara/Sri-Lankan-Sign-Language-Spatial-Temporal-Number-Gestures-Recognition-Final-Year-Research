import sys
import unittest

from app import create_app


class PredictionLazyLoadingTests(unittest.TestCase):
    def test_creating_app_does_not_import_inference_engine(self):
        create_app({
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        })

        self.assertNotIn("utils.inference_engine", sys.modules)


if __name__ == "__main__":
    unittest.main()
