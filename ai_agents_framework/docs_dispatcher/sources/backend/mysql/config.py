import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_SETTINGS_DIR = Path("/etc/dispatcher")
BUNDLED_SETTINGS_DIR = Path(__file__).resolve().parents[1] / "dispatcher"


@dataclass(frozen=True)
class MySQLBackendConfig:
    db_login_secret_path: Path
    db_pwd_secret_path: Path
    db_uri: str
    storage_uri: Path
    spec_path: Path


def load_mysql_backend_config() -> MySQLBackendConfig:
    settings_dir = _select_settings_dir()
    spec_path = _resolve_backend_spec_path(settings_dir)
    spec = _load_yaml_mapping(spec_path)

    return MySQLBackendConfig(
        db_login_secret_path=Path(_required_string(spec, "db_login_secret")),
        db_pwd_secret_path=Path(_required_string(spec, "db_pwd_secret")),
        db_uri=_db_uri(spec),
        storage_uri=Path(_required_string(spec, "storage_uri")),
        spec_path=spec_path,
    )


def _select_settings_dir() -> Path:
    configured_dir = Path(os.environ.get("DISPATCHER_SETTINGS_DIR", DEFAULT_SETTINGS_DIR))
    current_path = configured_dir / "current"
    if current_path.exists() or current_path.is_symlink():
        return configured_dir
    return BUNDLED_SETTINGS_DIR


def _resolve_backend_spec_path(settings_dir: Path) -> Path:
    current_path = settings_dir / "current"
    if current_path.is_symlink():
        return current_path.resolve()

    if not current_path.exists():
        raise FileNotFoundError(f"MySQL backend current specification is missing: {current_path}")

    return current_path


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        loaded = _parse_yaml_mapping(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"MySQL backend specification is missing: {path}") from exc

    if not isinstance(loaded, dict):
        raise ValueError(f"MySQL backend specification must be a YAML mapping: {path}")
    return loaded


def _parse_yaml_mapping(content: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"Invalid YAML mapping line {line_number}: {raw_line}")

        key, value = line.split(":", 1)
        key = key.strip()
        value = _strip_yaml_scalar(value.strip())
        if not key:
            raise ValueError(f"Invalid YAML mapping line {line_number}: empty key")
        parsed[key] = value
    return parsed


def _strip_yaml_scalar(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _required_string(spec: dict[str, Any], key: str) -> str:
    value = spec.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"MySQL backend specification requires a non-empty string field: {key}")
    return value


def _db_uri(spec: dict[str, Any]) -> str:
    value = spec.get("mysql_db_uri", spec.get("db_uri"))
    if not isinstance(value, str) or not value:
        raise ValueError("MySQL backend specification requires mysql_db_uri or db_uri")
    return value
