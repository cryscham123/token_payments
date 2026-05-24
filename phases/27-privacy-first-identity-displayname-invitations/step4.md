# Step 4: docs-postman-and-verification

## 작업

문서와 Postman 계약을 새 API surface에 맞춘 뒤 전체 검증한다.

1. `docs/API_SPEC.md`, `docs/DOMAIN_MODEL.md`, `README.md`, `app/README.md`의 user profile/privacy/OAuth/invitation 설명을 갱신한다.
2. Postman collection의 merchant invitation body에서 `targetEmail` 대신 `targetDisplayName` 또는 `targetUserId`를 사용한다.
3. route manifest count와 expected fixture를 새 surface에 맞춘다.
4. phase index summary를 실제 완료 내용으로 갱신한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts -q
python3 scripts/validate_phases.py
```
