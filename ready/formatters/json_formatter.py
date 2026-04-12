"""JSON output formatter for ready scan results."""

import json

from ready.engine import ScanResult


def format_json(result: ScanResult) -> str:
    """Return the scan result as a JSON string."""
    return json.dumps(result.to_dict(), indent=2)
