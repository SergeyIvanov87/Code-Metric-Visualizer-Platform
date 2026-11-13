"""Exercise range requests through the real dispatcher and SQLite backend."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from contextlib import nullcontext
from interfaces_impl.access.mysql.database import Base
from interfaces_impl.access.mysql import MysqlAccessRecordEntry
from interfaces_impl.store.persistent import PersistentStorageRecordEntry
from mysql_persistent.backend import MysqlPersistentBackend

SOURCES = Path("/package")
if not SOURCES.is_dir():
    SOURCES = Path(__file__).resolve().parents[3] / "sources"
MODULES = Path("/opt/modules") if SOURCES == Path("/package") else SOURCES.parents[2] / "common/modules"


@pytest.fixture
def document_backend(tmp_path):
    storage = tmp_path / "storage"
    storage.mkdir()
    db_uri = f"sqlite:///{tmp_path / 'docs.db'}"
    engine = create_engine(db_uri)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    backend = MysqlPersistentBackend(MysqlAccessRecordEntry(session), PersistentStorageRecordEntry(storage))
    for name, content in [("one.txt", b"first"), ("two.txt", b"second")]:
        backend.put_doc_by_data(name, content, doc_type="txt")
    settings = tmp_path / "settings"
    settings.mkdir()
    (settings / "current").write_text(
        f"name: mysql_persistent\ndb_login_secret: unused\ndb_pwd_secret: unused\n"
        f"mysql_db_uri: {db_uri}\nstorage_uri: {storage}\n"
    )
    env = os.environ | {
        "DISPATCHER_SETTINGS_DIR": str(settings),
        "PYTHONPATH": os.pathsep.join([str(MODULES), str(SOURCES), str(SOURCES / "backend")]),
        "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
    }
    yield session, storage, env
    session.close()
    engine.dispose()


def run_dispatcher(env, command, *args):
    result = subprocess.run(
        [sys.executable, str(SOURCES / f"{command}.py"), *args],
        env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    return result.stdout


def test_info_ranges_include_missing_ids_once_in_request_order(document_backend):
    session, storage, env = document_backend
    direct = MysqlPersistentBackend(MysqlAccessRecordEntry(session), PersistentStorageRecordEntry(storage)).get_document_info("2-4,1-3")
    result = json.loads(run_dispatcher(env, "get_doc_info", "-doc_ids", "2-4,1-3"))
    assert result == {"error_code": 0, **direct}
    assert result["found"] == [2, 1]
    assert result["not_found"] == [3, 4]
    assert list(key for key in result if key.isdigit()) == ["2", "3", "4", "1"]


def test_read_ranges_keep_valid_content_and_report_missing_ids(document_backend):
    session, storage, env = document_backend
    direct = MysqlPersistentBackend(MysqlAccessRecordEntry(session), PersistentStorageRecordEntry(storage)).read_ids("2-4,1-3")
    assert list(direct) == [2, 3, 4, 1]
    result = json.loads(run_dispatcher(env, "read_id", "id", "2-4,1-3"))
    assert result["error_code"] == 0
    assert result["not_found"] == [3, 4]
    assert result["unprocessed"] == []
    assert result["records"]["2"]["context"] == "second"
    assert result["records"]["1"]["context"] == "first"
    assert run_dispatcher(env, "read_id", "id", "1") == "first"
    assert run_dispatcher(env, "read_id", "id", "999") == "<Not found ID>"


def test_delete_ranges_overlap_and_missing_ids_do_not_fail(document_backend):
    _, storage, env = document_backend
    result = json.loads(run_dispatcher(env, "delete_doc", "-ids=2-4,1-3", "SESSION_ID=test"))
    assert result == {
        "error_code": 0,
        "deleted from DB": 2,
        "deleted from storage": 2,
        "not_found": [3, 4],
    }
    assert list(storage.iterdir()) == []
    again = json.loads(run_dispatcher(env, "delete_doc", "-ids", "1-3,2-4"))
    assert again["error_code"] == 0
    assert again["not_found"] == [1, 2, 3, 4]


@pytest.mark.parametrize("command,option,method", [
    ("delete_doc", "-ids", "delete_records"),
    ("get_doc_info", "-doc_ids", "get_document_info"),
    ("read_id", "id", "read_ids"),
])
def test_frontends_pass_large_ranges_without_expansion(monkeypatch, capsys, command, option, method):
    monkeypatch.syspath_prepend(str(SOURCES))
    spec = importlib.util.spec_from_file_location(f"dispatcher_{command}", SOURCES / f"{command}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    selection = "2-1000000000, 7"
    monkeypatch.setattr(sys, "argv", [command, option, selection])
    def operation(value):
        assert value == selection
        if command == "delete_doc":
            return 0, 0, []
        return {}
    backend = SimpleNamespace(**{method: operation})
    monkeypatch.setattr(module, "BackendDispatcher", lambda: SimpleNamespace(get_backend=lambda: nullcontext(backend)))
    assert module.main() == 0
    assert json.loads(capsys.readouterr().out)["error_code"] == 0


@pytest.mark.parametrize("command,option", [
    ("delete_doc", "-ids"), ("get_doc_info", "-doc_ids"), ("read_id", "id"),
])
def test_generated_executor_preserves_ranges_with_spaces(tmp_path, command, option):
    import io
    spec = importlib.util.spec_from_file_location("dispatcher_generator", SOURCES / "api_generator.py")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    script = io.StringIO()
    getattr(generator, f"make_{command}")(script)
    api_node = tmp_path / "api"
    api_node.mkdir()
    (api_node / f"0.{option}").write_text("")
    processor = tmp_path / f"{command}.py"
    processor.write_text("#!/usr/bin/env python\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n")
    processor.chmod(0o755)
    result = subprocess.run(
        ["bash", "-c", script.getvalue(), "executor", str(api_node), f'{option}="1 - 5, 7"'],
        env=os.environ | {"WORK_DIR": str(tmp_path)},
        capture_output=True, text=True, check=True,
    )
    assert json.loads(result.stdout) == [option, "1 - 5, 7"]
