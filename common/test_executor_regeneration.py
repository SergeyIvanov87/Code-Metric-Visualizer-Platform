import os
from pathlib import Path
import subprocess
import sys


def test_builder_replaces_persisted_executors_only_when_requested(tmp_path):
    root = Path(__file__).parent
    schema = tmp_path / 'schema'
    schema.mkdir()
    (schema / 'example.json').write_text('{"Content-Type":"application/json","Method":"POST","Query":"example","Params":{}}')
    generator = tmp_path / 'source'
    generator.mkdir()
    (generator / 'api_generator.py').write_text('def generate(script, extension):\n    script.write("#!/bin/bash\\necho current\\n")\ndef get():\n    return {"example": generate}, {}\n')
    out = tmp_path / 'generated'
    command = [sys.executable, str(root / 'build_api_executors.py'), str(schema), str(generator), '-o', str(out)]
    env = {**os.environ, 'PYTHONPATH': str(root / 'modules')}
    subprocess.run(command, env=env, check=True, capture_output=True)
    executor, = out.iterdir()
    executor.write_text('#!/bin/bash\necho stale\n')
    subprocess.run(command, env=env, check=True, capture_output=True)
    assert 'stale' in executor.read_text()
    subprocess.run([*command, '--overwrite'], env=env, check=True, capture_output=True)
    assert 'current' in executor.read_text()
    assert os.access(executor, os.X_OK)
