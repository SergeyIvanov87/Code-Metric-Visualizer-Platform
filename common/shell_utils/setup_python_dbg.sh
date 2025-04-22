#!/usr/bin/env bash

PY_SRC_DOWNLOAD_PATH=${1}

if [ -z ${PY_SRC_DOWNLOAD_PATH} ]; then
    PY_SRC_DOWNLOAD_PATH=./
PY_VERS=$(python --version | cut -d' ' -f2)
wget https://www.python.org/ftp/python/${VERS}/Python-${VERS}.tgz

#dirname `find ${PY_SRC_DOWNLOAD_PATH} | grep libpython.py`
PYDEBUG_LIB_RELPATH=$(find ./ | grep libpython.py)
PYDEBUG_MODULE_ABS_PATH=$(dirname `find / | grep ${PYDEBUG_LIB_RELPATH}`)

if [ -z ${PYDEBUG_MODULE_ABS_PATH} ]; then
    echo -e "$PYDEBUG_MODULE_ABS_PATH NOT FOUND! ${PYDEBUG_MODULE_ABS_PATH}"
else
    echo -e "PYDEBUG_MODULE_ABS_PATH has been FOUND: ${PYDEBUG_MODULE_ABS_PATH}..."
    export PYTHONPATH=${PYTHONPATH}:${PYDEBUG_MODULE_ABS_PATH}
    echo -e "To launch GDB please do:"
    echo -e "export PYTHONPATH=${PYTHONPATH}"
    echo -e "gdb <args>"
    echo -e "(gdb) python import libpython"
    echo -e "(gdb) py-bt"
    echo -e "(gdb) py-list"
    echo -e "(gdb) py-p"
    echo -e "(gdb) <continue debugging>"
fi
