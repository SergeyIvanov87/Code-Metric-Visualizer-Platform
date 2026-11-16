"""Verify that RAG command parsers return control on invalid arguments."""

import json
from pathlib import Path

import pytest

from cli_argument_parser import ArgumentParsingError, RaisingArgumentParser
import rag_bulk_add


def test_argument_parser_raises_instead_of_exiting(capsys):
    parser = RaisingArgumentParser(prog="rag-test")
    parser.add_argument("--count", required=True, type=int)

    with pytest.raises(ArgumentParsingError, match="invalid int value"):
        parser.parse_args(["--count", "many"])

    assert capsys.readouterr().err == ""


def test_bulk_add_reports_parser_errors_as_json(capsys):
    assert rag_bulk_add.main([]) == 1

    result = json.loads(capsys.readouterr().out)
    assert result["error_code"] == "1"
    assert "the following arguments are required: --request-directory" in result["error_description"]


def test_all_rag_command_parsers_use_raising_parser():
    sources = Path(rag_bulk_add.__file__).parent
    command_sources = []
    for path in sorted(sources.glob("rag_*.py")):
        text = path.read_text()
        if "parse_args(" in text:
            command_sources.append(path.name)
            assert "RaisingArgumentParser(" in text, path.name
            assert "argparse.ArgumentParser(" not in text, path.name

    assert command_sources == [
        "rag_add.py",
        "rag_add_data.py",
        "rag_answer_question.py",
        "rag_bulk_add.py",
        "rag_delete.py",
        "rag_get_docs.py",
        "rag_sync.py",
    ]
