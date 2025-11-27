"""OpenAPI helper functions for validation and inspection."""

from pathlib import Path
from typing import Any, Dict, List, Tuple

from openapi_spec_validator import validate_spec
from openapi_spec_validator.readers import read_from_filename
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPEC_PATH = PROJECT_ROOT / "tests" / "openapi.example.yml"


def load_spec(path: Path) -> Dict[str, Any]:
    """Read and return the OpenAPI spec dict plus its source URL."""
    spec_dict, spec_url = read_from_filename(str(path))
    return {"spec": spec_dict, "spec_url": spec_url}


def spec_info(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Return key top-level sections of the spec."""
    return {
        "openapi": spec.get("openapi"),
        "info": spec.get("info"),
        "servers": spec.get("servers"),
    }


def spec_list(spec: Dict[str, Any], section: str) -> List[Any]:
    """List contents of selected sections."""
    if section == "paths":
        paths = spec.get("paths", {}) or {}
        return [
            {"path": path, "verbs": list(verbs.keys())} for path, verbs in paths.items()
        ]

    if section == "schemas":
        schemas = spec.get("components", {}).get("schemas", {}) or {}
        return list(schemas.keys())

    if section == "parameters":
        params = spec.get("components", {}).get("parameters", {}) or {}
        return list(params.keys())

    if section == "responses":
        responses = spec.get("components", {}).get("responses", {}) or {}
        return list(responses.keys())

    if section == "requestBodies":
        bodies = spec.get("components", {}).get("requestBodies", {}) or {}
        return list(bodies.keys())

    if section == "headers":
        headers = spec.get("components", {}).get("headers", {}) or {}
        return list(headers.keys())

    if section == "securitySchemes":
        schemes = spec.get("components", {}).get("securitySchemes", {}) or {}
        return list(schemes.keys())

    if section == "links":
        links = spec.get("components", {}).get("links", {}) or {}
        return list(links.keys())

    if section == "callbacks":
        callbacks = spec.get("components", {}).get("callbacks", {}) or {}
        return list(callbacks.keys())

    if section == "examples":
        examples = spec.get("components", {}).get("examples", {}) or {}
        return list(examples.keys())

    raise ValueError(
        "Unsupported section "
        f"'{section}'. Expected one of: paths, schemas, parameters, responses, "
        "requestBodies, headers, securitySchemes, links, callbacks, examples."
    )


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


def _find_line_span(spec_path: Path, keys: List[str]) -> Tuple[int | None, int | None]:
    """Find start/end line numbers (0-based) for a nested key path in the YAML file."""
    root = yaml.compose(spec_path.read_text())
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


def spec_get(
    spec: Dict[str, Any], section: str, name: str, *, spec_path: Path | None = None
) -> Dict[str, Any]:
    """Get a specific item from supported sections, with optional line span."""
    if section == "paths":
        paths = spec.get("paths", {}) or {}
        if name not in paths:
            raise KeyError(f"Path '{name}' not found")
        value = paths[name]

    elif section == "schemas":
        schemas = spec.get("components", {}).get("schemas", {}) or {}
        if name not in schemas:
            raise KeyError(f"Schema '{name}' not found")
        value = schemas[name]

    elif section == "parameters":
        params = spec.get("components", {}).get("parameters", {}) or {}
        if name not in params:
            raise KeyError(f"Parameter '{name}' not found")
        value = params[name]

    elif section == "responses":
        responses = spec.get("components", {}).get("responses", {}) or {}
        if name not in responses:
            raise KeyError(f"Response '{name}' not found")
        value = responses[name]

    elif section == "requestBodies":
        bodies = spec.get("components", {}).get("requestBodies", {}) or {}
        if name not in bodies:
            raise KeyError(f"Request body '{name}' not found")
        value = bodies[name]

    elif section == "headers":
        headers = spec.get("components", {}).get("headers", {}) or {}
        if name not in headers:
            raise KeyError(f"Header '{name}' not found")
        value = headers[name]

    elif section == "securitySchemes":
        schemes = spec.get("components", {}).get("securitySchemes", {}) or {}
        if name not in schemes:
            raise KeyError(f"Security scheme '{name}' not found")
        value = schemes[name]

    elif section == "links":
        links = spec.get("components", {}).get("links", {}) or {}
        if name not in links:
            raise KeyError(f"Link '{name}' not found")
        value = links[name]

    elif section == "callbacks":
        callbacks = spec.get("components", {}).get("callbacks", {}) or {}
        if name not in callbacks:
            raise KeyError(f"Callback '{name}' not found")
        value = callbacks[name]

    elif section == "examples":
        examples = spec.get("components", {}).get("examples", {}) or {}
        if name not in examples:
            raise KeyError(f"Example '{name}' not found")
        value = examples[name]

    else:
        raise ValueError(
            "Unsupported section "
            f"'{section}'. Expected one of: paths, schemas, parameters, responses, "
            "requestBodies, headers, securitySchemes, links, callbacks, examples."
        )

    line_start: int | None = None
    line_end: int | None = None
    if spec_path:
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
