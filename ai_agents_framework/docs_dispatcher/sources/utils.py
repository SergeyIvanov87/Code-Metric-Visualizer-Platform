from pathlib import Path

def get_impl_procedure_name(caller_script_path):
    return Path(caller_script_path).stem
