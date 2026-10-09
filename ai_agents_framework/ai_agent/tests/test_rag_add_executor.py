import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(ROOT / 'common/modules'))
spec = importlib.util.spec_from_file_location('generator', ROOT / 'ai_agents_framework/ai_agent/sources/api_generator.py')
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


@pytest.mark.parametrize('metadata', ['', '""', 'team docs', '"team docs"'])
@pytest.mark.parametrize('override', [None, 'test compose-functional.dev.yaml', '\\"\\" test compose-functional.dev.yaml', '"aaa" test data poem_02.txt'])
def test_generated_add_executor_preserves_argv(tmp_path, metadata, override):
    api = tmp_path / 'api'
    api.mkdir()
    for name, value in [('0.-URI', ''), ('1.-metadata', metadata), ('2.-doc_type', 'txt'), ('3.doc_data', '')]:
        (api / name).write_text(value)
    stub = tmp_path / 'rag_add.py'
    stub.write_text('#!' + sys.executable + '\nimport argparse,json,sys\np=argparse.ArgumentParser()\np.add_argument("--session_id")\np.add_argument("-db_host")\np.add_argument("-db_port")\np.add_argument("-URI")\np.add_argument("-metadata")\np.add_argument("-doc_type")\np.add_argument("shared_api_dir")\np.add_argument("main_service_name")\na=p.parse_args(); print(json.dumps(vars(a)))\n')
    stub.chmod(0o755)
    script = io.StringIO()
    generator.make_script_rag_add(script)
    uri = str(tmp_path / 'file with spaces.yaml')
    query = 'SESSION_ID=bulk -URI=' + json.dumps(uri)
    if override is not None:
        query += ' -metadata=' + json.dumps(override)
    completed = subprocess.run(['bash', '-c', script.getvalue(), 'executor', str(api), query],
        env={**os.environ, 'WORK_DIR': str(tmp_path), 'SHARED_API_DIR': '/api',
             'MAIN_SERVICE_NAME': 'api.pmccabe_collector.restapi.org',
             'VECTOR_DB_HOST': 'rag-db', 'VECTOR_DB_PORT': '8000'},
        text=True, capture_output=True, check=True)
    result = json.loads(completed.stdout)
    assert result['URI'] == uri
    assert result['metadata'] == (override if override is not None else
                                 '' if metadata in ('', '""') else 'team docs')
    assert result['shared_api_dir'] == '/api'
    assert result['main_service_name'] == 'api.pmccabe_collector.restapi.org'
