"""Application service for admin store provisioning and product registration."""

from __future__ import annotations

from html import escape
from collections.abc import Callable
from typing import Any, Mapping

from token_payments.contexts.auth.domain import GroupId
from token_payments.contexts.auth.domain import User, UserRole
from token_payments.contexts.store_catalog.domain import (
    PublicStoreId,
    StoreMembership,
    StoreMembershipRole,
    StorePaymentSettings,
    StoreProduct,
    StoreProfile,
)
from token_payments.shared.domain import UserId

from .commands import (
    CreateOrReuseStoreUserCommand,
    CreateStoreCommand,
    GetStoreProfileQuery,
    GrantStoreMembershipCommand,
    ListMerchantStoresQuery,
    RegisterStoreProductCommand,
    UpdateStoreProfileCommand,
)
from .ports import (
    CatalogAuditRecord,
    CatalogIdempotencyRecord,
    CatalogWriteRepository,
    StoreCatalogCommandResult,
    StoreCatalogCommandStatus,
)


class StoreCatalogApplicationService:
    """Coordinates canonical catalog writes and existing runtime projections."""

    CREATE_USER_HANDLER = "createOrReuseStoreUser"
    CREATE_STORE_HANDLER = "createStore"
    GRANT_MEMBERSHIP_HANDLER = "grantStoreMembership"
    REGISTER_PRODUCT_HANDLER = "registerStoreProduct"
    UPDATE_STORE_PROFILE_HANDLER = "updateStoreProfile"

    def __init__(self, *, repository: CatalogWriteRepository, user_id_generator: Any | None = None) -> None:
        self._repository = repository
        self._user_id_generator = user_id_generator

    def create_or_reuse_store_user(self, command: CreateOrReuseStoreUserCommand) -> StoreCatalogCommandResult:
        return self._idempotent(
            self.CREATE_USER_HANDLER,
            command,
            lambda: self._create_or_reuse_store_user(command),
        )

    def create_store(self, command: CreateStoreCommand) -> StoreCatalogCommandResult:
        return self._idempotent(self.CREATE_STORE_HANDLER, command, lambda: self._create_store(command))

    def get_store_profile(self, query: GetStoreProfileQuery) -> Mapping[str, Any] | None:
        store = self._repository.get_store_by_public_id(query.public_store_id)
        return _public_store_payload(store) if store is not None else None

    def list_merchant_stores(self, query: ListMerchantStoresQuery) -> tuple[Mapping[str, Any], ...]:
        return tuple(_public_store_payload(store) for store in self._repository.list_stores_for_member(query.actor_user_id))

    def update_store_profile(self, command: UpdateStoreProfileCommand) -> StoreCatalogCommandResult:
        return self._idempotent(
            self.UPDATE_STORE_PROFILE_HANDLER,
            command,
            lambda: self._update_store_profile(command),
        )

    def grant_store_membership(self, command: GrantStoreMembershipCommand) -> StoreCatalogCommandResult:
        return self._idempotent(
            self.GRANT_MEMBERSHIP_HANDLER,
            command,
            lambda: self._grant_store_membership(command),
        )

    def register_store_product(self, command: RegisterStoreProductCommand) -> StoreCatalogCommandResult:
        return self._idempotent(
            self.REGISTER_PRODUCT_HANDLER,
            command,
            lambda: self._register_store_product(command),
        )

    def _create_or_reuse_store_user(self, command: CreateOrReuseStoreUserCommand) -> Mapping[str, Any]:
        user = self._repository.get_user_by_wallet(command.wallet_address)
        user_created = user is None
        if user is None:
            user = User.register_by_wallet(self._new_user_id(), command.wallet_address, role=UserRole.CUSTOMER)
            self._repository.save_user(user)
        return {
            "operation": self.CREATE_USER_HANDLER,
            "status": "created" if user_created else "reused",
            "userId": str(user.user_id),
            "walletAddress": str(user.primary_wallet),
            "platformRole": user.role.value,
            "userCreated": user_created,
            "userReused": not user_created,
            "globalStoreOwnerRoleGranted": False,
        }

    def _create_store(self, command: CreateStoreCommand) -> Mapping[str, Any]:
        owner = self._repository.get_user_by_id(command.owner_user_id)
        if owner is None:
            return _rejected("OWNER_USER_NOT_FOUND", "owner user must exist before store provisioning")
        existing = self._repository.get_store(command.store_id)
        store_created = existing is None
        if existing is not None and existing.owner_user_id != command.owner_user_id:
            return _rejected("STORE_OWNER_CONFLICT", "store id is already owned by another user")

        merchant_group_payload = self._ensure_merchant_group_owner(command)
        group_id = _group_id(merchant_group_payload["groupId"]) if merchant_group_payload is not None else None
        store = StoreProfile(
            store_id=command.store_id,
            public_store_id=existing.public_store_id if existing is not None else command.public_store_id,
            owner_user_id=command.owner_user_id,
            group_id=existing.group_id if existing is not None and existing.group_id is not None else group_id,
            active=command.active,
            display_name=command.display_name if existing is None else existing.display_name,
            description=command.description if existing is None else existing.description,
            support_email=command.support_email if existing is None else existing.support_email,
            support_email_public=command.support_email_public if existing is None else existing.support_email_public,
            business_registration_label=(
                command.business_registration_label if existing is None else existing.business_registration_label
            ),
            created_at=existing.created_at if existing is not None else command.requested_at,
            updated_at=command.requested_at,
            payment_settings=StorePaymentSettings(
                store_id=command.store_id,
                store_wallet=command.store_wallet,
                supported_chain_ids=command.supported_chain_ids,
                active=command.active,
            ),
        )
        previous_membership = self._repository.get_membership(command.store_id, command.owner_user_id)
        membership_created = previous_membership is None
        membership = StoreMembership.owner(command.store_id, command.owner_user_id, active=True)
        self._repository.save_store(store)
        self._repository.save_membership(membership)
        self._repository.save_order_store_projection(store)
        self._repository.save_store_approval_store_projection(store)
        self._repository.record_audit(
            CatalogAuditRecord(
                actor_user_id=command.actor_user_id,
                action=self.CREATE_STORE_HANDLER,
                store_id=command.store_id,
                product_id=None,
                target_user_id=command.owner_user_id,
                request_id=command.request_id,
                idempotency_key=str(command.command_id),
                before={
                    "storeExisted": existing is not None,
                    "membership": _membership_payload(previous_membership),
                },
                after={
                    "store": _store_payload(store),
                    "membership": _membership_payload(membership),
                },
                recorded_at=command.requested_at,
                group_id=merchant_group_payload["groupId"] if merchant_group_payload is not None else None,
                permission="admin:provision",
                resource_type="store",
                resource_id=str(command.store_id),
            )
        )
        return {
            "operation": self.CREATE_STORE_HANDLER,
            "status": "created" if store_created else "alreadyProvisioned",
            "store": _store_payload(store),
            "storeCreated": store_created,
            "ownershipCreated": membership_created,
            "alreadyProvisioned": not store_created and not membership_created,
            "projections": {
                "canonical": "store_catalog_stores",
                "order": "order_stores",
                "storeApproval": "store_approval_stores",
            },
            "merchantGroup": merchant_group_payload,
        }

    def _update_store_profile(self, command: UpdateStoreProfileCommand) -> Mapping[str, Any]:
        store = self._repository.get_store_by_public_id(command.public_store_id)
        if store is None:
            return _rejected("STORE_NOT_FOUND", "store profile was not found")
        store_role = self._repository.get_store_role(store.store_id, command.actor_user_id)
        if store_role is None and not command.platform_override:
            return _rejected("STORE_PROFILE_FORBIDDEN", "store:write requires scoped merchant membership")
        updated = store.update_business_profile(
            display_name=command.display_name,
            description=command.description,
            support_email=command.support_email,
            support_email_public=command.support_email_public,
            business_registration_label=command.business_registration_label,
            updated_at=command.requested_at,
        )
        self._repository.save_store(updated)
        self._repository.record_audit(
            CatalogAuditRecord(
                actor_user_id=command.actor_user_id,
                action=self.UPDATE_STORE_PROFILE_HANDLER,
                store_id=store.store_id,
                product_id=None,
                target_user_id=store.owner_user_id,
                request_id=command.request_id,
                idempotency_key=str(command.command_id),
                before={"store": _owner_store_payload(store), "storeRole": store_role.value if store_role else None},
                after={"store": _owner_store_payload(updated)},
                recorded_at=command.requested_at,
                group_id=str(updated.group_id) if updated.group_id is not None else None,
                permission="store:write:any" if command.platform_override else "store:write",
                resource_type="store",
                resource_id=str(updated.public_store_id),
            )
        )
        return {
            "operation": self.UPDATE_STORE_PROFILE_HANDLER,
            "status": "updated",
            "store": _owner_store_payload(updated),
        }

    def _grant_store_membership(self, command: GrantStoreMembershipCommand) -> Mapping[str, Any]:
        store = self._repository.get_store(command.store_id)
        if store is None:
            return _rejected("STORE_NOT_FOUND", "store must exist before granting membership")
        if self._repository.get_user_by_id(command.user_id) is None:
            return _rejected("MEMBER_USER_NOT_FOUND", "member user must exist before granting membership")
        previous = self._repository.get_membership(command.store_id, command.user_id)
        membership = StoreMembership(
            store_id=command.store_id,
            user_id=command.user_id,
            role=command.role,
            active=command.active,
        )
        self._repository.save_membership(membership)
        merchant_group_payload = self._grant_merchant_group_membership(command)
        self._repository.record_audit(
            CatalogAuditRecord(
                actor_user_id=command.actor_user_id,
                action=self.GRANT_MEMBERSHIP_HANDLER,
                store_id=command.store_id,
                product_id=None,
                target_user_id=command.user_id,
                request_id=command.request_id,
                idempotency_key=str(command.command_id),
                before={"membership": _membership_payload(previous)},
                after={"membership": _membership_payload(membership), "merchantGroup": merchant_group_payload},
                recorded_at=command.requested_at,
                group_id=merchant_group_payload["groupId"] if merchant_group_payload is not None else None,
                permission="rbac:manage",
                resource_type="store",
                resource_id=str(command.store_id),
            )
        )
        return {
            "operation": self.GRANT_MEMBERSHIP_HANDLER,
            "status": "created" if previous is None else "updated",
            "membership": _membership_payload(membership),
            "merchantGroup": merchant_group_payload,
            "ownershipCreated": previous is None,
            "alreadyProvisioned": previous == membership,
        }

    def _register_store_product(self, command: RegisterStoreProductCommand) -> Mapping[str, Any]:
        store = self._repository.get_store(command.store_id)
        if store is None:
            return _rejected("STORE_NOT_FOUND", "product registration requires an existing store")
        if not store.active:
            return _rejected("STORE_INACTIVE", "product registration requires an active store")
        if not store.supports_chain(command.price.chain_id):
            return _rejected("UNSUPPORTED_PRICE_CHAIN", "product price chain id is not supported by the store")

        store_role = self._repository.get_store_role(command.store_id, command.actor_user_id)
        if command.actor_platform_role is not UserRole.ADMIN and store_role is None:
            return _rejected("STORE_OWNER_STORE_FORBIDDEN", "store ownership or membership is required")

        previous = self._repository.get_product(command.store_id, command.product_id)
        product = StoreProduct(
            store_id=command.store_id,
            product_id=command.product_id,
            name=command.name,
            price=command.price,
            active=command.active,
        )
        self._repository.save_product(product)
        self._repository.save_order_product_projection(product)
        self._repository.save_store_approval_product_projection(product)
        self._repository.save_inventory_projection(product, command.initial_total_stock)
        self._repository.record_audit(
            CatalogAuditRecord(
                actor_user_id=command.actor_user_id,
                action=self.REGISTER_PRODUCT_HANDLER,
                store_id=command.store_id,
                product_id=command.product_id,
                target_user_id=store.owner_user_id,
                request_id=command.request_id,
                idempotency_key=str(command.command_id),
                before={"product": _product_payload(previous), "storeRole": store_role.value if store_role else None},
                after={"product": _product_payload(product), "initialTotalStock": command.initial_total_stock},
                recorded_at=command.requested_at,
                permission="product:write:any" if command.actor_platform_role is UserRole.ADMIN else "product:write",
                resource_type="store",
                resource_id=str(command.store_id),
            )
        )
        return {
            "operation": self.REGISTER_PRODUCT_HANDLER,
            "status": "created" if previous is None else "updated",
            "storeId": str(product.store_id),
            "productId": str(product.product_id),
            "name": product.name,
            "price": _crypto_payload(product.price),
            "initialTotalStock": command.initial_total_stock,
            "active": product.active,
            "available": product.active,
            "projections": {
                "canonical": "store_catalog_products",
                "order": "order_store_products",
                "storeApproval": "store_approval_products",
                "inventory": "product_inventory",
            },
        }

    def _idempotent(self, handler: str, command: Any, callback: Callable[[], Mapping[str, Any]]) -> StoreCatalogCommandResult:
        key = str(command.command_id)
        existing = self._repository.get_idempotency_record(handler, key)
        if existing is not None:
            if existing.payload_hash != command.payload_hash:
                return StoreCatalogCommandResult(
                    status=StoreCatalogCommandStatus.CONFLICT,
                    payload={
                        "error": {
                            "code": "IDEMPOTENCY_KEY_CONFLICT",
                            "message": "same idempotency key was used with a different payload",
                        }
                    },
                    rejection_reason="IDEMPOTENCY_KEY_CONFLICT",
                )
            payload = dict(existing.response_payload)
            payload["idempotentReplay"] = True
            return StoreCatalogCommandResult(status=StoreCatalogCommandStatus.DUPLICATE, payload=payload)

        payload = callback()
        if "error" in payload:
            return StoreCatalogCommandResult(
                status=StoreCatalogCommandStatus.REJECTED,
                payload=payload,
                rejection_reason=str(payload["error"]["code"]),
            )
        self._repository.save_idempotency_record(
            CatalogIdempotencyRecord(
                handler=handler,
                idempotency_key=key,
                payload_hash=command.payload_hash,
                response_payload=dict(payload),
                recorded_at=command.requested_at,
            )
        )
        return StoreCatalogCommandResult(status=StoreCatalogCommandStatus.COMPLETED, payload=payload)

    def _new_user_id(self) -> UserId:
        generator = self._user_id_generator
        if generator is None:
            return UserId.new()
        new_id = getattr(generator, "new_id", None)
        if callable(new_id):
            return UserId(str(new_id()))
        if callable(generator):
            return UserId(str(generator()))
        raise ValueError("user_id_generator must expose new_id() or be callable")

    def _ensure_merchant_group_owner(self, command: CreateStoreCommand) -> Mapping[str, Any] | None:
        ensure_group = getattr(self._repository, "ensure_merchant_group_for_store", None)
        grant_owner = getattr(self._repository, "grant_group_membership", None)
        if not callable(ensure_group) or not callable(grant_owner):
            return None
        group_id = ensure_group(command.store_id)
        grant_owner(group_id, command.owner_user_id, "MERCHANT_OWNER", active=True)
        return {
            "groupId": str(group_id),
            "ownerUserId": str(command.owner_user_id),
            "roleId": "MERCHANT_OWNER",
        }

    def _grant_merchant_group_membership(self, command: GrantStoreMembershipCommand) -> Mapping[str, Any] | None:
        group_id = self._merchant_group_id_for_store(command.store_id)
        grant_membership = getattr(self._repository, "grant_group_membership", None)
        if group_id is None or not callable(grant_membership):
            return None
        role_id = _merchant_role_for_store_role(command.role)
        grant_membership(group_id, command.user_id, role_id, active=command.active)
        return {
            "groupId": str(group_id),
            "userId": str(command.user_id),
            "roleId": role_id,
            "active": command.active,
        }

    def _merchant_group_id_for_store(self, store_id: Any) -> GroupId | None:
        merchant_group = getattr(self._repository, "merchant_group_for_store", None)
        if callable(merchant_group):
            group = merchant_group(store_id)
            if group is not None:
                return group.group_id
        ensure_group = getattr(self._repository, "ensure_merchant_group_for_store", None)
        if callable(ensure_group):
            return ensure_group(store_id)
        return None


def _rejected(code: str, message: str) -> Mapping[str, Any]:
    return {"error": {"code": code, "message": message}}


def _store_payload(store: StoreProfile | None) -> dict[str, Any] | None:
    if store is None:
        return None
    return {
        "storeId": str(store.store_id),
        "publicStoreId": str(store.public_store_id),
        "ownerUserId": str(store.owner_user_id),
        "groupId": str(store.group_id) if store.group_id is not None else None,
        "displayName": store.display_name,
        "description": store.description,
        "status": store.status.value,
        "supportEmail": store.support_email,
        "supportEmailPublic": store.support_email_public,
        "businessRegistrationLabel": store.business_registration_label,
        "active": store.active,
        "storeWallet": str(store.store_wallet) if store.store_wallet is not None else None,
        "supportedChainIds": list(store.supported_chain_ids),
    }


def _public_store_payload(store: StoreProfile | None) -> dict[str, Any] | None:
    if store is None:
        return None
    payload: dict[str, Any] = {
        "publicStoreId": str(store.public_store_id),
        "displayName": store.display_name,
        "displayNameHtml": escape(store.display_name),
        "description": store.description,
        "descriptionHtml": escape(store.description) if store.description is not None else None,
        "status": store.status.value,
    }
    if store.support_email_public and store.support_email is not None:
        payload["supportEmail"] = store.support_email
    return payload


def _owner_store_payload(store: StoreProfile) -> dict[str, Any]:
    return {
        "publicStoreId": str(store.public_store_id),
        "groupId": str(store.group_id) if store.group_id is not None else None,
        "displayName": store.display_name,
        "displayNameHtml": escape(store.display_name),
        "description": store.description,
        "descriptionHtml": escape(store.description) if store.description is not None else None,
        "status": store.status.value,
        "supportEmail": store.support_email,
        "supportEmailPublic": store.support_email_public,
        "businessRegistrationLabel": store.business_registration_label,
    }


def _membership_payload(membership: StoreMembership | None) -> dict[str, Any] | None:
    if membership is None:
        return None
    return {
        "storeId": str(membership.store_id),
        "userId": str(membership.user_id),
        "role": membership.role.value,
        "active": membership.active,
    }


def _merchant_role_for_store_role(role: StoreMembershipRole) -> str:
    if role is StoreMembershipRole.OWNER:
        return "MERCHANT_OWNER"
    return "MERCHANT_MANAGER"


def _product_payload(product: StoreProduct | None) -> dict[str, Any] | None:
    if product is None:
        return None
    return {
        "storeId": str(product.store_id),
        "productId": str(product.product_id),
        "name": product.name,
        "price": _crypto_payload(product.price),
        "active": product.active,
    }


def _crypto_payload(price: Any) -> dict[str, Any]:
    return {
        "amount": format(price.amount, "f"),
        "symbol": price.symbol,
        "chainId": price.chain_id,
        "tokenAddress": str(price.token_address) if price.token_address is not None else None,
        "decimals": price.decimals,
    }


def _group_id(value: Any) -> GroupId:
    if isinstance(value, GroupId):
        return value
    return GroupId(str(value))
