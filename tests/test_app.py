# Aurora Polaris 2025. All rights reserved.
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

import app


class DummyResponse:
    def __init__(self, status_code: int, data: Any):
        self.status_code = status_code
        self._data = data
        self.text = "{}" if data is None else str(data)

    def json(self):
        return self._data


class DummyAsyncClient:
    def __init__(self, *, response: DummyResponse | Exception):
        self._response_or_exc = response

    async def __aenter__(self):
        if isinstance(self._response_or_exc, Exception):
            raise self._response_or_exc
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, url: str, json: dict[str, Any]):
        if isinstance(self._response_or_exc, Exception):
            raise self._response_or_exc
        return self._response_or_exc


@pytest.fixture
def client(monkeypatch):
    test_client = TestClient(app.app)
    yield test_client
    test_client.close()


@pytest.fixture
def successful_webhook(monkeypatch):
    response = DummyResponse(200, {"status": "ok"})

    def _async_client_factory(*args, **kwargs):
        return DummyAsyncClient(response=response)

    monkeypatch.setattr(app.httpx, "AsyncClient", _async_client_factory)


def test_parse_to_stockholm_naive_time():
    dt = app._parse_to_stockholm("2024-06-01", "12:00")
    assert dt.tzinfo.key == "Europe/Stockholm"
    assert dt.hour in {14, 13}  # DST aware conversion from assumed UTC


def test_normalize_booking_payload_transforms_names():
    payload = {
        "Service": "Cut",
        "Phone": "123",
        "Stylist": "Alex",
        "Date": "2024-06-01",
        "Use_name": "Jamie",
        "Time": "13:00",
        "action": "book",
    }
    normalized, stockholm_dt = app._normalize_booking_payload(payload)
    assert normalized["User_Name"] == "Jamie"
    assert "Weekday" in normalized
    assert normalized["ISODateTime"].endswith("+02:00") or normalized["ISODateTime"].endswith("+01:00")
    assert stockholm_dt.strftime("%A") == normalized["Weekday"]


def test_normalize_booking_payload_missing_use_name():
    payload = {
        "Service": "Cut",
        "Phone": "123",
        "Stylist": "Alex",
        "Date": "2024-06-01",
        "Time": "13:00",
        "action": "book",
    }
    with pytest.raises(ValueError):
        app._normalize_booking_payload(payload)


def test_validate_endpoint_success(client):
    response = client.post(
        "/validate",
        json={
            "payload": {field: "x" for field in app.validator.DEFAULT_REQUIRED_FIELDS},
            "include_defaults": False,
        },
    )
    assert response.status_code == 200
    assert response.json()["valid"] is True


def test_validate_endpoint_missing_fields(client):
    response = client.post(
        "/validate",
        json={"payload": {"Service": "Cut"}, "include_defaults": False},
    )
    assert response.status_code == 200
    data = response.json()
    assert "Phone" in data["missing"]
    assert data["valid"] is False


def test_book_endpoint_success(client, monkeypatch, successful_webhook):
    payload = {
        "Service": "Cut",
        "Phone": "123",
        "Stylist": "Alex",
        "Date": "2024-06-01",
        "Use_name": "Jamie",
        "Time": "13:00",
        "action": "book",
    }
    response = client.post("/book", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["webhook_status"] == 200
    assert body["appointment"]["customer"] == "Jamie"


def test_book_endpoint_webhook_error_response(client, monkeypatch):
    response_obj = DummyResponse(500, {"detail": "error"})

    def _async_client_factory(*args, **kwargs):
        return DummyAsyncClient(response=response_obj)

    monkeypatch.setattr(app.httpx, "AsyncClient", _async_client_factory)

    payload = {
        "Service": "Cut",
        "Phone": "123",
        "Stylist": "Alex",
        "Date": "2024-06-01",
        "Use_name": "Jamie",
        "Time": "13:00",
        "action": "book",
    }
    response = client.post("/book", json=payload)
    assert response.status_code == 502


def test_book_endpoint_webhook_connection_error(client, monkeypatch):
    def _async_client_factory(*args, **kwargs):
        return DummyAsyncClient(response=httpx.HTTPError("boom"))

    monkeypatch.setattr(app.httpx, "AsyncClient", _async_client_factory)

    payload = {
        "Service": "Cut",
        "Phone": "123",
        "Stylist": "Alex",
        "Date": "2024-06-01",
        "Use_name": "Jamie",
        "Time": "13:00",
        "action": "book",
    }
    response = client.post("/book", json=payload)
    assert response.status_code == 502


def test_book_endpoint_missing_field_returns_400(client):
    payload = {
        "Service": "Cut",
        "Phone": "123",
        "Stylist": "Alex",
        "Date": "2024-06-01",
        "Time": "13:00",
        "action": "book",
    }
    response = client.post("/book", json=payload)
    assert response.status_code == 400
    assert "missing" in response.json()["detail"]
