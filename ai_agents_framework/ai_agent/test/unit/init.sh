#!/bin/bash
set -eu
TEST_ROOT=${1:?test root is required}
PACKAGE_ROOT=${2:?package root is required}
export PYTHONPATH="${PACKAGE_ROOT}:/opt/modules"
exec python -m pytest -q "${TEST_ROOT}/cases"
