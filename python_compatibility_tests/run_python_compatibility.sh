#!/usr/bin/env sh

set -eu

project_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
if [ "$#" -eq 0 ]; then
    set -- 3.9 3.10 3.11 3.12 3.13 3.14
fi

status=0
for python_version in "$@"; do
    if interpreter=$(uv python find --system --no-python-downloads "$python_version"); then
        if "$interpreter" "$project_root/python_compatibility_tests/check_syntax.py"; then
            :
        else
            status=1
        fi
    else
        echo "NOT CHECKED: Python $python_version is unavailable" >&2
        status=1
    fi
done
exit "$status"
