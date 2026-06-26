from __future__ import annotations

import sys
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.auth.application.authorization import AuthorizationPolicy, ResourceRef  # noqa: E402
from token_payments.contexts.auth.domain import (  # noqa: E402
    Group,
    GroupId,
    GroupInvitation,
    GroupMembership,
    GroupType,
    InvitationId,
    InvitationStatus,
    MerchantRoleTemplate,
    Permission,
    PermissionName,
    Role,
    RoleId,
    RolePermission,
    User,
)
from token_payments.shared.domain import StoreId, UserId, WalletAddress  # noqa: E402


USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdccaa01")
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdccaa02")
PERSONAL_GROUP_ID = GroupId("018f33aa-9e6d-73d8-9dc3-47d6cdccaa03")
MERCHANT_GROUP_ID = GroupId("018f33aa-9e6d-73d8-9dc3-47d6cdccaa04")
PLATFORM_GROUP_ID = GroupId("018f33aa-9e6d-73d8-9dc3-47d6cdccaa05")
NOW = datetime(2026, 5, 20, 2, 0, tzinfo=UTC)


def test_user_identity_has_no_global_role_field_and_can_join_multiple_group_types() -> None:
    user = User.register_by_wallet(USER_ID, "0x1111111111111111111111111111111111111111")
    personal = Group(PERSONAL_GROUP_ID, GroupType.PERSONAL, "personal self")
    merchant = Group(MERCHANT_GROUP_ID, GroupType.MERCHANT, "merchant store", resource_type="store", resource_id=str(STORE_ID))
    platform = Group(PLATFORM_GROUP_ID, GroupType.PLATFORM, "platform ops")
    memberships = (
        GroupMembership(user.user_id, personal.group_id, RoleId("PERSONAL_CUSTOMER"), joined_at=NOW),
        GroupMembership(user.user_id, merchant.group_id, RoleId("MERCHANT_MANAGER"), joined_at=NOW),
        GroupMembership(user.user_id, platform.group_id, RoleId("PLATFORM_OPERATOR"), joined_at=NOW),
    )

    assert "role" not in {field.name for field in fields(User)}
    assert user.primary_wallet == WalletAddress("0x1111111111111111111111111111111111111111")
    assert {group.group_type for group in (personal, merchant, platform)} == {
        GroupType.PERSONAL,
        GroupType.MERCHANT,
        GroupType.PLATFORM,
    }
    assert {membership.user_id for membership in memberships} == {user.user_id}


def test_roles_are_permission_bundles_and_inactive_edges_do_not_grant_access() -> None:
    repository = InMemoryPolicyRepository(
        groups=[
            Group(MERCHANT_GROUP_ID, GroupType.MERCHANT, "merchant store", resource_type="store", resource_id=str(STORE_ID)),
        ],
        roles=[
            Role(RoleId("MERCHANT_MANAGER"), "Merchant manager", GroupType.MERCHANT, active=True, merchant_assignable=True),
            Role(RoleId("MERCHANT_STAFF"), "Merchant staff", GroupType.MERCHANT, active=False, merchant_assignable=True),
        ],
        permissions=[
            Permission(PermissionName("inventory:write")),
            Permission(PermissionName("product:write")),
        ],
        role_permissions=[
            RolePermission(RoleId("MERCHANT_MANAGER"), PermissionName("inventory:write")),
            RolePermission(RoleId("MERCHANT_STAFF"), PermissionName("product:write")),
        ],
        memberships=[
            GroupMembership(USER_ID, MERCHANT_GROUP_ID, RoleId("MERCHANT_MANAGER"), active=True, joined_at=NOW),
            GroupMembership(USER_ID, MERCHANT_GROUP_ID, RoleId("MERCHANT_STAFF"), active=True, joined_at=NOW),
        ],
    )
    policy = AuthorizationPolicy(repository)

    assert policy.can(USER_ID, "inventory:write", ResourceRef.store(STORE_ID))
    assert not policy.can(USER_ID, "product:write", ResourceRef.store(STORE_ID))
    assert not policy.can(USER_ID, "inventory:write", ResourceRef.store(StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdccaa99")))


def test_merchant_role_templates_exclude_owner_assignment_from_merchant_surface() -> None:
    owner = Role(RoleId("MERCHANT_OWNER"), "Merchant owner", GroupType.MERCHANT, owner_role=True)
    manager = Role(
        RoleId(MerchantRoleTemplate.MERCHANT_MANAGER.value),
        "Merchant manager",
        GroupType.MERCHANT,
        merchant_assignable=True,
    )
    staff = Role(
        RoleId(MerchantRoleTemplate.MERCHANT_STAFF.value),
        "Merchant staff",
        GroupType.MERCHANT,
        merchant_assignable=True,
    )

    assert not owner.merchant_assignable
    assert {role.role_id.value for role in (manager, staff) if role.merchant_assignable} == {
        "MERCHANT_MANAGER",
        "MERCHANT_STAFF",
    }


def test_group_invitation_targets_users_or_wallets_without_nested_group_membership() -> None:
    invitation = GroupInvitation(
        invitation_id=InvitationId("018f33aa-9e6d-73d8-9dc3-47d6cdccaa06"),
        group_id=MERCHANT_GROUP_ID,
        invited_role_id=RoleId("MERCHANT_STAFF"),
        invited_by_user_id=USER_ID,
        target_wallet="0x2222222222222222222222222222222222222222",
        status=InvitationStatus.PENDING,
        created_at=NOW,
        expires_at=NOW + timedelta(days=7),
    )

    assert invitation.is_open_for(
        UserId("018f33aa-9e6d-73d8-9dc3-47d6cdccaa07"),
        "0x2222222222222222222222222222222222222222",
        NOW,
    )
    assert {field.name for field in fields(GroupMembership)} == {"user_id", "group_id", "role_id", "active", "joined_at", "wallet_address", "display_name"}


def test_postgres_schema_adds_additive_rbac_tables_and_store_group_link() -> None:
    schema = (ROOT / "app" / "postgres" / "init.d" / "001-token-payments-schema.sql").read_text(encoding="utf-8")
    compatibility = (ROOT / "app" / "token_payments" / "shared" / "adapter" / "postgres" / "schema.py").read_text(
        encoding="utf-8"
    )

    for table in (
        "auth_groups",
        "auth_roles",
        "auth_permissions",
        "auth_role_permissions",
        "auth_group_memberships",
        "auth_group_invitations",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in schema
        assert f"CREATE TABLE IF NOT EXISTS {table}" in compatibility
    assert "group_id UUID REFERENCES auth_groups (group_id)" in schema
    assert "ALTER TABLE IF EXISTS store_catalog_stores" in compatibility
    assert "('MERCHANT_OWNER', 'inventory:write', true)" in compatibility
    assert "('MERCHANT_MANAGER', 'inventory:write', true)" in compatibility
    assert "ON CONFLICT (role_id, permission_name) DO UPDATE SET" in compatibility
    assert "auth_users.role column is legacy compatibility only" in (ROOT / "docs" / "DOMAIN_MODEL.md").read_text(
        encoding="utf-8"
    )


class InMemoryPolicyRepository:
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
        self.role_permissions = role_permissions
        self.memberships = memberships

    def memberships_for_user(self, user_id: UserId) -> tuple[GroupMembership, ...]:
        return tuple(membership for membership in self.memberships if membership.user_id == user_id)

    def group_by_id(self, group_id: GroupId) -> Group | None:
        return self.groups.get(group_id)

    def role_by_id(self, role_id: RoleId) -> Role | None:
        return self.roles.get(role_id)

    def permissions_for_role(self, role_id: RoleId) -> tuple[PermissionName, ...]:
        active_permissions = []
        for edge in self.role_permissions:
            permission = self.permissions.get(edge.permission)
            if edge.role_id == role_id and edge.active and permission is not None and permission.active:
                active_permissions.append(edge.permission)
        return tuple(active_permissions)
