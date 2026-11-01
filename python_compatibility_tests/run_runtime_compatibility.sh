#!/usr/bin/env sh

set -eu

project_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$project_root"
if [ "$#" -eq 0 ]; then
    set -- 3.9 3.10 3.11 3.12 3.13 3.14
fi

status=0
for python_version in "$@"; do
    echo "Python $python_version: isolated dependency installation and regression suite"
    if PYTHONDONTWRITEBYTECODE=1 uv run --isolated --locked --all-extras \
        --python "$python_version" --no-python-downloads \
        pytest --strict-markers -p no:cacheprovider; then
        :
    else
        status=1
    fi
done
exit "$status"
