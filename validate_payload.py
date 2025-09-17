#!/usr/bin/env python3
"""Validate conversation payload JSON for required fields."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, List, Sequence, Tuple

DEFAULT_REQUIRED_FIELDS = [
    "Service",
    "Phone",
    "Stylist",
    "Date",
    "Use_name",
    "Time",
    "action",
]

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate that a payload JSON includes required dynamic variables.",
    )
    parser.add_argument(
        "payload",
        type=Path,
        help="Path to the JSON file to validate.",
    )
    parser.add_argument(
        "-r",
        "--require",
        dest="required",
        action="append",
        metavar="FIELD",
        help="Name of a required field. Repeat the flag to add more than one.",
    )
    parser.add_argument(
        "-R",
        "--require-from",
        dest="require_from",
        type=Path,
        metavar="FILE",
        help="File that lists required fields (newline separated or JSON array).",
    )
    parser.add_argument(
        "--include-defaults",
        action="store_true",
        help="Include the default development fields in addition to custom fields.",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Allow required fields to be empty or null.",
    )
    return parser.parse_args()

def load_payload(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SystemExit(f"error: payload file '{path}' not found.")
    except OSError as exc:
        raise SystemExit(f"error: could not read payload file '{path}': {exc}") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"error: invalid JSON in '{path}': {exc}") from exc

    if not isinstance(data, dict):
        raise SystemExit("error: payload must be a JSON object at the top level.")
    return data


def load_required_fields(args: argparse.Namespace) -> List[str]:
    fields: List[str] = []

    if args.include_defaults:
        fields.extend(DEFAULT_REQUIRED_FIELDS)

    if args.require_from:
        fields.extend(parse_fields_file(args.require_from))

    if args.required:
        fields.extend(args.required)

    if not fields:
        fields.extend(DEFAULT_REQUIRED_FIELDS)

    # Preserve ordering while removing duplicates.
    seen = set()
    ordered_fields = []
    for field in fields:
        if field in seen:
            continue
        seen.add(field)
        ordered_fields.append(field)
    return ordered_fields

def parse_fields_file(path: Path) -> List[str]:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise SystemExit(f"error: field list file '{path}' not found.")
    except OSError as exc:
        raise SystemExit(f"error: could not read field list file '{path}': {exc}") from exc

    if not text:
        raise SystemExit(f"error: field list file '{path}' is empty.")

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return [line for line in (line.strip() for line in text.splitlines()) if line]
    else:
        if isinstance(data, list):
            values = data
        elif isinstance(data, dict) and "fields" in data and isinstance(data["fields"], list):
            values = data["fields"]
        else:
            raise SystemExit(
                f"error: field list file '{path}' must be a JSON array or newline separated text.",
            )
        cleaned = [str(item).strip() for item in values if str(item).strip()]
        if not cleaned:
            raise SystemExit(f"error: field list file '{path}' does not contain any usable field names.")
        return cleaned

def validate_payload(
    payload: dict[str, Any],
    required_fields: Sequence[str],
    allow_empty: bool,
) -> Tuple[List[str], List[str], List[str]]:
    missing: List[str] = []
    empty: List[str] = []
    for field in required_fields:
        if field not in payload:
            missing.append(field)
            continue
        if allow_empty:
            continue
        if is_empty(payload[field]):
            empty.append(field)

    extras = sorted(set(payload) - set(required_fields))
    return missing, empty, extras


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def main() -> None:
    args = parse_args()
    required_fields = load_required_fields(args)
    payload = load_payload(args.payload)

    missing, empty, extras = validate_payload(payload, required_fields, args.allow_empty)

    if missing or empty:
        if missing:
            print(f"missing fields: {', '.join(missing)}", file=sys.stderr)
        if empty:
            print(f"empty values: {', '.join(empty)}", file=sys.stderr)
        raise SystemExit(1)

    print(f"Payload '{args.payload}' includes all required fields.")
    if extras:
        print(f"Note: extra fields present - {', '.join(extras)}")


if __name__ == "__main__":
    main()

