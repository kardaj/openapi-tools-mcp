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

    def test_resolve_refs_in_request_body(self):
        body = spec_get(self.spec, "requestBodies", "Pet", spec_path=FIXTURE_PATH)
        schema = body["value"]["content"]["application/json"]["schema"]
        self.assertNotIn("$ref", schema)
        self.assertEqual(schema.get("type"), "object")
        category = schema["properties"]["category"]
        self.assertNotIn("$ref", category)
        self.assertIn("properties", category)
        tag_items = schema["properties"]["tags"]["items"]
        self.assertNotIn("$ref", tag_items)
        self.assertIn("name", tag_items["properties"])

    def test_resolve_refs_in_schema(self):
        pet_schema = spec_get(self.spec, "schemas", "Pet", spec_path=FIXTURE_PATH)
        category = pet_schema["value"]["properties"]["category"]
        self.assertNotIn("$ref", category)
        self.assertIn("properties", category)

    def test_resolve_refs_in_parameter_chain(self):
        param = spec_get(
            self.spec, "parameters", "TraceIdAliasDeep", spec_path=FIXTURE_PATH
        )
        value = param["value"]
        self.assertNotIn("$ref", value)
        self.assertEqual(value.get("name"), "trace-id")
        self.assertEqual(value.get("in"), "header")

    def test_resolve_refs_in_header_chain(self):
        header = spec_get(
            self.spec, "headers", "Rate-Limit-Limit-Deep", spec_path=FIXTURE_PATH
        )
        value = header["value"]
        self.assertNotIn("$ref", value)
        self.assertIn("schema", value)
        self.assertEqual(value["schema"].get("type"), "integer")

    def test_resolve_refs_in_security_scheme_chain(self):
        scheme = spec_get(
            self.spec,
            "securitySchemes",
            "petstore_auth_alias_deep",
            spec_path=FIXTURE_PATH,
        )
        value = scheme["value"]
        self.assertNotIn("$ref", value)
        self.assertEqual(value.get("type"), "oauth2")
        self.assertIn("flows", value)

    def test_resolve_refs_in_links_chain(self):
        link = spec_get(
            self.spec, "links", "FindOrderByIdLinkDeep", spec_path=FIXTURE_PATH
        )
        value = link["value"]
        self.assertNotIn("$ref", value)
        self.assertEqual(value.get("operationId"), "getOrderById")

    def test_resolve_refs_in_callbacks_chain(self):
        callback = spec_get(
            self.spec, "callbacks", "NewPetCallbackDeep", spec_path=FIXTURE_PATH
        )
        value = callback["value"]
        self.assertNotIn("$ref", value)
        self.assertIn("post", next(iter(value.values())))

    def test_resolve_refs_in_examples_chain(self):
        example = spec_get(
            self.spec, "examples", "PetExampleAliasDeep", spec_path=FIXTURE_PATH
        )
        value = example["value"]
        self.assertNotIn("$ref", value)
        self.assertEqual(value.get("summary"), "A pet example")

    def test_spec_get_can_skip_resolving_refs(self):
        result = spec_get(
            self.spec, "paths", "/pet", spec_path=FIXTURE_PATH, resolve_refs=False
        )
        responses = result["value"]["put"]["responses"]
        self.assertIn("$ref", responses["default"])
        self.assertEqual(
            responses["default"]["$ref"], "#/components/responses/GenericError"
        )


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
