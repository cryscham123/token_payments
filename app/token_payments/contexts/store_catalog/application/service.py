"""Application service for admin store provisioning and product registration."""

from __future__ import annotations

from html import escape
from collections.abc import Callable
from typing import Any, Mapping
from uuid import NAMESPACE_URL, uuid5

from token_payments.contexts.store_catalog.domain import (
    ProductOption,
    ProductOptionValue,
    ProductStatus,
    ProductVariant,
    ProductVisibility,
    PublicProductId,
    PublicStoreId,
    StoreMembership,
    StoreMembershipRole,
    StorePaymentSettings,
    StoreProduct,
    StoreProfile,
)
from token_payments.shared.domain import EventMetadata, MessageId, Money, OutboxMessage, UserId

from .commands import (
    CreateOrReuseStoreUserCommand,
    CreateStoreCommand,
    GetStoreProfileQuery,
    GrantStoreMembershipCommand,
    ListMerchantStoresQuery,
    RegisterStoreProductCommand,
    UpdateStoreProfileCommand,
    UpdateStoreProductCommand,
)
from .ports import (
    CatalogAuditRecord,
    CatalogIdempotencyRecord,
    CatalogUserRecord,
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
    UPDATE_PRODUCT_HANDLER = "updateStoreProduct"

    def __init__(
        self,
        *,
        repository: CatalogWriteRepository,
        user_id_generator: Any | None = None,
        payment_assets: Any | None = None,
        exchange_rate: Any | None = None,
    ) -> None:
        self._repository = repository
        self._user_id_generator = user_id_generator
        self._payment_assets = payment_assets
        self._exchange_rate = exchange_rate

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
        return (
            _public_store_payload(
                store,
                include_payment_capability=True,
                asset_registry=self._payment_assets,
            )
            if store is not None
            else None
        )

    def list_merchant_stores(self, query: ListMerchantStoresQuery) -> tuple[Mapping[str, Any], ...]:
        stores = self._repository.list_stores_for_member(query.actor_user_id)
        payloads = []
        for store in stores:
            payload = _public_store_payload(store)
            if payload is not None:
                role = self._repository.get_store_role(store.store_id, query.actor_user_id)
                payload["role"] = role.value if role is not None else None
                payloads.append(payload)
        return tuple(payloads)

    def list_public_stores(self, *, limit: int, offset: int) -> Mapping[str, Any]:
        stores = self._stores_for_public_listing(limit=limit, offset=offset)
        return {
            "stores": [
                _public_store_payload(
                    store,
                    include_payment_capability=True,
                    asset_registry=self._payment_assets,
                )
                for store in stores
            ],
            "pagination": _pagination(limit=limit, offset=offset, count=len(stores)),
        }

    def list_all_public_products(self, *, filters: Mapping[str, Any]) -> Mapping[str, Any]:
        list_all = getattr(self._repository, "list_all_public_products", None)
        if callable(list_all):
            products = tuple(
                list_all(
                    category=filters.get("category"),
                    tag=filters.get("tag"),
                    query=filters.get("query"),
                    sort_by=str(filters.get("sort_by") or "title"),
                    sort_direction=str(filters.get("sort_direction") or "asc"),
                    limit=int(filters["limit"]),
                    offset=int(filters["offset"]),
                )
            )
        else:
            # In-memory fallback: gather all active/public products across all stores
            all_products = tuple(
                product
                for product in getattr(self._repository, "products", {}).values()
                if isinstance(product, StoreProduct)
                and product.status is ProductStatus.ACTIVE
                and product.visibility is ProductVisibility.PUBLIC
                and product.active
            )
            products = self._apply_product_filters(all_products, filters)
        store_ids = {p.store_id for p in products}
        stores_by_id: dict[Any, StoreProfile] = {}
        for store_id in store_ids:
            store = self._repository.get_store(store_id)
            if store is not None:
                stores_by_id[store_id] = store
        result = []
        for product in products:
            store = stores_by_id.get(product.store_id)
            if store is None:
                continue
            result.append(
                _public_product_payload(
                    store,
                    product,
                    self._availability(product),
                    options=self._options_for_product(product),
                    option_values=self._option_values_for_product(product),
                    variants=self._variants_for_product(product),
                    variant_availability=self._variant_availability_for_product(product),
                    asset_registry=self._payment_assets,
                    exchange_rate=self._exchange_rate,
                )
            )
        return {
            "products": result,
            "pagination": _pagination(
                limit=int(filters["limit"]),
                offset=int(filters["offset"]),
                count=len(result),
            ),
        }

    def _apply_product_filters(
        self, products: tuple[StoreProduct, ...], filters: Mapping[str, Any]
    ) -> tuple[StoreProduct, ...]:
        category = filters.get("category")
        tag = filters.get("tag")
        query = filters.get("query")
        limit = int(filters["limit"])
        offset = int(filters["offset"])
        sort_by = str(filters.get("sort_by") or "title")
        sort_direction = str(filters.get("sort_direction") or "asc")
        if category is not None:
            products = tuple(p for p in products if p.category == category)
        if tag is not None:
            products = tuple(p for p in products if tag in p.tags)
        if query is not None:
            query_lower = query.lower()
            products = tuple(
                p
                for p in products
                if query_lower in p.title.lower()
                or (p.description is not None and query_lower in p.description.lower())
            )
        reverse = sort_direction == "desc"
        key_map = {
            "title": lambda p: p.title.lower(),
            "createdAt": lambda p: p.created_at,
            "updatedAt": lambda p: p.updated_at,
            "price": lambda p: p.price.amount,
        }
        if sort_by in key_map:
            products = tuple(sorted(products, key=key_map[sort_by], reverse=reverse))
        return products[offset : offset + limit]

    def list_public_products(
        self,
        *,
        public_store_id: PublicStoreId,
        filters: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        store = self._repository.get_store_by_public_id(public_store_id)
        if store is None:
            return None
        products = self._products_for_store(
            store.store_id,
            status=ProductStatus.ACTIVE,
            visibility=ProductVisibility.PUBLIC,
            category=filters.get("category"),
            tag=filters.get("tag"),
            query=filters.get("query"),
            sort_by=str(filters.get("sort_by") or "title"),
            sort_direction=str(filters.get("sort_direction") or "asc"),
            limit=int(filters["limit"]),
            offset=int(filters["offset"]),
        )
        return {
            "store": _public_store_payload(
                store,
                include_payment_capability=True,
                asset_registry=self._payment_assets,
            ),
            "products": [
                _public_product_payload(
                    store,
                    product,
                    self._availability(product),
                    options=self._options_for_product(product),
                    option_values=self._option_values_for_product(product),
                    variants=self._variants_for_product(product),
                    variant_availability=self._variant_availability_for_product(product),
                    asset_registry=self._payment_assets,
                    exchange_rate=self._exchange_rate,
                )
                for product in products
            ],
            "pagination": _pagination(limit=int(filters["limit"]), offset=int(filters["offset"]), count=len(products)),
        }

    def get_public_product(
        self,
        *,
        public_store_id: PublicStoreId,
        public_product_id: PublicProductId,
    ) -> Mapping[str, Any] | None:
        store = self._repository.get_store_by_public_id(public_store_id)
        if store is None:
            return None
        product = self._repository.get_product_by_public_id(store.store_id, public_product_id)
        if product is None or product.status is not ProductStatus.ACTIVE or product.visibility is not ProductVisibility.PUBLIC:
            return None
        return {
            "store": _public_store_payload(
                store,
                include_payment_capability=True,
                asset_registry=self._payment_assets,
            ),
            "product": _public_product_payload(
                store,
                product,
                self._availability(product),
                include_detail=True,
                options=self._options_for_product(product),
                option_values=self._option_values_for_product(product),
                variants=self._variants_for_product(product),
                variant_availability=self._variant_availability_for_product(product),
                asset_registry=self._payment_assets,
                exchange_rate=self._exchange_rate,
            ),
        }

    def list_merchant_products(
        self,
        *,
        actor_user_id: UserId,
        public_store_id: PublicStoreId,
        filters: Mapping[str, Any],
        platform_override: bool = False,
    ) -> Mapping[str, Any]:
        store = self._repository.get_store_by_public_id(public_store_id)
        if store is None:
            return _rejected("STORE_NOT_FOUND", "store was not found")
        store_role = self._repository.get_store_role(store.store_id, actor_user_id)
        if store_role is None and not platform_override:
            return _rejected("STORE_OWNER_STORE_FORBIDDEN", "product:read requires scoped merchant membership")
        products = self._products_for_store(
            store.store_id,
            status=filters.get("status"),
            visibility=filters.get("visibility"),
            category=filters.get("category"),
            tag=filters.get("tag"),
            query=filters.get("query"),
            sort_by=str(filters.get("sort_by") or "title"),
            sort_direction=str(filters.get("sort_direction") or "asc"),
            limit=int(filters["limit"]),
            offset=int(filters["offset"]),
        )
        return {
            "store": _owner_store_payload(store),
            "products": [_merchant_product_payload(store, product, self._availability(product)) for product in products],
            "pagination": _pagination(limit=int(filters["limit"]), offset=int(filters["offset"]), count=len(products)),
        }

    def get_merchant_product(
        self,
        *,
        actor_user_id: UserId,
        public_store_id: PublicStoreId,
        public_product_id: PublicProductId,
        platform_override: bool = False,
    ) -> Mapping[str, Any]:
        store = self._repository.get_store_by_public_id(public_store_id)
        if store is None:
            return _rejected("STORE_NOT_FOUND", "store was not found")
        store_role = self._repository.get_store_role(store.store_id, actor_user_id)
        if store_role is None and not platform_override:
            return _rejected("STORE_OWNER_STORE_FORBIDDEN", "product:read requires scoped merchant membership")
        product = self._repository.get_product_by_public_id(store.store_id, public_product_id)
        if product is None:
            return _rejected("PRODUCT_NOT_FOUND", "product was not found")
        return {
            "store": _owner_store_payload(store),
            "product": _merchant_product_payload(store, product, self._availability(product), include_internal=True),
        }

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

    def update_store_product(self, command: UpdateStoreProductCommand) -> StoreCatalogCommandResult:
        return self._idempotent(
            self.UPDATE_PRODUCT_HANDLER,
            command,
            lambda: self._update_store_product(command),
        )

    def _create_or_reuse_store_user(self, command: CreateOrReuseStoreUserCommand) -> Mapping[str, Any]:
        user = self._repository.get_user_by_wallet(command.wallet_address)
        user_created = user is None
        if user is None:
            user = CatalogUserRecord(
                user_id=self._new_user_id(),
                primary_wallet=command.wallet_address,
                role="CUSTOMER",
                active=True,
            )
            self._repository.save_user(user)
        return {
            "operation": self.CREATE_USER_HANDLER,
            "status": "created" if user_created else "reused",
            "userId": str(user.user_id),
            "walletAddress": str(user.primary_wallet),
            "platformRole": _role_value(user.role),
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

        def build_store(group_id: Any | None) -> StoreProfile:
            return StoreProfile(
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

        store = build_store(existing.group_id if existing is not None else None)
        display_name_conflict = self._store_display_name_conflict(store.display_name, current_store_id=store.store_id)
        if display_name_conflict is not None:
            return display_name_conflict
        previous_membership = self._repository.get_membership(command.store_id, command.owner_user_id)
        membership_created = previous_membership is None
        membership = StoreMembership.owner(command.store_id, command.owner_user_id, active=True)
        merchant_group_payload = self._ensure_merchant_group_owner(command)
        group_id = _group_id(merchant_group_payload["groupId"]) if merchant_group_payload is not None else None
        store = build_store(group_id)
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
            supported_chain_ids=command.supported_chain_ids,
            supported_payment_asset_ids=command.supported_payment_asset_ids,
        )
        display_name_conflict = self._store_display_name_conflict(updated.display_name, current_store_id=store.store_id)
        if display_name_conflict is not None:
            return display_name_conflict
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
        store = self._repository.get_store_by_public_id(command.public_store_id)
        if store is None:
            return _rejected("STORE_NOT_FOUND", "product registration requires an existing store")
        if not store.active:
            return _rejected("STORE_INACTIVE", "product registration requires an active store")

        # Verify that the store supports at least one chain that the system supports
        system_supported_chains = {1337, 11155111}
        store_chains = set(store.supported_chain_ids)
        if not store_chains.intersection(system_supported_chains):
            return _rejected("UNSUPPORTED_PRICE_CHAIN", "store does not support any system-supported chains")

        store_role = self._repository.get_store_role(store.store_id, command.actor_user_id)
        if not command.platform_override and store_role is None:
            return _rejected("STORE_OWNER_STORE_FORBIDDEN", "store ownership or membership is required")

        product = StoreProduct(
            store_id=store.store_id,
            product_id=command.product_id,
            public_product_id=command.public_product_id,
            public_store_id=store.public_store_id,
            title=command.title,
            description=command.description,
            category=command.category,
            tags=command.tags,
            media=command.media,
            attributes=command.attributes or {},
            status=command.status,
            visibility=command.visibility,
            price=command.price,
            active=command.active,
            created_at=command.requested_at,
            updated_at=command.requested_at,
        )
        self._repository.save_product(product)
        self._repository.save_order_product_projection(product)
        self._repository.save_store_approval_product_projection(product)
        self._repository.save_inventory_projection(product, command.initial_total_stock)
        self._repository.record_audit(
            CatalogAuditRecord(
                actor_user_id=command.actor_user_id,
                action=self.REGISTER_PRODUCT_HANDLER,
                store_id=store.store_id,
                product_id=command.product_id,
                target_user_id=store.owner_user_id,
                request_id=command.request_id,
                idempotency_key=str(command.command_id),
                before={"product": None, "storeRole": store_role.value if store_role else None},
                after={"product": _product_payload(product), "initialTotalStock": command.initial_total_stock},
                recorded_at=command.requested_at,
                permission="product:write:any" if command.platform_override else "product:write",
                resource_type="store",
                resource_id=str(store.public_store_id),
            )
        )
        product_payload = _owner_product_payload(product)
        return {
            "operation": self.REGISTER_PRODUCT_HANDLER,
            "status": "created",
            "product": product_payload,
            "storeId": str(product.store_id),
            "productId": str(product.product_id),
            "name": product.name,
            "publicStoreId": str(product.public_store_id),
            "publicProductId": str(product.public_product_id),
            "title": product.title,
            "price": _money_payload(product.price),
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

    def _update_store_product(self, command: UpdateStoreProductCommand) -> Mapping[str, Any]:
        store = self._repository.get_store_by_public_id(command.public_store_id)
        if store is None:
            return _rejected("STORE_NOT_FOUND", "product update requires an existing store")
        store_role = self._repository.get_store_role(store.store_id, command.actor_user_id)
        if store_role is None and not command.platform_override:
            return _rejected("STORE_OWNER_STORE_FORBIDDEN", "product:write requires scoped merchant membership")
        product = self._repository.get_product_by_public_id(store.store_id, command.public_product_id)
        if product is None:
            return _rejected("PRODUCT_NOT_FOUND", "product catalog detail was not found")
        updated = product.update_detail(
            title=command.title,
            description=command.description,
            category=command.category,
            tags=command.tags,
            media=command.media,
            attributes=command.attributes,
            status=command.status,
            visibility=command.visibility,
            price=command.price,
            updated_at=command.requested_at,
        )
        self._repository.save_product(updated)
        self._repository.save_order_product_projection(updated)
        self._repository.save_store_approval_product_projection(updated)
        self._repository.record_audit(
            CatalogAuditRecord(
                actor_user_id=command.actor_user_id,
                action=self.UPDATE_PRODUCT_HANDLER,
                store_id=store.store_id,
                product_id=updated.product_id,
                target_user_id=store.owner_user_id,
                request_id=command.request_id,
                idempotency_key=str(command.command_id),
                before={"product": _product_payload(product), "storeRole": store_role.value if store_role else None},
                after={"product": _product_payload(updated)},
                recorded_at=command.requested_at,
                group_id=str(store.group_id) if store.group_id is not None else None,
                permission="product:write:any" if command.platform_override else "product:write",
                resource_type="product",
                resource_id=str(updated.public_product_id),
            )
        )
        return {
            "operation": self.UPDATE_PRODUCT_HANDLER,
            "status": "updated",
            "product": _owner_product_payload(updated),
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

    def _store_display_name_conflict(
        self,
        display_name: str,
        *,
        current_store_id: StoreId,
    ) -> Mapping[str, Any] | None:
        existing = self._repository.get_store_by_display_name(display_name)
        if existing is not None and existing.store_id != current_store_id:
            return _rejected("STORE_DISPLAY_NAME_CONFLICT", "store displayName is already in use")
        return None

    def _ensure_merchant_group_owner(self, command: CreateStoreCommand) -> Mapping[str, Any] | None:
        ensure_group = getattr(self._repository, "ensure_merchant_group_for_store", None)
        if not callable(ensure_group):
            return None
        group_id = ensure_group(command.store_id)
        projected = self._record_membership_projection_event(
            command=command,
            group_id=group_id,
            user_id=command.owner_user_id,
            role_id="MERCHANT_OWNER",
            active=True,
        )
        grant_owner = getattr(self._repository, "grant_group_membership", None)
        if callable(grant_owner):
            grant_owner(group_id, command.owner_user_id, "MERCHANT_OWNER", active=True)
        elif not projected:
            return None
        payload = {
            "groupId": str(group_id),
            "ownerUserId": str(command.owner_user_id),
            "roleId": "MERCHANT_OWNER",
        }
        if projected:
            payload["projection"] = "outbox"
        return payload

    def _grant_merchant_group_membership(self, command: GrantStoreMembershipCommand) -> Mapping[str, Any] | None:
        group_id = self._merchant_group_id_for_store(command.store_id)
        grant_membership = getattr(self._repository, "grant_group_membership", None)
        if group_id is None:
            return None
        role_id = _merchant_role_for_store_role(command.role)
        projected = self._record_membership_projection_event(
            command=command,
            group_id=group_id,
            user_id=command.user_id,
            role_id=role_id,
            active=command.active,
        )
        if callable(grant_membership):
            grant_membership(group_id, command.user_id, role_id, active=command.active)
        elif not projected:
            return None
        payload = {
            "groupId": str(group_id),
            "userId": str(command.user_id),
            "roleId": role_id,
            "active": command.active,
        }
        if projected:
            payload["projection"] = "outbox"
        return payload

    def _record_membership_projection_event(
        self,
        *,
        command: CreateStoreCommand | GrantStoreMembershipCommand,
        group_id: Any,
        user_id: UserId,
        role_id: str,
        active: bool,
    ) -> bool:
        record_event = getattr(self._repository, "record_membership_projection_event", None)
        if not callable(record_event):
            return False
        event_identity = _membership_event_identity(command.command_id, user_id)
        event_id = str(uuid5(NAMESPACE_URL, event_identity))
        message = OutboxMessage.record_event(
            metadata=EventMetadata(
                message_id=MessageId(event_id),
                name="StoreCatalogStoreMembershipChangedEvent",
                aggregate_id=f"store:{command.store_id}",
                occurred_at=command.requested_at,
                correlation_id=str(command.command_id),
                causation_id=command.request_id,
            ),
            topic="auth.rbac.projections",
            key=str(command.store_id),
            payload={
                "eventId": event_id,
                "sourceOfTruth": "store_catalog_store_memberships",
                "projection": "auth_group_memberships",
                "storeId": str(command.store_id),
                "groupId": str(group_id),
                "userId": str(user_id),
                "roleId": role_id,
                "active": active,
                "version": 1,
            },
        )
        record_event(message)
        return True

    def _merchant_group_id_for_store(self, store_id: Any) -> Any | None:
        merchant_group = getattr(self._repository, "merchant_group_for_store", None)
        if callable(merchant_group):
            group = merchant_group(store_id)
            if group is not None:
                return group.group_id
        ensure_group = getattr(self._repository, "ensure_merchant_group_for_store", None)
        if callable(ensure_group):
            return ensure_group(store_id)
        return None

    def _stores_for_public_listing(self, *, limit: int, offset: int) -> tuple[StoreProfile, ...]:
        list_public_stores = getattr(self._repository, "list_public_stores", None)
        if callable(list_public_stores):
            return tuple(list_public_stores(limit=limit, offset=offset))
        stores = tuple(
            store
            for store in getattr(self._repository, "stores", {}).values()
            if isinstance(store, StoreProfile) and store.active
        )
        return tuple(sorted(stores, key=lambda store: str(store.public_store_id))[offset : offset + limit])

    def _products_for_store(
        self,
        store_id: Any,
        *,
        status: ProductStatus | None,
        visibility: ProductVisibility | None,
        category: str | None,
        tag: str | None,
        query: str | None,
        sort_by: str,
        sort_direction: str,
        limit: int,
        offset: int,
    ) -> tuple[StoreProduct, ...]:
        list_products = getattr(self._repository, "list_products_for_store", None)
        if callable(list_products):
            return tuple(
                list_products(
                    store_id,
                    status=status,
                    visibility=visibility,
                    category=category,
                    tag=tag,
                    query=query,
                    sort_by=sort_by,
                    sort_direction=sort_direction,
                    limit=limit,
                    offset=offset,
                )
            )
        products = tuple(
            product
            for (stored_store_id, _product_id), product in getattr(self._repository, "products", {}).items()
            if stored_store_id == store_id
        )
        if status is not None:
            products = tuple(product for product in products if product.status is status)
        if visibility is not None:
            products = tuple(product for product in products if product.visibility is visibility)
        if category is not None:
            products = tuple(product for product in products if product.category == category)
        if tag is not None:
            products = tuple(product for product in products if tag in product.tags)
        if query is not None:
            query_lower = query.lower()
            products = tuple(
                product
                for product in products
                if query_lower in product.title.lower()
                or (product.description is not None and query_lower in product.description.lower())
            )
        reverse = sort_direction == "desc"
        key_map = {
            "title": lambda product: product.title.lower(),
            "createdAt": lambda product: product.created_at,
            "updatedAt": lambda product: product.updated_at,
            "price": lambda product: product.price.amount,
        }
        products = tuple(sorted(products, key=key_map[sort_by], reverse=reverse))
        return products[offset : offset + limit]

    def _availability(self, product: StoreProduct) -> Mapping[str, Any]:
        get_availability = getattr(self._repository, "get_product_availability", None)
        if callable(get_availability):
            availability = get_availability(product.store_id, product.product_id)
            if availability is not None:
                return dict(availability)
        inventory = getattr(self._repository, "inventory", {})
        available_stock = int(inventory.get((product.store_id, product.product_id), 0))
        return {
            "availableStock": available_stock,
            "saleStatus": "ACTIVE" if product.active and available_stock > 0 else "UNAVAILABLE",
        }

    def _options_for_product(self, product: StoreProduct) -> tuple[ProductOption, ...]:
        list_options = getattr(self._repository, "list_product_options", None)
        if callable(list_options):
            return tuple(list_options(product.store_id, product.product_id))
        return tuple(getattr(self._repository, "product_options", {}).get((product.store_id, product.product_id), ()))

    def _option_values_for_product(self, product: StoreProduct) -> Mapping[str, tuple[ProductOptionValue, ...]]:
        list_values = getattr(self._repository, "list_product_option_values", None)
        if callable(list_values):
            return {
                option.option_id: tuple(list_values(product.store_id, product.product_id, option.option_id))
                for option in self._options_for_product(product)
            }
        values = getattr(self._repository, "product_option_values", {})
        return {
            option.option_id: tuple(values.get(option.option_id, ()))
            for option in self._options_for_product(product)
        }

    def _variants_for_product(self, product: StoreProduct) -> tuple[ProductVariant, ...]:
        list_variants = getattr(self._repository, "list_product_variants", None)
        if callable(list_variants):
            return tuple(list_variants(product.store_id, product.product_id))
        return tuple(getattr(self._repository, "product_variants", {}).get((product.store_id, product.product_id), ()))

    def _variant_availability_for_product(self, product: StoreProduct) -> Mapping[str, Mapping[str, Any]]:
        variants = self._variants_for_product(product)
        if not variants:
            return {}
        get_availability = getattr(self._repository, "get_variant_availability", None)
        availability: dict[str, Mapping[str, Any]] = {}
        for variant in variants:
            public_variant_id = str(variant.public_variant_id)
            if callable(get_availability):
                current = get_availability(product.store_id, product.product_id, variant.public_variant_id)
                if current is not None:
                    availability[public_variant_id] = dict(current)
                    continue
            stock = getattr(self._repository, "variant_inventory", {}).get(public_variant_id)
            available_stock = int(stock or 0)
            availability[public_variant_id] = {
                "availableStock": available_stock,
                "saleStatus": "ACTIVE" if variant.saleable and available_stock > 0 else "UNAVAILABLE",
            }
        return availability


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


def _public_store_payload(
    store: StoreProfile | None,
    *,
    include_payment_capability: bool = False,
    asset_registry: Any | None = None,
) -> dict[str, Any] | None:
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
    if include_payment_capability:
        payload["paymentCapability"] = _payment_capability_payload(store, asset_registry=asset_registry)
    return payload


def _owner_store_payload(store: StoreProfile) -> dict[str, Any]:
    return {
        "storeId": str(store.store_id),
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


def _membership_event_identity(command_id: Any, user_id: UserId) -> str:
    return f"store-membership:{command_id}:{user_id}"


def _product_payload(product: StoreProduct | None) -> dict[str, Any] | None:
    if product is None:
        return None
    return {
        "storeId": str(product.store_id),
        "publicStoreId": str(product.public_store_id),
        "productId": str(product.product_id),
        "publicProductId": str(product.public_product_id),
        "name": product.name,
        "title": product.title,
        "description": product.description,
        "category": product.category,
        "tags": list(product.tags),
        "media": list(product.media),
        "attributes": dict(product.attributes),
        "status": product.status.value,
        "visibility": product.visibility.value,
        "price": _money_payload(product.price),
        "active": product.active,
    }


def _owner_product_payload(product: StoreProduct) -> dict[str, Any]:
    return {
        "publicStoreId": str(product.public_store_id),
        "publicProductId": str(product.public_product_id),
        "title": product.title,
        "titleHtml": escape(product.title),
        "description": product.description,
        "descriptionHtml": escape(product.description) if product.description is not None else None,
        "category": product.category,
        "tags": list(product.tags),
        "media": list(product.media),
        "attributes": dict(product.attributes),
        "status": product.status.value,
        "visibility": product.visibility.value,
        "price": _money_payload(product.price),
        "active": product.active,
    }


def _public_product_payload(
    store: StoreProfile,
    product: StoreProduct,
    availability: Mapping[str, Any],
    *,
    include_detail: bool = False,
    options: tuple[ProductOption, ...] = (),
    option_values: Mapping[str, tuple[ProductOptionValue, ...]] | None = None,
    variants: tuple[ProductVariant, ...] = (),
    variant_availability: Mapping[str, Mapping[str, Any]] | None = None,
    asset_registry: Any | None = None,
    exchange_rate: Any | None = None,
) -> dict[str, Any]:
    option_values = option_values or {}
    variant_availability = variant_availability or {}
    display_price = _display_price_payload(product, variants, variant_availability)
    display_availability = _aggregate_availability(availability, variants, variant_availability)

    # Per-asset display amounts: the product is priced in fiat (USD); convert it into each
    # accepted on-chain asset at the fixed exchange rate so the storefront can show, e.g.,
    # "$30 ≈ 0.01 ETH / 30 USDC".
    asset_prices = {}
    if asset_registry is not None and exchange_rate is not None:
        chain_ids = set(store.supported_chain_ids)
        configured_asset_ids = set(store.supported_payment_asset_ids)
        for asset in asset_registry.assets:
            if (
                asset.enabled
                and asset.chain_id in chain_ids
                and (not configured_asset_ids or asset.asset_id in configured_asset_ids)
            ):
                converted = exchange_rate.to_crypto(
                    product.price,
                    symbol=asset.symbol,
                    chain_id=asset.chain_id,
                    token_address=asset.contract_address,
                    decimals=asset.decimals,
                )
                asset_prices[asset.asset_id] = {
                    "assetId": asset.asset_id,
                    "chainId": asset.chain_id,
                    "symbol": asset.symbol,
                    "amount": format(converted.amount, "f"),
                    "decimals": asset.decimals,
                    "tokenAddress": str(asset.contract_address) if asset.contract_address is not None else None,
                }

    payload: dict[str, Any] = {
        "publicStoreId": str(product.public_store_id),
        "storeDisplayName": store.display_name,
        "publicProductId": str(product.public_product_id),
        "title": product.title,
        "titleHtml": escape(product.title),
        "description": product.description,
        "descriptionHtml": escape(product.description) if product.description is not None else None,
        "category": product.category,
        "tags": list(product.tags),
        "media": list(product.media),
        "status": product.status.value,
        "visibility": product.visibility.value,
        "basePrice": _money_payload(product.price),
        "displayPrice": display_price,
        "availability": display_availability,
        "paymentCapability": _payment_capability_payload(store, asset_registry=asset_registry),
        "assetPrices": asset_prices,
        "options": [_public_option_payload(option, option_values.get(option.option_id, ())) for option in options if option.active],
        "variants": [
            _public_variant_payload(product, variant, variant_availability.get(str(variant.public_variant_id)))
            for variant in variants
        ],
    }
    if include_detail:
        payload["attributes"] = dict(product.attributes)
    return payload


def _merchant_product_payload(
    store: StoreProfile,
    product: StoreProduct,
    availability: Mapping[str, Any],
    *,
    include_internal: bool = False,
    asset_registry: Any | None = None,
    exchange_rate: Any | None = None,
) -> dict[str, Any]:
    payload = _public_product_payload(
        store,
        product,
        availability,
        include_detail=True,
        asset_registry=asset_registry,
        exchange_rate=exchange_rate,
    )
    if include_internal:
        payload["productId"] = str(product.product_id)
        payload["storeId"] = str(product.store_id)
    return payload


def _public_option_payload(option: ProductOption, values: tuple[ProductOptionValue, ...]) -> dict[str, Any]:
    return {
        "key": option.option_key,
        "displayName": option.display_name,
        "sortOrder": option.sort_order,
        "required": option.required,
        "selectionType": option.selection_type,
        "optionType": option.option_type,
        "values": [
            {
                "value": value.value_key,
                "displayValue": value.display_value,
                "sortOrder": value.sort_order,
                "priceDelta": _money_payload(value.price_delta) if value.price_delta is not None else None,
            }
            for value in sorted(values, key=lambda value: value.sort_order)
            if value.active
        ],
    }


def _public_variant_payload(
    product: StoreProduct,
    variant: ProductVariant,
    availability: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "publicVariantId": str(variant.public_variant_id),
        "displayName": variant.display_name,
        "optionValues": dict(variant.option_values),
        "priceDelta": _money_payload(variant.price_delta),
        "displayPrice": _money_payload(_variant_display_price(product, variant)),
        "availability": dict(availability or {"availableStock": 0, "saleStatus": "UNAVAILABLE"}),
        "status": variant.status.value,
        "active": variant.saleable,
        "sku": variant.sku,
        "sortOrder": variant.sort_order,
    }


def _display_price_payload(
    product: StoreProduct,
    variants: tuple[ProductVariant, ...],
    variant_availability: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    saleable_variants = [
        variant
        for variant in variants
        if _variant_is_available(variant, variant_availability.get(str(variant.public_variant_id), {}))
    ]
    if not saleable_variants:
        return _money_payload(product.price)
    lowest = min(saleable_variants, key=lambda variant: _variant_display_price(product, variant).amount)
    payload = _money_payload(_variant_display_price(product, lowest))
    payload["priceLabel"] = "from"
    payload["publicVariantId"] = str(lowest.public_variant_id)
    return payload


def _aggregate_availability(
    availability: Mapping[str, Any],
    variants: tuple[ProductVariant, ...],
    variant_availability: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    if not variants:
        return dict(availability)
    total = sum(_variant_available_stock(variant, variant_availability.get(str(variant.public_variant_id), {})) for variant in variants)
    return {
        "availableStock": total,
        "saleStatus": "ACTIVE" if total > 0 and any(variant.saleable for variant in variants) else "UNAVAILABLE",
    }


def _variant_is_available(variant: ProductVariant, availability: Mapping[str, Any]) -> bool:
    return variant.saleable and _variant_available_stock(variant, availability) > 0


def _variant_available_stock(variant: ProductVariant, availability: Mapping[str, Any]) -> int:
    if not variant.saleable or str(availability.get("saleStatus", "ACTIVE")) != "ACTIVE":
        return 0
    return int(availability.get("availableStock", 0))


def _variant_display_price(product: StoreProduct, variant: ProductVariant) -> Money:
    return product.price.add(variant.price_delta)


def _payment_capability_payload(
    store: StoreProfile,
    *,
    asset_registry: Any | None = None,
) -> dict[str, Any]:
    if asset_registry is not None:
        chain_ids = set(store.supported_chain_ids)
        chains = [chain for chain in asset_registry.chains if chain.enabled and chain.chain_id in chain_ids]
        accepted_chain_ids = {chain.chain_id for chain in chains}
        configured_asset_ids = set(store.supported_payment_asset_ids)
        accepted_assets = [
            asset
            for asset in asset_registry.assets
            if asset.enabled
            and asset.chain_id in accepted_chain_ids
            and (not configured_asset_ids or asset.asset_id in configured_asset_ids)
        ]
        return {
            "supportedChains": [
                {
                    "chainId": chain.chain_id,
                    "displayName": chain.display_name,
                    "nativeSymbol": chain.native_symbol,
                }
                for chain in chains
            ],
            "acceptedAssets": [_payment_asset_payload(asset) for asset in accepted_assets],
            "settlement": {"available": store.store_wallet is not None},
        }

    return {
        "supportedChainIds": list(store.supported_chain_ids),
        "assets": [],
        "settlement": {"available": store.store_wallet is not None},
    }


def _payment_asset_payload(asset: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "assetId": asset.asset_id,
        "assetType": asset.asset_type.value,
        "chainId": asset.chain_id,
        "symbol": asset.symbol,
        "decimals": asset.decimals,
    }
    if asset.contract_address is not None:
        payload["tokenContract"] = {"address": str(asset.contract_address)}
    return payload


def _pagination(*, limit: int, offset: int, count: int) -> dict[str, int | None]:
    return {"limit": limit, "offset": offset, "nextOffset": offset + limit if count == limit else None}


def _money_payload(price: Any) -> dict[str, Any]:
    return {
        "amount": format(price.amount, "f"),
        "currency": price.currency,
    }


def _role_value(value: Any) -> str:
    enum_value = getattr(value, "value", None)
    return str(enum_value if enum_value is not None else value)


def _group_id(value: Any) -> str:
    return str(value)
