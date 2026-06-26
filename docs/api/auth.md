# 인증과 OAuth

이 페이지는 SIWE login, session, wallet link, current user profile, OAuth provider-subject identity API의 독립형 연동 명세다.

## 원칙

- 로그인 wallet은 SIWE challenge에 서명한 wallet이다.
- linked wallet은 인증된 사용자가 추가로 검증한 active wallet이다.
- OAuth identity는 email이 아니라 `provider`와 `providerSubject` 조합으로 식별한다.
- public OAuth response는 `providerSubject`, provider access token, refresh token, email claim, provider profile dump를 노출하지 않는다.
- 마지막 active login method를 제거하는 wallet/OAuth revoke는 거부한다.

## 인증 route

| 목적 | Method | Path | 요청 |
| --- | --- | --- | --- |
| SIWE challenge 발급 | `POST` | `/auth/challenges` | `walletAddress`, `domain`, `uri`, `chainId` |
| SIWE session 생성 | `POST` | `/auth/sessions` | `walletAddress`, `message`, `signature`, `deviceId` |
| session refresh | `POST` | `/auth/sessions/refresh` | refresh cookie/session context |
| session group switch | `POST` | `/auth/sessions/switch` | `activeGroupId` |
| logout | `DELETE` | `/auth/sessions` | active session |
| current user 조회 | `GET` | `/auth/me` | active session |
| current profile 조회 | `GET` | `/auth/me/profile` | active session |
| current profile 수정 | `PATCH` | `/auth/me/profile` | `displayName` |

## OAuth route

빠른 참조: `POST /auth/oauth/{provider}/authorize`, `POST /auth/oauth/{provider}/sessions`, `POST /auth/oauth/{provider}/links`, `GET /auth/oauth/identities`, `DELETE /auth/oauth/identities/{oauthIdentityId}`.

| 목적 | Method | Path | 권한 |
| --- | --- | --- | --- |
| provider authorization 시작 | `POST` | `/auth/oauth/{provider}/authorize` | anonymous 또는 active session |
| provider callback/session 완료 | `POST` | `/auth/oauth/{provider}/sessions` | authorization code/state |
| 현재 사용자에게 OAuth identity 연결 | `POST` | `/auth/oauth/{provider}/links` | active session |
| OAuth identity 목록 | `GET` | `/auth/oauth/identities` | active session |
| OAuth identity revoke | `DELETE` | `/auth/oauth/identities/{oauthIdentityId}` | active session |

## Wallet route

| 목적 | Method | Path | 요청 |
| --- | --- | --- | --- |
| wallet link challenge 발급 | `POST` | `/auth/wallets/challenges` | `walletAddress`, `chainId` |
| wallet link 완료 | `POST` | `/auth/wallets` | SIWE link message/signature |
| linked wallet 목록 | `GET` | `/auth/wallets` | active session |
| primary wallet 지정 | `PATCH` | `/auth/wallets/{walletId}/primary` | active session |
| linked wallet revoke | `DELETE` | `/auth/wallets/{walletId}` | active session |

## OAuth 응답 예시

```json
{
  "oauthIdentity": {
    "oauthIdentityId": "oauth_001",
    "provider": "google",
    "walletId": null,
    "linkedAt": "2026-05-24T10:00:00+09:00",
    "revokedAt": null
  }
}
```

`providerSubject`는 repository와 provider callback 검증 경계에서만 사용한다. API response, Postman expected fixture, log-friendly public payload에는 포함하지 않는다.

## Endpoint 상세

| Endpoint | 인증/권한 | 요청 | 성공 응답 | 오류 |
| --- | --- | --- | --- | --- |
| `POST /auth/challenges` | anonymous | JSON body: `walletAddress`, `domain`, optional `uri`, `chainId` | `201` SIWE challenge, `signingMessage`, `nonce`, `expiresAt`, CSRF metadata | `400 VALIDATION_ERROR` |
| `POST /auth/sessions` | anonymous, SIWE signature 필요 | JSON body: `walletAddress`, `message`, `signature`, optional `deviceId` | `200` `user`, redacted `session`, cookie transport `token`, `csrfToken`; access/refresh cookies는 header로 설정 | `400 VALIDATION_ERROR`, `401 INVALID_SIGNATURE`, `401 WALLET_MISMATCH`, `401 SIWE_MESSAGE_MISMATCH`, `409 EXPIRED_CHALLENGE`, `409 REUSED_NONCE` |
| `POST /auth/oauth/{provider}/authorize` | `mode=login`은 anonymous, `mode=link`는 active session | path `provider`, JSON body: `redirectUri`, `mode` | `201` `oauthAuthorization` with `authorizationUrl`, `state`, `mode`, `expiresAt`, `pkceRequired` | `400 VALIDATION_ERROR`, `400 OAUTH_PROVIDER_UNSUPPORTED`, `401 AUTHENTICATION_REQUIRED` |
| `POST /auth/oauth/{provider}/sessions` | anonymous callback completion | path `provider`, JSON body: `code`, `state`, `redirectUri`, optional `deviceId` | `200` `user`, redacted `session`, cookie transport `token`, public `oauthIdentity`, `authentication`, `csrfToken` | `400 VALIDATION_ERROR`, `400 OAUTH_PROVIDER_UNSUPPORTED`, `404 OAUTH_IDENTITY_NOT_LINKED` |
| `POST /auth/oauth/{provider}/links` | active session | path `provider`, JSON body: `code`, `state`, `redirectUri`, optional owned `walletId` | `201` public `oauthIdentity` | `400 VALIDATION_ERROR`, `400 OAUTH_PROVIDER_UNSUPPORTED`, `401 AUTHENTICATION_REQUIRED`, `404 WALLET_NOT_FOUND`, `409 OAUTH_IDENTITY_ALREADY_LINKED` |
| `GET /auth/oauth/identities` | active session | no body | `200` `oauthIdentities[]`; provider subject/token/email/profile dump 제외 | `401 AUTHENTICATION_REQUIRED` |
| `DELETE /auth/oauth/identities/{oauthIdentityId}` | active session, identity owner | path `oauthIdentityId` | `200` revoked public `oauthIdentity` with `revokedAt` | `401 AUTHENTICATION_REQUIRED`, `404 OAUTH_IDENTITY_NOT_FOUND`, `409 LAST_LOGIN_METHOD_REVOKE_DENIED` |
| `POST /auth/wallets/challenges` | active session | JSON body: `walletAddress`, `domain`, optional `uri`, `chainId` | `201` SIWE wallet-link challenge with `purpose=WALLET_LINK`, `targetUserId` | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `409 WALLET_ALREADY_LINKED` |
| `POST /auth/wallets` | active session, wallet-link SIWE signature 필요 | JSON body: `walletAddress`, `message`, `signature`, optional `walletType` | `201` `wallet` with `walletId`, `walletAddress`, `chainId`, `verificationStatus`, `primary`, `linkedAt` | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `401 INVALID_SIGNATURE`, `401 WALLET_MISMATCH`, `401 SIWE_MESSAGE_MISMATCH`, `409 WALLET_LINK_CHALLENGE_MISMATCH`, `409 WALLET_ALREADY_LINKED` |
| `GET /auth/wallets` | active session | no body | `200` `wallets[]`, revoked wallet은 audit 표시용으로 포함될 수 있음 | `401 AUTHENTICATION_REQUIRED` |
| `PATCH /auth/wallets/{walletId}/primary` | active session, wallet owner | path `walletId` | `200` updated `wallet`; same chain의 다른 active wallet은 primary 해제 | `401 AUTHENTICATION_REQUIRED`, `404 WALLET_NOT_FOUND`, `409 WALLET_NOT_ACTIVE` |
| `DELETE /auth/wallets/{walletId}` | active session, wallet owner | path `walletId` | `200` revoked `wallet` with `verificationStatus=REVOKED` | `401 AUTHENTICATION_REQUIRED`, `404 WALLET_NOT_FOUND`, `409 WALLET_NOT_ACTIVE`, `409 LAST_WALLET_REVOKE_DENIED` |
| `POST /auth/sessions/refresh` | refresh cookie/session context | browser는 empty body 가능; non-browser harness는 `sessionId` 모델 사용 가능 | `200` same shape as session login, access/refresh cookies rotate | `400 VALIDATION_ERROR`, `401 INVALID_SIGNATURE`, `409 EXPIRED_CHALLENGE` |
| `POST /auth/sessions/switch` | active session, target merchant/personal group membership | JSON body: `activeGroupId` | `200` same shape as session login, access/refresh cookies rotate with reduced active group claims | `400 VALIDATION_ERROR`, `403 AUTHORIZATION_ERROR` |
| `DELETE /auth/sessions` | active session | no JSON body; browser/public flow uses cookie/auth context, non-browser facade compatibility may pass `sessionId` internally | `200` revoked redacted `session` | `401 AUTHENTICATION_REQUIRED`, `404 SESSION_NOT_FOUND` |
| `GET /auth/me` | active session | optional local fallback query `userId` | `200` `user` with `userId`, primary `walletAddress`, `active`, `lastLoginAt` | `401 AUTHENTICATION_REQUIRED`, `404 USER_NOT_FOUND` |
| `GET /auth/me/profile` | active session | no body | `200` profile data such as optional `displayName`; email/locale/timezone은 저장하지 않음 | `401 AUTHENTICATION_REQUIRED`, `404 USER_NOT_FOUND` |
| `PATCH /auth/me/profile` | active session | JSON body: optional bounded `displayName` | `200` updated profile | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `404 USER_NOT_FOUND`, `409 DISPLAY_NAME_CONFLICT` |

## 요청 예시

SIWE challenge:

```json
{
  "walletAddress": "0x1111111111111111111111111111111111111111",
  "domain": "token-payments.local",
  "uri": "https://token-payments.local",
  "chainId": 1337
}
```

OAuth authorization:

```json
{
  "redirectUri": "https://token-payments.local/oauth/callback",
  "mode": "login"
}
```
