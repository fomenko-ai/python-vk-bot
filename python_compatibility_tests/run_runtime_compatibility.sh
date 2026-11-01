#!/usr/bin/env sh

set -eu

project_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$project_root"
if [ "$#" -eq 0 ]; then
    installations=$(uv python list --only-installed --offline --no-python-downloads 'cpython>=3.14')
    versions=$(printf '%s\n' "$installations" | awk 'NF && !seen[$1]++ { print $1 }')
    if [ -z "$versions" ]; then
        echo "NOT CHECKED: no installed CPython >=3.14 found" >&2
        exit 1
    fi
    # uv installation keys contain no whitespace; split them into requests.
    set -f
    set -- $versions
fi

status=0
for python_version in "$@"; do
    if interpreter=$(uv python find --system --no-project --no-python-downloads "$python_version"); then
        echo "Python $python_version: isolated dependency installation and regression suite"
        if PYTHONDONTWRITEBYTECODE=1 uv run --isolated --locked --all-extras --group dev \
            --python "$interpreter" --no-python-downloads \
            python -m pytest --strict-markers -p no:cacheprovider; then
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
