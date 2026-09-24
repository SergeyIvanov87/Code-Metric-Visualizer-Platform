#!/usr/bin/env python3
"""Prepare upload channels, validate arguments, and persist streamed files."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import sys
import tempfile
import time

CHUNK_SIZE = 64 * 1024
UPLOAD_TIMEOUT_EXIT_CODE = 124


def interrupt_upload(_signal, _frame):
    """Unwind through temporary-file cleanup when the executor stops us."""
    raise InterruptedError("upload interrupted")


def prepare_api_channel(request_directory):
    """Create this processor's input and result FIFOs and describe them."""
    request_directory = request_directory.resolve(strict=True)
    if not request_directory.is_dir():
        raise ValueError("request directory is not a directory")
    input_path = request_directory / "input"
    result_path = request_directory / "async_result"
    os.mkfifo(input_path, 0o620)
    os.mkfifo(result_path, 0o640)
    return {"input_FIFO": str(input_path), "result_FIFO": str(result_path)}


def drain_fifo(input_path, output, initial_timeout, update_timeout):
    """Drain the upload FIFO while enforcing initial and update deadlines."""
    descriptor = os.open(input_path, os.O_RDONLY | os.O_NONBLOCK)
    selector = selectors.DefaultSelector()
    selector.register(descriptor, selectors.EVENT_READ)
    started = False
    deadline = time.monotonic() + initial_timeout
    try:
        while True:
            remaining = max(0, deadline - time.monotonic())
            events = selector.select(remaining)
            if not events:
                raise TimeoutError("upload FIFO timed out")
            chunk = os.read(descriptor, CHUNK_SIZE)
            if chunk:
                output.write(chunk)
                started = True
                deadline = time.monotonic() + update_timeout
            elif started:
                return
            else:
                time.sleep(min(0.02, remaining))
    finally:
        selector.close()
        os.close(descriptor)


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


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check-arguments", action="store_true")
    modes.add_argument("--prepare-api-channel", type=Path)
    modes.add_argument("--input-path", type=Path)
    parser.add_argument("--initial-timeout", type=float)
    parser.add_argument("--update-timeout", type=float)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    options = parser.parse_args(argv)
    if options.input_path is not None:
        if options.initial_timeout is None or options.update_timeout is None:
            parser.error("--input-path requires both upload timeouts")
        if options.initial_timeout <= 0 or options.update_timeout <= 0:
            parser.error("upload timeouts must be greater than zero")
    return options


def main(argv=None):
    options = parse_arguments(argv)
    if options.prepare_api_channel is not None:
        try:
            print(json.dumps(prepare_api_channel(options.prepare_api_channel)))
            return 0
        except (OSError, ValueError) as error:
            print(str(error), file=sys.stderr)
            return 1

    arguments = options.arguments[1:] if options.arguments[:1] == ["--"] else options.arguments
    try:
        metadata, preferred_filename, destination = validate_arguments(arguments)
        if options.check_arguments:
            response(0, "")
            return 0

        filename = preferred_filename or generated_filename(destination)
        final_path = destination / filename
        if preferred_filename and final_path.exists():
            raise FileExistsError(f"preferred filename already exists: {filename}")

        descriptor, temporary_name = tempfile.mkstemp(prefix=".upload-", dir=destination)
        try:
            with os.fdopen(descriptor, "wb") as output:
                if options.input_path is None:
                    shutil.copyfileobj(sys.stdin.buffer, output)
                else:
                    drain_fifo(
                        options.input_path, output,
                        options.initial_timeout, options.update_timeout,
                    )
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
    except TimeoutError:
        return UPLOAD_TIMEOUT_EXIT_CODE
    except (OSError, ValueError, json.JSONDecodeError) as error:
        response(getattr(error, "errno", None) or 1, str(error))
        return 1


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, interrupt_upload)
    raise SystemExit(main())
