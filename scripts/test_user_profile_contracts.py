from __future__ import annotations

import re
import sys
from dataclasses import dataclass, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import ApiAuthContext, ApiRequest  # noqa: E402
from token_payments.api.auth import AuthApi  # noqa: E402
from token_payments.contexts.auth.adapter import PostgresUserProfileRepository  # noqa: E402
from token_payments.contexts.auth.application import (  # noqa: E402
    AuthApplicationError,
    AuthApplicationService,
    GetCurrentUserProfileQuery,
    GetUserProfileQuery,
    UpdateUserProfileCommand,
)
from token_payments.contexts.auth.domain import User, UserProfile, UserProfileStatus  # noqa: E402
from token_payments.shared.adapter.postgres.schema import POSTGRES_SCHEMA_COMPATIBILITY_SQL  # noqa: E402
from token_payments.shared.domain import UserId  # noqa: E402


NOW = datetime(2026, 5, 22, 1, 0, tzinfo=UTC)
USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc2301")
OTHER_USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc2302")
ADMIN_USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc2303")


def test_user_profile_is_separate_from_auth_identity_and_supports_tombstones() -> None:
    user_fields = {field.name for field in fields(User)}
    assert {"display_name", "email", "email_verified_at", "locale", "timezone", "status"}.isdisjoint(user_fields)

    profile = _profile(
        display_name="  Cafe\u0301 Wallet  ",
        email="ALICE@Example.COM",
        email_verified_at=NOW,
        locale="ko-KR",
        timezone="Asia/Seoul",
    )

    assert profile.display_name == "Caf\u00e9 Wallet"
    assert profile.email == "alice@example.com"
    assert profile.locale == "ko-KR"
    assert profile.timezone == "Asia/Seoul"
    assert profile.status is UserProfileStatus.ACTIVE

    tombstone = profile.delete(deleted_at=NOW + timedelta(minutes=1))

    assert tombstone.status is UserProfileStatus.DELETED
    assert tombstone.display_name is None
    assert tombstone.email is None
    assert tombstone.email_verified_at is None
    assert tombstone.locale is None
    assert tombstone.timezone is None
    assert tombstone.user_id == profile.user_id


@pytest.mark.parametrize(
    "display_name",
    [
        "",
        " ",
        "Alice\nBob",
        "Alice\x00Bob",
        "=SUM(A1:A2)",
        "+Alice",
        "-Alice",
        "@Alice",
        "x" * 81,
    ],
)
def test_user_profile_display_name_rejects_untrusted_text(display_name: str) -> None:
    with pytest.raises(ValueError, match="display_name"):
        _profile(display_name=display_name)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"email": "not-an-email"},
        {"email": "alice@example"},
        {"locale": "en_US"},
        {"locale": "ko-\x00KR"},
        {"timezone": "Mars/Phobos"},
        {"timezone": "Asia/Seoul\n"},
    ],
)
def test_user_profile_contact_and_locale_fields_are_bounded(kwargs: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        _profile(**kwargs)


def test_email_profile_field_does_not_enable_email_login_recovery_or_did_identity() -> None:
    profile_fields = {field.name for field in fields(UserProfile)}
    assert "email" in profile_fields
    assert {"password_hash", "email_recovery_token", "did", "did_document"}.isdisjoint(profile_fields)

    forbidden_methods = {
        "loginWithEmail",
        "requestEmailAccountRecovery",
        "verifyEmailRecovery",
        "verifyDid",
        "linkDid",
    }
    assert forbidden_methods.isdisjoint(dir(AuthApplicationService))


def test_user_profile_display_name_must_be_unique_across_active_profiles() -> None:
    profiles = FakeProfileRepository()
    profiles.save(_profile(user_id=OTHER_USER_ID, display_name="Cafe\u0301 Wallet"))
    service = _profile_service(profiles)

    with pytest.raises(AuthApplicationError) as exc_info:
        service.updateUserProfile(
            UpdateUserProfileCommand(
                actor_user_id=USER_ID,
                target_user_id=USER_ID,
                display_name="caf\u00e9 wallet",
                requested_at=NOW,
            )
        )

    assert exc_info.value.code.value == "USER_PROFILE_DISPLAY_NAME_CONFLICT"
    assert profiles.get_by_user_id(USER_ID) is None


def test_profile_api_redacts_contact_fields_and_requires_self_or_user_manage_for_update() -> None:
    use_case = FakeProfileUseCase(_profile(display_name="<Alice & Bob>", email="alice@example.com"))
    api = AuthApi(use_case)

    public_response = api.get_user_profile(
        ApiRequest(
            request_id="req-public-profile",
            method="GET",
            path="/users/profile",
            query={"userId": str(USER_ID)},
            received_at=NOW,
        )
    )

    assert public_response.status_code == 200
    public_profile = public_response.body["profile"]
    assert public_profile["userId"] == str(USER_ID)
    assert public_profile["displayName"] == "<Alice & Bob>"
    assert public_profile["displayNameHtml"] == "&lt;Alice &amp; Bob&gt;"
    assert "email" not in public_profile
    assert "emailVerifiedAt" not in public_profile

    self_response = api.current_user_profile(
        ApiRequest(
            request_id="req-self-profile",
            method="GET",
            path="/auth/me/profile",
            auth_context=ApiAuthContext(user_id=str(USER_ID), session_id="session", scopes=("user:self",)),
            received_at=NOW,
        )
    )

    assert self_response.status_code == 200
    assert self_response.body["profile"]["email"] == "alice@example.com"

    forbidden_update = api.update_current_user_profile(
        ApiRequest(
            request_id="req-update-forbidden",
            method="PATCH",
            path="/users/profile",
            query={"userId": str(USER_ID)},
            body={"displayName": "New Name"},
            auth_context=ApiAuthContext(user_id=str(OTHER_USER_ID), session_id="session", scopes=("user:self",)),
            received_at=NOW,
        )
    )

    assert forbidden_update.status_code == 403
    assert forbidden_update.body["error"]["code"] == "USER_PROFILE_FORBIDDEN"

    admin_update = api.update_current_user_profile(
        ApiRequest(
            request_id="req-update-admin",
            method="PATCH",
            path="/users/profile",
            query={"userId": str(USER_ID)},
            body={"displayName": "New Name", "locale": "en-US", "timezone": "UTC"},
            auth_context=ApiAuthContext(user_id=str(ADMIN_USER_ID), session_id="session", scopes=("user:manage",)),
            received_at=NOW,
        )
    )

    assert admin_update.status_code == 200
    assert use_case.update_commands[-1].actor_user_id == ADMIN_USER_ID
    assert use_case.update_commands[-1].target_user_id == USER_ID
    assert use_case.update_commands[-1].request_id == "req-update-admin"
    assert admin_update.body["profile"]["displayName"] == "New Name"


def test_postgres_profile_schema_and_repository_keep_profile_out_of_auth_users() -> None:
    schema = (ROOT / "app/postgres/init.d/001-token-payments-schema.sql").read_text(encoding="utf-8")
    normalized_schema = " ".join(schema.lower().split())
    compatibility_sql = " ".join("\n".join(POSTGRES_SCHEMA_COMPATIBILITY_SQL).lower().split())

    assert "create table if not exists auth_user_profiles" in normalized_schema
    assert "create table if not exists auth_user_profiles" in compatibility_sql
    assert "references auth_users (user_id)" in normalized_schema
    assert "idx_auth_user_profiles_display_name_unique" in normalized_schema
    assert "idx_auth_user_profiles_display_name_unique" in compatibility_sql

    auth_users_block = re.search(
        r"create table if not exists auth_users \((.*?)\);",
        normalized_schema,
    )
    assert auth_users_block is not None
    assert {"display_name", "email_verified_at", "locale", "timezone"}.isdisjoint(
        set(auth_users_block.group(1).replace(",", " ").split())
    )

    connection = FakeProfileConnection()
    repository = PostgresUserProfileRepository(connection)
    profile = _profile(display_name="Alice <Ops>", email="alice@example.com")

    assert repository.get_by_user_id(USER_ID) is None
    repository.save(profile)

    assert repository.get_by_user_id(USER_ID) == profile
    assert repository.get_by_display_name("alice <ops>") == profile
    combined_sql = "\n".join(statement.sql for statement in connection.statements)
    normalized_sql = " ".join(combined_sql.lower().split())
    assert "insert into auth_user_profiles" in normalized_sql
    assert "%(display_name)s" in combined_sql
    assert "%(email)s" in combined_sql
    assert profile.display_name not in combined_sql
    assert profile.email not in combined_sql
    insert_statement = next(
        statement
        for statement in connection.statements
        if "insert into auth_user_profiles" in " ".join(statement.sql.lower().split())
    )
    assert insert_statement.params["display_name"] == "Alice <Ops>"


def _profile(
    *,
    user_id: UserId = USER_ID,
    display_name: str | None = "Alice",
    email: str | None = None,
    email_verified_at: datetime | None = None,
    locale: str | None = "en-US",
    timezone: str | None = "UTC",
    status: UserProfileStatus = UserProfileStatus.ACTIVE,
) -> UserProfile:
    return UserProfile(
        user_id=user_id,
        display_name=display_name,
        email=email,
        email_verified_at=email_verified_at,
        locale=locale,
        timezone=timezone,
        status=status,
        created_at=NOW,
        updated_at=NOW,
    )


class FakeProfileUseCase:
    def __init__(self, profile: UserProfile) -> None:
        self.profile = profile
        self.get_queries: list[object] = []
        self.update_commands: list[UpdateUserProfileCommand] = []

    def getCurrentUserProfile(self, query: GetCurrentUserProfileQuery) -> UserProfile | None:
        self.get_queries.append(query)
        return self.profile if query.user_id == self.profile.user_id else None

    def getUserProfile(self, query: GetUserProfileQuery) -> UserProfile | None:
        self.get_queries.append(query)
        return self.profile if query.user_id == self.profile.user_id else None

    def updateUserProfile(self, command: UpdateUserProfileCommand) -> UserProfile:
        self.update_commands.append(command)
        self.profile = self.profile.update(
            display_name=command.display_name,
            email=command.email,
            locale=command.locale,
            timezone=command.timezone,
            updated_at=command.requested_at,
        )
        return self.profile


class FakeProfileRepository:
    def __init__(self) -> None:
        self.profiles: dict[UserId, UserProfile] = {}

    def save(self, profile: UserProfile) -> None:
        self.profiles[profile.user_id] = profile

    def get_by_user_id(self, user_id: UserId) -> UserProfile | None:
        return self.profiles.get(user_id)

    def get_by_display_name(self, display_name: str) -> UserProfile | None:
        key = display_name.casefold()
        return next(
            (
                profile
                for profile in self.profiles.values()
                if profile.display_name is not None and profile.display_name.casefold() == key
            ),
            None,
        )


class FakeClock:
    def now(self) -> datetime:
        return NOW


def _profile_service(profiles: FakeProfileRepository) -> AuthApplicationService:
    return AuthApplicationService(
        clock=FakeClock(),
        nonce_generator=object(),
        user_id_generator=object(),
        session_id_generator=object(),
        users=object(),
        login_challenges=object(),
        sessions=object(),
        signature_verifier=object(),
        token_issuer=object(),
        event_publisher=object(),
        profiles=profiles,
    )


@dataclass(frozen=True)
class ExecutedStatement:
    sql: str
    params: Mapping[str, Any]


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def __iter__(self) -> Any:
        return iter(self._rows)


class FakeProfileConnection:
    def __init__(self) -> None:
        self.statements: list[ExecutedStatement] = []
        self.profiles: dict[str, dict[str, Any]] = {}

    def execute(self, sql: str, params: Mapping[str, Any] | None = None) -> FakeResult:
        statement = ExecutedStatement(sql=sql, params=dict(params or {}))
        self.statements.append(statement)
        normalized_sql = " ".join(sql.lower().split())

        if "insert into auth_user_profiles" in normalized_sql:
            self.profiles[str(statement.params["user_id"])] = dict(statement.params)
            return FakeResult()
        if "from auth_user_profiles" in normalized_sql and "user_id =" in normalized_sql:
            row = self.profiles.get(str(statement.params["user_id"]))
            return FakeResult([dict(row)] if row else [])
        if "from auth_user_profiles" in normalized_sql and "lower(display_name)" in normalized_sql:
            key = str(statement.params["display_name"]).casefold()
            row = next(
                (
                    profile
                    for profile in self.profiles.values()
                    if str(profile["status"]) != "DELETED"
                    and profile["display_name"] is not None
                    and str(profile["display_name"]).casefold() == key
                ),
                None,
            )
            return FakeResult([dict(row)] if row else [])
        return FakeResult()
