from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEED_SCRIPT_PATH = ROOT / "app" / "postgres" / "init.d" / "002-token-payments-default-seed.sh"
DEMO_SEED_SCRIPT_PATH = ROOT / "app" / "postgres" / "init.d" / "003-token-payments-demo-seed.sh"
ENV_EXAMPLE_PATH = ROOT / ".env.example"
COMPOSE_PATH = ROOT / "docker-compose.yml"


REQUIRED_DEFAULT_SEED_TABLES = {
    "auth_roles",
    "auth_permissions",
    "auth_role_permissions",
    "auth_users",
    "auth_groups",
    "auth_group_memberships",
}
REQUIRED_BOOTSTRAP_ENV_KEYS = {"BOOTSTRAP_ADMIN_WALLET_ADDRESS"}
FORBIDDEN_BOOTSTRAP_ENV_PREFIXES = ("BOOTSTRAP_STORE_", "BOOTSTRAP_PRODUCT_", "BOOTSTRAP_CUSTOMER_")
FORBIDDEN_DEFAULT_SEED_TABLES = {
    "order_customers",
    "store_catalog_stores",
    "store_catalog_store_memberships",
    "store_catalog_products",
    "order_stores",
    "order_store_products",
    "product_inventory",
    "store_approval_stores",
    "store_approval_products",
}
REQUIRED_DEMO_SEED_TABLES = {
    "auth_users",
    "auth_user_wallets",
    "auth_user_profiles",
    "auth_groups",
    "auth_group_memberships",
    "auth_group_invitations",
    "chains",
    "payment_assets",
    "order_customers",
    "store_catalog_stores",
    "store_catalog_store_memberships",
    "store_catalog_products",
    "order_stores",
    "order_store_products",
    "product_inventory",
    "store_approval_stores",
    "store_approval_products",
}
FORBIDDEN_PLACEHOLDER_SEED_VALUES = {
    "store-1",
    "Token Payments Mug",
}


def test_default_postgres_seed_runs_after_schema_from_compose_init_directory() -> None:
    compose = COMPOSE_PATH.read_text(encoding="utf-8")
    seed_script = SEED_SCRIPT_PATH.read_text(encoding="utf-8")

    assert "${PWD}/app/postgres/init.d:/docker-entrypoint-initdb.d" in compose
    assert SEED_SCRIPT_PATH.name > "001-token-payments-schema.sql"
    assert "psql" in seed_script
    assert "ON_ERROR_STOP=1" in seed_script
    assert "BEGIN;" in seed_script
    assert "COMMIT;" in seed_script


def test_compose_runs_idempotent_default_seed_service_after_postgres_is_healthy() -> None:
    compose = COMPOSE_PATH.read_text(encoding="utf-8")

    assert "postgres_seed:" in compose
    assert "container_name: postgres_seed" in compose
    assert "BOOTSTRAP_POSTGRES_HOST=postgres" in compose
    assert "test_network_data:${TEST_NETWORK_DB_PATH}:ro" in compose
    assert "ADAPTER_BLOCKCHAIN_DEPLOYED_CONTRACTS_PATH=/var/chainDB/deployed_contracts.json" in compose
    assert "sh /docker-entrypoint-initdb.d/002-token-payments-default-seed.sh" in compose
    assert "sh /docker-entrypoint-initdb.d/003-token-payments-demo-seed.sh" in compose
    assert "&&" in compose
    assert "condition: service_healthy" in compose
    assert "test_network:" in compose
    assert "condition: service_started" in compose


def test_default_postgres_seed_bootstraps_only_rbac_catalog_and_platform_admin() -> None:
    seed_script = SEED_SCRIPT_PATH.read_text(encoding="utf-8")
    inserted_tables = set(re.findall(r"INSERT INTO\s+([a-z_]+)", seed_script))

    assert REQUIRED_DEFAULT_SEED_TABLES <= inserted_tables
    assert inserted_tables.isdisjoint(FORBIDDEN_DEFAULT_SEED_TABLES)
    assert "PLATFORM_ADMIN" in seed_script
    assert "admin:provision" in seed_script
    assert "rbac:manage" in seed_script
    assert "MERCHANT_OWNER" in seed_script
    assert "product:write" in seed_script
    assert "inventory:write" in seed_script
    assert "ON CONFLICT" in seed_script

    for forbidden in FORBIDDEN_PLACEHOLDER_SEED_VALUES:
        assert forbidden not in seed_script


def test_default_postgres_seed_uses_env_backed_admin_and_realistic_wallet_validation() -> None:
    env = _env_values()
    seed_script = SEED_SCRIPT_PATH.read_text(encoding="utf-8")

    assert REQUIRED_BOOTSTRAP_ENV_KEYS <= set(env)
    assert env["BOOTSTRAP_ADMIN_WALLET_ADDRESS"] == ""
    assert not any(key.startswith(FORBIDDEN_BOOTSTRAP_ENV_PREFIXES) for key in env)
    assert "BOOTSTRAP_ADMIN_WALLET_ADDRESS:-${TEST_NETWORK_ACCOUNT:-}" in seed_script
    assert "gen_random_uuid()" in seed_script
    assert "CREATE EXTENSION IF NOT EXISTS pgcrypto" in seed_script
    assert "ADMIN_PERSONAL_GROUP_ID" not in seed_script
    assert "PLATFORM_GROUP_ID" not in seed_script
    assert "018f33aa-9e6d-73d8-9dc3-47d6cdcc900" not in seed_script
    assert "BOOTSTRAP_STORE_WALLET_ADDRESS" not in seed_script
    assert "BOOTSTRAP_POSTGRES_HOST" in seed_script
    assert "PGPASSWORD" in seed_script
    assert "0x[0-9a-fA-F]{40}" in seed_script
    assert "BOOTSTRAP_ADMIN_WALLET_ADDRESS must be a 20-byte hex wallet address" in seed_script


def test_demo_postgres_seed_is_separate_idempotent_checkout_fixture() -> None:
    demo_seed = DEMO_SEED_SCRIPT_PATH.read_text(encoding="utf-8")
    inserted_tables = set(re.findall(r"INSERT INTO\s+([a-z_]+)", demo_seed))

    assert DEMO_SEED_SCRIPT_PATH.name > SEED_SCRIPT_PATH.name
    assert REQUIRED_DEMO_SEED_TABLES <= inserted_tables
    assert "BEGIN;" in demo_seed
    assert "COMMIT;" in demo_seed
    assert "ON CONFLICT" in demo_seed
    assert "st_demo_store_001" in demo_seed
    assert "prd_local_hoodie_001" in demo_seed
    assert "11111111-1111-4111-8111-111111111111" in demo_seed
    assert "33333333-3333-4333-8333-333333333333" in demo_seed
    assert "Local Hoodie" in demo_seed
    assert "TPAY" not in demo_seed
    assert "'ETH'" in demo_seed
    assert "0x3333333333333333333333333333333333333333" not in demo_seed
    assert "available_stock = EXCLUDED.available_stock" in demo_seed

    for forbidden in FORBIDDEN_PLACEHOLDER_SEED_VALUES:
        assert forbidden not in demo_seed


def test_demo_postgres_seed_does_not_commit_secret_material_or_private_keys() -> None:
    demo_seed = DEMO_SEED_SCRIPT_PATH.read_text(encoding="utf-8")

    assert "private_key" not in demo_seed.lower()
    assert "seed phrase" not in demo_seed.lower()
    assert "mnemonic" not in demo_seed.lower()
    assert "refresh_token_hash" not in demo_seed
    assert not re.search(r"\b0x[a-fA-F0-9]{64}\b", demo_seed)


def test_demo_postgres_seed_uses_deployed_token_contracts_instead_of_legacy_placeholders() -> None:
    demo_seed = DEMO_SEED_SCRIPT_PATH.read_text(encoding="utf-8")
    env_example = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")

    assert "ADAPTER_BLOCKCHAIN_DEPLOYED_CONTRACTS_PATH=/var/chainDB/deployed_contracts.json" in env_example
    assert "ADAPTER_BLOCKCHAIN_TOKEN_ADDRESS" not in env_example
    assert "0x4444444444444444444444444444444444444444" not in demo_seed
    assert "0x5555555555555555555555555555555555555555" not in demo_seed
    assert "0x6666666666666666666666666666666666666666" not in demo_seed
    assert "LOCAL_USDC_CONTRACT_ADDRESS" in demo_seed
    assert "LOCAL_USDT_CONTRACT_ADDRESS" in demo_seed
    assert "deployed_contracts.json" in demo_seed
    assert ":'local_usdc_contract_address'" in demo_seed
    assert ":'local_usdt_contract_address'" in demo_seed
    assert "local-disabled-dai" not in demo_seed


def _env_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        values[key] = value
    return values
