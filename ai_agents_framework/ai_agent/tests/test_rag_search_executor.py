import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "common/modules"))
spec = importlib.util.spec_from_file_location(
    "generator",
    ROOT / "ai_agents_framework/ai_agent/sources/api_generator.py",
)
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


def test_generated_search_executor_preserves_spaces_and_empty_avoid_regex(
    tmp_path,
):
    api = tmp_path / "api"
    api.mkdir()
    defaults = [
        ("0.search", ""),
        ("1.score_min", "0.0"),
        ("2.score_max", "1.0"),
        ("3.count", "5"),
        ("4.collection_use_regex", ".*"),
        ("5.collection_avoid_regex", ""),
    ]
    for name, value in defaults:
        (api / name).write_text(value)

    stub = tmp_path / "rag_search.py"
    stub.write_text(
        "#!/usr/bin/env python3\n"
        "import json,sys\n"
        "print(json.dumps(sys.argv[1:]))\n"
    )
    stub.chmod(0o755)
    executor = io.StringIO()
    generator.make_script_rag_search(executor)
    request = (
        'SESSION_ID=search-session search="words with spaces" '
        'collection_use_regex="^team docs$"'
    )
    completed = subprocess.run(
        ["bash", "-c", executor.getvalue(), "executor", str(api), request],
        env=os.environ
        | {
            "WORK_DIR": str(tmp_path),
            "SHARED_API_DIR": "/api",
            "MAIN_SERVICE_NAME": "api.pmccabe_collector.restapi.org",
            "VECTOR_DB_HOST": "rag-db",
            "VECTOR_DB_PORT": "8000",
        },
        text=True,
        capture_output=True,
        check=True,
    )
    arguments = json.loads(completed.stdout)

    assert "--session_id=search-session" in arguments
    assert arguments[-12:] == [
        "search", "words with spaces",
        "score_min", "0.0",
        "score_max", "1.0",
        "count", "5",
        "collection_use_regex", "^team docs$",
        "collection_avoid_regex", "",
    ]
