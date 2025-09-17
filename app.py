from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Sequence
from zoneinfo import ZoneInfo

import httpx
from dateutil import parser as date_parser
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import validate_payload as validator

WEBHOOK_URL = "https://hook.eu2.make.com/e73ginw1b4moa9gypzuf8qwh4c29fo2x"
STOCKHOLM_TZ = ZoneInfo("Europe/Stockholm")
ASSUMED_SOURCE_TZ = ZoneInfo("UTC")

app = FastAPI(title="Payload Validator", version="1.1.0")


class ValidationRequest(BaseModel):
    payload: dict[str, Any]
    required_fields: List[str] | None = Field(
        default=None,
        description="Overrides the required field list when provided.",
    )
    include_defaults: bool = Field(
        default=True,
        description="Include the default development field set.",
    )
    allow_empty: bool = Field(
        default=False,
        description="Allow required fields to be empty or null.",
    )


class ValidationResponse(BaseModel):
    valid: bool
    missing: List[str] = Field(default_factory=list)
    empty: List[str] = Field(default_factory=list)
    extras: List[str] = Field(default_factory=list)


class BookRequest(BaseModel):
    Service: str
    Phone: str
    Stylist: str | None = None
    Date: str
    Use_name: str
    Time: str
    action: str

    model_config = {
        "extra": "allow",
    }


class BookResponse(BaseModel):
    status: str
    appointment: Dict[str, Any]
    webhook_status: int
    webhook_response: Any


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "POST JSON to /validate or /book to verify required fields."}


@app.post("/validate", response_model=ValidationResponse)
async def validate(request: ValidationRequest) -> ValidationResponse:
    required = _build_required_fields(
        request.required_fields,
        request.include_defaults,
    )
    if not required:
        raise HTTPException(status_code=400, detail="No required fields specified.")

    missing, empty, extras = validator.validate_payload(
        request.payload,
        required,
        request.allow_empty,
    )
    return ValidationResponse(
        valid=not missing and not empty,
        missing=missing,
        empty=empty,
        extras=extras,
    )


@app.post("/book", response_model=BookResponse)
async def book_appointment(request: BookRequest) -> BookResponse:
    payload = request.model_dump()

    missing, empty, _ = validator.validate_payload(
        payload,
        validator.DEFAULT_REQUIRED_FIELDS,
        allow_empty=False,
    )
    if missing or empty:
        detail: Dict[str, List[str]] = {}
        if missing:
            detail["missing"] = missing
        if empty:
            detail["empty"] = empty
        raise HTTPException(status_code=400, detail=detail)

    try:
        normalized_payload, stockholm_dt = _normalize_booking_payload(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(WEBHOOK_URL, json=normalized_payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to reach booking service: {exc}") from exc

    webhook_status = response.status_code
    try:
        webhook_body = response.json()
    except ValueError:
        webhook_body = {"raw": response.text}

    if webhook_status >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Booking service returned an error.",
                "status": webhook_status,
                "body": webhook_body,
            },
        )

    appointment_info = {
        "service": normalized_payload.get("Service"),
        "stylist": normalized_payload.get("Stylist"),
        "customer": normalized_payload.get("User_Name"),
        "stockholm_iso": stockholm_dt.isoformat(),
        "weekday": stockholm_dt.strftime("%A"),
    }

    return BookResponse(
        status="success",
        appointment=appointment_info,
        webhook_status=webhook_status,
        webhook_response=webhook_body,
    )


def _build_required_fields(
    required_fields: Sequence[str] | None,
    include_defaults: bool,
) -> List[str]:
    fields: List[str] = []
    if include_defaults:
        fields.extend(validator.DEFAULT_REQUIRED_FIELDS)
    if required_fields:
        fields.extend(required_fields)

    ordered: List[str] = []
    seen: set[str] = set()
    for field in fields:
        if field in seen:
            continue
        seen.add(field)
        ordered.append(field)
    return ordered


def _normalize_booking_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], datetime]:
    normalized = dict(payload)

    if "Use_name" not in normalized or not normalized["Use_name"]:
        raise ValueError("'Use_name' must be provided and non-empty.")

    stockholm_dt = _parse_to_stockholm(normalized["Date"], normalized["Time"])

    normalized["Date"] = stockholm_dt.strftime("%Y-%m-%d")
    normalized["Time"] = stockholm_dt.strftime("%H:%M")
    normalized["Weekday"] = stockholm_dt.strftime("%A")
    normalized["ISODateTime"] = stockholm_dt.isoformat()
    normalized["User_Name"] = normalized.pop("Use_name")

    return normalized, stockholm_dt


def _parse_to_stockholm(date_str: str, time_str: str) -> datetime:
    combined = f"{date_str} {time_str}".strip()
    if not combined.strip():
        raise ValueError("Date and Time must be provided to schedule an appointment.")

    try:
        parsed = date_parser.parse(combined, fuzzy=True)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"Could not understand date/time input: {combined!r}") from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ASSUMED_SOURCE_TZ)

    return parsed.astimezone(STOCKHOLM_TZ)
