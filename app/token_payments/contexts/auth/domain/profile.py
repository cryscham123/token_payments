"""User profile domain model separated from auth identity."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
import html
import re
import unicodedata
from typing import Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from token_payments.shared.domain import UserId


DISPLAY_NAME_MAX_LENGTH = 80
EMAIL_MAX_LENGTH = 254
LOCALE_MAX_LENGTH = 35
TIMEZONE_MAX_LENGTH = 64
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@")
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251})\.[A-Za-z]{2,63}$")
_LOCALE_RE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")


class UserProfileStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DELETED = "DELETED"


@dataclass(frozen=True)
class UserProfile:
    """Display/contact profile for a User identity.

    The auth User remains the login/session/wallet/group-membership actor.
    This model stores bounded display/contact data and can be tombstoned
    without revoking or deleting the auth identity used by orders and audit.
    """

    user_id: UserId
    display_name: str | None
    email: str | None = None
    email_verified_at: datetime | None = None
    locale: str | None = None
    timezone: str | None = None
    status: UserProfileStatus | str = UserProfileStatus.ACTIVE
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, UserId):
            raise ValueError("UserProfile.user_id must be a UserId")
        object.__setattr__(self, "status", _profile_status(self.status))
        if self.created_at is not None:
            object.__setattr__(self, "created_at", _aware_datetime(self.created_at, "UserProfile.created_at"))
        if self.updated_at is not None:
            object.__setattr__(self, "updated_at", _aware_datetime(self.updated_at, "UserProfile.updated_at"))

        if self.status is UserProfileStatus.DELETED:
            object.__setattr__(self, "display_name", None)
            object.__setattr__(self, "email", None)
            object.__setattr__(self, "email_verified_at", None)
            object.__setattr__(self, "locale", None)
            object.__setattr__(self, "timezone", None)
            return

        object.__setattr__(self, "display_name", _display_name(self.display_name))
        object.__setattr__(self, "email", _optional_email(self.email))
        if self.email_verified_at is not None:
            if self.email is None:
                raise ValueError("UserProfile.email_verified_at requires email")
            object.__setattr__(
                self,
                "email_verified_at",
                _aware_datetime(self.email_verified_at, "UserProfile.email_verified_at"),
            )
        object.__setattr__(self, "locale", _optional_locale(self.locale))
        object.__setattr__(self, "timezone", _optional_timezone(self.timezone))

    @property
    def display_name_html(self) -> str | None:
        if self.display_name is None:
            return None
        return html.escape(self.display_name, quote=True)

    def update(
        self,
        *,
        display_name: str | None = None,
        email: str | None = None,
        locale: str | None = None,
        timezone: str | None = None,
        updated_at: datetime,
    ) -> Self:
        if self.status is UserProfileStatus.DELETED:
            raise ValueError("UserProfile.DELETED cannot be updated")
        return replace(
            self,
            display_name=self.display_name if display_name is None else display_name,
            email=self.email if email is None else email,
            locale=self.locale if locale is None else locale,
            timezone=self.timezone if timezone is None else timezone,
            updated_at=updated_at,
        )

    def suspend(self, *, suspended_at: datetime) -> Self:
        return replace(self, status=UserProfileStatus.SUSPENDED, updated_at=suspended_at)

    def activate(self, *, activated_at: datetime) -> Self:
        return replace(self, status=UserProfileStatus.ACTIVE, updated_at=activated_at)

    def delete(self, *, deleted_at: datetime) -> Self:
        return type(self)(
            user_id=self.user_id,
            display_name=None,
            email=None,
            email_verified_at=None,
            locale=None,
            timezone=None,
            status=UserProfileStatus.DELETED,
            created_at=self.created_at,
            updated_at=deleted_at,
        )


def _profile_status(value: UserProfileStatus | str) -> UserProfileStatus:
    if isinstance(value, UserProfileStatus):
        return value
    try:
        return UserProfileStatus(str(value))
    except ValueError as exc:
        raise ValueError("UserProfile.status must be ACTIVE, SUSPENDED, or DELETED") from exc


def _display_name(value: str | None) -> str:
    text = _bounded_text(
        value,
        "UserProfile.display_name",
        max_length=DISPLAY_NAME_MAX_LENGTH,
        required=True,
    )
    assert text is not None
    if text.startswith(_CSV_FORMULA_PREFIXES):
        raise ValueError("UserProfile.display_name starts with a log/CSV injection prefix")
    return text


def _optional_email(value: str | None) -> str | None:
    text = _bounded_text(value, "UserProfile.email", max_length=EMAIL_MAX_LENGTH, required=False)
    if text is None:
        return None
    normalized = text.lower()
    if not _EMAIL_RE.fullmatch(normalized):
        raise ValueError("UserProfile.email must be a bounded email address")
    return normalized


def _optional_locale(value: str | None) -> str | None:
    text = _bounded_text(value, "UserProfile.locale", max_length=LOCALE_MAX_LENGTH, required=False)
    if text is None:
        return None
    if not _LOCALE_RE.fullmatch(text):
        raise ValueError("UserProfile.locale must be a BCP 47-style locale tag")
    return text


def _optional_timezone(value: str | None) -> str | None:
    text = _bounded_text(value, "UserProfile.timezone", max_length=TIMEZONE_MAX_LENGTH, required=False)
    if text is None:
        return None
    try:
        ZoneInfo(text)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("UserProfile.timezone must be a standard IANA timezone name") from exc
    return text


def _bounded_text(value: str | None, field_name: str, *, max_length: int, required: bool) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"{field_name} must be a non-empty string")
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    if any(_is_control_character(character) for character in value):
        raise ValueError(f"{field_name} must not contain control characters")
    normalized = unicodedata.normalize("NFC", value.strip())
    if not normalized:
        if required:
            raise ValueError(f"{field_name} must be a non-empty string")
        return None
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return normalized


def _is_control_character(value: str) -> bool:
    return unicodedata.category(value).startswith("C")


def _aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


__all__ = ["UserProfile", "UserProfileStatus"]
