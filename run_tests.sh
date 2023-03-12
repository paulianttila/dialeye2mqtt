#!/usr/bin/env bash

# exit when any command fails
set -e

PWD=$(pwd)

echo "Current folder: ${PWD}"

export PYTHONPATH=${PYTHONPATH}:${PWD}/src/

python -m pytest tests/
