from __future__ import annotations

import sys
from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import ApiAuthContext, ApiRequest  # noqa: E402
from token_payments.api.operator import AdminRoleOperatorPolicy, OperatorClaims  # noqa: E402
from token_payments.api.operator_actions import AdminRoleOperatorActionPolicy, OperatorActionName  # noqa: E402
from token_payments.contexts.auth.application.authorization import AuthorizationPolicy, ResourceRef  # noqa: E402
from token_payments.contexts.auth.domain import (  # noqa: E402
    Group,
    GroupId,
    GroupMembership,
    GroupType,
    Permission,
    PermissionName,
    Role,
    RoleId,
    RolePermission,
)
from token_payments.shared.domain import StoreId, UserId  # noqa: E402


NOW = datetime(2026, 5, 20, 4, 0, tzinfo=UTC)
PLATFORM_USER = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcccc01")
MERCHANT_USER = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcccc02")
CUSTOMER_USER = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcccc03")
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcccc04")
OTHER_STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcccc05")
PLATFORM_GROUP = GroupId("018f33aa-9e6d-73d8-9dc3-47d6cdcccc06")
MERCHANT_GROUP = GroupId("018f33aa-9e6d-73d8-9dc3-47d6cdcccc07")
OTHER_MERCHANT_GROUP = GroupId("018f33aa-9e6d-73d8-9dc3-47d6cdcccc08")
PERSONAL_GROUP = GroupId("018f33aa-9e6d-73d8-9dc3-47d6cdcccc09")


def test_platform_permissions_are_explicit_and_outbox_retry_requires_two_permissions() -> None:
    policy = AuthorizationPolicy(_repository())

    assert policy.can(PLATFORM_USER, "operator:read", ResourceRef.platform())
    assert policy.can(PLATFORM_USER, "operator:action", ResourceRef.platform())
    assert policy.can(PLATFORM_USER, "outbox:retry", ResourceRef(resource_type="outbox", resource_id="message-1"))
    assert not policy.can(CUSTOMER_USER, "operator:read", ResourceRef.platform())

    action_policy = AdminRoleOperatorActionPolicy()
    assert action_policy.can_execute_action(
        OperatorClaims(user_id=str(PLATFORM_USER), scopes=("operator:action",)),
        OperatorActionName.CANCEL_ORDER,
    )
    assert not action_policy.can_execute_action(
        OperatorClaims(user_id=str(PLATFORM_USER), scopes=("operator:action",)),
        OperatorActionName.RETRY_OUTBOX_MESSAGE,
    )
    assert action_policy.can_execute_action(
        OperatorClaims(user_id=str(PLATFORM_USER), scopes=("operator:action", "outbox:retry")),
        OperatorActionName.RETRY_OUTBOX_MESSAGE,
    )


def test_merchant_permissions_are_scoped_to_requested_store_and_ignore_role_name_shortcuts() -> None:
    policy = AuthorizationPolicy(_repository())

    assert policy.can(MERCHANT_USER, "product:write", ResourceRef.store(STORE_ID))
    assert policy.can(MERCHANT_USER, "inventory:write", ResourceRef.store(STORE_ID))
    assert policy.can(MERCHANT_USER, "merchant_member:invite", ResourceRef.store(STORE_ID))
    assert not policy.can(MERCHANT_USER, "product:write", ResourceRef.store(OTHER_STORE_ID))
    assert not policy.can(MERCHANT_USER, "merchant_member:manage", ResourceRef.store(STORE_ID))
    assert not policy.can(CUSTOMER_USER, "inventory:write", ResourceRef.store(STORE_ID))


def test_inactive_membership_inactive_role_and_missing_permission_are_denied() -> None:
    repository = _repository()
    repository.roles[RoleId("MERCHANT_MANAGER")] = Role(
        RoleId("MERCHANT_MANAGER"),
        "inactive manager",
        GroupType.MERCHANT,
        active=False,
        merchant_assignable=True,
    )

    assert not AuthorizationPolicy(repository).can(MERCHANT_USER, "product:write", ResourceRef.store(STORE_ID))

    inactive_membership_repo = _repository()
    inactive_membership_repo.memberships = (
        GroupMembership(MERCHANT_USER, MERCHANT_GROUP, RoleId("MERCHANT_MANAGER"), active=False, joined_at=NOW),
    )

    assert not AuthorizationPolicy(inactive_membership_repo).can(
        MERCHANT_USER,
        "product:write",
        ResourceRef.store(STORE_ID),
    )


def test_scope_operator_policy_ignores_legacy_x_user_role_authority() -> None:
    read_policy = AdminRoleOperatorPolicy()

    assert read_policy.can_read_observability(OperatorClaims(user_id=str(PLATFORM_USER), scopes=("operator:read",)))
    assert not read_policy.can_read_observability(OperatorClaims(user_id=str(PLATFORM_USER), role="ADMIN", scopes=()))


def test_api_auth_context_permission_snapshot_is_bounded_and_role_is_not_a_field() -> None:
    context = ApiAuthContext(
        user_id=str(MERCHANT_USER),
        session_id="session-1",
        active_group_id=str(MERCHANT_GROUP),
        scopes=("product:write", "inventory:write"),
        role="ADMIN",
    )
    request = ApiRequest(request_id="req", method="GET", path="/operator/dashboard", auth_context=context)

    assert context.role == "ADMIN"
    assert request.auth_context is context
    assert "product:write" in context.scopes
    assert "role" not in {field.name for field in fields(ApiAuthContext)}


def _repository() -> "InMemoryAuthorizationRepository":
    return InMemoryAuthorizationRepository(
        groups=[
            Group(PLATFORM_GROUP, GroupType.PLATFORM, "platform ops"),
            Group(MERCHANT_GROUP, GroupType.MERCHANT, "merchant store", resource_type="store", resource_id=str(STORE_ID)),
            Group(
                OTHER_MERCHANT_GROUP,
                GroupType.MERCHANT,
                "other merchant store",
                resource_type="store",
                resource_id=str(OTHER_STORE_ID),
            ),
            Group(PERSONAL_GROUP, GroupType.PERSONAL, "personal", resource_type="user", resource_id=str(CUSTOMER_USER)),
        ],
        roles=[
            Role(RoleId("PLATFORM_ADMIN"), "platform admin", GroupType.PLATFORM),
            Role(RoleId("MERCHANT_MANAGER"), "merchant manager", GroupType.MERCHANT, merchant_assignable=True),
            Role(RoleId("PERSONAL_CUSTOMER"), "personal customer", GroupType.PERSONAL),
        ],
        permissions=[
            Permission(PermissionName("operator:read")),
            Permission(PermissionName("operator:action")),
            Permission(PermissionName("outbox:retry")),
            Permission(PermissionName("product:write")),
            Permission(PermissionName("inventory:write")),
            Permission(PermissionName("merchant_member:invite")),
            Permission(PermissionName("user:self")),
        ],
        role_permissions=[
            RolePermission(RoleId("PLATFORM_ADMIN"), PermissionName("operator:read")),
            RolePermission(RoleId("PLATFORM_ADMIN"), PermissionName("operator:action")),
            RolePermission(RoleId("PLATFORM_ADMIN"), PermissionName("outbox:retry")),
            RolePermission(RoleId("MERCHANT_MANAGER"), PermissionName("product:write")),
            RolePermission(RoleId("MERCHANT_MANAGER"), PermissionName("inventory:write")),
            RolePermission(RoleId("MERCHANT_MANAGER"), PermissionName("merchant_member:invite")),
            RolePermission(RoleId("PERSONAL_CUSTOMER"), PermissionName("user:self")),
        ],
        memberships=[
            GroupMembership(PLATFORM_USER, PLATFORM_GROUP, RoleId("PLATFORM_ADMIN"), joined_at=NOW),
            GroupMembership(MERCHANT_USER, MERCHANT_GROUP, RoleId("MERCHANT_MANAGER"), joined_at=NOW),
            GroupMembership(CUSTOMER_USER, PERSONAL_GROUP, RoleId("PERSONAL_CUSTOMER"), joined_at=NOW),
        ],
    )


class InMemoryAuthorizationRepository:
    def __init__(
        self,
        *,
        groups: list[Group],
        roles: list[Role],
        permissions: list[Permission],
        role_permissions: list[RolePermission],
        memberships: list[GroupMembership],
    ) -> None:
        self.groups = {group.group_id: group for group in groups}
        self.roles = {role.role_id: role for role in roles}
        self.permissions = {permission.name: permission for permission in permissions}
        self.role_permissions = tuple(role_permissions)
        self.memberships = tuple(memberships)

    def memberships_for_user(self, user_id: UserId) -> tuple[GroupMembership, ...]:
        return tuple(membership for membership in self.memberships if membership.user_id == user_id)

    def group_by_id(self, group_id: GroupId) -> Group | None:
        return self.groups.get(group_id)

    def role_by_id(self, role_id: RoleId) -> Role | None:
        return self.roles.get(role_id)

    def permissions_for_role(self, role_id: RoleId) -> tuple[PermissionName, ...]:
        values = []
        for edge in self.role_permissions:
            permission = self.permissions.get(edge.permission)
            if edge.role_id == role_id and edge.active and permission is not None and permission.active:
                values.append(edge.permission)
        return tuple(values)
