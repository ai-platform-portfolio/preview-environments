"""Keep the deployment readiness probe aligned with the API route."""

import ast
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


class ReadinessContractTests(unittest.TestCase):
    def test_probe_targets_the_readiness_get_route(self):
        values = yaml.safe_load((ROOT / "deploy/values.yaml").read_text())
        api = values["components"]["api"]
        tree = ast.parse((ROOT / "backend/app.py").read_text())
        readiness_routes = []
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name != "readyz":
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
                ):
                    readiness_routes.append(decorator.args[0].value)

        self.assertEqual(len(readiness_routes), 1, "Expected one readiness GET route")
        self.assertEqual(api["readinessPath"], readiness_routes[0])
        self.assertNotEqual(api["readinessPath"], api["healthPath"],
                            "Readiness must not use the database-independent liveness route")


if __name__ == "__main__":
    unittest.main()
