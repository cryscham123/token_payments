# 인증과 OAuth

이 페이지는 SIWE login, session, wallet link, current user profile, OAuth provider-subject identity API를 GitBook에서 읽기 좋게 묶은 요약이다. 전체 요청/응답 예시는 [API 명세](../API_SPEC.md)의 Auth 섹션을 기준으로 한다.

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
