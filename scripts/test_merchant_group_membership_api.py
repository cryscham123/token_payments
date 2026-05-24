from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import (  # noqa: E402
    ApiAuthContext,
    HttpRouter,
    MERCHANT_MEMBERSHIP_HTTP_ROUTES,
    MerchantMembershipApi,
    register_merchant_membership_routes,
)
from token_payments.contexts.auth.application import MerchantMembershipService  # noqa: E402
from token_payments.contexts.auth.domain import (  # noqa: E402
    Group,
    GroupId,
    GroupInvitation,
    GroupMembership,
    GroupType,
    InvitationId,
    InvitationStatus,
    Role,
    RoleId,
)
from token_payments.contexts.store_catalog.application import StoreCatalogApplicationService  # noqa: E402
from token_payments.contexts.store_catalog.application.commands import GrantStoreMembershipCommand  # noqa: E402
from token_payments.contexts.store_catalog.domain import StoreMembership, StoreProfile  # noqa: E402
from token_payments.contexts.store_catalog.domain import StoreMembershipRole  # noqa: E402
from token_payments.shared.domain import CommandId, StoreId, UserId, WalletAddress  # noqa: E402

from _store_catalog_test_support import OWNER_ID, STORE_ID, STORE_WALLET, OWNER_WALLET  # noqa: E402


NOW = datetime(2026, 5, 20, 5, 0, tzinfo=UTC)
GROUP_ID = GroupId("018f33aa-9e6d-73d8-9dc3-47d6cdccdd01")
INVITATION_ID = InvitationId("018f33aa-9e6d-73d8-9dc3-47d6cdccdd02")
STAFF_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdccdd03")
OTHER_STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdccdd04")


def test_store_provisioning_links_merchant_group_and_initial_owner_membership() -> None:
    repository = FakeMerchantRepository()
    service = StoreCatalogApplicationService(repository=repository)
    repository.seed_user(OWNER_ID, OWNER_WALLET)

    result = service.create_store(
        command=__import__(
            "token_payments.contexts.store_catalog.application.commands",
            fromlist=["CreateStoreCommand"],
        ).CreateStoreCommand(
            command_id=CommandId("merchant-group-store-001"),
            actor_user_id=OWNER_ID,
            store_id=STORE_ID,
            owner_user_id=OWNER_ID,
            store_wallet=STORE_WALLET,
            supported_chain_ids=(1337,),
            active=True,
            requested_at=NOW,
            request_id="req-merchant-group-store",
            payload_hash="hash-merchant-group-store",
        )
    )

    assert result.status.value == "completed"
    assert result.payload["merchantGroup"] == {
        "groupId": str(GROUP_ID),
        "ownerUserId": str(OWNER_ID),
        "roleId": "MERCHANT_OWNER",
    }
    assert repository.group_memberships[(GROUP_ID, OWNER_ID)].role_id == RoleId("MERCHANT_OWNER")


def test_admin_grant_membership_route_contract_links_merchant_group_membership() -> None:
    repository = FakeMerchantRepository()
    service = StoreCatalogApplicationService(repository=repository)
    repository.seed_user(OWNER_ID, OWNER_WALLET)
    repository.seed_user(STAFF_ID, WalletAddress("0x5555555555555555555555555555555555555555"))
    repository.save_store(
        StoreProfile(
            store_id=STORE_ID,
            owner_user_id=OWNER_ID,
            active=True,
            store_wallet=STORE_WALLET,
            supported_chain_ids=(1337,),
        )
    )

    result = service.grant_store_membership(
        GrantStoreMembershipCommand(
            command_id=CommandId("merchant-group-grant-001"),
            actor_user_id=OWNER_ID,
            store_id=STORE_ID,
            user_id=STAFF_ID,
            role=StoreMembershipRole.MANAGER,
            active=True,
            requested_at=NOW,
            request_id="req-merchant-group-grant",
            payload_hash="hash-merchant-group-grant",
        )
    )

    assert result.status.value == "completed"
    assert result.payload["merchantGroup"] == {
        "groupId": str(GROUP_ID),
        "userId": str(STAFF_ID),
        "roleId": "MERCHANT_MANAGER",
        "active": True,
    }
    assert repository.group_memberships[(GROUP_ID, STAFF_ID)].role_id == RoleId("MERCHANT_MANAGER")


def test_merchant_member_invitation_accept_and_lists_are_store_scoped() -> None:
    repository = FakeMerchantRepository()
    router = _router(repository, _auth(OWNER_ID, "merchant_member:read", "merchant_member:invite"))

    created = router.handle(
        "POST",
        f"/merchant/stores/{STORE_ID}/invitations",
        headers={"Content-Type": "application/json"},
        body=_json_body({"targetUserId": str(STAFF_ID), "roleId": "MERCHANT_STAFF"}),
        received_at=NOW,
    )
    listed = router.handle("GET", f"/merchant/stores/{STORE_ID}/invitations", received_at=NOW)
    accepted = _router(repository, _auth(STAFF_ID)).handle(
        "POST",
        f"/merchant/invitations/{INVITATION_ID}/accept",
        headers={"Content-Type": "application/json"},
        body=_json_body({}),
        received_at=NOW + timedelta(minutes=5),
    )
    members = _router(repository, _auth(OWNER_ID, "merchant_member:read")).handle(
        "GET",
        f"/merchant/stores/{STORE_ID}/members",
        received_at=NOW,
    )

    assert created.status_code == 201
    assert _json(created.body)["invitation"]["roleId"] == "MERCHANT_STAFF"
    assert listed.status_code == 200
    assert len(_json(listed.body)["invitations"]) == 1
    assert accepted.status_code == 200
    assert repository.group_memberships[(GROUP_ID, STAFF_ID)].role_id == RoleId("MERCHANT_STAFF")
    assert {member["userId"] for member in _json(members.body)["members"]} == {str(OWNER_ID), str(STAFF_ID)}


def test_merchant_facing_apis_reject_owner_and_platform_role_assignment() -> None:
    repository = FakeMerchantRepository()
    router = _router(repository, _auth(OWNER_ID, "merchant_member:invite", "merchant_member:manage"))

    owner_invite = router.handle(
        "POST",
        f"/merchant/stores/{STORE_ID}/invitations",
        headers={"Content-Type": "application/json"},
        body=_json_body({"targetUserId": str(STAFF_ID), "roleId": "MERCHANT_OWNER"}),
        received_at=NOW,
    )
    platform_invite = router.handle(
        "POST",
        f"/merchant/stores/{STORE_ID}/invitations",
        headers={"Content-Type": "application/json"},
        body=_json_body({"targetUserId": str(STAFF_ID), "roleId": "PLATFORM_ADMIN"}),
        received_at=NOW,
    )

    assert owner_invite.status_code == 409
    assert _json(owner_invite.body)["error"]["code"] == "OWNER_ROLE_PROTECTED"
    assert platform_invite.status_code == 400
    assert _json(platform_invite.body)["error"]["code"] == "ROLE_TEMPLATE_NOT_ALLOWED"


def test_member_role_update_and_removal_allow_staff_only_and_protect_owner() -> None:
    repository = FakeMerchantRepository()
    repository.group_memberships[(GROUP_ID, STAFF_ID)] = GroupMembership(STAFF_ID, GROUP_ID, RoleId("MERCHANT_STAFF"), joined_at=NOW)
    router = _router(repository, _auth(OWNER_ID, "merchant_member:manage"))

    updated = router.handle(
        "PATCH",
        f"/merchant/stores/{STORE_ID}/members/{STAFF_ID}",
        headers={"Content-Type": "application/json"},
        body=_json_body({"roleId": "MERCHANT_MANAGER"}),
        received_at=NOW,
    )
    removed = router.handle("DELETE", f"/merchant/stores/{STORE_ID}/members/{STAFF_ID}", received_at=NOW)
    owner_removed = router.handle("DELETE", f"/merchant/stores/{STORE_ID}/members/{OWNER_ID}", received_at=NOW)

    assert updated.status_code == 200
    assert repository.group_memberships[(GROUP_ID, STAFF_ID)].role_id == RoleId("MERCHANT_MANAGER")
    assert removed.status_code == 200
    assert repository.group_memberships[(GROUP_ID, STAFF_ID)].active is False
    assert owner_removed.status_code == 409
    assert _json(owner_removed.body)["error"]["code"] == "OWNER_ROLE_PROTECTED"


def test_role_catalog_exposes_only_non_owner_merchant_staff_templates_and_route_manifest() -> None:
    response = _router(FakeMerchantRepository(), _auth(OWNER_ID)).handle("GET", "/merchant/role-catalog")
    roles = _json(response.body)["roles"]

    assert {role["roleId"] for role in roles} == {"MERCHANT_MANAGER", "MERCHANT_STAFF"}
    assert all(role["rawPermissionMutationAllowed"] is False for role in roles)
    assert {
        spec.operation_id for spec in MERCHANT_MEMBERSHIP_HTTP_ROUTES.values()
    } == {
        "listMerchantStoreMembers",
        "listMerchantStoreInvitations",
        "createMerchantStoreInvitation",
        "acceptMerchantInvitation",
        "revokeMerchantInvitation",
        "updateMerchantStoreMemberRole",
        "removeMerchantStoreMember",
        "getMerchantRoleCatalog",
    }


def _router(repository: "FakeMerchantRepository", auth_context: ApiAuthContext) -> HttpRouter:
    router = HttpRouter(auth_context_factory=lambda _request: auth_context, allow_dev_auth_headers=False)
    register_merchant_membership_routes(router, MerchantMembershipApi(MerchantMembershipService(repository, invitation_id_generator=FixedIdGenerator(str(INVITATION_ID)))))
    return router


def _auth(user_id: UserId, *scopes: str) -> ApiAuthContext:
    return ApiAuthContext(user_id=str(user_id), scopes=tuple(scopes), session_id="session")


def _json_body(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _json(body: bytes) -> dict[str, Any]:
    decoded = json.loads(body)
    assert isinstance(decoded, dict)
    return decoded


class FixedIdGenerator:
    def __init__(self, value: str) -> None:
        self.value = value

    def new_id(self) -> str:
        return self.value


class FakeMerchantRepository:
    def __init__(self) -> None:
        self.users: dict[UserId, object] = {}
        self.groups = {GROUP_ID: Group(GROUP_ID, GroupType.MERCHANT, "Demo store group", resource_type="store", resource_id=str(STORE_ID))}
        self.store_groups = {STORE_ID: GROUP_ID}
        self.group_memberships: dict[tuple[GroupId, UserId], GroupMembership] = {
            (GROUP_ID, OWNER_ID): GroupMembership(OWNER_ID, GROUP_ID, RoleId("MERCHANT_OWNER"), joined_at=NOW)
        }
        self.invitations: dict[InvitationId, GroupInvitation] = {}
        self.idempotency = {}
        self.stores = {}
        self.store_memberships = {}
        self.audit_records = []

    def seed_user(self, user_id: UserId, wallet: WalletAddress) -> None:
        from token_payments.contexts.auth.domain import User

        self.users[user_id] = User.register_by_wallet(user_id, wallet)

    def get_user_by_id(self, user_id: UserId):
        return self.users.get(user_id)

    def get_idempotency_record(self, handler: str, idempotency_key: str):
        return self.idempotency.get((handler, idempotency_key))

    def save_idempotency_record(self, record) -> None:
        self.idempotency[(record.handler, record.idempotency_key)] = record

    def get_store(self, store_id: StoreId):
        return self.stores.get(store_id)

    def get_store_by_display_name(self, display_name: str):
        key = display_name.casefold()
        return next((store for store in self.stores.values() if store.display_name.casefold() == key), None)

    def get_membership(self, store_id: StoreId, user_id: UserId):
        return self.store_memberships.get((store_id, user_id))

    def save_store(self, store: StoreProfile) -> None:
        self.stores[store.store_id] = store

    def save_membership(self, membership: StoreMembership) -> None:
        self.store_memberships[(membership.store_id, membership.user_id)] = membership

    def save_order_store_projection(self, _store: StoreProfile) -> None:
        return None

    def save_store_approval_store_projection(self, _store: StoreProfile) -> None:
        return None

    def record_audit(self, record) -> str:
        self.audit_records.append(record)
        return f"audit-{len(self.audit_records)}"

    def ensure_merchant_group_for_store(self, store_id: StoreId) -> GroupId:
        self.store_groups[store_id] = GROUP_ID
        return GROUP_ID

    def grant_group_membership(self, group_id: GroupId, user_id: UserId, role_id: str, *, active: bool) -> None:
        self.group_memberships[(group_id, user_id)] = GroupMembership(user_id, group_id, RoleId(role_id), active=active, joined_at=NOW)

    def merchant_group_for_store(self, store_id: StoreId) -> Group | None:
        group_id = self.store_groups.get(store_id)
        return self.groups.get(group_id) if group_id is not None else None

    def members_for_group(self, group_id: GroupId) -> tuple[GroupMembership, ...]:
        return tuple(membership for (gid, _uid), membership in self.group_memberships.items() if gid == group_id)

    def save_membership(self, membership):  # type: ignore[no-redef]
        if isinstance(membership, GroupMembership):
            self.group_memberships[(membership.group_id, membership.user_id)] = membership
            return
        self.store_memberships[(membership.store_id, membership.user_id)] = membership

    def get_membership(self, first, second):  # type: ignore[no-redef]
        if isinstance(first, GroupId):
            return self.group_memberships.get((first, second))
        return self.store_memberships.get((first, second))

    def invitations_for_group(self, group_id: GroupId) -> tuple[GroupInvitation, ...]:
        return tuple(invitation for invitation in self.invitations.values() if invitation.group_id == group_id)

    def get_invitation(self, invitation_id: InvitationId) -> GroupInvitation | None:
        return self.invitations.get(invitation_id)

    def save_invitation(self, invitation: GroupInvitation) -> None:
        self.invitations[invitation.invitation_id] = invitation

    def role_catalog(self) -> tuple[Role, ...]:
        return (
            Role(RoleId("MERCHANT_OWNER"), "Owner", GroupType.MERCHANT, owner_role=True),
            Role(RoleId("MERCHANT_MANAGER"), "Manager", GroupType.MERCHANT, merchant_assignable=True),
            Role(RoleId("MERCHANT_STAFF"), "Staff", GroupType.MERCHANT, merchant_assignable=True),
            Role(RoleId("PLATFORM_ADMIN"), "Platform admin", GroupType.PLATFORM),
        )
