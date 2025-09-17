#!/usr/bin/env python3
# Aurora Polaris 2025. All rights reserved.
"""Utilities and CLI helpers for Google Calendar operations."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def get_calendar_service(credentials_path: str | None = None):
    """Create an authenticated Calendar API service using a service account."""
    credentials_file = credentials_path or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_file:
        raise ValueError("Credentials path must be provided or GOOGLE_APPLICATION_CREDENTIALS set.")

    path = Path(credentials_file)
    if not path.exists():
        raise FileNotFoundError(f"Credentials file not found: {path}")

    creds = service_account.Credentials.from_service_account_file(str(path), scopes=SCOPES)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def create_event(calendar_id: str, event_body: Dict[str, Any], credentials_path: str | None = None) -> Dict[str, Any]:
    service = get_calendar_service(credentials_path)
    return service.events().insert(calendarId=calendar_id, body=event_body).execute()


def update_event(
    calendar_id: str,
    event_id: str,
    event_body: Dict[str, Any],
    credentials_path: str | None = None,
) -> Dict[str, Any]:
    service = get_calendar_service(credentials_path)
    return service.events().update(calendarId=calendar_id, eventId=event_id, body=event_body).execute()


def delete_event(calendar_id: str, event_id: str, credentials_path: str | None = None) -> None:
    service = get_calendar_service(credentials_path)
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()


def list_events(
    calendar_id: str,
    time_min: str | None = None,
    time_max: str | None = None,
    max_results: int = 10,
    credentials_path: str | None = None,
) -> Iterable[Dict[str, Any]]:
    service = get_calendar_service(credentials_path)

    params: Dict[str, Any] = {
        "calendarId": calendar_id,
        "maxResults": max_results,
        "singleEvents": True,
        "orderBy": "startTime",
    }
    if time_min:
        params["timeMin"] = _ensure_rfc3339(time_min)
    if time_max:
        params["timeMax"] = _ensure_rfc3339(time_max)

    response = service.events().list(**params).execute()
    return response.get("items", [])


def check_availability(
    calendar_id: str,
    start: str,
    end: str,
    credentials_path: str | None = None,
) -> Dict[str, Any]:
    service = get_calendar_service(credentials_path)
    body = {
        "timeMin": _ensure_rfc3339(start),
        "timeMax": _ensure_rfc3339(end),
        "items": [{"id": calendar_id}],
    }
    response = service.freebusy().query(body=body).execute()
    return response["calendars"].get(calendar_id, {})


def _ensure_rfc3339(value: str) -> str:
    """Parse incoming date/time and output RFC3339 format if possible."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Could not parse datetime value: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError("Datetime must include timezone information.")
    return parsed.isoformat().replace("+00:00", "Z")


def _load_event_from_json(source: str) -> Dict[str, Any]:
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"Event JSON file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Google Calendar helper CLI.")
    parser.add_argument("--credentials", dest="credentials", help="Path to service account JSON.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Create a calendar event from a JSON file.")
    create_parser.add_argument("calendar_id", help="Target calendar ID, e.g., primary.")
    create_parser.add_argument("event_json", help="Path to JSON file describing the event body.")

    update_parser = subparsers.add_parser("update", help="Update an existing calendar event.")
    update_parser.add_argument("calendar_id", help="Target calendar ID.")
    update_parser.add_argument("event_id", help="Google Calendar event ID.")
    update_parser.add_argument("event_json", help="Path to JSON file describing the updated event body.")

    delete_parser = subparsers.add_parser("delete", help="Delete an event from the calendar.")
    delete_parser.add_argument("calendar_id", help="Target calendar ID.")
    delete_parser.add_argument("event_id", help="Google Calendar event ID.")

    list_parser = subparsers.add_parser("list", help="List upcoming events within a window.")
    list_parser.add_argument("calendar_id", help="Target calendar ID.")
    list_parser.add_argument("--time-min", dest="time_min", help="Start of window (RFC3339).")
    list_parser.add_argument("--time-max", dest="time_max", help="End of window (RFC3339).")
    list_parser.add_argument("--max-results", dest="max_results", type=int, default=10, help="Maximum events to return.")

    freebusy_parser = subparsers.add_parser("freebusy", help="Check availability for a time window.")
    freebusy_parser.add_argument("calendar_id", help="Target calendar ID.")
    freebusy_parser.add_argument("start", help="Window start (RFC3339).")
    freebusy_parser.add_argument("end", help="Window end (RFC3339).")

    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    credentials_path = args.credentials

    try:
        if args.command == "create":
            event = _load_event_from_json(args.event_json)
            created = create_event(args.calendar_id, event, credentials_path)
            print(json.dumps(created, indent=2))
        elif args.command == "update":
            event = _load_event_from_json(args.event_json)
            updated = update_event(args.calendar_id, args.event_id, event, credentials_path)
            print(json.dumps(updated, indent=2))
        elif args.command == "delete":
            delete_event(args.calendar_id, args.event_id, credentials_path)
            print("Event deleted.")
        elif args.command == "list":
            events = list_events(
                args.calendar_id,
                time_min=args.time_min,
                time_max=args.time_max,
                max_results=args.max_results,
                credentials_path=credentials_path,
            )
            print(json.dumps(list(events), indent=2))
        elif args.command == "freebusy":
            availability = check_availability(
                args.calendar_id,
                args.start,
                args.end,
                credentials_path=credentials_path,
            )
            print(json.dumps(availability, indent=2))
        else:
            raise ValueError(f"Unknown command: {args.command}")
    except (HttpError, ValueError, FileNotFoundError) as exc:
        raise SystemExit(f"error: {exc}") from exc


if __name__ == "__main__":
    main()
