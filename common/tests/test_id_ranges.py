import argparse
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "modules"))
from id_ranges import expand_ids, parse_id_ranges


def test_ranges_are_inclusive_ordered_and_deduplicated():
    assert expand_ids("7, 1 - 3,2-5,7,9-9") == [7, 1, 2, 3, 4, 5, 9]
    assert expand_ids(iter([7, 1, 7])) == [7, 1]


def test_parsing_retains_large_bounds():
    assert parse_id_ranges("1-1000000000,7") == [(1, 1000000000), (7, 7)]


@pytest.mark.parametrize("selection", ["", " ", "1,", "1,,2", "nope", "1-", "-5", "5-1", "1-2-3", "1.5", "1;DROP TABLE file_records"])
def test_invalid_selections_are_rejected(selection):
    with pytest.raises(argparse.ArgumentTypeError):
        expand_ids(selection)
