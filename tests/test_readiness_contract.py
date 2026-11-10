"""Check probe routes without importing the API or connecting to a database."""

import ast
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


class ReadinessContractTests(unittest.TestCase):
    def setUp(self):
        values = yaml.safe_load((ROOT / "deploy/values.yaml").read_text())
        self.api = values["components"]["api"]
        self.source = ast.parse((ROOT / "backend/app.py").read_text())

    def test_readiness_uses_dedicated_endpoint(self):
        self.assertEqual(self.api["readinessPath"], "/api/readyz")
        self.assertEqual(self.api["healthPath"], "/api/healthz")
        self.assertNotEqual(self.api["readinessPath"], self.api["healthPath"])

    def test_configured_probes_are_registered_get_routes(self):
        routes = set()
        for node in self.source.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and isinstance(decorator.func.value, ast.Name)
                    and decorator.func.value.id == "app"
                    and decorator.func.attr == "get"
                    and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)
                    and isinstance(decorator.args[0].value, str)
                ):
                    routes.add(decorator.args[0].value)
        for key in ("healthPath", "readinessPath"):
            with self.subTest(probe=key):
                self.assertIn(self.api[key], routes)


if __name__ == "__main__":
    unittest.main()
