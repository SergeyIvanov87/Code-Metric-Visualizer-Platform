from pathlib import Path
import json
import sys
from types import SimpleNamespace
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sources'))
import inference_config as inference


def profile(mode):
    return inference.load_inference_config(ROOT / 'config' / f'inference.{mode}.json')


def test_cpu_does_not_probe_gpu():
    assert inference.model_options(profile('cpu'), object())['n_gpu_layers'] == 0


@pytest.mark.parametrize('mode,backend,description', [
    ('nvidia', 'CUDA', 'NVIDIA RTX'), ('intel', 'Vulkan', 'Intel Graphics')])
def test_gpu_selection(monkeypatch, mode, backend, description):
    calls = []
    monkeypatch.setattr(inference, 'gpu_devices', lambda lib, name: calls.append(name) or [description])
    lib = SimpleNamespace(llama_supports_gpu_offload=lambda: True, llama_backend_init=lambda: None)
    options = inference.model_options(profile(mode), lib)
    assert calls == [backend]
    assert options['n_gpu_layers'] == -1
    assert options['model_kwargs']['split_mode'] == 0


def test_cpu_build_rejects_gpu():
    with pytest.raises(RuntimeError, match='no GPU backend'):
        inference.model_options(profile('nvidia'), SimpleNamespace(llama_supports_gpu_offload=lambda: False))


@pytest.mark.parametrize('devices', [[], ['AMD Radeon']])
def test_intel_rejects_missing_or_wrong_device(monkeypatch, devices):
    monkeypatch.setattr(inference, 'gpu_devices', lambda *args: devices)
    lib = SimpleNamespace(llama_supports_gpu_offload=lambda: True, llama_backend_init=lambda: None)
    with pytest.raises(RuntimeError):
        inference.model_options(profile('intel'), lib)


@pytest.mark.parametrize('key,value', [('n_gpu_layers', 0), ('n_ctx', -1), ('main_gpu', -1), ('n_threads', 0)])
def test_invalid_gpu_config(tmp_path, key, value):
    config = profile('intel')
    config[key] = value
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError):
        inference.load_inference_config(path)


def test_environment_config(monkeypatch):
    monkeypatch.setenv('AI_AGENT_INFERENCE_CONFIG', str(ROOT / 'config/inference.nvidia.json'))
    assert inference.load_inference_config()['accelerator'] == 'nvidia'
