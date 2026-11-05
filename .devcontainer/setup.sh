#!/usr/bin/env bash
set -euo pipefail

python -m pip install --disable-pip-version-check -e '.[dev]'
python -m playwright install --with-deps chromium
python -m compileall -q src
printf '%s\n' 'Development environment ready. Run: python -m pytest -o addopts="" -q'
printf '%s\n' 'Hermes runtime/model authentication and private profiles are configured separately.'
