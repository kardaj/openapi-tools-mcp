import unittest
from pathlib import Path

from openapi_tools_mcp.tools import load_spec, spec_get, spec_info, spec_list

FIXTURE_PATH = Path(__file__).parent / "openapi31.example.yml"


class OpenAPI31FixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        loaded = load_spec(FIXTURE_PATH)
        cls.spec = loaded["spec"]

    def test_spec_info_lists_public_server(self):
        info = spec_info(self.spec)

        self.assertEqual(info["openapi"], "3.1.0")
        self.assertEqual(info["info"]["title"], "Social Data API")
        self.assertEqual(info["servers"][0]["url"], "https://social.example.test")

    def test_paths_and_tags_are_discoverable(self):
        paths = spec_list(self.spec, "paths", filter_by_tag="Posts")

        self.assertEqual(paths[0]["path"], "/posts/search")
        self.assertEqual(spec_list(self.spec, "tags"), ["Posts", "Trends", "Users"])

    def test_get_path_and_security_scheme_details(self):
        search_path = spec_get(
            self.spec,
            "paths",
            "/posts/search",
            spec_path=FIXTURE_PATH,
        )
        api_key = spec_get(
            self.spec,
            "securitySchemes",
            "apiKey",
            spec_path=FIXTURE_PATH,
        )

        self.assertEqual(search_path["value"]["get"]["operationId"], "searchPosts")
        self.assertEqual(api_key["value"]["name"], "X-API-Key")
