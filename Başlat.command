#!/bin/sh
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python3 ]; then
  echo 'Önce proje klasöründe python3 scripts/setup.py çalıştırın.'
  read -r answer
  exit 1
fi
exec .venv/bin/python3 scripts/run.py
