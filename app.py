from __future__ import annotations

from typing import Any, List, Sequence

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import validate_payload as validator

app = FastAPI(title="Payload Validator", version="1.0.0")


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


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "POST JSON to /validate to verify required fields."}


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
