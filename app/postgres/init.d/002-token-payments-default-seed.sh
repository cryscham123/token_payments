#!/usr/bin/env sh
set -eu

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"

BOOTSTRAP_POSTGRES_HOST="${BOOTSTRAP_POSTGRES_HOST:-}"
BOOTSTRAP_POSTGRES_PORT="${BOOTSTRAP_POSTGRES_PORT:-5432}"
BOOTSTRAP_ADMIN_WALLET_ADDRESS="${BOOTSTRAP_ADMIN_WALLET_ADDRESS:-${TEST_NETWORK_ACCOUNT:-}}"

is_wallet_address() {
    printf '%s' "$1" | grep -Eq '^0x[0-9a-fA-F]{40}$'
}

lower_hex() {
    printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

if ! is_wallet_address "$BOOTSTRAP_ADMIN_WALLET_ADDRESS"; then
    echo "BOOTSTRAP_ADMIN_WALLET_ADDRESS must be a 20-byte hex wallet address or TEST_NETWORK_ACCOUNT must be set" >&2
    exit 1
fi

BOOTSTRAP_ADMIN_WALLET_ADDRESS="$(lower_hex "$BOOTSTRAP_ADMIN_WALLET_ADDRESS")"

PSQL_HOST_OPTION=""
PSQL_PORT_OPTION=""
if [ -n "$BOOTSTRAP_POSTGRES_HOST" ]; then
    PSQL_HOST_OPTION="--host=$BOOTSTRAP_POSTGRES_HOST"
    PSQL_PORT_OPTION="--port=$BOOTSTRAP_POSTGRES_PORT"
    if [ -z "${PGPASSWORD:-}" ] && [ -n "${POSTGRES_PASSWORD:-}" ]; then
        export PGPASSWORD="$POSTGRES_PASSWORD"
    fi
fi

psql -v ON_ERROR_STOP=1 \
    $PSQL_HOST_OPTION \
    $PSQL_PORT_OPTION \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    -v bootstrap_admin_wallet_address="$BOOTSTRAP_ADMIN_WALLET_ADDRESS" <<'SQL'
BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

INSERT INTO auth_roles (
    role_id,
    name,
    group_type,
    active,
    merchant_assignable,
    owner_role
) VALUES
    ('PERSONAL_CUSTOMER', 'Personal Customer', 'PERSONAL', true, false, false),
    ('MERCHANT_OWNER', 'Merchant Owner', 'MERCHANT', true, false, true),
    ('MERCHANT_MANAGER', 'Merchant Manager', 'MERCHANT', true, true, false),
    ('MERCHANT_STAFF', 'Merchant Staff', 'MERCHANT', true, true, false),
    ('PLATFORM_OPERATOR', 'Platform Operator', 'PLATFORM', true, false, false),
    ('PLATFORM_ADMIN', 'Platform Admin', 'PLATFORM', true, false, false)
ON CONFLICT (role_id) DO UPDATE SET
    name = EXCLUDED.name,
    group_type = EXCLUDED.group_type,
    active = EXCLUDED.active,
    merchant_assignable = EXCLUDED.merchant_assignable,
    owner_role = EXCLUDED.owner_role,
    updated_at = now();

INSERT INTO auth_permissions (
    permission_name,
    description,
    active
) VALUES
    ('user:self', 'Manage the authenticated user profile', true),
    ('store:read', 'Read merchant store details', true),
    ('store:read:any', 'Read stores across merchant groups as platform admin', true),
    ('store:write', 'Update merchant store details', true),
    ('store:write:any', 'Update stores across merchant groups as platform admin', true),
    ('store:manage', 'Manage merchant store settings', true),
    ('merchant_member:read', 'Read merchant group members', true),
    ('merchant_member:invite', 'Invite merchant group members', true),
    ('merchant_member:manage', 'Manage merchant group members', true),
    ('product:read', 'Read store products', true),
    ('product:read:any', 'Read products across merchant groups as platform admin', true),
    ('product:write', 'Write store products', true),
    ('product:write:any', 'Write products across stores as platform admin', true),
    ('inventory:read', 'Read store inventory', true),
    ('inventory:read:any', 'Read inventory across merchant groups as platform admin', true),
    ('inventory:write', 'Write store inventory', true),
    ('inventory:write:any', 'Write inventory across merchant groups as platform admin', true),
    ('operator:read', 'Read operator recovery state', true),
    ('operator:action', 'Run operator recovery actions', true),
    ('outbox:retry', 'Retry outbox publishing', true),
    ('rbac:manage', 'Manage group memberships and RBAC assignments', true),
    ('admin:provision', 'Provision platform catalog data', true)
ON CONFLICT (permission_name) DO UPDATE SET
    description = EXCLUDED.description,
    active = EXCLUDED.active,
    updated_at = now();

INSERT INTO auth_role_permissions (
    role_id,
    permission_name,
    active
) VALUES
    ('PERSONAL_CUSTOMER', 'user:self', true),
    ('MERCHANT_OWNER', 'store:read', true),
    ('MERCHANT_OWNER', 'store:write', true),
    ('MERCHANT_OWNER', 'store:manage', true),
    ('MERCHANT_OWNER', 'merchant_member:read', true),
    ('MERCHANT_OWNER', 'merchant_member:invite', true),
    ('MERCHANT_OWNER', 'merchant_member:manage', true),
    ('MERCHANT_OWNER', 'product:read', true),
    ('MERCHANT_OWNER', 'product:write', true),
    ('MERCHANT_OWNER', 'inventory:read', true),
    ('MERCHANT_OWNER', 'inventory:write', true),
    ('MERCHANT_MANAGER', 'store:read', true),
    ('MERCHANT_MANAGER', 'store:write', true),
    ('MERCHANT_MANAGER', 'merchant_member:read', true),
    ('MERCHANT_MANAGER', 'merchant_member:invite', true),
    ('MERCHANT_MANAGER', 'product:read', true),
    ('MERCHANT_MANAGER', 'product:write', true),
    ('MERCHANT_MANAGER', 'inventory:read', true),
    ('MERCHANT_MANAGER', 'inventory:write', true),
    ('MERCHANT_STAFF', 'store:read', true),
    ('MERCHANT_STAFF', 'product:read', true),
    ('MERCHANT_STAFF', 'inventory:read', true),
    ('PLATFORM_OPERATOR', 'operator:read', true),
    ('PLATFORM_OPERATOR', 'operator:action', true),
    ('PLATFORM_OPERATOR', 'outbox:retry', true),
    ('PLATFORM_ADMIN', 'store:read', true),
    ('PLATFORM_ADMIN', 'store:read:any', true),
    ('PLATFORM_ADMIN', 'store:write', true),
    ('PLATFORM_ADMIN', 'store:write:any', true),
    ('PLATFORM_ADMIN', 'product:read', true),
    ('PLATFORM_ADMIN', 'product:read:any', true),
    ('PLATFORM_ADMIN', 'product:write:any', true),
    ('PLATFORM_ADMIN', 'inventory:read', true),
    ('PLATFORM_ADMIN', 'inventory:read:any', true),
    ('PLATFORM_ADMIN', 'inventory:write', true),
    ('PLATFORM_ADMIN', 'inventory:write:any', true),
    ('PLATFORM_ADMIN', 'operator:read', true),
    ('PLATFORM_ADMIN', 'operator:action', true),
    ('PLATFORM_ADMIN', 'outbox:retry', true),
    ('PLATFORM_ADMIN', 'rbac:manage', true),
    ('PLATFORM_ADMIN', 'admin:provision', true)
ON CONFLICT (role_id, permission_name) DO UPDATE SET
    active = EXCLUDED.active;

CREATE TEMP TABLE bootstrap_ids (
    key TEXT PRIMARY KEY,
    id UUID NOT NULL
) ON COMMIT DROP;

WITH admin_user AS (
    INSERT INTO auth_users (
        user_id,
        wallet_address,
        role,
        active
    ) VALUES (
        gen_random_uuid(),
        :'bootstrap_admin_wallet_address',
        'ADMIN',
        true
    )
    ON CONFLICT (wallet_address) DO UPDATE SET
        role = EXCLUDED.role,
        active = EXCLUDED.active,
        updated_at = now()
    RETURNING user_id
)
INSERT INTO bootstrap_ids (key, id)
SELECT 'admin_user', user_id
FROM admin_user;

WITH existing_group AS (
    SELECT group_id
    FROM auth_groups
    WHERE group_type = 'PERSONAL'
      AND resource_type = 'user'
      AND resource_id = (SELECT id::text FROM bootstrap_ids WHERE key = 'admin_user')
    ORDER BY created_at ASC, group_id ASC
    LIMIT 1
),
inserted_group AS (
    INSERT INTO auth_groups (
        group_id,
        group_type,
        name,
        resource_type,
        resource_id,
        active
    )
    SELECT
        gen_random_uuid(),
        'PERSONAL',
        'Bootstrap admin personal group',
        'user',
        id::text,
        true
    FROM bootstrap_ids
    WHERE key = 'admin_user'
      AND NOT EXISTS (SELECT 1 FROM existing_group)
    RETURNING group_id
),
target_group AS (
    SELECT group_id FROM inserted_group
    UNION ALL
    SELECT group_id FROM existing_group
)
INSERT INTO bootstrap_ids (key, id)
SELECT 'admin_personal_group', group_id
FROM target_group;

UPDATE auth_groups
SET
    name = 'Bootstrap admin personal group',
    resource_type = 'user',
    resource_id = (SELECT id::text FROM bootstrap_ids WHERE key = 'admin_user'),
    active = true,
    updated_at = now()
WHERE group_id = (SELECT id FROM bootstrap_ids WHERE key = 'admin_personal_group');

WITH existing_group AS (
    SELECT group_id
    FROM auth_groups
    WHERE group_type = 'PLATFORM'
      AND name = 'Bootstrap platform administrators'
      AND resource_type IS NULL
      AND resource_id IS NULL
    ORDER BY created_at ASC, group_id ASC
    LIMIT 1
),
inserted_group AS (
    INSERT INTO auth_groups (
        group_id,
        group_type,
        name,
        resource_type,
        resource_id,
        active
    )
    SELECT
        gen_random_uuid(),
        'PLATFORM',
        'Bootstrap platform administrators',
        NULL,
        NULL,
        true
    WHERE NOT EXISTS (SELECT 1 FROM existing_group)
    RETURNING group_id
),
target_group AS (
    SELECT group_id FROM inserted_group
    UNION ALL
    SELECT group_id FROM existing_group
)
INSERT INTO bootstrap_ids (key, id)
SELECT 'platform_group', group_id
FROM target_group;

UPDATE auth_groups
SET
    resource_type = NULL,
    resource_id = NULL,
    active = true,
    updated_at = now()
WHERE group_id = (SELECT id FROM bootstrap_ids WHERE key = 'platform_group');

INSERT INTO auth_group_memberships (
    group_id,
    user_id,
    role_id,
    active
) VALUES
    (
        (SELECT id FROM bootstrap_ids WHERE key = 'admin_personal_group'),
        (SELECT id FROM bootstrap_ids WHERE key = 'admin_user'),
        'PERSONAL_CUSTOMER',
        true
    ),
    (
        (SELECT id FROM bootstrap_ids WHERE key = 'platform_group'),
        (SELECT id FROM bootstrap_ids WHERE key = 'admin_user'),
        'PLATFORM_ADMIN',
        true
    )
ON CONFLICT (group_id, user_id) DO UPDATE SET
    role_id = EXCLUDED.role_id,
    active = EXCLUDED.active,
    updated_at = now();

COMMIT;
SQL
