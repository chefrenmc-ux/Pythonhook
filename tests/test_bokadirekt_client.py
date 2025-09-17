# Aurora Polaris 2025. All rights reserved.
import json
from types import SimpleNamespace

import httpx
import pytest

import bokadirekt_client as bd


class FakeClient:
    def __init__(self, *args, **kwargs):
        self.requests = []

    def get(self, path, params=None):
        self.requests.append(("GET", path, params))
        return SimpleNamespace(
            json=lambda: {"method": "GET", "path": path, "params": params},
            status_code=200,
            text="{}",
            raise_for_status=lambda: None,
        )

    def post(self, path, json=None):
        self.requests.append(("POST", path, json))
        return SimpleNamespace(
            json=lambda: {"method": "POST", "path": path, "json": json},
            status_code=200,
            text="{}",
            raise_for_status=lambda: None,
        )

    def close(self):
        pass


def make_client(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(bd.httpx, "Client", lambda *args, **kwargs: fake)
    client = bd.BokaDirektClient(api_key="KEY", base_url="https://example.com")
    return client, fake


def test_default_headers(monkeypatch):
    client, _ = make_client(monkeypatch)
    headers = client._default_headers("KEY")
    assert headers["Authorization"] == "Bearer KEY"
    assert headers["X-Api-Key"] == "KEY"
    client.close()


def test_list_services_uses_get(monkeypatch):
    client, fake = make_client(monkeypatch)
    data = client.list_services("123")
    assert data["path"] == "/company/123/services"
    method, path, params = fake.requests[-1]
    assert method == "GET"
    assert path == "/company/123/services"
    client.close()


def test_check_availability_with_staff(monkeypatch):
    client, fake = make_client(monkeypatch)
    data = client.check_availability(
        "123",
        "svc",
        from_date="2024-06-01",
        to_date="2024-06-02",
        stylist_id="sty",
    )
    method, path, params = fake.requests[-1]
    assert method == "GET"
    assert params["staffId"] == "sty"
    assert data["path"] == "/availability/123"
    client.close()


def test_cancel_booking_sends_post(monkeypatch):
    client, fake = make_client(monkeypatch)
    data = client.cancel_booking("booking-1", reason="test")
    method, path, body = fake.requests[-1]
    assert method == "POST"
    assert body["reason"] == "test"
    assert data["path"] == "/booking/cancel"
    client.close()


def test_raw_post_uses_payload(monkeypatch, tmp_path):
    client, fake = make_client(monkeypatch)
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")
    data = client.raw_post("/custom", {"foo": "bar"})
    method, path, body = fake.requests[-1]
    assert method == "POST"
    assert path == "/custom"
    assert body["foo"] == "bar"
    client.close()
