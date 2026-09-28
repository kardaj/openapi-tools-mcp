import asyncio
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from importlib.metadata import distribution
from io import StringIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from openapi_tools_mcp import server as mcp_server
from openapi_tools_mcp.cli import main

FIXTURE_PATH = Path(__file__).parent / "openapi.example.yml"


def _run_cli(arguments):
    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            status = main(arguments)
        except SystemExit as exc:
            status = exc.code
    return status, stdout.getvalue(), stderr.getvalue()


def _call_mcp_tool(tool, *args, **kwargs):
    if hasattr(tool, "fn"):
        return tool.fn(*args, **kwargs)
    return tool(*args, **kwargs)


def _registered_mcp_tools():
    if hasattr(mcp_server.mcp, "get_tools"):
        return asyncio.run(mcp_server.mcp.get_tools())
    return {tool.name: tool for tool in asyncio.run(mcp_server.mcp.list_tools())}


class CliOperationTests(unittest.TestCase):
    def assert_json_success(self, arguments, expected):
        status, stdout, stderr = _run_cli(arguments)
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertTrue(stdout.endswith("\n"))
        self.assertEqual(stdout.count("\n"), 1)
        self.assertEqual(json.loads(stdout), expected)

    def test_local_info_matches_mcp(self):
        expected = _call_mcp_tool(mcp_server.spec_info, str(FIXTURE_PATH))
        self.assert_json_success(["info", str(FIXTURE_PATH)], expected)

    def test_local_list_filters_match_mcp(self):
        expected = _call_mcp_tool(
            mcp_server.spec_list,
            "paths",
            str(FIXTURE_PATH),
            filter_by_glob="/pet*",
            filter_by_tag=["pet", "admin"],
        )
        self.assert_json_success(
            [
                "list",
                "paths",
                str(FIXTURE_PATH),
                "--glob",
                "/pet*",
                "--tag",
                "pet",
                "--tag",
                "admin",
            ],
            expected,
        )

    def test_empty_list_is_serialized_as_json_array(self):
        self.assert_json_success(
            ["list", "paths", str(FIXTURE_PATH), "--glob", "/does-not-exist/*"],
            [],
        )

    def test_local_get_defaults_to_resolving_refs(self):
        expected = _call_mcp_tool(
            mcp_server.spec_get, "schemas", "Pet", str(FIXTURE_PATH)
        )
        self.assert_json_success(["get", "schemas", "Pet", str(FIXTURE_PATH)], expected)

    def test_local_get_can_preserve_refs(self):
        expected = _call_mcp_tool(
            mcp_server.spec_get,
            "schemas",
            "Pet",
            str(FIXTURE_PATH),
            resolve_refs=False,
        )
        self.assert_json_success(
            [
                "get",
                "schemas",
                "Pet",
                str(FIXTURE_PATH),
                "--no-resolve-refs",
            ],
            expected,
        )
        self.assertIn(
            "$ref",
            expected["value"]["properties"]["category"],
        )

    def test_relative_source_keeps_local_resolution_and_line_spans(self):
        previous_directory = Path.cwd()
        try:
            os.chdir(FIXTURE_PATH.parent)
            expected = _call_mcp_tool(
                mcp_server.spec_get, "schemas", "Pet", "openapi.example.yml"
            )
            self.assert_json_success(
                ["get", "schemas", "Pet", "./openapi.example.yml"], expected
            )
        finally:
            os.chdir(previous_directory)

    def test_tilde_source_keeps_local_resolution_and_line_spans(self):
        with TemporaryDirectory() as temporary_directory:
            spec_path = Path(temporary_directory) / "openapi.yml"
            spec_path.write_text(
                FIXTURE_PATH.read_text(encoding="utf-8"), encoding="utf-8"
            )
            with patch.dict(
                os.environ,
                {"HOME": temporary_directory, "USERPROFILE": temporary_directory},
            ):
                expected = _call_mcp_tool(
                    mcp_server.spec_get, "schemas", "Pet", "~/openapi.yml"
                )
                self.assert_json_success(
                    ["get", "schemas", "Pet", "~/openapi.yml"], expected
                )

    def test_url_headers_are_trimmed_split_once_and_last_value_wins(self):
        captured = []

        def load_source(source):
            captured.append(source)
            return {"spec": {"openapi": "3.0.0"}}

        with patch(
            "openapi_tools_mcp.cli.load_cli_spec_source", side_effect=load_source
        ):
            status, stdout, stderr = _run_cli(
                [
                    "info",
                    "https://example.test/openapi.yaml",
                    "-H",
                    "  X-Tenant  : old ",
                    "-H",
                    "X-Callback: https://example.test:8443/path",
                    "-H",
                    "X-Tenant: new",
                ]
            )

        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout)["openapi"], "3.0.0")
        self.assertEqual(
            captured,
            [
                {
                    "url": "https://example.test/openapi.yaml",
                    "headers": {
                        "X-Tenant": "new",
                        "X-Callback": "https://example.test:8443/path",
                    },
                }
            ],
        )

    def test_only_lowercase_http_prefixes_are_urls(self):
        captured = []

        def load_source(source):
            captured.append(source)
            return {"spec": {}}

        with patch(
            "openapi_tools_mcp.cli.load_cli_spec_source", side_effect=load_source
        ):
            self.assertEqual(_run_cli(["info", "http://example.test/spec"])[0], 0)
            self.assertEqual(_run_cli(["info", "https://example.test/spec"])[0], 0)
            self.assertEqual(_run_cli(["info", "HTTPS://example.test/spec"])[0], 0)

        self.assertIsInstance(captured[0], dict)
        self.assertIsInstance(captured[1], dict)
        self.assertEqual(captured[2], "HTTPS://example.test/spec")


class CliErrorAndHelpTests(unittest.TestCase):
    def test_header_usage_errors_use_argparse_exit_two(self):
        cases = [
            ["info", str(FIXTURE_PATH), "-H", "X-Test: value"],
            ["info", "https://example.test/spec", "-H", "Authorization"],
            ["info", "https://example.test/spec", "-H", ": value"],
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                status, stdout, stderr = _run_cli(arguments)
                self.assertEqual(status, 2)
                self.assertEqual(stdout, "")
                self.assertIn("usage:", stderr)
                self.assertIn("error:", stderr)

    def test_each_tag_option_consumes_exactly_one_value(self):
        status, stdout, stderr = _run_cli(
            ["list", "paths", str(FIXTURE_PATH), "--tag", "pet", "admin"]
        )
        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertIn("unrecognized arguments: admin", stderr)

    def test_runtime_errors_use_exit_one_without_traceback(self):
        cases = [
            ["list", "nope", str(FIXTURE_PATH)],
            ["get", "schemas", "Nope", str(FIXTURE_PATH)],
            ["info", str(FIXTURE_PATH.parent / "missing.yml")],
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                status, stdout, stderr = _run_cli(arguments)
                self.assertEqual(status, 1)
                self.assertEqual(stdout, "")
                self.assertTrue(stderr.strip())
                self.assertNotIn("Traceback", stderr)

    def test_url_download_failure_uses_runtime_error_channels(self):
        with patch(
            "openapi_tools_mcp.cli.load_cli_spec_source",
            side_effect=ValueError("Failed to download OpenAPI spec: timed out"),
        ):
            status, stdout, stderr = _run_cli(
                ["info", "https://example.test/openapi.yaml"]
            )
        self.assertEqual(status, 1)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "Failed to download OpenAPI spec: timed out\n")

    def test_malformed_local_spec_is_a_runtime_error(self):
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "broken.yaml"
            path.write_text("openapi: [", encoding="utf-8")
            status, stdout, stderr = _run_cli(["info", str(path)])
        self.assertEqual(status, 1)
        self.assertEqual(stdout, "")
        self.assertTrue(stderr.strip())
        self.assertNotIn("Traceback", stderr)

    def test_unexpected_serialization_failure_writes_no_partial_result(self):
        loaded = {
            "spec": {
                "openapi": "3.0.0",
                "info": {"title": "Dated", "released": date(2026, 1, 1)},
            }
        }
        stdout = StringIO()
        stderr = StringIO()
        with (
            patch("openapi_tools_mcp.cli.load_cli_spec_source", return_value=loaded),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
            self.assertRaises(TypeError),
        ):
            main(["info", "ignored.yml"])
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")

    def test_top_level_and_subcommand_help_are_human_readable(self):
        for arguments in [
            ["--help"],
            ["info", "--help"],
            ["list", "--help"],
            ["get", "--help"],
        ]:
            with self.subTest(arguments=arguments):
                status, stdout, stderr = _run_cli(arguments)
                self.assertEqual(status, 0)
                self.assertEqual(stderr, "")
                self.assertIn("usage:", stdout)

    def test_subcommand_help_uses_shared_summaries_and_cli_guidance(self):
        for command, summary in [
            ("info", "Quickly summarize an OpenAPI spec"),
            ("list", "Enumerate keys within a spec section"),
            ("get", "Retrieve a specific item"),
        ]:
            with self.subTest(command=command):
                status, stdout, stderr = _run_cli([command, "--help"])
                self.assertEqual(status, 0)
                self.assertEqual(stderr, "")
                normalized_help = " ".join(stdout.split())
                self.assertIn(summary, normalized_help)
                self.assertIn("private 15-minute disk cache", normalized_help)
                self.assertNotIn("URL source object", stdout)
                self.assertNotIn("cached in memory", stdout)


class PackagingAndMetadataTests(unittest.TestCase):
    def test_distribution_exposes_both_console_scripts(self):
        scripts = {
            entry.name: entry.value
            for entry in distribution("openapi-tools-mcp").entry_points
            if entry.group == "console_scripts"
        }
        self.assertEqual(scripts["openapi-tools-mcp"], "openapi_tools_mcp.server:main")
        self.assertEqual(scripts["openapi-tools-cli"], "openapi_tools_mcp.cli:main")

    def test_generated_mcp_metadata_is_exactly_unchanged(self):
        tools = _registered_mcp_tools()
        actual = {
            name: {
                "description": tools[name].description,
                "parameters": tools[name].parameters,
            }
            for name in ["spec_info", "spec_list", "spec_get"]
        }
        self.assertEqual(actual, _EXPECTED_MCP_METADATA)


_SOURCE_SCHEMA = {
    "anyOf": [
        {"type": "string"},
        {"additionalProperties": True, "type": "object"},
    ]
}
_EXPECTED_MCP_METADATA = {
    "spec_info": {
        "description": (
            "Quickly summarize an OpenAPI spec from a local path string or URL "
            'source object. For remote specs, pass {"url": '
            '"https://example.com/openapi.yaml", "headers": {"Header-Name": '
            '"value"}}; headers are optional, only http/https URLs are supported, '
            "and successful downloads are cached in memory for 15 minutes with "
            "stale fallback on network errors or HTTP 5XX refresh failures."
        ),
        "parameters": {
            "additionalProperties": False,
            "properties": {"spec_path": _SOURCE_SCHEMA},
            "required": ["spec_path"],
            "type": "object",
        },
    },
    "spec_list": {
        "description": (
            "Enumerate keys within a spec section from a local path string or URL "
            'source object. For remote specs, pass spec_path as {"url": '
            '"https://example.com/openapi.yaml", "headers": {"Header-Name": '
            '"value"}}; headers are optional, only http/https URLs are supported, '
            "and successful downloads are cached in memory for 15 minutes with "
            "stale fallback on network errors or HTTP 5XX refresh failures."
        ),
        "parameters": {
            "additionalProperties": False,
            "properties": {
                "filter_by_glob": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "default": None,
                },
                "filter_by_tag": {
                    "anyOf": [
                        {"type": "string"},
                        {"items": {"type": "string"}, "type": "array"},
                        {"type": "null"},
                    ],
                    "default": None,
                },
                "section": {"type": "string"},
                "spec_path": _SOURCE_SCHEMA,
            },
            "required": ["section", "spec_path"],
            "type": "object",
        },
    },
    "spec_get": {
        "description": (
            "Retrieve a specific item from a local path string or URL source object, "
            "with optional $ref resolution and source line numbers. For remote "
            'specs, pass spec_path as {"url": '
            '"https://example.com/openapi.yaml", "headers": {"Header-Name": '
            '"value"}}; headers are optional, only http/https URLs are supported, '
            "and successful downloads are cached in memory for 15 minutes with "
            "stale fallback on network errors or HTTP 5XX refresh failures."
        ),
        "parameters": {
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string"},
                "resolve_refs": {"default": True, "type": "boolean"},
                "section": {"type": "string"},
                "spec_path": _SOURCE_SCHEMA,
            },
            "required": ["section", "name", "spec_path"],
            "type": "object",
        },
    },
}
