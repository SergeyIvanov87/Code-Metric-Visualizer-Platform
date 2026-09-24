#!/usr/bin/env python3
"""Validate upload arguments and persist stdin in the selected directory."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import tempfile


def interrupt_upload(_signal, _frame):
    """Unwind through temporary-file cleanup when the executor stops us."""
    raise InterruptedError("upload interrupted")


def value_of(arguments, name, default=None):
    for index, argument in enumerate(arguments[:-1]):
        if argument.lstrip("-") == name:
            return arguments[index + 1]
    if default is not None:
        return default
    raise ValueError(f"missing {name}")


def normalize_empty(value):
    """Normalize quoted empty values preserved by API parameter files."""
    return "" if value in ("", "\"\"", "''") else value


def validate_arguments(arguments):
    metadata_text = normalize_empty(value_of(arguments, "metadata", ""))
    metadata = json.loads(metadata_text) if metadata_text else {}
    if not isinstance(metadata, dict):
        raise ValueError(
            f"metadata must be empty or a JSON object; got {metadata!r} "
            f"from raw value {metadata_text!r}"
        )

    preferred_filename = normalize_empty(value_of(arguments, "preferred_filename", ""))
    if preferred_filename and Path(preferred_filename).name != preferred_filename:
        raise ValueError(
            f"preferred_filename must be a base filename; got {preferred_filename!r}"
        )

    destination = Path(value_of(arguments, "destination")).resolve(strict=True)
    if not destination.is_dir():
        raise ValueError("destination must be an existing directory")
    if not os.access(destination, os.W_OK):
        raise ValueError("destination is not writable")
    return metadata, preferred_filename, destination


def generated_filename(destination):
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%f")[:-3] + "Z"
    base = f"uploaded.{timestamp}"
    candidate = base
    suffix = 0
    while (destination / candidate).exists():
        suffix += 1
        candidate = f"{base}.{suffix}"
    return candidate


def response(error_code, error_description, **values):
    print(json.dumps({
        "error_code": str(error_code),
        "error_description": error_description,
        **values,
    }))


def main():
    checking = sys.argv[1:2] == ["--check-arguments"]
    arguments = sys.argv[2:] if checking else sys.argv[1:]
    try:
        metadata, preferred_filename, destination = validate_arguments(arguments)
        if checking:
            response(0, "")
            return 0

        filename = preferred_filename or generated_filename(destination)
        final_path = destination / filename
        if preferred_filename and final_path.exists():
            raise FileExistsError(f"preferred filename already exists: {filename}")

        descriptor, temporary_name = tempfile.mkstemp(prefix=".upload-", dir=destination)
        try:
            with os.fdopen(descriptor, "wb") as output:
                shutil.copyfileobj(sys.stdin.buffer, output)
                output.flush()
                os.fsync(output.fileno())
            # Linking makes creation non-overwriting and atomic. Retry the generated
            # name if another upload claimed the same millisecond concurrently.
            while True:
                try:
                    os.link(temporary_name, final_path)
                    break
                except FileExistsError:
                    if preferred_filename:
                        raise
                    filename = generated_filename(destination)
                    final_path = destination / filename
            os.unlink(temporary_name)
        except BaseException:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise
        response(0, "", metadata=metadata, path=str(final_path), size=final_path.stat().st_size)
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        response(getattr(error, "errno", None) or 1, str(error))
        return 1


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, interrupt_upload)
    raise SystemExit(main())
