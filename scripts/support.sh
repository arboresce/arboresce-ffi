#!/usr/bin/env bash

check_support() { uv run --python 3.14.7 --no-project python tests/platforms/targets.py --check; }
update_support() { uv run --python 3.14.7 --no-project python tests/platforms/targets.py; }
