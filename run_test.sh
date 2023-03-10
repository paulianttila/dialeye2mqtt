#!/usr/bin/env bash

# exit when any command fails
set -e

PWD=$(pwd)

echo "Current folder: ${PWD}"

python -m pytest tests/
