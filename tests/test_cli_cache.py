import os
from pathlib import Path
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest
from unittest.mock import patch

from openapi_tools_mcp.cli_cache import (
    CLI_CACHE_DIR_ENV,
    CLI_CACHE_LOCK_STALE_SECONDS,
    _cache_digest,
    _entry_path,
    _load_cli_url_spec,
    _lock_path,
    _user_cache_dir,
    load_cli_spec_source,
)
from openapi_tools_mcp.tools import (
    URL_CACHE_TTL_SECONDS,
    _URL_SPEC_CACHE,
    _UrlHttpError,
    _UrlNetworkError,
)

FIXTURE_PATH = Path(__file__).parent / "openapi.example.yml"


def _spec_text(title="Remote"):
    return f"""openapi: 3.0.0
info:
  title: {title}
  version: 1.0.0
paths: {{}}
"""


def _expire(path):
    expired_at = time.time() - URL_CACHE_TTL_SECONDS - 1
    os.utime(path, (expired_at, expired_at))


class CliDiskCacheTests(unittest.TestCase):
    def setUp(self):
        _URL_SPEC_CACHE.clear()
        self.temporary_directory = TemporaryDirectory()
        self.cache_dir = Path(self.temporary_directory.name) / "cache"
        self.source = {
            "url": "https://example.test/openapi.yaml",
            "headers": {"Authorization": "Bearer secret"},
        }

    def tearDown(self):
        self.temporary_directory.cleanup()

    def entry_path(self, source=None):
        source = source or self.source
        return _entry_path(
            self.cache_dir,
            _cache_digest(source["url"], source.get("headers", {})),
        )

    def test_fresh_entry_is_reused_without_downloading(self):
        with patch(
            "openapi_tools_mcp.cli_cache._fetch_url",
            return_value=_spec_text("First"),
        ) as fetch:
            first = _load_cli_url_spec(self.source, cache_dir=self.cache_dir)
            second = _load_cli_url_spec(self.source, cache_dir=self.cache_dir)
        self.assertEqual(first["spec"]["info"]["title"], "First")
        self.assertEqual(second, first)
        fetch.assert_called_once()
        self.assertFalse(_URL_SPEC_CACHE)

    def test_complete_header_mapping_isolates_cache_entries(self):
        second_source = {
            "url": self.source["url"],
            "headers": {"Authorization": "Bearer other"},
        }
        with patch(
            "openapi_tools_mcp.cli_cache._fetch_url",
            side_effect=[_spec_text("One"), _spec_text("Two")],
        ) as fetch:
            one = _load_cli_url_spec(self.source, cache_dir=self.cache_dir)
            two = _load_cli_url_spec(second_source, cache_dir=self.cache_dir)
        self.assertEqual(one["spec"]["info"]["title"], "One")
        self.assertEqual(two["spec"]["info"]["title"], "Two")
        self.assertEqual(fetch.call_count, 2)
        self.assertNotEqual(self.entry_path(), self.entry_path(second_source))

    def test_header_insertion_order_shares_a_cache_entry(self):
        first_source = {
            "url": self.source["url"],
            "headers": {"Accept": "application/yaml", "Authorization": "token"},
        }
        second_source = {
            "url": self.source["url"],
            "headers": {"Authorization": "token", "Accept": "application/yaml"},
        }
        with patch(
            "openapi_tools_mcp.cli_cache._fetch_url",
            return_value=_spec_text("Shared"),
        ) as fetch:
            first = _load_cli_url_spec(first_source, cache_dir=self.cache_dir)
            second = _load_cli_url_spec(second_source, cache_dir=self.cache_dir)
        self.assertEqual(first, second)
        fetch.assert_called_once()

    def test_platform_cache_locations_follow_user_conventions(self):
        with (
            patch("openapi_tools_mcp.cli_cache.sys.platform", "win32"),
            patch.dict(
                os.environ,
                {
                    CLI_CACHE_DIR_ENV: "",
                    "LOCALAPPDATA": "C:/Users/test/AppData/Local",
                },
            ),
        ):
            self.assertEqual(
                _user_cache_dir(),
                Path("C:/Users/test/AppData/Local") / "openapi-tools-mcp",
            )
        with (
            patch("openapi_tools_mcp.cli_cache.sys.platform", "darwin"),
            patch.dict(os.environ, {CLI_CACHE_DIR_ENV: ""}),
            patch(
                "openapi_tools_mcp.cli_cache.Path.home",
                return_value=Path("/Users/test"),
            ),
        ):
            self.assertEqual(
                _user_cache_dir(),
                Path("/Users/test/Library/Caches/openapi-tools-mcp"),
            )
        with (
            patch("openapi_tools_mcp.cli_cache.sys.platform", "linux"),
            patch.dict(
                os.environ,
                {CLI_CACHE_DIR_ENV: "", "XDG_CACHE_HOME": "/cache/test"},
            ),
        ):
            self.assertEqual(_user_cache_dir(), Path("/cache/test/openapi-tools-mcp"))

    def test_cache_directory_environment_override_is_exact_on_all_platforms(self):
        override = self.cache_dir.parent / "configured-cache"
        for platform in ["darwin", "linux", "win32"]:
            with (
                self.subTest(platform=platform),
                patch("openapi_tools_mcp.cli_cache.sys.platform", platform),
                patch.dict(os.environ, {CLI_CACHE_DIR_ENV: str(override)}),
            ):
                self.assertEqual(_user_cache_dir(), override)

    def test_explicit_cache_directory_wins_over_environment_override(self):
        environment_cache = self.cache_dir.parent / "environment-cache"
        with (
            patch.dict(os.environ, {CLI_CACHE_DIR_ENV: str(environment_cache)}),
            patch(
                "openapi_tools_mcp.cli_cache._fetch_url",
                return_value=_spec_text("Explicit"),
            ),
        ):
            loaded = _load_cli_url_spec(self.source, cache_dir=self.cache_dir)

        self.assertEqual(loaded["spec"]["info"]["title"], "Explicit")
        self.assertTrue(self.entry_path().is_file())
        self.assertFalse(environment_cache.exists())

    def test_unwritable_environment_cache_degrades_to_uncached_success(self):
        environment_cache = self.cache_dir.parent / "unwritable-cache"
        with (
            patch.dict(os.environ, {CLI_CACHE_DIR_ENV: str(environment_cache)}),
            patch(
                "openapi_tools_mcp.cli_cache._secure_cache_dir", return_value=False
            ) as secure_cache_dir,
            patch(
                "openapi_tools_mcp.cli_cache._fetch_url",
                return_value=_spec_text("Uncached"),
            ) as fetch,
        ):
            loaded = _load_cli_url_spec(self.source)

        self.assertEqual(loaded["spec"]["info"]["title"], "Uncached")
        secure_cache_dir.assert_called_once_with(environment_cache)
        fetch.assert_called_once()
        self.assertFalse(environment_cache.exists())

    def test_cache_names_permissions_and_contents_protect_headers(self):
        with patch(
            "openapi_tools_mcp.cli_cache._fetch_url",
            return_value=_spec_text(),
        ):
            _load_cli_url_spec(self.source, cache_dir=self.cache_dir)

        entry_path = self.entry_path()
        names = " ".join(path.name for path in self.cache_dir.iterdir())
        self.assertNotIn("Authorization", names)
        self.assertNotIn("Bearer", names)
        self.assertNotIn("secret", names)
        self.assertNotIn("Authorization", entry_path.read_text(encoding="utf-8"))
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(self.cache_dir.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(entry_path.stat().st_mode), 0o600)

    def test_expired_entry_refreshes_atomically(self):
        with patch(
            "openapi_tools_mcp.cli_cache._fetch_url",
            return_value=_spec_text("Old"),
        ):
            _load_cli_url_spec(self.source, cache_dir=self.cache_dir)
        _expire(self.entry_path())

        with patch(
            "openapi_tools_mcp.cli_cache._fetch_url",
            return_value=_spec_text("New"),
        ):
            loaded = _load_cli_url_spec(self.source, cache_dir=self.cache_dir)

        self.assertEqual(loaded["spec"]["info"]["title"], "New")
        self.assertIn("title: New", self.entry_path().read_text(encoding="utf-8"))
        self.assertFalse(list(self.cache_dir.glob("*.tmp")))

    def test_expired_entry_uses_stale_on_network_and_5xx_failures(self):
        for failure in [
            _UrlNetworkError("timed out"),
            _UrlHttpError(503, "Service Unavailable"),
        ]:
            with self.subTest(failure=failure):
                self.temporary_directory.cleanup()
                self.temporary_directory = TemporaryDirectory()
                self.cache_dir = Path(self.temporary_directory.name) / "cache"
                with patch(
                    "openapi_tools_mcp.cli_cache._fetch_url",
                    return_value=_spec_text("Stale"),
                ):
                    _load_cli_url_spec(self.source, cache_dir=self.cache_dir)
                _expire(self.entry_path())
                with patch(
                    "openapi_tools_mcp.cli_cache._fetch_url", side_effect=failure
                ):
                    loaded = _load_cli_url_spec(self.source, cache_dir=self.cache_dir)
                self.assertEqual(loaded["spec"]["info"]["title"], "Stale")

    def test_expired_entry_does_not_mask_4xx_or_invalid_content(self):
        for failure in [
            _UrlHttpError(404, "Not Found"),
            None,
        ]:
            with self.subTest(failure=failure):
                self.temporary_directory.cleanup()
                self.temporary_directory = TemporaryDirectory()
                self.cache_dir = Path(self.temporary_directory.name) / "cache"
                with patch(
                    "openapi_tools_mcp.cli_cache._fetch_url",
                    return_value=_spec_text("Stale"),
                ):
                    _load_cli_url_spec(self.source, cache_dir=self.cache_dir)
                _expire(self.entry_path())
                if failure is None:
                    fetch_patch = patch(
                        "openapi_tools_mcp.cli_cache._fetch_url", return_value="["
                    )
                else:
                    fetch_patch = patch(
                        "openapi_tools_mcp.cli_cache._fetch_url", side_effect=failure
                    )
                with fetch_patch, self.assertRaises(ValueError):
                    _load_cli_url_spec(self.source, cache_dir=self.cache_dir)

    def test_corrupt_entry_is_replaced_after_successful_download(self):
        self.cache_dir.mkdir(mode=0o700)
        self.entry_path().write_text("not an object", encoding="utf-8")
        self.entry_path().chmod(0o600)
        with patch(
            "openapi_tools_mcp.cli_cache._fetch_url",
            return_value=_spec_text("Replacement"),
        ):
            loaded = _load_cli_url_spec(self.source, cache_dir=self.cache_dir)
        self.assertEqual(loaded["spec"]["info"]["title"], "Replacement")
        self.assertIn(
            "title: Replacement", self.entry_path().read_text(encoding="utf-8")
        )

    def test_abandoned_per_key_lock_is_recovered(self):
        self.cache_dir.mkdir(mode=0o700)
        digest = _cache_digest(self.source["url"], self.source["headers"])
        lock_path = _lock_path(self.cache_dir, digest)
        lock_path.mkdir(mode=0o700)
        abandoned_at = time.time() - CLI_CACHE_LOCK_STALE_SECONDS - 1
        os.utime(lock_path, (abandoned_at, abandoned_at))

        with patch(
            "openapi_tools_mcp.cli_cache._fetch_url",
            return_value=_spec_text("Recovered"),
        ):
            loaded = _load_cli_url_spec(self.source, cache_dir=self.cache_dir)

        self.assertEqual(loaded["spec"]["info"]["title"], "Recovered")
        self.assertFalse(lock_path.exists())

    def test_lock_for_an_unrelated_key_does_not_block_download(self):
        self.cache_dir.mkdir(mode=0o700)
        digest = _cache_digest(self.source["url"], self.source["headers"])
        _lock_path(self.cache_dir, digest).mkdir(mode=0o700)
        other_source = {
            "url": "https://other.example.test/openapi.yaml",
            "headers": self.source["headers"],
        }
        started_at = time.monotonic()
        with patch(
            "openapi_tools_mcp.cli_cache._fetch_url",
            return_value=_spec_text("Independent"),
        ):
            loaded = _load_cli_url_spec(other_source, cache_dir=self.cache_dir)
        self.assertLess(time.monotonic() - started_at, 1.0)
        self.assertEqual(loaded["spec"]["info"]["title"], "Independent")

    def test_cache_infrastructure_failures_degrade_to_uncached_success(self):
        cases = [
            patch("openapi_tools_mcp.cli_cache._secure_cache_dir", return_value=False),
            patch("openapi_tools_mcp.cli_cache._acquire_lock", return_value=False),
            patch(
                "openapi_tools_mcp.cli_cache._write_entry",
                side_effect=OSError("read-only"),
            ),
        ]
        for cache_failure in cases:
            with self.subTest(cache_failure=cache_failure):
                self.temporary_directory.cleanup()
                self.temporary_directory = TemporaryDirectory()
                self.cache_dir = Path(self.temporary_directory.name) / "cache"
                with (
                    cache_failure,
                    patch(
                        "openapi_tools_mcp.cli_cache._fetch_url",
                        return_value=_spec_text("Uncached"),
                    ),
                ):
                    loaded = _load_cli_url_spec(self.source, cache_dir=self.cache_dir)
                self.assertEqual(loaded["spec"]["info"]["title"], "Uncached")

    def test_local_sources_do_not_create_disk_cache_entries(self):
        loaded = load_cli_spec_source(FIXTURE_PATH, cache_dir=self.cache_dir)
        self.assertIn("openapi", loaded["spec"])
        self.assertFalse(self.cache_dir.exists())


class CliDiskCacheProcessTests(unittest.TestCase):
    def setUp(self):
        self.request_count = 0
        self.request_count_lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                with outer.request_count_lock:
                    outer.request_count += 1
                time.sleep(0.25)
                body = _spec_text("Concurrent").encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/yaml; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server_thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.server_thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=2)

    def run_callers(self, cache_dir, *, use_environment=False):
        url = f"http://127.0.0.1:{self.server.server_port}/openapi.yaml"
        if use_environment:
            script = (
                "import sys; "
                "from openapi_tools_mcp.cli_cache import _load_cli_url_spec; "
                "loaded = _load_cli_url_spec({'url': sys.argv[1]}); "
                "print(loaded['spec']['info']['title'])"
            )
            arguments = [url]
            environment = os.environ | {CLI_CACHE_DIR_ENV: str(cache_dir)}
        else:
            script = (
                "from pathlib import Path; import sys; "
                "from openapi_tools_mcp.cli_cache import _load_cli_url_spec; "
                "loaded = _load_cli_url_spec({'url': sys.argv[1]}, "
                "cache_dir=Path(sys.argv[2])); "
                "print(loaded['spec']['info']['title'])"
            )
            arguments = [url, str(cache_dir)]
            environment = None
        processes = [
            subprocess.Popen(
                [sys.executable, "-c", script, *arguments],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=environment,
            )
            for _ in range(4)
        ]
        results = [process.communicate(timeout=15) for process in processes]
        for process, (stdout, stderr) in zip(processes, results):
            self.assertEqual(process.returncode, 0, stderr)
            self.assertEqual(stdout.strip(), "Concurrent")
            self.assertEqual(stderr, "")

    def test_cold_and_expired_cross_process_calls_coalesce(self):
        for expired in [False, True]:
            with (
                self.subTest(expired=expired),
                TemporaryDirectory() as temporary_directory,
            ):
                cache_dir = Path(temporary_directory) / "cache"
                if expired:
                    self.run_callers(cache_dir)
                    entry_path = next(cache_dir.glob("*.spec"))
                    _expire(entry_path)
                    with self.request_count_lock:
                        self.request_count = 0

                self.run_callers(cache_dir)
                with self.request_count_lock:
                    self.assertEqual(self.request_count, 1)
                self.assertFalse(list(cache_dir.glob("*.tmp")))
                self.assertFalse(list(cache_dir.glob("*.lock")))

    def test_environment_cache_is_shared_across_processes(self):
        with TemporaryDirectory() as temporary_directory:
            cache_dir = Path(temporary_directory) / "configured-cache"
            self.run_callers(cache_dir, use_environment=True)

            with self.request_count_lock:
                self.assertEqual(self.request_count, 1)
            self.assertEqual(len(list(cache_dir.glob("*.spec"))), 1)
            self.assertFalse(list(cache_dir.glob("*.tmp")))
            self.assertFalse(list(cache_dir.glob("*.lock")))
