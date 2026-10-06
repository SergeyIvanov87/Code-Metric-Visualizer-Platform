"""Configuration and strict backend validation for GGUF inference."""
import ctypes
import json
import multiprocessing
import os
from pathlib import Path

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config/inference.cpu.json"


def load_inference_config(path=None):
    path = Path(path or os.environ.get("AI_AGENT_INFERENCE_CONFIG", DEFAULT_CONFIG))
    with path.open(encoding="utf-8") as source:
        config = json.load(source)
    expected = {"accelerator", "n_gpu_layers", "main_gpu", "n_ctx", "n_batch", "n_threads"}
    if set(config) != expected:
        raise ValueError(f"Inference config must contain exactly {sorted(expected)}")
    if config["accelerator"] not in ("cpu", "nvidia", "intel"):
        raise ValueError("accelerator must be cpu, nvidia, or intel")
    for key in ("n_gpu_layers", "main_gpu", "n_ctx", "n_batch"):
        if type(config[key]) is not int:
            raise ValueError(f"{key} must be an integer")
    if config["main_gpu"] < 0 or config["n_ctx"] < 1 or config["n_batch"] < 1:
        raise ValueError("Invalid device, context, or batch size")
    layers = config["n_gpu_layers"]
    if config["accelerator"] == "cpu" and layers != 0:
        raise ValueError("CPU inference requires n_gpu_layers=0")
    if config["accelerator"] != "cpu" and (layers == 0 or layers < -1):
        raise ValueError("GPU inference requires n_gpu_layers=-1 or a positive count")
    threads = config["n_threads"]
    if threads is not None and (type(threads) is not int or threads < 1):
        raise ValueError("n_threads must be null or a positive integer")
    config["n_threads"] = threads or max(1, multiprocessing.cpu_count() - 1)
    return config


def model_options(config, llama_cpp):
    accelerator = config["accelerator"]
    if accelerator != "cpu":
        if not llama_cpp.llama_supports_gpu_offload():
            raise RuntimeError("GPU requested but llama-cpp-python has no GPU backend")
        # Device enumeration checks actual accessible devices, not just build flags.
        llama_cpp.llama_backend_init()
        expected = "CUDA" if accelerator == "nvidia" else "Vulkan"
        devices = gpu_devices(llama_cpp, expected)
        if config["main_gpu"] >= len(devices):
            raise RuntimeError(f"No accessible {expected} GPU at index {config['main_gpu']}")
        if accelerator == "intel" and "intel" not in devices[config["main_gpu"]].lower():
            raise RuntimeError("Selected Vulkan GPU is not an Intel device")
    options = {key: config[key] for key in
               ("n_gpu_layers", "main_gpu", "n_ctx", "n_batch", "n_threads")}
    # Keep all offloaded layers on the selected GPU rather than splitting them.
    options["model_kwargs"] = {"split_mode": 0}
    return options


def gpu_devices(llama_cpp, expected):
    """Use the bundled ggml C API (not exposed by Python bindings in 0.3.16)."""
    library = llama_cpp.llama_cpp._lib
    signatures = {
        "ggml_backend_dev_count": ([], ctypes.c_size_t),
        "ggml_backend_dev_get": ([ctypes.c_size_t], ctypes.c_void_p),
        "ggml_backend_dev_type": ([ctypes.c_void_p], ctypes.c_int),
        "ggml_backend_dev_backend_reg": ([ctypes.c_void_p], ctypes.c_void_p),
        "ggml_backend_reg_name": ([ctypes.c_void_p], ctypes.c_char_p),
        "ggml_backend_dev_description": ([ctypes.c_void_p], ctypes.c_char_p),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(library, name)
        function.argtypes, function.restype = arguments, result
    devices = []
    for index in range(library.ggml_backend_dev_count()):
        device = library.ggml_backend_dev_get(index)
        # ggml GPU and integrated GPU device types.
        if library.ggml_backend_dev_type(device) not in (1, 2):
            continue
        backend = library.ggml_backend_dev_backend_reg(device)
        name = library.ggml_backend_reg_name(backend).decode()
        description = library.ggml_backend_dev_description(device).decode()
        if name.lower() == expected.lower():
            devices.append(description)
    return devices
