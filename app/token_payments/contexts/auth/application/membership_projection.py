"""Auth RBAC membership projection consumer."""

from __future__ import annotations

from typing import Any, Mapping, Protocol


class StoreMembershipProjectionRepository(Protocol):
    def was_membership_event_processed(self, event_id: str) -> bool:
        ...

    def last_membership_projection_version(self, group_id: str, user_id: str) -> int:
        ...

    def upsert_projected_membership(self, *, group_id: str, user_id: str, role_id: str, active: bool, version: int) -> None:
        ...

    def mark_membership_event_processed(self, event_id: str) -> None:
        ...


class StoreMembershipProjectionConsumer:
    """Project canonical store catalog memberships into auth RBAC read model."""

    def __init__(self, repository: StoreMembershipProjectionRepository) -> None:
        self._repository = repository

    def handle(self, payload: Mapping[str, Any]) -> dict[str, str]:
        event_id = _text(payload.get("eventId"), "eventId")
        if self._repository.was_membership_event_processed(event_id):
            return {"status": "duplicate", "eventId": event_id}

        group_id = _text(payload.get("groupId"), "groupId")
        user_id = _text(payload.get("userId"), "userId")
        role_id = _text(payload.get("roleId"), "roleId")
        active = _bool(payload.get("active"), "active")
        version = _positive_int(payload.get("version", 1), "version")

        if version <= self._repository.last_membership_projection_version(group_id, user_id):
            self._repository.mark_membership_event_processed(event_id)
            return {"status": "stale", "eventId": event_id}

        self._repository.upsert_projected_membership(
            group_id=group_id,
            user_id=user_id,
            role_id=role_id,
            active=active,
            version=version,
        )
        self._repository.mark_membership_event_processed(event_id)
        return {"status": "projected", "eventId": event_id}


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a bool")
    return value


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


__all__ = ["StoreMembershipProjectionConsumer", "StoreMembershipProjectionRepository"]
