#!/bin/bash

set -euo pipefail
IFS=$'\n\t'

function format() {
    echo "Running format..."
    find automudae/ -name '*.py' -exec autoflake {} \
        --in-place \
        --remove-all-unused-imports \
        --remove-unused-variables \
        --remove-duplicate-keys \
        --verbose \
        \;
    isort automudae/
    black automudae/
}

function lint() {
    echo "Running lint..."
    mypy automudae/

}

function check() {
    echo "Running check..."
    pyflakes automudae/
}

if [ "$1" == "format" ]; then
    format
elif [ "$1" == "lint" ]; then
    lint
elif [ "$1" == "check" ]; then
    check
elif [ "$1" == "all" ]; then
    format
    lint
    check
else
    echo "Usage: $0 {format|lint|check|all}"
    exit 1
fi
