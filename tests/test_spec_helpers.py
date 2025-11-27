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

    def test_resolve_response_refs_in_paths(self):
        result = spec_get(self.spec, "paths", "/pet", spec_path=FIXTURE_PATH)
        put_responses = result["value"]["put"]["responses"]
        self.assertNotIn("$ref", put_responses["404"])
        self.assertEqual(put_responses["404"]["description"], "Pet not found")
        self.assertNotIn("$ref", put_responses["default"])
        self.assertEqual(put_responses["default"]["description"], "Pet not found")

    def test_resolve_response_refs_in_components(self):
        response = spec_get(
            self.spec, "responses", "GenericError", spec_path=FIXTURE_PATH
        )
        value = response["value"]
        self.assertIsInstance(value, dict)
        self.assertNotIn("$ref", value)
        self.assertEqual(value.get("description"), "Pet not found")


class SpecListFilteringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        loaded = load_spec(FIXTURE_PATH)
        cls.spec = loaded["spec"]

    def test_list_tags_section(self):
        tags = spec_list(self.spec, "tags")
        self.assertIn("pet", tags)
        self.assertIn("store", tags)
        self.assertIn("beta", tags)

    def test_filter_paths_by_glob(self):
        store_paths = spec_list(self.spec, "paths", filter_by_glob="/store/*")
        self.assertTrue(store_paths)
        self.assertTrue(all(item["path"].startswith("/store/") for item in store_paths))

    def test_filter_paths_by_tag(self):
        store_paths = spec_list(self.spec, "paths", filter_by_tag="store")
        path_names = {item["path"] for item in store_paths}
        self.assertIn("/store/inventory", path_names)
        self.assertNotIn("/pet", path_names)

    def test_filter_schemas_by_tag(self):
        store_schemas = spec_list(self.spec, "schemas", filter_by_tag="store")
        self.assertIn("Order", store_schemas)
        self.assertNotIn("Pet", store_schemas)
        pet_schemas = spec_list(self.spec, "schemas", filter_by_tag=["pet"])
        self.assertIn("Pet", pet_schemas)


if __name__ == "__main__":
    unittest.main()
