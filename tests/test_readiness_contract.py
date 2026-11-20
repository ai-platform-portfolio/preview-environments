"""Check the deployed readiness contract without a running database or API."""
import ast
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


class ReadinessContractTests(unittest.TestCase):
    def setUp(self):
        self.api = yaml.safe_load((ROOT / 'deploy/values.yaml').read_text())['components']['api']
        self.routes = {}
        for node in ast.parse((ROOT / 'backend/app.py').read_text()).body:
            if not isinstance(node, ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                if (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
                        and decorator.func.attr == 'get' and decorator.args
                        and isinstance(decorator.args[0], ast.Constant)):
                    self.routes[decorator.args[0].value] = node

    def test_configured_probes_are_implemented_get_routes(self):
        self.assertIn(self.api['healthPath'], self.routes)
        self.assertIn(self.api['readinessPath'], self.routes)
        self.assertNotEqual(self.api['healthPath'], self.api['readinessPath'])

    def test_readiness_checks_application_database_schema(self):
        readiness = self.routes[self.api['readinessPath']]
        self.assertTrue(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                            and n.func.id == 'connect' for n in ast.walk(readiness)))
        self.assertTrue(any(isinstance(n, ast.Constant) and isinstance(n.value, str)
                            and 'FROM public.messages' in n.value for n in ast.walk(readiness)))

    def test_liveness_does_not_depend_on_database_availability(self):
        liveness = self.routes[self.api['healthPath']]
        self.assertFalse(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                             and n.func.id == 'connect' for n in ast.walk(liveness)))


if __name__ == '__main__':
    unittest.main()
