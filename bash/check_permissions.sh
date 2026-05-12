#!/usr/bin/env bash

# Usage: ./check_permissions.sh <input_file>
# Input file format: /path/to/file username groupname permissions
# Example: /opt/path/to/file username1 groupname1 -rw-rw-r--

INPUT_FILE="${1:-}"

if [[ -z "$INPUT_FILE" ]]; then
    echo "Usage: $0 <input_file>" >&2
    exit 1
fi

if [[ ! -f "$INPUT_FILE" ]]; then
    echo "Error: input file '$INPUT_FILE' not found" >&2
    exit 1
fi

while IFS= read -r line || [[ -n "$line" ]]; do
    # Skip empty lines and comments
    [[ -z "$line" || "$line" =~ ^# ]] && continue

    # Parse fields (collapse multiple spaces)
    read -r path exp_user exp_group exp_perms <<< "$line"

    # Validate we have all fields
    if [[ -z "$path" || -z "$exp_user" || -z "$exp_group" || -z "$exp_perms" ]]; then
        echo "WARN: skipping malformed line: $line" >&2
        continue
    fi

    # Check existence
    if [[ ! -e "$path" ]]; then
        echo "$path => NOT FOUND (expected user=$exp_user group=$exp_group perms=$exp_perms)"
        continue
    fi

    # Get actual stat info (portable: works on GNU/Linux)
    actual_user=$(stat -c '%U' "$path")
    actual_group=$(stat -c '%G' "$path")
    actual_perms=$(stat -c '%A' "$path")   # e.g. -rw-rw-r--

    # Compare each field
    if [[ "$actual_user" == "$exp_user" ]]; then
        user_result="Ok"
    else
        user_result="Fail"
    fi

    if [[ "$actual_group" == "$exp_group" ]]; then
        group_result="Ok"
    else
        group_result="Fail"
    fi

    if [[ "$actual_perms" == "$exp_perms" ]]; then
        perms_result="Ok"
    else
        perms_result="Fail"
    fi

    # Build output line
    printf '%s user=%s (expected=%s) group=%s (expected=%s) %s (expected=%s) => %s, %s, %s\n' \
        "$path" \
        "$actual_user" "$exp_user" \
        "$actual_group" "$exp_group" \
        "$actual_perms" "$exp_perms" \
        "$user_result" "$group_result" "$perms_result"

done < "$INPUT_FILE"
