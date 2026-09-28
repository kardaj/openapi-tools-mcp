"""Canonical operation summaries and unchanged MCP tool descriptions."""

SPEC_INFO_SUMMARY = "Quickly summarize an OpenAPI spec"
SPEC_LIST_SUMMARY = "Enumerate keys within a spec section"
SPEC_GET_SUMMARY = "Retrieve a specific item"

SPEC_INFO_DESCRIPTION = (
    f"{SPEC_INFO_SUMMARY} from a local path string or URL source object. For remote "
    'specs, pass {"url": "https://example.com/openapi.yaml", "headers": '
    '{"Header-Name": "value"}}; headers are optional, only http/https URLs are '
    "supported, and successful downloads are cached in memory for 15 minutes with "
    "stale fallback on network errors or HTTP 5XX refresh failures."
)
SPEC_LIST_DESCRIPTION = (
    f"{SPEC_LIST_SUMMARY} from a local path string or URL source object. For remote "
    'specs, pass spec_path as {"url": "https://example.com/openapi.yaml", '
    '"headers": {"Header-Name": "value"}}; headers are optional, only http/https '
    "URLs are supported, and successful downloads are cached in memory for 15 "
    "minutes with stale fallback on network errors or HTTP 5XX refresh failures."
)
SPEC_GET_DESCRIPTION = (
    "Retrieve a specific item from a local path string or URL source object, with "
    "optional $ref resolution and source line numbers. For remote specs, pass "
    'spec_path as {"url": "https://example.com/openapi.yaml", "headers": '
    '{"Header-Name": "value"}}; headers are optional, only http/https URLs are '
    "supported, and successful downloads are cached in memory for 15 minutes with "
    "stale fallback on network errors or HTTP 5XX refresh failures."
)
