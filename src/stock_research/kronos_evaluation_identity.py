"""Shared fail-closed model identity parsing for Kronos evaluation flows."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


MODEL_FIELDS = frozenset({"model", "model_identity", "model_name"})
WEIGHT_FIELDS = frozenset({"weights", "weights_identity", "weights_fingerprint"})


@dataclass(frozen=True)
class IdentityRecord:
    source: str
    location: str
    field: str
    value: Any
    family: str | None
    version: str | None
    opaque: bool


@dataclass(frozen=True)
class IdentityValidation:
    model_records: tuple[IdentityRecord, ...]
    weight_records: tuple[IdentityRecord, ...]
    opaque_model_records: tuple[IdentityRecord, ...]
    opaque_weight_records: tuple[IdentityRecord, ...]


class IdentityValidationError(ValueError):
    """A deterministic, categorized identity-contract failure."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


def iter_identity_fields(
    value: Any,
    path: str = "",
    seen: set[int] | None = None,
) -> Iterable[tuple[str, str, Any]]:
    """Yield every explicit identity field, including nested raw envelopes."""

    if seen is None:
        seen = set()
    if isinstance(value, Mapping):
        object_id = id(value)
        if object_id in seen:
            return
        seen.add(object_id)
        for key, item in value.items():
            if not isinstance(key, str):
                continue
            location = f"{path}.{key}" if path else key
            if key in MODEL_FIELDS or key in WEIGHT_FIELDS:
                yield location, key, item
            if isinstance(item, (Mapping, list, tuple)):
                yield from iter_identity_fields(item, location, seen)
    elif isinstance(value, (list, tuple)):
        object_id = id(value)
        if object_id in seen:
            return
        seen.add(object_id)
        for index, item in enumerate(value):
            if isinstance(item, (Mapping, list, tuple)):
                yield from iter_identity_fields(item, f"{path}[{index}]", seen)


def model_identity_parts(
    value: Any,
    *,
    allow_weight_prefix: bool = False,
) -> tuple[str, str | None] | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower().replace("_", "-").replace(" ", "-")
    normalized = re.sub(r"-+", "-", normalized)
    match = re.fullmatch(r"(?:kronos-)?(small|base)(?:-v(\d+))?", normalized)
    if match:
        return (
            match.group(1),
            f"v{int(match.group(2))}" if match.group(2) else None,
        )
    if allow_weight_prefix:
        match = re.fullmatch(
            r"(?:kronos-)?weights-(?:kronos-)?(small|base)(?:-v(\d+))?",
            normalized,
        )
        if match:
            return (
                match.group(1),
                f"v{int(match.group(2))}" if match.group(2) else None,
            )
    return None


def model_family(value: Any) -> str | None:
    parsed = model_identity_parts(value, allow_weight_prefix=True)
    return parsed[0] if parsed is not None else None


def canonical_identity(
    value: Any,
    *,
    allow_weight_prefix: bool = False,
) -> str | None:
    """Return the stable family/version form used for cache identity."""

    parsed = model_identity_parts(value, allow_weight_prefix=allow_weight_prefix)
    if parsed is None:
        return None
    family, version = parsed
    prefix = "weights-" if allow_weight_prefix else ""
    return f"{prefix}{family}{f'-{version}' if version else ''}"


def _records(payloads: Sequence[tuple[str, Any]]) -> tuple[
    list[IdentityRecord],
    list[IdentityRecord],
    list[IdentityRecord],
    list[IdentityRecord],
]:
    model_records: list[IdentityRecord] = []
    weight_records: list[IdentityRecord] = []
    opaque_model_records: list[IdentityRecord] = []
    opaque_weight_records: list[IdentityRecord] = []
    for source, payload in payloads:
        for location, field, value in iter_identity_fields(payload):
            if value in (None, ""):
                continue
            if field in MODEL_FIELDS:
                parsed = model_identity_parts(value)
                record = IdentityRecord(
                    source,
                    location,
                    field,
                    value,
                    parsed[0] if parsed else None,
                    parsed[1] if parsed else None,
                    parsed is None,
                )
                (model_records if parsed is not None else opaque_model_records).append(record)
            elif field in WEIGHT_FIELDS:
                parsed = model_identity_parts(value, allow_weight_prefix=True)
                record = IdentityRecord(
                    source,
                    location,
                    field,
                    value,
                    parsed[0] if parsed else None,
                    parsed[1] if parsed else None,
                    parsed is None,
                )
                (weight_records if parsed is not None else opaque_weight_records).append(record)
    return model_records, weight_records, opaque_model_records, opaque_weight_records


def validate_identity_payloads(
    payloads: Sequence[tuple[str, Any]],
    requested_model: str,
) -> IdentityValidation:
    """Validate all explicit identities while retaining opaque provenance.

    A family-only model field is sufficient when it agrees with the requested
    family.  Opaque model/build identifiers are accepted as audit metadata if
    at least one recognized family is present.  Opaque-only explicit model
    fields fail closed because there is no trustworthy family to compare.
    """

    requested_family = model_family(requested_model)
    if requested_family not in {"small", "base"}:
        raise IdentityValidationError(
            "requested Kronos model identity is unsupported",
            code="unknown_model_identity",
        )

    model_records, weight_records, opaque_model_records, opaque_weight_records = _records(
        payloads
    )
    if opaque_model_records and not model_records:
        raise IdentityValidationError(
            "Kronos response contains an opaque model identity without a model family",
            code="unknown_model_identity",
        )

    for record in model_records:
        if record.family != requested_family:
            raise IdentityValidationError(
                f"Kronos {record.source} model identity does not match the requested model",
                code="model_identity_mismatch",
            )
    for record in weight_records:
        if record.family != requested_family:
            raise IdentityValidationError(
                "Kronos weights identity does not match the requested model",
                code="weights_identity_mismatch",
            )

    model_versions = {record.version for record in model_records if record.version is not None}
    if len(model_versions) > 1:
        raise IdentityValidationError(
            "Kronos model identities have conflicting versions",
            code="model_identity_version_mismatch",
        )
    weight_versions = {
        record.version for record in weight_records if record.version is not None
    }
    if len(weight_versions) > 1:
        raise IdentityValidationError(
            "Kronos weights identities have conflicting versions",
            code="weights_identity_version_mismatch",
        )
    return IdentityValidation(
        tuple(model_records),
        tuple(weight_records),
        tuple(opaque_model_records),
        tuple(opaque_weight_records),
    )


def explicit_model_identity(payload: Any) -> str | None:
    records = list(iter_identity_fields(payload))
    recognized: list[Any] = []
    opaque: list[Any] = []
    for preferred_field in ("model_identity", "model_name", "model"):
        values = [
            value
            for _, field, value in records
            if field == preferred_field and value not in (None, "")
        ]
        if not values:
            continue
        recognized = [value for value in values if model_identity_parts(value) is not None]
        if recognized:
            return str(recognized[0])
        opaque = values
    return str(opaque[0]) if opaque else None


def explicit_weight_identity(payload: Any) -> str | None:
    for preferred_field in ("weights_identity", "weights_fingerprint", "weights"):
        for _, field, value in iter_identity_fields(payload):
            if field == preferred_field and value not in (None, ""):
                if isinstance(value, (Mapping, list, tuple)):
                    return json.dumps(
                        value,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    )
                return str(value)
    return None


__all__ = [
    "canonical_identity",
    "IdentityRecord",
    "IdentityValidation",
    "IdentityValidationError",
    "explicit_model_identity",
    "explicit_weight_identity",
    "iter_identity_fields",
    "model_family",
    "model_identity_parts",
    "validate_identity_payloads",
]
