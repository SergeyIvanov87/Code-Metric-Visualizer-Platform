#!/usr/bin/env python3
"""Prepare upload channels, validate arguments, and persist streamed files."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import selectors
import signal
import sys
import tempfile
import time

CHUNK_SIZE = 64 * 1024
UPLOAD_TIMEOUT_EXIT_CODE = 124


def interrupt_upload(_signal, _frame):
    """Unwind through temporary-file cleanup when the executor stops us."""
    raise InterruptedError("upload interrupted")


def validate_request_dir(request_directory):
    request_directory = request_directory.resolve(strict=True)
    if not request_directory.is_dir():
        raise ValueError(f"request directory: {request_directory} is not a directory")


def prepare_api_channel(request_directory):
    """Create and describe the input FIFO owned by this processor."""
    validate_request_dir(request_directory)
    input_path = request_directory / "input"
    os.mkfifo(input_path, 0o620)
    return {"input": str(input_path), "input_type": "FIFO"}


def drain_fifo(input_path, output, initial_timeout, update_timeout):
    """Drain the upload FIFO while enforcing initial and update deadlines."""
    descriptor = os.open(input_path, os.O_RDONLY | os.O_NONBLOCK)
    selector = selectors.DefaultSelector()
    selector.register(descriptor, selectors.EVENT_READ)
    deadline = time.monotonic() + initial_timeout
    bytes_read = 0
    try:
        while True:
            remaining = max(0, deadline - time.monotonic())
            events = selector.select(remaining)
            if not events:
                raise TimeoutError(f"upload FIFO timed out: {input_path}")
            chunk = os.read(descriptor, CHUNK_SIZE)
            bytes_read += len(chunk)
            if chunk:
                output.write(chunk)
                deadline = time.monotonic() + update_timeout
            elif bytes_read != 0:
                return bytes_read
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
    parser.add_argument("--request-directory", required=True, type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check-arguments", action="store_true")
    modes.add_argument("--prepare-api-channel", action="store_true")
    parser.add_argument("--initial-timeout", type=float)
    parser.add_argument("--update-timeout", type=float)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    options = parser.parse_args(argv)
    if not options.check_arguments and not options.prepare_api_channel:
        if options.initial_timeout is None or options.update_timeout is None:
            parser.error("upload processing requires both upload timeouts")
        if options.initial_timeout <= 0 or options.update_timeout <= 0:
            parser.error("upload timeouts must be greater than zero")
    return options


def main(argv=None):
    options = parse_arguments(argv)

    try:
        validate_request_dir(options.request_directory)
    except (OSError, ValueError) as error:
        response(getattr(error, "errno", None) or 1, str(error))
        return 1

    if options.prepare_api_channel:
        try:
            print(json.dumps(prepare_api_channel(options.request_directory)))
            return 0
        except (OSError, ValueError) as error:
            print(str(error), file=sys.stderr)
            return 1

    arguments = options.arguments[1:] if options.arguments[:1] == ["--"] else options.arguments
    captured_bytes_from_input = 0
    try:
        metadata, preferred_filename, destination = validate_arguments(arguments)
        if options.check_arguments:
            response(0, "")
            return 0

        filename = preferred_filename or generated_filename(destination)
        final_path = destination / filename
        if preferred_filename and final_path.exists():
            raise FileExistsError(f"preferred filename already exists: {final_path}")

        descriptor, temporary_name = tempfile.mkstemp(prefix=".upload-", dir=destination)
        try:
            with os.fdopen(descriptor, "wb") as output:
                captured_bytes_from_input = drain_fifo(
                    options.request_directory / "input", output,
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
        response(0, "", received_bytes=captured_bytes_from_input, metadata=metadata, path=str(final_path), size=final_path.stat().st_size)
        return 0
    except TimeoutError:
        return UPLOAD_TIMEOUT_EXIT_CODE
    except (OSError, ValueError, json.JSONDecodeError) as error:
        response(getattr(error, "errno", None) or 1, str(error))
        return 1


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, interrupt_upload)
    raise SystemExit(main())
