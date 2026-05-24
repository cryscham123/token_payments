"""User profile domain model separated from auth identity."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
import html
import unicodedata
from typing import Self

from token_payments.shared.domain import UserId


DISPLAY_NAME_MAX_LENGTH = 80
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@")


class UserProfileStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DELETED = "DELETED"


@dataclass(frozen=True)
class UserProfile:
    """Display profile for a User identity.

    The auth User remains the login/session/wallet/group-membership actor.
    This model stores only optional bounded display data and can be tombstoned
    without revoking or deleting the auth identity used by orders and audit.
    """

    user_id: UserId
    display_name: str | None
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
            return

        object.__setattr__(self, "display_name", _display_name(self.display_name))

    @property
    def display_name_html(self) -> str | None:
        if self.display_name is None:
            return None
        return html.escape(self.display_name, quote=True)

    def update(
        self,
        *,
        display_name: str | None = None,
        display_name_provided: bool = False,
        updated_at: datetime,
    ) -> Self:
        if self.status is UserProfileStatus.DELETED:
            raise ValueError("UserProfile.DELETED cannot be updated")
        return replace(
            self,
            display_name=display_name if display_name_provided else self.display_name,
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


def _display_name(value: str | None) -> str | None:
    text = _bounded_text(
        value,
        "UserProfile.display_name",
        max_length=DISPLAY_NAME_MAX_LENGTH,
        required=False,
    )
    if text is None:
        return None
    if text.startswith(_CSV_FORMULA_PREFIXES):
        raise ValueError("UserProfile.display_name starts with a log/CSV injection prefix")
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
        raise ValueError(f"{field_name} must be a non-empty string")
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
