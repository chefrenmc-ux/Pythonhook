# Aurora Polaris 2025. All rights reserved.
import json
from pathlib import Path

import pytest

import validate_payload as vp


def write_temp(tmp_path, filename, content):
    path = tmp_path / filename
    path.write_text(content, encoding="utf-8")
    return path


def test_load_required_fields_defaults():
    args = type("Args", (), {"include_defaults": False, "require_from": None, "required": None})()
    fields = vp.load_required_fields(args)
    assert fields == vp.DEFAULT_REQUIRED_FIELDS


def test_load_required_fields_custom_and_defaults():
    args = type(
        "Args",
        (),
        {
            "include_defaults": True,
            "require_from": None,
            "required": ["Custom", "Service"],
        },
    )()
    fields = vp.load_required_fields(args)
    assert fields[0] == "Service"
    assert "Custom" in fields
    assert len(fields) == len(set(fields))


def test_parse_fields_file_json_array(tmp_path):
    path = write_temp(tmp_path, "fields.json", json.dumps(["A", "B", "C"]))
    assert vp.parse_fields_file(path) == ["A", "B", "C"]


def test_parse_fields_file_newlines(tmp_path):
    path = write_temp(tmp_path, "fields.txt", "one\n\ntwo\n")
    assert vp.parse_fields_file(path) == ["one", "two"]


def test_parse_fields_file_empty_raises(tmp_path):
    path = write_temp(tmp_path, "empty.txt", "\n\n")
    with pytest.raises(SystemExit) as exc:
        vp.parse_fields_file(path)
    assert "empty" in str(exc.value)


def test_validate_payload_finds_missing():
    payload = {"Service": "Cut"}
    required = ["Service", "Phone"]
    missing, empty, extras = vp.validate_payload(payload, required, allow_empty=False)
    assert missing == ["Phone"]
    assert not empty
    assert extras == []


def test_validate_payload_detects_empty_string():
    payload = {"Service": "", "Phone": "123"}
    required = ["Service", "Phone"]
    missing, empty, _ = vp.validate_payload(payload, required, allow_empty=False)
    assert missing == []
    assert empty == ["Service"]


def test_is_empty_whitespace_string():
    assert vp.is_empty("   ") is True


def test_is_empty_nonempty_collection():
    assert vp.is_empty([1]) is False
