import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

from openapi_tools_mcp import server as mcp_server
from openapi_tools_mcp.tools import (
    URL_CACHE_TTL_SECONDS,
    _URL_SPEC_CACHE,
    _UrlHttpError,
    _UrlNetworkError,
    load_spec,
    load_spec_source,
    spec_get,
    spec_info,
    spec_list,
    validate_example_spec,
)

FIXTURE_PATH = Path(__file__).parent / "openapi.example.yml"


def _minimal_spec_text(title="Remote"):
    return f"""openapi: 3.0.0
info:
  title: {title}
  version: 1.0.0
paths:
  /pets:
    get:
      tags:
        - pet
      responses:
        "200":
          description: OK
components:
  schemas:
    Pet:
      type: object
"""


def _minimal_json_spec_text(title="Remote JSON"):
    return (
        '{"openapi":"3.0.0","info":{"title":"'
        + title
        + '","version":"1.0.0"},"paths":{"/pets":{"get":{"responses":{"200":{"description":"OK"}}}}}}'
    )


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

    def test_spec_info_smoke(self):
        info = spec_info(self.spec)
        self.assertIn("openapi", info)
        self.assertIn("info", info)
        self.assertIn("servers", info)


class SpecSourceTests(unittest.TestCase):
    def setUp(self):
        _URL_SPEC_CACHE.clear()

    def test_load_spec_source_keeps_local_path_behavior(self):
        loaded = load_spec_source(str(FIXTURE_PATH))
        self.assertEqual(
            loaded["spec"]["info"]["title"], "Swagger Petstore - OpenAPI 3.0"
        )
        self.assertEqual(loaded["source_path"], FIXTURE_PATH.resolve())

    def test_load_spec_source_downloads_yaml_url_and_caches(self):
        source = {
            "url": "https://example.test/openapi.yaml",
            "headers": {"Authorization": "Bearer token"},
        }
        with patch(
            "openapi_tools_mcp.tools._fetch_url", return_value=_minimal_spec_text()
        ) as fetch_stub:
            first = load_spec_source(source)
            second = load_spec_source(source)

        self.assertEqual(first["spec"]["info"]["title"], "Remote")
        self.assertIs(first, second)
        fetch_stub.assert_called_once_with(
            "https://example.test/openapi.yaml", {"Authorization": "Bearer token"}
        )

    def test_load_spec_source_downloads_json_url(self):
        with patch(
            "openapi_tools_mcp.tools._fetch_url",
            return_value=_minimal_json_spec_text(),
        ):
            loaded = load_spec_source({"url": "https://example.test/openapi.json"})

        self.assertEqual(loaded["spec"]["info"]["title"], "Remote JSON")
        self.assertIn("/pets", spec_list(loaded["spec"], "paths")[0]["path"])

    def test_url_cache_key_ignores_header_insertion_order(self):
        with patch(
            "openapi_tools_mcp.tools._fetch_url", return_value=_minimal_spec_text()
        ) as fetch_stub:
            load_spec_source(
                {
                    "url": "https://example.test/openapi.yaml",
                    "headers": {"Accept": "application/yaml", "Authorization": "token"},
                }
            )
            load_spec_source(
                {
                    "url": "https://example.test/openapi.yaml",
                    "headers": {"Authorization": "token", "Accept": "application/yaml"},
                }
            )

        fetch_stub.assert_called_once()

    def test_url_cache_separates_different_headers(self):
        with patch(
            "openapi_tools_mcp.tools._fetch_url",
            side_effect=[_minimal_spec_text("One"), _minimal_spec_text("Two")],
        ) as fetch_stub:
            one = load_spec_source(
                {
                    "url": "https://example.test/openapi.yaml",
                    "headers": {"X-Tenant": "1"},
                }
            )
            two = load_spec_source(
                {
                    "url": "https://example.test/openapi.yaml",
                    "headers": {"X-Tenant": "2"},
                }
            )

        self.assertEqual(one["spec"]["info"]["title"], "One")
        self.assertEqual(two["spec"]["info"]["title"], "Two")
        self.assertEqual(fetch_stub.call_count, 2)

    def test_expired_url_cache_refreshes_successfully(self):
        with (
            patch(
                "openapi_tools_mcp.tools._fetch_url",
                side_effect=[_minimal_spec_text("Old"), _minimal_spec_text("New")],
            ),
            patch(
                "openapi_tools_mcp.tools._monotonic",
                side_effect=[0.0, URL_CACHE_TTL_SECONDS + 1.0],
            ),
        ):
            old = load_spec_source({"url": "https://example.test/openapi.yaml"})
            new = load_spec_source({"url": "https://example.test/openapi.yaml"})

        self.assertEqual(old["spec"]["info"]["title"], "Old")
        self.assertEqual(new["spec"]["info"]["title"], "New")

    def test_expired_url_cache_uses_stale_on_network_error(self):
        with (
            patch(
                "openapi_tools_mcp.tools._fetch_url",
                side_effect=[_minimal_spec_text("Old"), _UrlNetworkError("timed out")],
            ),
            patch(
                "openapi_tools_mcp.tools._monotonic",
                side_effect=[0.0, URL_CACHE_TTL_SECONDS + 1.0],
            ),
        ):
            old = load_spec_source({"url": "https://example.test/openapi.yaml"})
            stale = load_spec_source({"url": "https://example.test/openapi.yaml"})

        self.assertIs(stale, old)
        self.assertEqual(stale["spec"]["info"]["title"], "Old")

    def test_expired_url_cache_uses_stale_on_5xx(self):
        with (
            patch(
                "openapi_tools_mcp.tools._fetch_url",
                side_effect=[
                    _minimal_spec_text("Old"),
                    _UrlHttpError(503, "Service Unavailable"),
                ],
            ),
            patch(
                "openapi_tools_mcp.tools._monotonic",
                side_effect=[0.0, URL_CACHE_TTL_SECONDS + 1.0],
            ),
        ):
            old = load_spec_source({"url": "https://example.test/openapi.yaml"})
            stale = load_spec_source({"url": "https://example.test/openapi.yaml"})

        self.assertIs(stale, old)
        self.assertEqual(stale["spec"]["info"]["title"], "Old")

    def test_expired_url_cache_does_not_use_stale_on_4xx(self):
        with (
            patch(
                "openapi_tools_mcp.tools._fetch_url",
                side_effect=[
                    _minimal_spec_text("Old"),
                    _UrlHttpError(404, "Not Found"),
                ],
            ),
            patch(
                "openapi_tools_mcp.tools._monotonic",
                side_effect=[0.0, URL_CACHE_TTL_SECONDS + 1.0],
            ),
        ):
            load_spec_source({"url": "https://example.test/openapi.yaml"})
            with self.assertRaisesRegex(ValueError, "HTTP 404"):
                load_spec_source({"url": "https://example.test/openapi.yaml"})

    def test_initial_url_failures_are_not_cached(self):
        for failure in [
            _UrlNetworkError("timed out"),
            _UrlHttpError(404, "Not Found"),
            _UrlHttpError(503, "Service Unavailable"),
        ]:
            with self.subTest(failure=failure):
                _URL_SPEC_CACHE.clear()
                with patch("openapi_tools_mcp.tools._fetch_url", side_effect=failure):
                    with self.assertRaises(ValueError):
                        load_spec_source({"url": "https://example.test/openapi.yaml"})
                self.assertFalse(_URL_SPEC_CACHE)

    def test_url_source_validation_errors_are_clear(self):
        cases = [
            ({}, "url"),
            ({"url": "ftp://example.test/openapi.yaml"}, "Unsupported URL scheme"),
            ({"url": "https://example.test/openapi.yaml", "headers": []}, "headers"),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                with self.assertRaisesRegex(ValueError, expected):
                    load_spec_source(source)

    def test_spec_get_line_span_from_url_source_text(self):
        source_text = _minimal_spec_text()
        with patch("openapi_tools_mcp.tools._fetch_url", return_value=source_text):
            loaded = load_spec_source({"url": "https://example.test/openapi.yaml"})

        result = spec_get(
            loaded["spec"],
            "schemas",
            "Pet",
            source_text=loaded["source_text"],
        )

        self.assertEqual(result["value"], {"type": "object"})
        self.assertIsInstance(result["line_start"], int)
        self.assertIsInstance(result["line_end"], int)


class McpToolSourceTests(unittest.TestCase):
    def setUp(self):
        _URL_SPEC_CACHE.clear()

    def test_mcp_tools_keep_local_path_behavior(self):
        info = mcp_server.spec_info.fn(str(FIXTURE_PATH))

        self.assertEqual(info["info"]["title"], "Swagger Petstore - OpenAPI 3.0")

    def test_mcp_tools_accept_url_source_object(self):
        source = {"url": "https://example.test/openapi.yaml"}
        with patch(
            "openapi_tools_mcp.tools._fetch_url", return_value=_minimal_spec_text()
        ) as fetch_stub:
            info = mcp_server.spec_info.fn(source)
            paths = mcp_server.spec_list.fn("paths", source)
            schema = mcp_server.spec_get.fn("schemas", "Pet", source)

        self.assertEqual(info["info"]["title"], "Remote")
        self.assertEqual(paths, [{"path": "/pets", "verbs": ["get"]}])
        self.assertEqual(schema["value"], {"type": "object"})
        self.assertIsInstance(schema["line_start"], int)
        fetch_stub.assert_called_once_with("https://example.test/openapi.yaml", {})


class McpToolDocumentationTests(unittest.TestCase):
    def test_mcp_tool_metadata_documents_url_sources(self):
        for tool in [
            mcp_server.spec_info,
            mcp_server.spec_list,
            mcp_server.spec_get,
        ]:
            with self.subTest(tool=tool.name):
                description = tool.description
                spec_path_schema = tool.parameters["properties"]["spec_path"]

                self.assertIn("local path string or URL source object", description)
                self.assertIn('"url"', description)
                self.assertIn("headers are optional", description)
                self.assertIn("cached in memory for 15 minutes", description)
                self.assertIn("stale fallback", description)
                self.assertEqual(
                    spec_path_schema,
                    {
                        "anyOf": [
                            {"type": "string"},
                            {"additionalProperties": True, "type": "object"},
                        ]
                    },
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

    def test_filter_schemas_by_x_tags(self):
        spec = {
            "components": {
                "schemas": {
                    "Widget": {"type": "object", "x-tags": ["alpha"]},
                    "Gadget": {"type": "object", "tags": ["beta"]},
                }
            }
        }
        alpha_schemas = spec_list(spec, "schemas", filter_by_tag="alpha")
        beta_schemas = spec_list(spec, "schemas", filter_by_tag="beta")
        self.assertEqual(alpha_schemas, ["Widget"])
        self.assertEqual(beta_schemas, ["Gadget"])

    def test_filter_paths_skips_non_dict_operations(self):
        spec = {
            "paths": {
                "/widgets": {
                    "get": {"tags": ["store"], "responses": {}},
                    "summary": "not an operation",
                }
            }
        }
        store_paths = spec_list(spec, "paths", filter_by_tag=["", "store"])
        self.assertEqual(
            store_paths, [{"path": "/widgets", "verbs": ["get", "summary"]}]
        )

    def test_filter_paths_skips_non_dict_operations_first(self):
        spec = {
            "paths": {
                "/widgets": {
                    "summary": "not an operation",
                    "get": {"tags": ["store"], "responses": {}},
                }
            }
        }
        store_paths = spec_list(spec, "paths", filter_by_tag="store")
        self.assertEqual(
            store_paths, [{"path": "/widgets", "verbs": ["summary", "get"]}]
        )

    def test_filter_by_glob_empty_pattern(self):
        tags = spec_list(self.spec, "tags", filter_by_glob="")
        self.assertIn("pet", tags)

    def test_list_other_sections(self):
        self.assertTrue(spec_list(self.spec, "parameters"))
        self.assertTrue(spec_list(self.spec, "requestBodies"))
        self.assertTrue(spec_list(self.spec, "headers"))
        self.assertTrue(spec_list(self.spec, "securitySchemes"))
        self.assertTrue(spec_list(self.spec, "links"))
        self.assertTrue(spec_list(self.spec, "callbacks"))
        self.assertTrue(spec_list(self.spec, "examples"))

    def test_list_tags_skips_non_dict_items(self):
        spec = {
            "paths": {
                "/widgets": [
                    "not a dict",
                ],
                "/gizmos": {
                    "get": ["not a dict"],
                    "post": {"tags": ["store"]},
                },
            }
        }
        tags = spec_list(spec, "tags")
        self.assertEqual(tags, ["store"])

    def test_list_schemas_without_tag_filter(self):
        schemas = spec_list(self.spec, "schemas")
        self.assertIn("Pet", schemas)


class SpecGetErrorsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        loaded = load_spec(FIXTURE_PATH)
        cls.spec = loaded["spec"]

    def test_spec_list_unsupported_section(self):
        with self.assertRaises(ValueError):
            spec_list(self.spec, "nope")

    def test_spec_get_unsupported_section(self):
        with self.assertRaises(ValueError):
            spec_get(self.spec, "nope", "thing")

    def test_spec_get_missing_items_raise_key_error(self):
        missing = [
            ("paths", "/nope"),
            ("schemas", "Nope"),
            ("parameters", "Nope"),
            ("responses", "Nope"),
            ("requestBodies", "Nope"),
            ("headers", "Nope"),
            ("securitySchemes", "Nope"),
            ("links", "Nope"),
            ("callbacks", "Nope"),
            ("examples", "Nope"),
        ]
        for section, name in missing:
            with self.subTest(section=section):
                with self.assertRaises(KeyError):
                    spec_get(self.spec, section, name)


class SpecGetRefErrorTests(unittest.TestCase):
    def test_spec_get_rejects_non_local_ref(self):
        spec = {
            "components": {
                "schemas": {"Widget": {"$ref": "http://example.com/spec.yml#/Widget"}}
            }
        }
        with self.assertRaises(ValueError):
            spec_get(spec, "schemas", "Widget")

    def test_spec_get_missing_ref_path(self):
        spec = {
            "components": {"schemas": {"Widget": {"$ref": "#/components/schemas/Nope"}}}
        }
        with self.assertRaises(KeyError):
            spec_get(spec, "schemas", "Widget")

    def test_spec_get_detects_circular_ref(self):
        spec = {
            "components": {
                "schemas": {
                    "A": {"$ref": "#/components/schemas/B"},
                    "B": {"$ref": "#/components/schemas/A"},
                }
            }
        }
        with self.assertRaises(ValueError):
            spec_get(spec, "schemas", "A")

    def test_spec_get_keeps_non_string_nested_ref(self):
        spec = {
            "components": {
                "schemas": {
                    "A": {"$ref": "#/components/schemas/B"},
                    "B": {"$ref": {"bad": "value"}},
                }
            }
        }
        value = spec_get(spec, "schemas", "A")["value"]
        self.assertEqual(value, {"$ref": {"bad": "value"}})


class SpecGetLineSpanTests(unittest.TestCase):
    def test_spec_get_line_span_missing_path(self):
        spec = {"paths": {"/pets": {"get": {"responses": {}}}}}
        with TemporaryDirectory() as tmpdir:
            spec_path = Path(tmpdir) / "missing.yml"
            spec_path.write_text("openapi: 3.0.0\n")
            result = spec_get(spec, "paths", "/pets", spec_path=spec_path)
            self.assertIsNone(result["line_start"])
            self.assertIsNone(result["line_end"])

    def test_spec_get_line_span_empty_file(self):
        spec = {"paths": {"/pets": {"get": {"responses": {}}}}}
        with TemporaryDirectory() as tmpdir:
            spec_path = Path(tmpdir) / "empty.yml"
            spec_path.write_text("")
            result = spec_get(spec, "paths", "/pets", spec_path=spec_path)
            self.assertIsNone(result["line_start"])
            self.assertIsNone(result["line_end"])


class ValidateSpecTests(unittest.TestCase):
    def test_validate_example_spec_smoke(self):
        fake_spec = {"openapi": "3.0.0", "info": {"title": "OK", "version": "1.0.0"}}
        with patch(
            "openapi_tools_mcp.tools.load_spec",
            return_value={"spec": fake_spec, "spec_url": "file://fake"},
        ) as load_stub:
            with patch("openapi_tools_mcp.tools.validate_spec") as validate_stub:
                result = validate_example_spec(Path("unused.yml"))
        load_stub.assert_called_once()
        validate_stub.assert_called_once_with(fake_spec, spec_url="file://fake")
        self.assertEqual(result["info"], spec_info(fake_spec))


if __name__ == "__main__":
    unittest.main()
