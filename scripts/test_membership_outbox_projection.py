from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.auth.application import StoreMembershipProjectionConsumer  # noqa: E402
from token_payments.contexts.store_catalog.application import CreateStoreCommand, GrantStoreMembershipCommand  # noqa: E402
from token_payments.contexts.store_catalog.application import StoreCatalogApplicationService  # noqa: E402
from token_payments.contexts.store_catalog.domain import StoreMembership, StoreMembershipRole, StoreProfile  # noqa: E402
from token_payments.shared.domain import CommandId, OutboxMessage, StoreId, UserId, WalletAddress  # noqa: E402

from _store_catalog_test_support import OWNER_ID, OWNER_WALLET, STORE_ID, STORE_WALLET  # noqa: E402


NOW = datetime(2026, 5, 22, 5, 0, tzinfo=UTC)
STAFF_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdccaa55")
STAFF_WALLET = WalletAddress("0x5555555555555555555555555555555555555555")
OTHER_STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdccaa56")


def test_admin_create_store_grants_owner_rbac_projection_synchronously_and_emits_outbox() -> None:
    repository = ProjectionAwareCatalogRepository()
    repository.seed_user(OWNER_ID, OWNER_WALLET)
    service = StoreCatalogApplicationService(repository=repository)

    result = service.create_store(
        CreateStoreCommand(
            command_id=CommandId("store-owner-projection-001"),
            actor_user_id=OWNER_ID,
            store_id=STORE_ID,
            owner_user_id=OWNER_ID,
            store_wallet=STORE_WALLET,
            supported_chain_ids=(1337,),
            active=True,
            requested_at=NOW,
            request_id="req-store-owner-projection",
            payload_hash="hash-store-owner-projection",
        )
    )

    assert result.status.value == "completed"
    assert repository.memberships[(STORE_ID, OWNER_ID)].role is StoreMembershipRole.OWNER
    assert repository.direct_group_writes == [
        ("018f33aa-9e6d-73d8-9dc3-47d6cdccaa57", OWNER_ID, "MERCHANT_OWNER", True)
    ]
    assert len(repository.outbox_messages) == 1
    message = repository.outbox_messages[0]
    assert message.topic == "auth.rbac.projections"
    assert message.payload["roleId"] == "MERCHANT_OWNER"
    assert message.payload["userId"] == str(OWNER_ID)
    assert result.payload["merchantGroup"]["projection"] == "outbox"


def test_rejected_store_create_does_not_emit_or_apply_rbac_projection() -> None:
    repository = ProjectionAwareCatalogRepository()
    repository.seed_user(OWNER_ID, OWNER_WALLET)
    repository.save_store(
        StoreProfile(
            store_id=OTHER_STORE_ID,
            owner_user_id=OWNER_ID,
            display_name="Untitled Store",
            active=True,
            store_wallet=STORE_WALLET,
            supported_chain_ids=(1337,),
        )
    )
    service = StoreCatalogApplicationService(repository=repository)

    result = service.create_store(
        CreateStoreCommand(
            command_id=CommandId("store-owner-projection-conflict-001"),
            actor_user_id=OWNER_ID,
            store_id=STORE_ID,
            owner_user_id=OWNER_ID,
            store_wallet=STORE_WALLET,
            supported_chain_ids=(1337,),
            active=True,
            requested_at=NOW,
            request_id="req-store-owner-projection-conflict",
            payload_hash="hash-store-owner-projection-conflict",
        )
    )

    assert result.status.value == "rejected"
    assert result.rejection_reason == "STORE_DISPLAY_NAME_CONFLICT"
    assert repository.direct_group_writes == []
    assert repository.outbox_messages == []


def test_store_catalog_membership_write_updates_rbac_projection_synchronously_and_emits_outbox() -> None:
    repository = ProjectionAwareCatalogRepository()
    repository.seed_user(OWNER_ID, OWNER_WALLET)
    repository.seed_user(STAFF_ID, STAFF_WALLET)
    repository.save_store(
        StoreProfile(
            store_id=STORE_ID,
            owner_user_id=OWNER_ID,
            active=True,
            store_wallet=STORE_WALLET,
            supported_chain_ids=(1337,),
        )
    )
    service = StoreCatalogApplicationService(repository=repository)

    result = service.grant_store_membership(
        GrantStoreMembershipCommand(
            command_id=CommandId("membership-projection-001"),
            actor_user_id=OWNER_ID,
            store_id=STORE_ID,
            user_id=STAFF_ID,
            role=StoreMembershipRole.MANAGER,
            active=True,
            requested_at=NOW,
            request_id="req-membership-projection",
            payload_hash="hash-membership-projection",
        )
    )

    assert result.status.value == "completed"
    assert repository.memberships[(STORE_ID, STAFF_ID)].role is StoreMembershipRole.MANAGER
    assert repository.direct_group_writes == [
        ("018f33aa-9e6d-73d8-9dc3-47d6cdccaa57", STAFF_ID, "MERCHANT_MANAGER", True)
    ]
    assert len(repository.outbox_messages) == 1

    message = repository.outbox_messages[0]
    assert message.topic == "auth.rbac.projections"
    assert message.name == "StoreCatalogStoreMembershipChangedEvent"
    assert message.payload["sourceOfTruth"] == "store_catalog_store_memberships"
    assert message.payload["projection"] == "auth_group_memberships"
    assert message.payload["storeId"] == str(STORE_ID)
    assert message.payload["userId"] == str(STAFF_ID)
    assert message.payload["roleId"] == "MERCHANT_MANAGER"
    assert message.payload["active"] is True
    assert result.payload["merchantGroup"]["projection"] == "outbox"


def test_auth_membership_projection_consumer_is_idempotent_and_order_tolerant() -> None:
    repository = ProjectionRepository()
    consumer = StoreMembershipProjectionConsumer(repository)
    payload = {
        "eventId": "evt-membership-001",
        "storeId": str(STORE_ID),
        "groupId": "018f33aa-9e6d-73d8-9dc3-47d6cdccaa57",
        "userId": str(STAFF_ID),
        "roleId": "MERCHANT_MANAGER",
        "active": True,
        "version": 2,
    }

    first = consumer.handle(payload)
    duplicate = consumer.handle(payload)
    stale = consumer.handle({**payload, "eventId": "evt-membership-000", "active": False, "version": 1})

    assert first["status"] == "projected"
    assert duplicate["status"] == "duplicate"
    assert stale["status"] == "stale"
    assert repository.projected[(payload["groupId"], str(STAFF_ID))] == {
        "roleId": "MERCHANT_MANAGER",
        "active": True,
        "version": 2,
    }


def test_postgres_catalog_repository_exposes_transactional_membership_projection_hook() -> None:
    source = (ROOT / "app/token_payments/contexts/store_catalog/adapter/postgres.py").read_text(encoding="utf-8")

    assert "def record_membership_projection_event" in source
    assert "PostgresOutboxMessageRepository(self._connection).save(message)" in source


class ProjectionAwareCatalogRepository:
    def __init__(self) -> None:
        self.users: dict[UserId, object] = {}
        self.stores: dict[StoreId, StoreProfile] = {}
        self.memberships: dict[tuple[StoreId, UserId], StoreMembership] = {}
        self.idempotency = {}
        self.audit_records = []
        self.outbox_messages: list[OutboxMessage] = []
        self.direct_group_writes: list[tuple[str, UserId, str, bool]] = []

    def seed_user(self, user_id: UserId, wallet: WalletAddress) -> None:
        self.users[user_id] = type("UserRecord", (), {"user_id": user_id, "primary_wallet": wallet, "role": "CUSTOMER"})()

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

    def save_store(self, store: StoreProfile) -> None:
        self.stores[store.store_id] = store

    def save_order_store_projection(self, store: StoreProfile) -> None:
        pass

    def save_store_approval_store_projection(self, store: StoreProfile) -> None:
        pass

    def get_membership(self, store_id: StoreId, user_id: UserId):
        return self.memberships.get((store_id, user_id))

    def save_membership(self, membership: StoreMembership) -> None:
        self.memberships[(membership.store_id, membership.user_id)] = membership

    def ensure_merchant_group_for_store(self, store_id: StoreId) -> str:
        return "018f33aa-9e6d-73d8-9dc3-47d6cdccaa57"

    def grant_group_membership(self, group_id: str, user_id: UserId, role_id: str, *, active: bool) -> None:
        self.direct_group_writes.append((group_id, user_id, role_id, active))

    def record_membership_projection_event(self, message: OutboxMessage) -> None:
        self.outbox_messages.append(message)

    def record_audit(self, record) -> str:
        self.audit_records.append(record)
        return f"audit-{len(self.audit_records)}"


class ProjectionRepository:
    def __init__(self) -> None:
        self.processed: set[str] = set()
        self.versions: dict[tuple[str, str], int] = {}
        self.projected: dict[tuple[str, str], dict[str, object]] = {}

    def was_membership_event_processed(self, event_id: str) -> bool:
        return event_id in self.processed

    def last_membership_projection_version(self, group_id: str, user_id: str) -> int:
        return self.versions.get((group_id, user_id), 0)

    def upsert_projected_membership(self, *, group_id: str, user_id: str, role_id: str, active: bool, version: int) -> None:
        self.projected[(group_id, user_id)] = {"roleId": role_id, "active": active, "version": version}
        self.versions[(group_id, user_id)] = version

    def mark_membership_event_processed(self, event_id: str) -> None:
        self.processed.add(event_id)
