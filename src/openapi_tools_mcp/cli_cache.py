"""Private cross-process URL cache used only by the command-line interface."""

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
from typing import Any, Dict, Mapping

from .tools import (
    URL_CACHE_TTL_SECONDS,
    URL_REQUEST_TIMEOUT_SECONDS,
    _UrlHttpError,
    _UrlNetworkError,
    _fetch_url,
    _parse_spec_text,
    _parse_url_source,
    load_spec_source,
)

CLI_CACHE_LOCK_POLL_SECONDS = 0.05
CLI_CACHE_LOCK_STALE_SECONDS = URL_REQUEST_TIMEOUT_SECONDS * 3


@dataclass(frozen=True)
class _CacheEntry:
    loaded: Dict[str, Any]
    fresh: bool


def _user_cache_dir() -> Path:
    """Return the platform's conventional per-user cache directory."""
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA")
        if root:
            return Path(root) / "openapi-tools-mcp"
        return Path.home() / "AppData" / "Local" / "openapi-tools-mcp"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "openapi-tools-mcp"
    root = os.environ.get("XDG_CACHE_HOME")
    if root:
        return Path(root) / "openapi-tools-mcp"
    return Path.home() / ".cache" / "openapi-tools-mcp"


def _secure_cache_dir(cache_dir: Path) -> bool:
    try:
        cache_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        cache_dir.chmod(0o700)
        if os.name != "nt" and stat.S_IMODE(cache_dir.stat().st_mode) != 0o700:
            return False
    except OSError:
        return False
    return True


def _cache_digest(url: str, headers: Mapping[str, str]) -> str:
    identity = json.dumps(
        [url, sorted(headers.items())],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(identity).hexdigest()


def _entry_path(cache_dir: Path, digest: str) -> Path:
    return cache_dir / f"{digest}.spec"


def _lock_path(cache_dir: Path, digest: str) -> Path:
    return cache_dir / f"{digest}.lock"


def _read_entry(entry_path: Path, url: str, now: float) -> _CacheEntry | None:
    try:
        if os.name != "nt" and stat.S_IMODE(entry_path.stat().st_mode) != 0o600:
            entry_path.chmod(0o600)
        source_text = entry_path.read_text(encoding="utf-8")
        modified_at = entry_path.stat().st_mtime
        loaded = _parse_spec_text(source_text, url)
    except Exception:
        return None
    return _CacheEntry(
        loaded=loaded,
        fresh=now - modified_at <= URL_CACHE_TTL_SECONDS,
    )


def _write_entry(entry_path: Path, source_text: str) -> None:
    descriptor: int | None = None
    temporary_path: Path | None = None
    try:
        descriptor, raw_path = tempfile.mkstemp(
            dir=entry_path.parent,
            prefix=f".{entry_path.stem}.",
            suffix=".tmp",
        )
        temporary_path = Path(raw_path)
        os.chmod(temporary_path, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = None
            stream.write(source_text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, entry_path)
        temporary_path = None
        entry_path.chmod(0o600)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except OSError:
                pass


def _acquire_lock(lock_path: Path) -> bool:
    deadline = time.monotonic() + CLI_CACHE_LOCK_STALE_SECONDS
    while time.monotonic() < deadline:
        try:
            lock_path.mkdir(mode=0o700)
            if os.name != "nt":
                lock_path.chmod(0o700)
            return True
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
                if age >= CLI_CACHE_LOCK_STALE_SECONDS:
                    lock_path.rmdir()
                    continue
            except FileNotFoundError:
                continue
            except OSError:
                return False
            time.sleep(CLI_CACHE_LOCK_POLL_SECONDS)
        except OSError:
            return False
    return False


def _release_lock(lock_path: Path) -> None:
    try:
        lock_path.rmdir()
    except OSError:
        pass


def _download(
    url: str,
    headers: Mapping[str, str],
    stale: _CacheEntry | None,
) -> tuple[Dict[str, Any], str | None]:
    try:
        source_text = _fetch_url(url, headers)
    except _UrlHttpError as exc:
        if stale is not None and 500 <= exc.status_code <= 599:
            return stale.loaded, None
        raise ValueError(
            f"Failed to download OpenAPI spec from {url}: "
            f"HTTP {exc.status_code} {exc.reason}"
        ) from exc
    except _UrlNetworkError as exc:
        if stale is not None:
            return stale.loaded, None
        raise ValueError(f"Failed to download OpenAPI spec from {url}: {exc}") from exc

    return _parse_spec_text(source_text, url), source_text


def _load_cli_url_spec(
    source: Mapping[str, Any],
    *,
    cache_dir: Path | None = None,
) -> Dict[str, Any]:
    url, headers = _parse_url_source(source)
    cache_dir = cache_dir or _user_cache_dir()
    if not _secure_cache_dir(cache_dir):
        return _download(url, headers, None)[0]

    digest = _cache_digest(url, headers)
    entry_path = _entry_path(cache_dir, digest)
    cached = _read_entry(entry_path, url, time.time())
    if cached is not None and cached.fresh:
        return cached.loaded

    lock_path = _lock_path(cache_dir, digest)
    if not _acquire_lock(lock_path):
        return _download(url, headers, cached)[0]

    try:
        rechecked = _read_entry(entry_path, url, time.time())
        if rechecked is not None and rechecked.fresh:
            return rechecked.loaded
        stale = rechecked or cached
        loaded, source_text = _download(url, headers, stale)
        if source_text is not None:
            try:
                _write_entry(entry_path, source_text)
            except OSError:
                pass
        return loaded
    finally:
        _release_lock(lock_path)


def load_cli_spec_source(
    source: str | Path | Mapping[str, Any],
    *,
    cache_dir: Path | None = None,
) -> Dict[str, Any]:
    """Load a source with the CLI disk cache applied only to URL objects."""
    if isinstance(source, Mapping):
        return _load_cli_url_spec(source, cache_dir=cache_dir)
    return load_spec_source(source)
