"""Group-scoped authorization policy for RBAC permission checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from token_payments.contexts.auth.domain import (
    Group,
    GroupId,
    GroupMembership,
    GroupType,
    PermissionName,
    Role,
    RoleId,
)
from token_payments.shared.domain import StoreId, UserId


@dataclass(frozen=True)
class ResourceRef:
    """Resource identity passed from API/application code into policy checks."""

    resource_type: str
    resource_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "resource_type", _text(self.resource_type, "ResourceRef.resource_type"))
        if self.resource_id is not None:
            object.__setattr__(self, "resource_id", _text(self.resource_id, "ResourceRef.resource_id"))

    @classmethod
    def store(cls, store_id: StoreId | str) -> "ResourceRef":
        return cls(resource_type="store", resource_id=str(store_id))

    @classmethod
    def platform(cls) -> "ResourceRef":
        return cls(resource_type="platform")

    @classmethod
    def user(cls, user_id: UserId | str) -> "ResourceRef":
        return cls(resource_type="user", resource_id=str(user_id))


class AuthorizationRepository(Protocol):
    def memberships_for_user(self, user_id: UserId) -> tuple[GroupMembership, ...]:
        ...

    def group_by_id(self, group_id: GroupId) -> Group | None:
        ...

    def role_by_id(self, role_id: RoleId) -> Role | None:
        ...

    def permissions_for_role(self, role_id: RoleId) -> tuple[PermissionName, ...]:
        ...


class AuthorizationPolicy:
    """Permission lookup policy backed by group memberships and role permissions."""

    def __init__(self, repository: AuthorizationRepository) -> None:
        self._repository = repository

    def can(self, user_id: UserId, permission: PermissionName | str, resource: ResourceRef) -> bool:
        if not isinstance(user_id, UserId):
            raise ValueError("AuthorizationPolicy.can user_id must be a UserId")
        permission_name = permission if isinstance(permission, PermissionName) else PermissionName(str(permission))
        if not isinstance(resource, ResourceRef):
            raise ValueError("AuthorizationPolicy.can resource must be a ResourceRef")
        if permission_name.value == "user:self":
            return resource.resource_type == "user" and resource.resource_id == str(user_id)

        for membership in self._repository.memberships_for_user(user_id):
            if not membership.active:
                continue
            group = self._repository.group_by_id(membership.group_id)
            if group is None or not group.active or not _group_matches_resource(group, resource):
                continue
            role = self._repository.role_by_id(membership.role_id)
            if role is None or not role.active:
                continue
            permissions = self._repository.permissions_for_role(role.role_id)
            if permission_name in permissions:
                return True
        return False

    def can_any(self, user_id: UserId, permissions: tuple[str, ...], resource: ResourceRef) -> bool:
        return any(self.can(user_id, permission, resource) for permission in permissions)


class ScopeAuthorizationPolicy:
    """Bounded session-scope policy for tests and local in-memory facades.

    Critical mutations should still re-check repository-backed AuthorizationPolicy.
    This class exists for framework-neutral API tests that inject already bounded
    scopes without a database.
    """

    def can(self, user_id: UserId, permission: PermissionName | str, resource: ResourceRef) -> bool:
        raise NotImplementedError("ScopeAuthorizationPolicy requires request-scoped claims")


def _group_matches_resource(group: Group, resource: ResourceRef) -> bool:
    if group.group_type is GroupType.PLATFORM:
        return resource.resource_type == "platform" or resource.resource_type in {
            "operator",
            "outbox",
            "store",
            "product",
            "inventory",
        }
    if group.group_type is GroupType.PERSONAL:
        return resource.resource_type == "user" and group.resource_id in {None, resource.resource_id}
    return group.resource_type == resource.resource_type and group.resource_id == resource.resource_id


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


__all__ = ["AuthorizationPolicy", "AuthorizationRepository", "ResourceRef"]
