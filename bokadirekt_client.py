#!/usr/bin/env python3
"""Minimal helper for the Bokadirekt public API (https://external.api.portal.bokadirekt.se)."""
from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, Optional

import httpx

DEFAULT_BASE_URL = "https://external.api.portal.bokadirekt.se"
DEFAULT_TIMEOUT = 20.0


class BokaDirektClient:
    """Convenience wrapper around the Bokadirekt API.

    Notes
    -----
    * The API key can be provided explicitly, or via the environment variable
      `BOKADIREKT_API_KEY`.
    * Authentication headers differ per integration. By default we send both
      `Authorization: Bearer <key>` and `X-Api-Key: <key>`; adjust as needed.
    * Endpoints below reflect the public portal documentation as of writing.
      Verify paths/query parameters against the latest API specification.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.api_key = api_key or os.environ.get("BOKADIREKT_API_KEY")
        if not self.api_key:
            raise ValueError("API key not provided. Set BOKADIREKT_API_KEY or pass api_key.")

        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            headers=self._default_headers(self.api_key),
        )

    @staticmethod
    def _default_headers(api_key: str) -> Dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "X-Api-Key": api_key,
        }

    def close(self) -> None:
        self._client.close()

    def list_services(self, company_id: str) -> Dict[str, Any]:
        """Fetch services for a company."""
        return self._get(f"/company/{company_id}/services")

    def list_staff(self, company_id: str) -> Dict[str, Any]:
        """Fetch staff members for a company."""
        return self._get(f"/company/{company_id}/staff")

    def check_availability(
        self,
        company_id: str,
        service_id: str,
        *,
        from_date: str,
        to_date: str,
        stylist_id: str | None = None,
    ) -> Dict[str, Any]:
        """Retrieve availability slots for a service within a date range."""
        params = {
            "from": from_date,
            "to": to_date,
            "serviceId": service_id,
        }
        if stylist_id:
            params["staffId"] = stylist_id
        return self._get(f"/availability/{company_id}", params)

    def create_booking(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create a booking. Payload must follow Bokadirekt's schema."""
        return self._post("/booking", json=payload)

    def cancel_booking(self, booking_id: str, *, reason: str | None = None) -> Dict[str, Any]:
        """Cancel an existing booking."""
        body: Dict[str, Any] = {"bookingId": booking_id}
        if reason:
            body["reason"] = reason
        return self._post("/booking/cancel", json=body)

    def raw_get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._get(path, params)

    def raw_post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._post(path, json=payload)

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        response = self._client.get(path, params=params)
        return self._handle_response(response)

    def _post(self, path: str, json: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        response = self._client.post(path, json=json)
        return self._handle_response(response)

    @staticmethod
    def _handle_response(response: httpx.Response) -> Dict[str, Any]:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = {
                "status": exc.response.status_code,
                "body": _safe_json(exc.response),
            }
            raise RuntimeError(f"API request failed ({detail['status']}): {detail['body']}") from exc
        return _safe_json(response)


def _safe_json(response: httpx.Response) -> Dict[str, Any]:
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text}


def _load_payload_from_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CLI for the Bokadirekt API.")
    parser.add_argument("--api-key", dest="api_key", help="Bokadirekt API key. Falls back to BOKADIREKT_API_KEY.")
    parser.add_argument("--base-url", dest="base_url", default=DEFAULT_BASE_URL, help="Override API base URL.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    services_parser = subparsers.add_parser("services", help="List services for a company.")
    services_parser.add_argument("company_id", help="Bokadirekt company ID.")

    staff_parser = subparsers.add_parser("staff", help="List staff for a company.")
    staff_parser.add_argument("company_id", help="Bokadirekt company ID.")

    availability_parser = subparsers.add_parser("availability", help="Check availability for a service.")
    availability_parser.add_argument("company_id", help="Company ID.")
    availability_parser.add_argument("service_id", help="Service ID.")
    availability_parser.add_argument("from_date", help="Start date (YYYY-MM-DD).")
    availability_parser.add_argument("to_date", help="End date (YYYY-MM-DD).")
    availability_parser.add_argument("--staff-id", dest="staff_id", help="Optional staff/member ID.")

    create_parser = subparsers.add_parser("create", help="Create a booking from a JSON payload.")
    create_parser.add_argument("payload", help="Path to JSON payload.")

    cancel_parser = subparsers.add_parser("cancel", help="Cancel an existing booking.")
    cancel_parser.add_argument("booking_id", help="Booking ID.")
    cancel_parser.add_argument("--reason", dest="reason", help="Optional cancellation reason.")

    raw_get_parser = subparsers.add_parser("raw-get", help="Call an arbitrary GET path.")
    raw_get_parser.add_argument("path", help="Endpoint path, e.g., /foo/bar.")
    raw_get_parser.add_argument("--params", dest="params", help="JSON string of query parameters.")

    raw_post_parser = subparsers.add_parser("raw-post", help="Call an arbitrary POST path.")
    raw_post_parser.add_argument("path", help="Endpoint path, e.g., /foo/bar.")
    raw_post_parser.add_argument("payload", help="Path to JSON payload.")

    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    client = BokaDirektClient(api_key=args.api_key, base_url=args.base_url)

    try:
        if args.command == "services":
            result = client.list_services(args.company_id)
        elif args.command == "staff":
            result = client.list_staff(args.company_id)
        elif args.command == "availability":
            result = client.check_availability(
                args.company_id,
                args.service_id,
                from_date=args.from_date,
                to_date=args.to_date,
                stylist_id=args.staff_id,
            )
        elif args.command == "create":
            payload = _load_payload_from_file(args.payload)
            result = client.create_booking(payload)
        elif args.command == "cancel":
            result = client.cancel_booking(args.booking_id, reason=args.reason)
        elif args.command == "raw-get":
            params = json.loads(args.params) if args.params else None
            result = client.raw_get(args.path, params=params)
        elif args.command == "raw-post":
            payload = _load_payload_from_file(args.payload)
            result = client.raw_post(args.path, payload)
        else:
            raise ValueError(f"Unsupported command: {args.command}")

        print(json.dumps(result, indent=2, ensure_ascii=False))
    finally:
        client.close()


if __name__ == "__main__":
    main()
