"""Merchant group membership and invitation application service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping, Protocol

from token_payments.contexts.auth.application.authorization import ResourceRef
from token_payments.contexts.auth.domain import (
    Group,
    GroupId,
    GroupInvitation,
    GroupMembership,
    InvitationId,
    InvitationStatus,
    MerchantRoleTemplate,
    Role,
    RoleId,
)
from token_payments.shared.domain import StoreId, UserId, WalletAddress


OWNER_ROLE_ID = RoleId("MERCHANT_OWNER")
MERCHANT_ASSIGNABLE_ROLE_IDS = frozenset({template.value for template in MerchantRoleTemplate})


@dataclass(frozen=True)
class MerchantActor:
    user_id: UserId
    scopes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, UserId):
            raise ValueError("MerchantActor.user_id must be a UserId")
        if not isinstance(self.scopes, tuple):
            raise ValueError("MerchantActor.scopes must be a tuple")
        object.__setattr__(self, "scopes", tuple(_text(scope, "MerchantActor.scopes") for scope in self.scopes))


@dataclass(frozen=True)
class MerchantMembershipResult:
    status: str
    payload: Mapping[str, Any]
    rejection_reason: str | None = None


class MerchantMembershipRepository(Protocol):
    def merchant_group_for_store(self, store_id: StoreId) -> Group | None:
        ...

    def members_for_group(self, group_id: GroupId) -> tuple[GroupMembership, ...]:
        ...

    def get_membership(self, group_id: GroupId, user_id: UserId) -> GroupMembership | None:
        ...

    def save_membership(self, membership: GroupMembership) -> None:
        ...

    def invitations_for_group(self, group_id: GroupId) -> tuple[GroupInvitation, ...]:
        ...

    def get_invitation(self, invitation_id: InvitationId) -> GroupInvitation | None:
        ...

    def save_invitation(self, invitation: GroupInvitation) -> None:
        ...

    def user_id_for_active_wallet(self, wallet: WalletAddress) -> UserId | None:
        ...

    def user_id_for_active_display_name(self, display_name: str) -> UserId | None:
        ...

    def role_catalog(self) -> tuple[Role, ...]:
        ...

    def search_users(self, query: str) -> tuple[dict[str, Any], ...]:
        ...

    def store_id_for_group(self, group_id: GroupId) -> StoreId | None:
        ...


class MerchantMembershipService:
    def __init__(self, repository: MerchantMembershipRepository, *, invitation_id_generator: Any | None = None) -> None:
        self._repository = repository
        self._invitation_id_generator = invitation_id_generator

    def role_catalog(self, actor: MerchantActor) -> MerchantMembershipResult:
        if not actor.user_id:
            return _rejected("AUTHENTICATION_REQUIRED", "authenticated session is required")
        roles = [
            _role_payload(role)
            for role in self._repository.role_catalog()
            if role.group_type.value == "MERCHANT" and role.merchant_assignable and not role.owner_role
        ]
        return _completed({"roles": roles, "rawPermissionMutationAllowed": False})

    def search_users(self, actor: MerchantActor, query: str) -> MerchantMembershipResult:
        if not actor.user_id:
            return _rejected("AUTHENTICATION_REQUIRED", "authenticated session is required")
        if not query or not query.strip():
            return _completed({"users": []})
        users = self._repository.search_users(query.strip())
        return _completed({"users": users})

    def list_members(self, actor: MerchantActor, store_id: StoreId) -> MerchantMembershipResult:
        group = self._require_group(store_id)
        denied = self._deny_without(actor, "merchant_member:read", store_id)
        if denied is not None:
            return denied
        return _completed({"storeId": str(store_id), "members": [_membership_payload(item) for item in self._repository.members_for_group(group.group_id)]})

    def list_invitations(self, actor: MerchantActor, store_id: StoreId) -> MerchantMembershipResult:
        group = self._require_group(store_id)
        denied = self._deny_without(actor, "merchant_member:read", store_id)
        if denied is not None:
            return denied
        return _completed({"storeId": str(store_id), "invitations": [_invitation_payload(item) for item in self._repository.invitations_for_group(group.group_id)]})

    def create_invitation(
        self,
        actor: MerchantActor,
        store_id: StoreId,
        *,
        role_id: RoleId,
        target_user_id: UserId | None = None,
        target_wallet: WalletAddress | None = None,
        target_display_name: str | None = None,
        expires_at: datetime | None = None,
        requested_at: datetime | None = None,
    ) -> MerchantMembershipResult:
        group = self._require_group(store_id)
        denied = self._deny_without(actor, "merchant_member:invite", store_id)
        if denied is not None:
            return denied
        rejected = self._reject_merchant_role(role_id)
        if rejected is not None:
            return rejected
        resolved_user_id = target_user_id
        if target_display_name is not None:
            resolved_user_id = self._repository.user_id_for_active_display_name(_text(target_display_name, "targetDisplayName"))
            if resolved_user_id is None:
                return _rejected("INVITATION_TARGET_NOT_FOUND", "target displayName was not found")
        elif target_wallet is not None:
            resolved_user_id = self._repository.user_id_for_active_wallet(target_wallet)

        admin_wallet = WalletAddress("0x32b31C74fE628e9164996f727F0D11A3C49EC27f")
        admin_user_id = self._repository.user_id_for_active_wallet(admin_wallet)

        if resolved_user_id is not None:
            if resolved_user_id == actor.user_id:
                return _rejected("INVITATION_TARGET_INVALID", "cannot invite yourself")
            if admin_user_id is not None and resolved_user_id == admin_user_id:
                return _rejected("INVITATION_TARGET_INVALID", "cannot invite platform admin")

        if target_wallet is not None:
            if str(target_wallet).lower() == str(admin_wallet).lower():
                return _rejected("INVITATION_TARGET_INVALID", "cannot invite platform admin")
        now = requested_at or datetime.now(UTC)
        invitation = GroupInvitation(
            invitation_id=self._new_invitation_id(),
            group_id=group.group_id,
            invited_role_id=role_id,
            invited_by_user_id=actor.user_id,
            target_user_id=resolved_user_id,
            target_wallet=target_wallet,
            status=InvitationStatus.PENDING,
            created_at=now,
            expires_at=expires_at,
        )
        self._repository.save_invitation(invitation)
        return _completed({"invitation": _invitation_payload(invitation)}, status="created")

    def accept_invitation(
        self,
        actor: MerchantActor,
        invitation_id: InvitationId,
        *,
        wallet: WalletAddress | None = None,
        accepted_at: datetime | None = None,
    ) -> MerchantMembershipResult:
        invitation = self._repository.get_invitation(invitation_id)
        if invitation is None:
            return _rejected("INVITATION_NOT_FOUND", "invitation was not found")
        now = accepted_at or datetime.now(UTC)
        not_acceptable = "invitation is expired, revoked, accepted, or not targeted to this user"
        accepted_wallet = wallet
        if invitation.target_wallet is not None:
            if wallet is not None and wallet != invitation.target_wallet:
                return _rejected("INVITATION_NOT_ACCEPTABLE", not_acceptable)
            wallet_owner = self._repository.user_id_for_active_wallet(invitation.target_wallet)
            if wallet_owner != actor.user_id:
                return _rejected("INVITATION_NOT_ACCEPTABLE", not_acceptable)
            accepted_wallet = invitation.target_wallet
        if not invitation.is_open_for(actor.user_id, accepted_wallet, now):
            return _rejected("INVITATION_NOT_ACCEPTABLE", not_acceptable)
        existing = self._repository.get_membership(invitation.group_id, actor.user_id)
        if existing is not None and existing.active:
            return _rejected("MEMBERSHIP_ALREADY_EXISTS", "target user is already an active merchant member")
        membership = GroupMembership(actor.user_id, invitation.group_id, invitation.invited_role_id, active=True, joined_at=now)
        accepted = GroupInvitation(
            invitation_id=invitation.invitation_id,
            group_id=invitation.group_id,
            invited_role_id=invitation.invited_role_id,
            invited_by_user_id=invitation.invited_by_user_id,
            target_user_id=invitation.target_user_id,
            target_wallet=invitation.target_wallet,
            status=InvitationStatus.ACCEPTED,
            created_at=invitation.created_at,
            expires_at=invitation.expires_at,
        )
        self._repository.save_membership(membership)
        self._repository.save_invitation(accepted)
        return _completed({"membership": _membership_payload(membership), "invitation": _invitation_payload(accepted)})

    def revoke_invitation(self, actor: MerchantActor, invitation_id: InvitationId) -> MerchantMembershipResult:
        invitation = self._repository.get_invitation(invitation_id)
        if invitation is None:
            return _rejected("INVITATION_NOT_FOUND", "invitation was not found")
        store_id = self._store_for_group(invitation.group_id)
        denied = self._deny_without_any(actor, ("merchant_member:invite", "merchant_member:manage"), store_id)
        if denied is not None:
            return denied
        if invitation.status is not InvitationStatus.PENDING:
            return _rejected("INVITATION_NOT_PENDING", "only pending invitations can be revoked")
        revoked = GroupInvitation(
            invitation_id=invitation.invitation_id,
            group_id=invitation.group_id,
            invited_role_id=invitation.invited_role_id,
            invited_by_user_id=invitation.invited_by_user_id,
            target_user_id=invitation.target_user_id,
            target_wallet=invitation.target_wallet,
            status=InvitationStatus.REVOKED,
            created_at=invitation.created_at,
            expires_at=invitation.expires_at,
        )
        self._repository.save_invitation(revoked)
        return _completed({"invitation": _invitation_payload(revoked)})

    def update_member_role(self, actor: MerchantActor, store_id: StoreId, user_id: UserId, role_id: RoleId) -> MerchantMembershipResult:
        group = self._require_group(store_id)
        denied = self._deny_without(actor, "merchant_member:manage", store_id)
        if denied is not None:
            return denied
        rejected = self._reject_merchant_role(role_id)
        if rejected is not None:
            return rejected
        current = self._repository.get_membership(group.group_id, user_id)
        if current is None or not current.active:
            return _rejected("MEMBER_NOT_FOUND", "active merchant member was not found")
        if current.role_id == OWNER_ROLE_ID:
            return _rejected("OWNER_ROLE_PROTECTED", "merchant-facing APIs cannot change owner membership")
        updated = GroupMembership(user_id, group.group_id, role_id, active=True, joined_at=current.joined_at)
        self._repository.save_membership(updated)
        return _completed({"membership": _membership_payload(updated)})

    def remove_member(self, actor: MerchantActor, store_id: StoreId, user_id: UserId) -> MerchantMembershipResult:
        group = self._require_group(store_id)
        denied = self._deny_without(actor, "merchant_member:manage", store_id)
        if denied is not None:
            return denied
        current = self._repository.get_membership(group.group_id, user_id)
        if current is None or not current.active:
            return _rejected("MEMBER_NOT_FOUND", "active merchant member was not found")
        if current.role_id == OWNER_ROLE_ID:
            return _rejected("OWNER_ROLE_PROTECTED", "merchant-facing APIs cannot remove owner membership")
        removed = GroupMembership(user_id, group.group_id, current.role_id, active=False, joined_at=current.joined_at)
        self._repository.save_membership(removed)
        return _completed({"membership": _membership_payload(removed)})

    def _require_group(self, store_id: StoreId) -> Group:
        group = self._repository.merchant_group_for_store(store_id)
        if group is None:
            raise ValueError("merchant group was not found for store")
        return group

    def _store_for_group(self, group_id: GroupId) -> StoreId:
        store_id = self._repository.store_id_for_group(group_id)
        if store_id is not None:
            return store_id
        for role_group_store in getattr(self._repository, "store_groups", {}).items():
            s_id, existing_group_id = role_group_store
            if existing_group_id == group_id:
                return s_id
        raise ValueError("merchant group was not linked to a store")

    def _deny_without(self, actor: MerchantActor, permission: str, store_id: StoreId) -> MerchantMembershipResult | None:
        return None if permission in actor.scopes else _rejected("MERCHANT_MEMBER_FORBIDDEN", f"{permission} permission is required for {ResourceRef.store(store_id).resource_type}")

    def _deny_without_any(self, actor: MerchantActor, permissions: tuple[str, ...], store_id: StoreId) -> MerchantMembershipResult | None:
        return None if any(permission in actor.scopes for permission in permissions) else _rejected("MERCHANT_MEMBER_FORBIDDEN", f"one of {permissions} is required for store {store_id}")

    def _reject_merchant_role(self, role_id: RoleId) -> MerchantMembershipResult | None:
        if role_id.value == OWNER_ROLE_ID.value:
            return _rejected("OWNER_ROLE_PROTECTED", "MERCHANT_OWNER assignment or transfer is not merchant-facing")
        if role_id.value not in MERCHANT_ASSIGNABLE_ROLE_IDS:
            return _rejected("ROLE_TEMPLATE_NOT_ALLOWED", "merchant APIs accept only server-defined non-owner merchant staff templates")
        return None

    def _new_invitation_id(self) -> InvitationId:
        generator = self._invitation_id_generator
        if generator is None:
            return InvitationId.new()
        new_id = getattr(generator, "new_id", None)
        return InvitationId(str(new_id() if callable(new_id) else generator()))


def _completed(payload: Mapping[str, Any], *, status: str = "completed") -> MerchantMembershipResult:
    return MerchantMembershipResult(status=status, payload=payload)


def _rejected(code: str, message: str) -> MerchantMembershipResult:
    return MerchantMembershipResult(
        status="rejected",
        payload={"error": {"code": code, "message": message}},
        rejection_reason=code,
    )


def _membership_payload(membership: GroupMembership) -> dict[str, Any]:
    return {
        "userId": str(membership.user_id),
        "groupId": str(membership.group_id),
        "roleId": str(membership.role_id),
        "active": membership.active,
        "joinedAt": membership.joined_at.isoformat() if membership.joined_at is not None else None,
        "displayName": membership.display_name,
        "walletAddress": str(membership.wallet_address) if membership.wallet_address is not None else None,
    }


def _invitation_payload(invitation: GroupInvitation) -> dict[str, Any]:
    return {
        "invitationId": str(invitation.invitation_id),
        "groupId": str(invitation.group_id),
        "roleId": str(invitation.invited_role_id),
        "targetUserId": str(invitation.target_user_id) if invitation.target_user_id is not None else None,
        "targetWallet": str(invitation.target_wallet) if invitation.target_wallet is not None else None,
        "targetDisplayName": invitation.target_display_name,
        "status": invitation.status.value,
        "expiresAt": invitation.expires_at.isoformat() if invitation.expires_at is not None else None,
    }


def _role_payload(role: Role) -> dict[str, Any]:
    return {
        "roleId": str(role.role_id),
        "name": role.name,
        "groupType": role.group_type.value,
        "merchantAssignable": role.merchant_assignable,
        "rawPermissionMutationAllowed": False,
    }


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


__all__ = [
    "MERCHANT_ASSIGNABLE_ROLE_IDS",
    "OWNER_ROLE_ID",
    "MerchantActor",
    "MerchantMembershipRepository",
    "MerchantMembershipResult",
    "MerchantMembershipService",
]
