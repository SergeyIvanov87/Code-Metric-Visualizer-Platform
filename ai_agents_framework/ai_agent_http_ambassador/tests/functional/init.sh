#!/bin/sh
set -eu
exec python -m unittest discover -v /tests
