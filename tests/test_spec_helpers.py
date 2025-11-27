import unittest
from pathlib import Path

from openapi_tools_mcp.tools import load_spec, spec_get, spec_list


FIXTURE_PATH = Path(__file__).parent / "openapi.example.yml"


class SpecGetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        loaded = load_spec(FIXTURE_PATH)
        cls.spec = loaded["spec"]

    def test_get_path_details(self):
        result = spec_get(self.spec, "paths", "/pet", spec_path=FIXTURE_PATH)
        self.assertIn("put", result["value"])
        self.assertIsInstance(result["line_start"], int)
        self.assertIsInstance(result["line_end"], int)
        self.assertGreaterEqual(result["line_end"], result["line_start"])

    def test_get_schema_details(self):
        result = spec_get(self.spec, "schemas", "Pet", spec_path=FIXTURE_PATH)
        schema = result["value"]
        self.assertEqual(schema.get("type"), "object")
        self.assertIsInstance(result["line_start"], int)
        self.assertIsInstance(result["line_end"], int)
        self.assertGreaterEqual(result["line_end"], result["line_start"])

    def test_list_responses(self):
        responses = spec_list(self.spec, "responses")
        self.assertIsInstance(responses, list)

    def test_get_security_scheme(self):
        result = spec_get(
            self.spec, "securitySchemes", "api_key", spec_path=FIXTURE_PATH
        )
        scheme = result["value"]
        self.assertEqual(scheme.get("type"), "apiKey")
        self.assertEqual(scheme.get("name"), "api_key")


if __name__ == "__main__":
    unittest.main()
