"""OpenAPI helper functions for validation and inspection."""

from copy import deepcopy
from fnmatch import fnmatch
from pathlib import Path
import socket
import time
from typing import Any, Dict, Iterable, List, Mapping, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from openapi_spec_validator import validate_spec
from openapi_spec_validator.readers import read_from_filename
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPEC_PATH = PROJECT_ROOT / "tests" / "openapi.example.yml"
URL_CACHE_TTL_SECONDS = 15 * 60
URL_REQUEST_TIMEOUT_SECONDS = 10.0
SUPPORTED_URL_SCHEMES = {"http", "https"}
_URL_SPEC_CACHE: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], Dict[str, Any]] = {}


class _UrlFetchError(Exception):
    """Base class for URL fetch failures."""


class _UrlHttpError(_UrlFetchError):
    def __init__(self, status_code: int, reason: str):
        super().__init__(f"HTTP {status_code} {reason}".strip())
        self.status_code = status_code
        self.reason = reason


class _UrlNetworkError(_UrlFetchError):
    """Network-level URL fetch failure."""


def load_spec(path: Path) -> Dict[str, Any]:
    """Read and return the OpenAPI spec dict plus its source URL."""
    spec_dict, spec_url = read_from_filename(str(path))
    return {"spec": spec_dict, "spec_url": spec_url}


def _monotonic() -> float:
    return time.monotonic()


def _normalize_headers(headers: Any) -> Dict[str, str]:
    if headers is None:
        return {}
    if not isinstance(headers, Mapping):
        raise ValueError(
            "URL source 'headers' must be an object mapping names to values."
        )
    return {str(name): str(value) for name, value in headers.items()}


def _url_cache_key(
    url: str, headers: Mapping[str, str]
) -> Tuple[str, Tuple[Tuple[str, str], ...]]:
    return (url, tuple(sorted(headers.items())))


def _parse_url_source(source: Mapping[str, Any]) -> Tuple[str, Dict[str, str]]:
    raw_url = source.get("url")
    if not isinstance(raw_url, str) or not raw_url:
        raise ValueError("URL source must include a non-empty string 'url'.")

    parsed = urlparse(raw_url)
    if parsed.scheme not in SUPPORTED_URL_SCHEMES:
        supported = ", ".join(sorted(SUPPORTED_URL_SCHEMES))
        raise ValueError(
            f"Unsupported URL scheme '{parsed.scheme}'. Expected one of: {supported}."
        )

    return raw_url, _normalize_headers(source.get("headers"))


def _fetch_url(url: str, headers: Mapping[str, str]) -> str:
    request = Request(url, headers=dict(headers))
    try:
        with urlopen(request, timeout=URL_REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
    except HTTPError as exc:
        raise _UrlHttpError(exc.code, exc.reason) from exc
    except (URLError, TimeoutError, socket.timeout, OSError) as exc:
        raise _UrlNetworkError(str(exc)) from exc

    return body.decode(charset)


def _parse_spec_text(source_text: str, spec_url: str) -> Dict[str, Any]:
    try:
        spec = yaml.safe_load(source_text)
    except yaml.YAMLError as exc:
        raise ValueError(
            f"Unable to parse OpenAPI spec from {spec_url}: {exc}"
        ) from exc
    if not isinstance(spec, dict):
        raise ValueError(f"OpenAPI spec from {spec_url} must be a JSON/YAML object.")
    return {"spec": spec, "spec_url": spec_url, "source_text": source_text}


def _load_url_spec(source: Mapping[str, Any]) -> Dict[str, Any]:
    url, headers = _parse_url_source(source)
    cache_key = _url_cache_key(url, headers)
    cached = _URL_SPEC_CACHE.get(cache_key)
    now = _monotonic()
    if cached and now - cached["loaded_at"] <= URL_CACHE_TTL_SECONDS:
        return cached["loaded"]

    try:
        loaded = _parse_spec_text(_fetch_url(url, headers), url)
    except _UrlHttpError as exc:
        if cached and 500 <= exc.status_code <= 599:
            return cached["loaded"]
        raise ValueError(
            f"Failed to download OpenAPI spec from {url}: HTTP {exc.status_code} {exc.reason}"
        ) from exc
    except _UrlNetworkError as exc:
        if cached:
            return cached["loaded"]
        raise ValueError(f"Failed to download OpenAPI spec from {url}: {exc}") from exc

    _URL_SPEC_CACHE[cache_key] = {"loaded_at": now, "loaded": loaded}
    return loaded


def load_spec_source(source: str | Path | Mapping[str, Any]) -> Dict[str, Any]:
    """Read an OpenAPI spec from a local path string/path or URL source object."""
    if isinstance(source, Mapping):
        return _load_url_spec(source)

    if isinstance(source, (str, Path)):
        path = Path(source).expanduser().resolve()
        loaded = load_spec(path)
        loaded["source_path"] = path
        return loaded

    raise ValueError(
        "spec_path must be a local path string or a URL source object with 'url' and optional 'headers'."
    )


def spec_info(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Return key top-level sections of the spec."""
    return {
        "openapi": spec.get("openapi"),
        "info": spec.get("info"),
        "servers": spec.get("servers"),
    }


def _normalize_tag_filter(filter_by_tag: str | Iterable[str] | None) -> set[str]:
    if filter_by_tag is None:
        return set()
    if isinstance(filter_by_tag, str):
        return {filter_by_tag}
    return {tag for tag in filter_by_tag if tag}


def _matches_glob(name: str, pattern: str | None) -> bool:
    if not pattern:
        return True
    return fnmatch(name, pattern)


def _schema_has_tag(schema: Dict[str, Any], tag_filter: set[str]) -> bool:
    if not tag_filter:
        return True
    tags = schema.get("tags") or schema.get("x-tags") or []
    return bool(set(tags) & tag_filter)


def _path_has_tag(path_item: Dict[str, Any], tag_filter: set[str]) -> bool:
    if not tag_filter:
        return True
    for operation in path_item.values():
        if not isinstance(operation, dict):
            continue
        tags = operation.get("tags") or []
        if set(tags) & tag_filter:
            return True
    return False


def spec_list(
    spec: Dict[str, Any],
    section: str,
    *,
    filter_by_glob: str | None = None,
    filter_by_tag: str | Iterable[str] | None = None,
) -> List[Any]:
    """List contents of selected sections."""
    tag_filter = _normalize_tag_filter(filter_by_tag)
    if section == "paths":
        paths = spec.get("paths", {}) or {}
        return [
            {"path": path, "verbs": list(verbs.keys())}
            for path, verbs in paths.items()
            if _matches_glob(path, filter_by_glob) and _path_has_tag(verbs, tag_filter)
        ]

    if section == "tags":
        tags: set[str] = set()
        for path_item in (spec.get("paths", {}) or {}).values():
            if not isinstance(path_item, dict):
                continue
            for operation in path_item.values():
                if not isinstance(operation, dict):
                    continue
                for tag in operation.get("tags") or []:
                    if isinstance(tag, str):
                        tags.add(tag)
        return [name for name in sorted(tags) if _matches_glob(name, filter_by_glob)]

    if section == "schemas":
        schemas = spec.get("components", {}).get("schemas", {}) or {}
        return [
            name
            for name, schema in schemas.items()
            if _matches_glob(name, filter_by_glob)
            and _schema_has_tag(schema, tag_filter)
        ]

    if section == "parameters":
        params = spec.get("components", {}).get("parameters", {}) or {}
        return [name for name in params.keys() if _matches_glob(name, filter_by_glob)]

    if section == "responses":
        responses = spec.get("components", {}).get("responses", {}) or {}
        return [
            name for name in responses.keys() if _matches_glob(name, filter_by_glob)
        ]

    if section == "requestBodies":
        bodies = spec.get("components", {}).get("requestBodies", {}) or {}
        return [name for name in bodies.keys() if _matches_glob(name, filter_by_glob)]

    if section == "headers":
        headers = spec.get("components", {}).get("headers", {}) or {}
        return [name for name in headers.keys() if _matches_glob(name, filter_by_glob)]

    if section == "securitySchemes":
        schemes = spec.get("components", {}).get("securitySchemes", {}) or {}
        return [name for name in schemes.keys() if _matches_glob(name, filter_by_glob)]

    if section == "links":
        links = spec.get("components", {}).get("links", {}) or {}
        return [name for name in links.keys() if _matches_glob(name, filter_by_glob)]

    if section == "callbacks":
        callbacks = spec.get("components", {}).get("callbacks", {}) or {}
        return [
            name for name in callbacks.keys() if _matches_glob(name, filter_by_glob)
        ]

    if section == "examples":
        examples = spec.get("components", {}).get("examples", {}) or {}
        return [name for name in examples.keys() if _matches_glob(name, filter_by_glob)]

    raise ValueError(
        "Unsupported section "
        f"'{section}'. Expected one of: paths, schemas, parameters, responses, tags, "
        "requestBodies, headers, securitySchemes, links, callbacks, examples."
    )


def _resolve_ref(spec: Dict[str, Any], ref: str) -> Any:
    if not ref.startswith("#/"):
        raise ValueError(f"Only local $ref values are supported, got '{ref}'.")

    target: Any = spec
    for part in ref.lstrip("#/").split("/"):
        if not isinstance(target, dict) or part not in target:
            raise KeyError(f"Unable to resolve $ref path part '{part}' in '{ref}'.")
        target = target[part]
    return target


def _resolve_ref_chain(
    spec: Dict[str, Any], ref: str, seen: set[str] | None = None
) -> Any:
    seen = seen or set()
    if ref in seen:
        raise ValueError(f"Circular $ref detected for '{ref}'.")
    seen.add(ref)

    resolved = _resolve_ref(spec, ref)
    if isinstance(resolved, dict) and "$ref" in resolved:
        nested_ref = resolved["$ref"]
        if not isinstance(nested_ref, str):
            return resolved
        return _resolve_ref_chain(spec, nested_ref, seen)
    return resolved


def _resolve_all_refs(
    spec: Dict[str, Any], value: Any, seen: set[str] | None = None
) -> Any:
    """Recursively resolve all $ref pointers within `value`."""
    if isinstance(value, dict):
        if "$ref" in value and isinstance(value["$ref"], str):
            resolved = _resolve_ref_chain(spec, value["$ref"], seen)
            # Recurse again in case the resolved object contains further $ref values.
            return _resolve_all_refs(spec, deepcopy(resolved), seen)
        return {key: _resolve_all_refs(spec, item, seen) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_all_refs(spec, item, seen) for item in value]
    return value


def _resolve_response_value(spec: Dict[str, Any], response: Any) -> Any:
    if (
        isinstance(response, dict)
        and "$ref" in response
        and isinstance(response["$ref"], str)
    ):
        resolved = _resolve_ref_chain(spec, response["$ref"])
        return deepcopy(resolved)
    return response


def _resolve_response_refs(
    spec: Dict[str, Any], responses: Dict[str, Any]
) -> Dict[str, Any]:
    resolved: Dict[str, Any] = {}
    for status, response in responses.items():
        resolved[status] = _resolve_response_value(spec, response)
    return resolved


def _resolve_path_responses(
    spec: Dict[str, Any], path_item: Dict[str, Any]
) -> Dict[str, Any]:
    resolved_path = deepcopy(path_item)
    for _, operation in resolved_path.items():
        if not isinstance(operation, dict):
            continue
        responses = operation.get("responses")
        if isinstance(responses, dict):
            operation["responses"] = _resolve_response_refs(spec, responses)
    return resolved_path


def _section_keys(section: str, name: str) -> List[str]:
    if section == "paths":
        return ["paths", name]
    if section == "schemas":
        return ["components", "schemas", name]
    if section == "parameters":
        return ["components", "parameters", name]
    if section == "responses":
        return ["components", "responses", name]
    if section == "requestBodies":
        return ["components", "requestBodies", name]
    if section == "headers":
        return ["components", "headers", name]
    if section == "securitySchemes":
        return ["components", "securitySchemes", name]
    if section == "links":
        return ["components", "links", name]
    if section == "callbacks":
        return ["components", "callbacks", name]
    if section == "examples":
        return ["components", "examples", name]
    raise ValueError(
        "Unsupported section "
        f"'{section}'. Expected one of: paths, schemas, parameters, responses, "
        "requestBodies, headers, securitySchemes, links, callbacks, examples."
    )


def _find_line_span_in_text(
    source_text: str, keys: List[str]
) -> Tuple[int | None, int | None]:
    """Find start/end line numbers (0-based) for a nested key path in YAML text."""
    root = yaml.compose(source_text)
    node = root
    for key in keys:
        if not hasattr(node, "value"):
            return (None, None)
        next_node = None
        for key_node, value_node in node.value:
            if getattr(key_node, "value", None) == key:
                next_node = value_node
                break
        if next_node is None:
            return (None, None)
        node = next_node

    start = getattr(node.start_mark, "line", None)
    end = getattr(node.end_mark, "line", None)
    return (start, end)


def _find_line_span(spec_path: Path, keys: List[str]) -> Tuple[int | None, int | None]:
    """Find start/end line numbers (0-based) for a nested key path in the YAML file."""
    return _find_line_span_in_text(spec_path.read_text(), keys)


def spec_get(
    spec: Dict[str, Any],
    section: str,
    name: str,
    *,
    spec_path: Path | None = None,
    source_text: str | None = None,
    resolve_refs: bool = True,
) -> Dict[str, Any]:
    """Get a specific item from supported sections, with optional line span.

    When `resolve_refs` is True, response objects have their $ref pointers resolved.
    """
    if section == "paths":
        paths = spec.get("paths", {}) or {}
        if name not in paths:
            raise KeyError(f"Path '{name}' not found")
        value = deepcopy(paths[name])
        if resolve_refs:
            value = _resolve_all_refs(spec, value)

    elif section == "schemas":
        schemas = spec.get("components", {}).get("schemas", {}) or {}
        if name not in schemas:
            raise KeyError(f"Schema '{name}' not found")
        value = deepcopy(schemas[name])
        if resolve_refs:
            value = _resolve_all_refs(spec, value)

    elif section == "parameters":
        params = spec.get("components", {}).get("parameters", {}) or {}
        if name not in params:
            raise KeyError(f"Parameter '{name}' not found")
        value = deepcopy(params[name])
        if resolve_refs:
            value = _resolve_all_refs(spec, value)

    elif section == "responses":
        responses = spec.get("components", {}).get("responses", {}) or {}
        if name not in responses:
            raise KeyError(f"Response '{name}' not found")
        value = deepcopy(responses[name])
        if resolve_refs:
            value = _resolve_all_refs(spec, value)

    elif section == "requestBodies":
        bodies = spec.get("components", {}).get("requestBodies", {}) or {}
        if name not in bodies:
            raise KeyError(f"Request body '{name}' not found")
        value = deepcopy(bodies[name])
        if resolve_refs:
            value = _resolve_all_refs(spec, value)

    elif section == "headers":
        headers = spec.get("components", {}).get("headers", {}) or {}
        if name not in headers:
            raise KeyError(f"Header '{name}' not found")
        value = deepcopy(headers[name])
        if resolve_refs:
            value = _resolve_all_refs(spec, value)

    elif section == "securitySchemes":
        schemes = spec.get("components", {}).get("securitySchemes", {}) or {}
        if name not in schemes:
            raise KeyError(f"Security scheme '{name}' not found")
        value = deepcopy(schemes[name])
        if resolve_refs:
            value = _resolve_all_refs(spec, value)

    elif section == "links":
        links = spec.get("components", {}).get("links", {}) or {}
        if name not in links:
            raise KeyError(f"Link '{name}' not found")
        value = deepcopy(links[name])
        if resolve_refs:
            value = _resolve_all_refs(spec, value)

    elif section == "callbacks":
        callbacks = spec.get("components", {}).get("callbacks", {}) or {}
        if name not in callbacks:
            raise KeyError(f"Callback '{name}' not found")
        value = deepcopy(callbacks[name])
        if resolve_refs:
            value = _resolve_all_refs(spec, value)

    elif section == "examples":
        examples = spec.get("components", {}).get("examples", {}) or {}
        if name not in examples:
            raise KeyError(f"Example '{name}' not found")
        value = deepcopy(examples[name])
        if resolve_refs:
            value = _resolve_all_refs(spec, value)

    else:
        raise ValueError(
            "Unsupported section "
            f"'{section}'. Expected one of: paths, schemas, parameters, responses, "
            "requestBodies, headers, securitySchemes, links, callbacks, examples."
        )

    line_start: int | None = None
    line_end: int | None = None
    if source_text is not None:
        line_start, line_end = _find_line_span_in_text(
            source_text, _section_keys(section, name)
        )
    elif spec_path:
        line_start, line_end = _find_line_span(spec_path, _section_keys(section, name))
    return {"value": value, "line_start": line_start, "line_end": line_end}


def validate_example_spec(spec_path: Path | None = None) -> Dict[str, Any]:
    """Validate the example spec and return information and listings."""
    path = spec_path or DEFAULT_SPEC_PATH
    loaded = load_spec(path)
    spec_dict = loaded["spec"]
    spec_url = loaded["spec_url"]
    validate_spec(spec_dict, spec_url=spec_url)
    return {
        "info": spec_info(spec_dict),
        "paths": spec_list(spec_dict, "paths"),
        "schemas": spec_list(spec_dict, "schemas"),
        "parameters": spec_list(spec_dict, "parameters"),
    }
