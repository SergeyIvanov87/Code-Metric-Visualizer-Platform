#!/bin/bash
set -eu
TEST_ROOT=${1:?test root is required}
PACKAGE_ROOT=${2:?package root is required}
export PYTHONPATH="${PACKAGE_ROOT}:${PACKAGE_ROOT}/backend:/opt/modules"
exec python3 -m pytest -q "${TEST_ROOT}/cases"
