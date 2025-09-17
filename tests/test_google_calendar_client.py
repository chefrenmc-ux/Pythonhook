# Aurora Polaris 2025. All rights reserved.
import json
from types import SimpleNamespace

import pytest

import google_calendar_client as gcc


class FakeEventsResource:
    def __init__(self):
        self.insert_called_with = None
        self.update_called_with = None
        self.delete_called_with = None
        self.list_called_with = None

    def insert(self, calendarId, body):
        self.insert_called_with = {"calendarId": calendarId, "body": body}
        return SimpleNamespace(execute=lambda: {"id": "evt-123", "body": body})

    def update(self, calendarId, eventId, body):
        self.update_called_with = {"calendarId": calendarId, "eventId": eventId, "body": body}
        return SimpleNamespace(execute=lambda: {"id": eventId, "body": body})

    def delete(self, calendarId, eventId):
        self.delete_called_with = {"calendarId": calendarId, "eventId": eventId}
        return SimpleNamespace(execute=lambda: None)

    def list(self, **kwargs):
        self.list_called_with = kwargs
        return SimpleNamespace(execute=lambda: {"items": [{"id": "evt", "start": {"dateTime": kwargs.get("timeMin")}}]})


class FakeFreeBusyResource:
    def __init__(self):
        self.query_payload = None

    def query(self, body):
        self.query_payload = body
        return SimpleNamespace(execute=lambda: {"calendars": {body["items"][0]["id"]: {"busy": []}}})


class FakeService:
    def __init__(self):
        self.events_resource = FakeEventsResource()
        self.freebusy_resource = FakeFreeBusyResource()

    def events(self):
        return self.events_resource

    def freebusy(self):
        return self.freebusy_resource


@pytest.fixture
def fake_service(monkeypatch):
    service = FakeService()
    monkeypatch.setattr(gcc, "get_calendar_service", lambda credentials_path=None: service)
    return service


def test_create_event_calls_insert(fake_service):
    body = {"summary": "Test"}
    result = gcc.create_event("primary", body)
    assert result["id"] == "evt-123"
    assert fake_service.events_resource.insert_called_with["body"] == body


def test_update_event_calls_update(fake_service):
    body = {"summary": "Updated"}
    result = gcc.update_event("primary", "evt-123", body)
    assert result["id"] == "evt-123"
    assert fake_service.events_resource.update_called_with["eventId"] == "evt-123"


def test_delete_event_calls_delete(fake_service):
    gcc.delete_event("primary", "evt-123")
    assert fake_service.events_resource.delete_called_with == {"calendarId": "primary", "eventId": "evt-123"}


def test_list_events_with_time_bounds(fake_service):
    events = list(
        gcc.list_events(
            "primary",
            time_min="2024-06-01T10:00:00+00:00",
            time_max="2024-06-01T12:00:00+00:00",
            max_results=5,
        )
    )
    called = fake_service.events_resource.list_called_with
    assert called["maxResults"] == 5
    assert called["timeMin"].endswith("Z")
    assert events[0]["id"] == "evt"


def test_check_availability(fake_service):
    availability = gcc.check_availability(
        "primary",
        start="2024-06-01T10:00:00+00:00",
        end="2024-06-01T11:00:00+00:00",
    )
    payload = fake_service.freebusy_resource.query_payload
    assert payload["timeMin"].endswith("Z")
    assert availability == {"busy": []}


def test_ensure_rfc3339_requires_timezone():
    with pytest.raises(ValueError):
        gcc._ensure_rfc3339("2024-06-01T10:00:00")


def test_ensure_rfc3339_allows_zulu():
    value = gcc._ensure_rfc3339("2024-06-01T10:00:00Z")
    assert value.endswith("Z")
