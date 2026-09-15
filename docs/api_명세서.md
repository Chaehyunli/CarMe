# CarMe API 명세서

> 버전: v1 · Base URL: `/api/v1` · 형식: JSON (`application/json`)

## Swagger / OpenAPI

| 문서 | 경로 |
|---|---|
| Swagger UI | `GET /docs` |
| ReDoc | `GET /redoc` |
| OpenAPI JSON | `GET /api/v1/openapi.json` |

보호 endpoint는 OpenAPI `bearerAuth`를 선언한다. Swagger UI의 Authorize에는 `POST /auth/access-token`이 발급한 access JWT를 넣는다.

## 1. 공통 규칙

- 보호 API는 `Authorization: Bearer {access_jwt}`가 필요하다. access JWT는 frontend 메모리에만 둔다.
- refresh token은 `HttpOnly`, 운영에서는 `Secure`, 기본 `SameSite=Lax` cookie로 보관하고 DB에는 해시만 저장한다.
- OAuth callback과 refresh API는 cookie를 사용한다. refresh/logout에는 Origin 검증과 CSRF 방어를 적용한다.
- 인증 실패는 `401`, 타 사용자 리소스는 존재 여부와 무관하게 `403`이다.
- 역할은 `USER`/`ADMIN`이며 `/admin/*`은 JWT claim과 DB 활성 상태를 함께 확인한다.
- UUID와 UTC ISO-8601 시간을 쓴다. `pdf_page_number`는 PDF 물리 페이지(1부터), `printed_page_number`는 본문 쪽수다.

```json
{
  "error": {
    "code": "CHAT_SESSION_EXPIRED",
    "message": "채팅 세션이 종료되었습니다. 새로 시작해 주세요.",
    "request_id": "uuid"
  }
}
```

| HTTP | code | 의미 |
|---|---|---|
| 400 | `VALIDATION_ERROR` | 형식·값 검증 실패 |
| 401 | `UNAUTHENTICATED` | JWT가 없거나 유효하지 않음 |
| 403 | `FORBIDDEN` | 소유자가 아닌 리소스 접근 |
| 404 | `NOT_FOUND` | 공개적으로 확인해도 되는 리소스 없음 |
| 409 | `DUPLICATE_VEHICLE`, `CATALOG_NOT_PUBLISHABLE`, `MANUAL_STATE_CONFLICT` | 중복·상태 전이 조건 불충족 |
| 410 | `CHAT_SESSION_EXPIRED` | 메모리 세션이 종료·만료·재시작으로 사라짐 |
| 422 | `UNSUPPORTED_VEHICLE`, `MANUAL_NOT_READY` | 지원되지 않거나 준비되지 않은 차량 |
| 429 | `RATE_LIMITED` | 로그인·질문 제한 초과 |

## 2. 인증 API

### `GET /auth/kakao/start`

카카오 인가 화면으로 `302` redirect 한다. 서버가 생성·검증한 `state`를 사용한다.

### `GET /auth/kakao/callback?code={code}&state={state}`

**backend callback URL**이다. 인가 코드를 교환해 `kakao_subject` 기준으로 사용자를 생성/조회하고 refresh cookie를 설정한 뒤, frontend `FRONTEND_LOGIN_CALLBACK_URL`의 `/auth/callback?login=success`로 `302` redirect 한다. 실패 시 frontend `/login?error={code}`로 redirect 한다.

### `POST /auth/access-token`

refresh cookie를 검증해 access JWT를 발급한다.

```json
{
  "access_token": "jwt",
  "token_type": "Bearer",
  "expires_in": 1800,
  "user": {"id": "uuid", "display_name": "사용자", "role": "USER"}
}
```

### `POST /auth/logout` / `GET /auth/me`

logout은 refresh token을 폐기·cookie 삭제하고 `204`를 반환한다. `GET /auth/me`는 현재 사용자 id, display_name, role, created_at을 반환한다.

## 3. 차량 카탈로그와 내 차량

초기 MVP 차량 선택값은 **모델 + 연식**만이다. 트림·옵션·하이브리드 등은 받지 않는다.

### `GET /vehicle-catalog`

`ACTIVE`이면서 기본 `READY` 매뉴얼이 연결된 차량만 반환한다.

```json
{"items": [{"catalog_id": "uuid", "manufacturer": "HYUNDAI", "model_name": "아반떼", "model_year": 2025, "display_name": "아반떼 2025"}]}
```

### `POST /vehicles`

**인증 필요.** `{ "catalog_id": "uuid", "nickname": "우리 차" }`로 내 차량을 만든다. 같은 사용자의 같은 catalog는 `409 DUPLICATE_VEHICLE`이다.

### `GET /vehicles` / `GET /vehicles/{vehicleId}` / `PATCH /vehicles/{vehicleId}` / `DELETE /vehicles/{vehicleId}`

소유자만 조회·수정·삭제한다. PATCH는 별칭만 바꾼다. DELETE는 `vehicle.deleted_at`을 설정하고 `204`를 반환한다. 이 차량을 참조하는 살아 있는 메모리 세션은 즉시 제거한다.

## 4. 단기 채팅 세션 API

대화·질문·답변·citation은 영구 저장하지 않는다. `session_id`는 API 프로세스 RAM에서만 유효하며 화면 이탈의 `DELETE`, 30분 idle TTL, API 재시작/배포에서 사라진다.

### `POST /chat-sessions`

**인증 필요.** 질문 없이 선택 차량의 채팅 세션을 시작한다.

```json
{ "vehicle_id": "uuid" }
```

```json
{
  "id": "session-uuid",
  "vehicle_id": "uuid",
  "expires_at": "2026-09-15T00:30:00Z",
  "manuals": [{
    "id": "manual-uuid", "title": "아반떼 2025 취급설명서",
    "manual_type": "OWNER_MANUAL", "pdf_page_count": 444,
    "is_primary": true, "download_available": true
  }]
}
```

차량 소유권, `ACTIVE` 카탈로그, 현재 기본 `READY` 매뉴얼을 검증한다. 이 조건이 아니면 세션을 만들지 않는다.

### `GET /chat-sessions/{sessionId}/manuals`

**인증 필요.** 현재 적용되는 `READY` 매뉴얼 목록을 반환하고 idle TTL을 연장한다.

### `POST /chat-sessions/{sessionId}/manuals/{manualId}/download-url`

**인증 필요.** 세션 소유자만 호출한다. 해당 차량에 현재 적용되고 `READY`인 매뉴얼일 때만 5분 만료 private PDF URL을 발급한다.

```json
{"url": "https://signed.example/...", "filename": "avante_2025_ko.pdf", "expires_at": "2026-09-15T00:05:00Z"}
```

### `POST /chat-sessions/{sessionId}/messages`

**인증 필요.** 메모리 history에 현재 질문을 넣고, 매 요청마다 최신 `READY` 매뉴얼을 결정하여 계층형 RAG를 실행한다. `content`는 1–1,000자, `category`는 선택 사항이며 검색 강제 필터가 아니다.

```json
{"content": "내비게이션 화면이 켜지지 않아요.", "category": "공조·편의"}
```

```json
{
  "result_status": "GROUNDED",
  "answer": "매뉴얼의 안내에 따라 ...",
  "citations": [{
    "manual_id": "manual-uuid",
    "manual_title": "아반떼 2025 취급설명서",
    "pdf_page_number": 87,
    "printed_page_number": "5-23",
    "quote_text": "원문에서 검증한 짧은 인용문"
  }],
  "clarifying_question": null,
  "escalation": null,
  "expires_at": "2026-09-15T00:30:00Z"
}
```

| `result_status` | 필수 값 | citation |
|---|---|---|
| `GROUNDED` | `answer` | 1개 이상 |
| `AMBIGUOUS` | `clarifying_question` | 없음 |
| `INSUFFICIENT_EVIDENCE` | `escalation` | 없음 |
| `SAFETY_ESCALATION` | 정적 안전 `escalation` | **없음** |

### `DELETE /chat-sessions/{sessionId}`

**인증 필요.** 세션과 in-memory history를 즉시 파기하고 `204`를 반환한다. 이미 TTL/재시작으로 없어진 세션도 사용자 화면 이탈을 단순하게 처리할 수 있도록 `204`를 반환한다.

과거 대화 목록, 과거 메시지 상세, citation ID 조회 API는 제공하지 않는다.

## 5. 사용자 삭제 API

### `DELETE /users/me`

**인증 필요.** refresh token을 폐기하고 해당 사용자의 살아 있는 메모리 채팅 세션을 제거한다. 차량·계정의 soft delete 및 백업 삭제는 제품 보존 정책에 따라 비동기 처리하며 `202 Accepted`를 반환한다.

## 6. 관리자 카탈로그·매뉴얼 API

모든 endpoint는 `ADMIN` 권한이 필요하다. UI 응답에는 `아반떼 2025` 같은 표시명만 포함하며 object key, bucket, 장기 자격증명은 포함하지 않는다. 초기 변경 이력은 별도 DB 대신 구조화 로그에 남긴다.

```text
차량 카탈로그: DRAFT → ACTIVE → ARCHIVED
매뉴얼:         DRAFT → UPLOADED → INDEXING → READY → ARCHIVED
                                  └──────→ FAILED → UPLOADED
```

`READY`는 파일 검증·추출·청킹·임베딩·매뉴얼 평가 세트 통과까지 끝난 상태다. `ACTIVE` 전환에는 `is_primary=true`인 `READY` 매뉴얼이 정확히 하나 필요하다.

### 차량 카탈로그

- `GET /admin/vehicle-catalog?status=&cursor=`: 목록(모델명·연식·표시명·상태·ready_manual_count)
- `POST /admin/vehicle-catalog`: `{manufacturer, model_name, model_year}`로 `DRAFT` 생성. 표시명은 서버 생성, 동일 조합은 `409`.
- `GET/PATCH /admin/vehicle-catalog/{catalogId}`: 상세/수정 및 조건 충족 시 `ACTIVE` 공개.

### 매뉴얼

- `POST /admin/manuals`: 제목, 종류, 언어, 출처, 적용 `catalog_ids`, primary 대상 목록으로 `DRAFT` 생성.
- `POST /admin/manuals/{manualId}/upload-url`: 짧은 만료의 범위 제한 presigned PUT URL 발급. 고유 staging key, 예상 MIME/크기/해시를 서버에 기록한다. presigned URL 자체를 “한 번만 사용 가능”하다고 가정하지 않는다.
- `POST /admin/manuals/{manualId}/upload-complete`: object 존재, MIME, 크기, SHA-256, PDF 쪽수를 서버가 재검증하고 `UPLOADED` 후 worker를 요청한다.
- `GET /admin/manuals/{manualId}` / `POST /admin/manuals/{manualId}/ingestions`: 상태·안전한 오류·사람이 읽는 적용 차량명 조회, 재적재 요청.
- `POST /admin/manuals/{manualId}/archive`: 신규 세션/다운로드 대상에서 제외한다. 이미 진행 중인 메모리 세션도 다음 요청 때 현재 상태로 다시 판정한다.

직접 브라우저 업로드를 허용하는 bucket은 admin frontend origin만 허용하는 CORS와 private bucket 정책을 별도로 설정한다.

## 7. Worker 작업

1. staging object를 재검증하고 최종 private object로 확정한다.
2. 페이지 텍스트/OCR, 목차 섹션, 페이지 청크를 생성한다.
3. 임베딩과 `manual_section`/`manual_chunk`를 저장한다.
4. 매뉴얼 평가 세트를 실행·기록한다.
5. 기준 통과 시 `READY`, 실패 시 `FAILED`와 안전한 `ingestion_error`를 저장한다.
