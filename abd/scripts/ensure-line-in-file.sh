#!/usr/bin/env bash

set -e

CREATE_IF_MISSING=${CREATE_IF_MISSING:-false}

ensure_line() {
    local file="$1"
    local line="$2"

    # Create file if missing?
    if [ "$CREATE_IF_MISSING" = "true" ] && [ ! -f "$file" ]; then
        printf '%s\n' "$line" > "$file"
        return 0
    fi

    # Check if the exact line already exists
    if grep -Fxq -- "$line" "$file"; then
        return 0    # no change
    fi

    # Ensure trailing newline before appending
    if [ -s "$file" ] && [ "$(tail -c1 "$file" | wc -l)" -eq 0 ]; then
        printf '\n' >> "$file"
    fi

    printf '%s\n' "$line" >> "$file"
    return 0
}

usage() {
    echo "Usage: $0 <file> <line>"
    exit 1
}

if [ "$#" -ne 2 ]; then
    usage
fi
ensure_line "$1" "$2"
