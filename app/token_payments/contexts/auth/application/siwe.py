"""SIWE message contract helpers for the auth application layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import re
from urllib.parse import urlsplit

from token_payments.shared.domain import WalletAddress


SIWE_VERSION = "1"

_NONCE_RE = re.compile(r"^[A-Za-z0-9]{8,}$")
_SIWE_PREFIX = " wants you to sign in with your Ethereum account:"


@dataclass(frozen=True)
class SiweMessage:
    domain: str
    address: WalletAddress | str
    uri: str
    version: str
    chain_id: int
    nonce: str
    issued_at: datetime
    expiration_time: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "domain", _require_domain(self.domain))
        address = self.address if isinstance(self.address, WalletAddress) else WalletAddress(self.address)
        object.__setattr__(self, "address", address)
        object.__setattr__(self, "uri", _require_uri(self.uri))
        object.__setattr__(self, "version", _require_version(self.version))
        object.__setattr__(self, "chain_id", _require_positive_int(self.chain_id, "chain_id"))
        object.__setattr__(self, "nonce", _require_siwe_nonce(self.nonce))
        issued_at = _require_aware_datetime(self.issued_at, "issued_at")
        expiration_time = _require_aware_datetime(self.expiration_time, "expiration_time")
        if expiration_time <= issued_at:
            raise ValueError("SIWE expiration_time must be after issued_at")
        object.__setattr__(self, "issued_at", issued_at)
        object.__setattr__(self, "expiration_time", expiration_time)


def build_siwe_message(message: SiweMessage) -> str:
    """Build a minimal EIP-4361/SIWE v1 message."""

    if not isinstance(message, SiweMessage):
        raise ValueError("message must be a SiweMessage")
    return "\n".join(
        (
            f"{message.domain}{_SIWE_PREFIX}",
            str(message.address),
            "",
            f"URI: {message.uri}",
            f"Version: {message.version}",
            f"Chain ID: {message.chain_id}",
            f"Nonce: {message.nonce}",
            f"Issued At: {message.issued_at.isoformat()}",
            f"Expiration Time: {message.expiration_time.isoformat()}",
        )
    )


def parse_siwe_message(message: str) -> SiweMessage:
    """Parse the SIWE fields this application signs and verifies."""

    if not isinstance(message, str) or not message.strip():
        raise ValueError("SIWE message must be a non-empty string")
    lines = message.splitlines()
    if len(lines) < 9:
        raise ValueError("SIWE message is missing required fields")
    first_line = lines[0]
    if not first_line.endswith(_SIWE_PREFIX):
        raise ValueError("SIWE message is missing the domain sign-in prefix")
    domain = first_line[: -len(_SIWE_PREFIX)]
    if lines[2] != "":
        raise ValueError("SIWE message must separate address and fields with a blank line")
    fields = _field_mapping(lines[3:])
    return SiweMessage(
        domain=domain,
        address=WalletAddress(lines[1]),
        uri=fields["URI"],
        version=fields["Version"],
        chain_id=int(fields["Chain ID"]),
        nonce=fields["Nonce"],
        issued_at=_parse_datetime(fields["Issued At"], "Issued At"),
        expiration_time=_parse_datetime(fields["Expiration Time"], "Expiration Time"),
    )


def default_siwe_uri(domain: str) -> str:
    return f"https://{_require_domain(domain)}"


def normalize_siwe_nonce(value: str) -> str:
    """Return an alphanumeric SIWE nonce with at least eight characters."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError("nonce source must be a non-empty string")
    candidate = "".join(character for character in value.strip() if character.isalnum())
    if _NONCE_RE.fullmatch(candidate):
        return candidate
    return hashlib.sha256(value.strip().encode("utf-8")).hexdigest()[:16]


def _field_mapping(lines: list[str]) -> dict[str, str]:
    required = ("URI", "Version", "Chain ID", "Nonce", "Issued At", "Expiration Time")
    fields: dict[str, str] = {}
    for line in lines:
        if not line:
            continue
        if ":" not in line:
            raise ValueError("SIWE message contains an invalid field line")
        label, raw_value = line.split(":", 1)
        if label in fields:
            raise ValueError(f"SIWE message contains duplicate {label}")
        fields[label] = raw_value.strip()
    missing = [label for label in required if label not in fields]
    if missing:
        raise ValueError(f"SIWE message is missing {', '.join(missing)}")
    return fields


def _parse_datetime(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"SIWE {field_name} must be an ISO-8601 datetime") from exc
    return _require_aware_datetime(parsed, field_name)


def _require_domain(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("SIWE domain must be a non-empty string")
    domain = value.strip()
    if "://" in domain or any(character.isspace() for character in domain):
        raise ValueError("SIWE domain must be an authority, not a URI")
    return domain


def _require_uri(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("SIWE uri must be a non-empty string")
    uri = value.strip()
    parsed = urlsplit(uri)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("SIWE uri must include a scheme and authority")
    return uri


def _require_version(value: str) -> str:
    if not isinstance(value, str) or value.strip() != SIWE_VERSION:
        raise ValueError(f"SIWE version must be {SIWE_VERSION}")
    return SIWE_VERSION


def _require_siwe_nonce(value: str) -> str:
    if not isinstance(value, str) or not _NONCE_RE.fullmatch(value.strip()):
        raise ValueError("SIWE nonce must be at least 8 alphanumeric characters")
    return value.strip()


def _require_positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"SIWE {field_name} must be a positive integer")
    return value


def _require_aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"SIWE {field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"SIWE {field_name} must be timezone-aware")
    return value.astimezone(UTC)


__all__ = [
    "SIWE_VERSION",
    "SiweMessage",
    "build_siwe_message",
    "default_siwe_uri",
    "normalize_siwe_nonce",
    "parse_siwe_message",
]
