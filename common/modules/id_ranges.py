"""Compact, inclusive ID selections shared by APIs and their backends.

Parsing retains bounds. Only backend operations should call ``expand_ids``.
Open-ended and descending ranges are deliberately unsupported.
"""

import argparse
import re
from collections.abc import Iterable


IdSelection = str | Iterable[int]
_TOKEN = re.compile(r"([0-9]+)(?:-([0-9]+))?")


def parse_id_ranges(value: str) -> list[tuple[int, int]]:
    bounds = []
    for token in value.split(","):
        match = _TOKEN.fullmatch(token)
        if match is None:
            raise argparse.ArgumentTypeError(
                "IDs must be comma-separated integers or terminated inclusive ranges (e.g. 1-5,7); only ASCII digits, commas and hyphens are allowed, without whitespace"
            )
        start = int(match[1])
        end = int(match[2]) if match[2] is not None else start
        if end < start:
            raise argparse.ArgumentTypeError("ID range end must be greater than or equal to its start")
        bounds.append((start, end))
    return bounds


def expand_ids(selection: IdSelection) -> list[int]:
    """Expand and deduplicate a selection, preserving first occurrence order."""
    if isinstance(selection, str):
        return list(dict.fromkeys(
            record_id
            for start, end in parse_id_ranges(selection)
            for record_id in range(start, end + 1)
        ))
    return list(dict.fromkeys(selection))


def ids_expression(selection: IdSelection) -> str:
    """Serialize existing ID iterables while passing range expressions unchanged."""
    if isinstance(selection, str):
        return selection
    return ",".join(str(record_id) for record_id in selection)
