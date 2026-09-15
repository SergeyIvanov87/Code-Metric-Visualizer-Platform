#!/bin/sh
set -eu
cd /tests
pytest -s "$@"
