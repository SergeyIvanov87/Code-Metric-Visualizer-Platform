"""Check routing without loading embedding models or contacting Chroma."""

import base64
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import rag_add
import rag_add_data
from fs_api_wrappers import rag_add_file


@pytest.mark.parametrize("failure_stage", [None, "chunks", "chroma"])
@pytest.mark.parametrize("uri", [None, "/stage/file with spaces.txt"])
@pytest.mark.parametrize("preserveOriginal", [0, 1])
def test_main_selects_uri_or_data_endpoint(monkeypatch, tmp_path, uri, preserveOriginal, failure_stage):
    schemas = {
        f"domain_ai_agent_rag_dispatcher_{name}_v1": name
        for name in ("put_doc", "put_doc_data", "attach_doc_chunk", "delete_doc")
    }
    monkeypatch.setattr("fs_api_wrappers.get_doc_dispatcher_queries", lambda *args: schemas)
    processor = rag_add if uri else rag_add_data
    monkeypatch.setattr(processor, "create_api_query_interruptible", lambda root, schema, session: schema)
    if uri:
        uri = str(tmp_path / "file with spaces.txt")
        __import__("pathlib").Path(uri).write_bytes(b"text\r\n")
    collection = Mock()
    client = Mock()
    client.get_or_create_collection.return_value = collection
    monkeypatch.setitem(sys.modules, "chromadb", SimpleNamespace(HttpClient=lambda **kwargs: client))
    monkeypatch.setitem(sys.modules, "langchain_chroma", SimpleNamespace(Chroma=Mock()))
    model = SimpleNamespace(embed_documents=lambda texts: [[0.1]])
    monkeypatch.setitem(sys.modules, "embedding_model", SimpleNamespace(get_embedding_model=lambda: model))
    split = Mock(return_value=[SimpleNamespace(page_content="text")])
    monkeypatch.setattr(processor, "split_document", split)
    put = Mock(return_value={"unique_id": 123})
    monkeypatch.setattr(rag_add, "execute_put_doc_query", put)
    monkeypatch.setattr(processor, "execute_attach_doc_chunks_query", lambda *args: (["456"], [{"doc_id": 123}]))
    monkeypatch.setattr(rag_add_data, "execute_put_doc_data_query", put)
    rollback = Mock()
    monkeypatch.setattr(processor, "execute_delete_doc_query", rollback)
    if failure_stage == "chunks":
        monkeypatch.setattr(processor, "execute_attach_doc_chunks_query", Mock(side_effect=RuntimeError("chunk failure")))
    if failure_stage == "chroma":
        collection.add.side_effect = RuntimeError("chroma failure")
    if failure_stage:
        with pytest.raises(RuntimeError, match="Rollback was finished"):
            if uri:
                rag_add.main("/api", "domain", "outer", "db", 8000, uri, "metadata", "txt", 20, preserveOriginal=preserveOriginal)
            else:
                rag_add_data.main("/api", "domain", "outer", "db", 8000, "text", "metadata", "txt", 20)
        assert rollback.call_args.args[3] == 123
        return
    if uri:
        result = rag_add.main("/api", "domain", "outer", "db", 8000, uri, "metadata", "txt", 20,
                              preserveOriginal=preserveOriginal)
    else:
        result = rag_add_data.main("/api", "domain", "outer", "db", 8000, "text", "metadata", "txt", 20)
    assert result == (123, ["456"])
    assert split.call_args.args[0] == ("text\r\n" if uri else "text")
    assert put.call_args.args[0] == ("put_doc" if uri else "put_doc_data")
    if uri:
        assert put.call_args.kwargs["preserveOriginal"] == preserveOriginal
        assert put.call_args.args[3] == uri
    else:
        assert put.call_args.args[3] == base64.b64encode(b"text").decode()
    assert collection.add.call_args.kwargs["embeddings"] == [[0.1]]


@pytest.mark.parametrize("preserveOriginal", ["0", "1"])
def test_bulk_worker_forwards_preservation_policy(monkeypatch, tmp_path, preserveOriginal):
    execute = Mock(return_value={"error_code": 0, "doc_id": 123})
    monkeypatch.setattr("fs_api_wrappers._execute_json_query", execute)
    rag_add_file(object(), "session", {"metadata": "", "preserveOriginal": preserveOriginal},
                 tmp_path, "file with spaces.txt", 1)
    assert f"preserveOriginal={preserveOriginal}" in execute.call_args.args[3]


def test_data_generator_passes_only_data_query_arguments(tmp_path):
    import importlib.util
    import io
    import json
    import os
    from pathlib import Path
    import subprocess
    from api_fs_args import write_args
    from api_fs_conventions import get_api_request_plain_params

    root = Path('/repo')
    spec = importlib.util.spec_from_file_location('agent_generator', root / 'ai_agents_framework/ai_agent/sources/api_generator.py')
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    schema = json.loads((root / 'ai_agents_framework/ai_agent/API/rag_add_data.json').read_text())
    api = tmp_path / 'api'
    api.mkdir()
    write_args(api, get_api_request_plain_params(schema['Params']))
    stub = tmp_path / 'rag_add_data.py'
    stub.write_text('#!/usr/bin/env python3\nimport json,sys\nprint(json.dumps({"arguments":sys.argv[1:],"data":sys.stdin.read()}))\n')
    stub.chmod(0o755)
    output = io.StringIO()
    generator.make_script_rag_add_data(output, 'json')
    executor = tmp_path / 'executor.sh'
    executor.write_text(output.getvalue())
    data = 'aGVsbG8=' * 1000
    metadata = 'with spaces "quoted" 日本語'
    arguments = ' '.join(f'{key}={json.dumps(value, ensure_ascii=False)}' for key, value in {
        'SESSION_ID':'data', 'doc_data':data, 'doc_type':'txt', 'metadata':metadata,
        'URI':'/must/not/be/forwarded', 'preserveOriginal':'0',
    }.items())
    completed = subprocess.run(['bash', str(executor), str(api), arguments],
        env={**os.environ, 'WORK_DIR':str(tmp_path), 'VECTOR_DB_HOST':'db',
             'VECTOR_DB_PORT':'8000', 'SHARED_API_DIR':'/api', 'MAIN_SERVICE_NAME':'domain'},
        capture_output=True, text=True, check=True)
    result = json.loads(completed.stdout)
    assert result['data'] == data
    assert result['arguments'][result['arguments'].index('--metadata') + 1] == metadata
    assert '--URI' not in result['arguments']
    assert '--preserveOriginal' not in result['arguments']
