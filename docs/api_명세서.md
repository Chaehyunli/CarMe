# CarMe API 명세서

> 버전: v1 · Base URL: `/api/v1` · 형식: JSON (`application/json`)

## Swagger / OpenAPI

개발 서버에서 아래 문서를 제공한다.

| 문서 | 경로 |
|---|---|
| Swagger UI | `GET /docs` |
| ReDoc | `GET /redoc` |
| OpenAPI JSON | `GET /api/v1/openapi.json` |

Swagger UI의 **Authorize** 버튼에는 `POST /auth/access-token`에서 발급받은 access JWT만 입력한다. 이후 구현되는 보호 endpoint에는 OpenAPI의 `bearerAuth` security requirement를 명시한다.

## 1. 공통 규칙

### 인증

- 보호 API는 `Authorization: Bearer {access_jwt}`가 필요하다.
- access JWT는 짧게 사용하고 frontend 메모리에만 보관한다.
- refresh token은 backend가 `HttpOnly`, `Secure`(운영), `SameSite=Lax` cookie로 보관한다. DB에는 원문이 아닌 해시만 저장한다.
- OAuth callback과 refresh API는 refresh cookie를 사용한다. 나머지 API는 access JWT를 사용한다.
- refresh·logout 요청은 `Origin` 검증과 CSRF 방어를 적용한다. 운영에서 frontend와 API를 다른 site로 분리하면 `SameSite=None; Secure` 및 명시적 CSRF token 정책으로 전환한다.
- 인증 실패는 `401`, 다른 사용자의 리소스 접근은 리소스 존재 여부와 무관하게 `403`을 반환한다.
- 역할은 `USER`와 `ADMIN`이다. `/admin/*`은 `ADMIN` claim과 DB의 활성 사용자 상태를 모두 확인한다. 역할을 변경하는 공개 API는 없다.

### 시간·식별자·페이지

- 모든 식별자는 UUID 문자열이다.
- 모든 시간은 ISO-8601 UTC 문자열이다.
- `pdf_page_number`는 PDF 뷰어의 1부터 시작하는 물리 페이지다.
- `printed_page_number`는 매뉴얼 본문 쪽수이며 없을 수 있다.

### 공통 오류 응답

```json
{
  "error": {
    "code": "MANUAL_NOT_READY",
    "message": "선택한 차량의 매뉴얼을 아직 준비하고 있습니다.",
    "request_id": "uuid"
  }
}
```

| HTTP | code | 의미 |
|---|---|---|
| 400 | `VALIDATION_ERROR` | 형식·값 검증 실패 |
| 401 | `UNAUTHENTICATED` | access JWT가 없거나 유효하지 않음 |
| 403 | `FORBIDDEN` | 소유자가 아닌 리소스 접근 |
| 409 | `DUPLICATE_VEHICLE`, `IDEMPOTENCY_CONFLICT`, `CATALOG_NOT_PUBLISHABLE`, `MANUAL_STATE_CONFLICT` | 중복 요청 또는 공개·상태 전이 조건 불충족 |
| 404 | `NOT_FOUND` | 공개적으로 존재를 확인해도 되는 리소스가 없음 |
| 422 | `UNSUPPORTED_VEHICLE`, `MANUAL_NOT_READY` | 지원되지 않거나 준비되지 않은 차량 |
| 429 | `RATE_LIMITED` | 로그인·질문 요청 제한 초과 |
| 500 | `INTERNAL_ERROR` | 내부 오류; 상세 원인·자격증명은 노출하지 않음 |

## 2. 인증 API

### `GET /auth/kakao/start`

카카오 인가 화면으로 `302` redirect 한다. `state`는 서버가 생성·검증한다.

### `GET /auth/kakao/callback?code={code}&state={state}`

카카오 인가 코드를 교환한다. 신규 사용자는 `kakao_subject` 기준으로 생성하고, refresh cookie를 설정한 뒤 frontend의 `/auth/callback?login=success`로 `302` redirect 한다. 실패 시 `/login?error={code}`로 redirect 한다.

### `POST /auth/access-token`

refresh cookie를 검증해 새 access JWT를 발급한다.

**200 response**

```json
{
  "access_token": "jwt",
  "token_type": "Bearer",
  "expires_in": 1800,
  "user": {
    "id": "uuid",
    "display_name": "사용자",
    "role": "USER"
  }
}
```

### `POST /auth/logout`

현재 refresh token을 폐기하고 cookie를 삭제한다. 응답은 `204 No Content`다.

### `GET /auth/me`

현재 로그인 사용자를 반환한다.

```json
{
  "id": "uuid",
  "display_name": "사용자",
  "role": "USER",
  "created_at": "2026-09-14T00:00:00Z"
}
```

## 3. 차량 카탈로그와 내 차량 API

차량 선택값은 세부 옵션이 아닌 **차종·연식 단위**다. 초기 MVP에는 트림·옵션·하이브리드 등의 별도 모델 구분을 받지 않는다.

### `GET /vehicle-catalog`

`ACTIVE`이며 `READY` 기본 매뉴얼이 하나 이상 연결된 등록 가능 차량을 반환한다.

```json
{
  "items": [
    {
      "catalog_id": "uuid",
      "manufacturer": "HYUNDAI",
      "model_name": "아반떼",
      "model_year": 2025,
      "display_name": "아반떼 2025"
    }
  ]
}
```

### `POST /vehicles`

**인증 필요.** 내 차량을 등록한다.

```json
{
  "catalog_id": "uuid",
  "nickname": "우리 차"
}
```

**201 response**

```json
{
  "id": "uuid",
  "nickname": "우리 차",
  "catalog": {
    "id": "uuid",
    "model_name": "아반떼",
    "model_year": 2025,
    "display_name": "아반떼 2025"
  },
  "manual_status": "READY",
  "created_at": "2026-09-14T00:00:00Z"
}
```

### `GET /vehicles`

**인증 필요.** 현재 사용자의 차량 목록을 반환한다.

### `GET /vehicles/{vehicleId}`

**인증 필요.** 소유 차량 하나를 반환한다.

### `PATCH /vehicles/{vehicleId}`

**인증 필요.** 별칭만 수정한다.

```json
{ "nickname": "아빠 차" }
```

### `DELETE /vehicles/{vehicleId}`

**인증 필요.** 차량 삭제 정책에 따라 soft delete 한다. 연결 상담 이력은 즉시 제거하지 않고, 계정·보존 정책에 따라 읽기 불가 상태로 전환한다. 응답은 `204 No Content`다.

## 4. 상담 API

### `POST /conversations`

**인증 필요.** 선택 차량 기준의 새 상담을 시작한다.

```json
{ "vehicle_id": "uuid" }
```

질문 없이 생성할 수 있으며, 현재 차량 카탈로그에 연결된 `READY` 문서 목록을 반환한다. 상세 흐름은 [RAG 검색 및 근거 응답 상세 설계](./RAG_검색_및_근거응답_상세설계.md)를 따른다.

**201 response**

```json
{
  "id": "uuid",
  "vehicle_id": "uuid",
  "status": "OPEN",
  "manuals": [{
    "id": "uuid",
    "title": "선택 차량 취급설명서",
    "manual_type": "OWNER_MANUAL",
    "pdf_page_count": 444,
    "is_primary": true,
    "download_available": true
  }],
  "started_at": "2026-09-14T00:00:00Z"
}
```

### `GET /conversations/{conversationId}/manuals`

**인증 필요.** 현재 차량 카탈로그에 적용되는 `READY` 매뉴얼 목록을 반환한다.

### `POST /conversations/{conversationId}/manuals/{manualId}/download-url`

**인증 필요.** 해당 대화에 연결된 매뉴얼의 private S3 PDF에 대한 짧은 만료 download URL을 발급한다. 대화 또는 문서가 요청 사용자에게 속하지 않으면 `403`을 반환한다.

### `GET /vehicles/{vehicleId}/conversations?cursor={cursor}&limit=20`

**인증 필요.** 차량별 상담 이력을 최신순으로 반환한다.

```json
{
  "items": [{
    "id": "uuid",
    "status": "OPEN",
    "last_result_status": "GROUNDED",
    "last_message_preview": "에어컨이 약해요",
    "updated_at": "2026-09-14T00:00:00Z"
  }],
  "next_cursor": null
}
```

### `GET /conversations/{conversationId}`

**인증 필요.** 대화와 근거 카드를 반환한다. 이력용 조회이므로 RAG를 재실행하지 않는다.

### `POST /conversations/{conversationId}/messages`

**인증 필요.** 질문을 저장하고 계층형 RAG를 실행한다. 같은 버튼을 두 번 눌러도 중복 답변이 생성되지 않도록 `Idempotency-Key` header를 권장한다.

**request**

```json
{
  "content": "내비게이션 화면이 켜지지 않아요.",
  "category": "공조·편의"
}
```

`category`는 선택 사항이며 검색 범위를 제한하지 않는다. `content`는 1~1,000자다.

**`GROUNDED` response — 201**

```json
{
  "question_message_id": "uuid",
  "answer_message_id": "uuid",
  "result_status": "GROUNDED",
  "answer": "매뉴얼의 안내에 따라 ...",
  "citations": [{
    "id": "uuid",
    "manual_title": "아반떼 2025 취급설명서",
    "pdf_page_number": 87,
    "printed_page_number": "5-23",
    "quote_text": "원문에서 추출한 인용문"
  }],
  "clarifying_question": null,
  "escalation": null
}
```

**근거 부족·모호·안전 전환 response — 201**

```json
{
  "question_message_id": "uuid",
  "answer_message_id": "uuid",
  "result_status": "INSUFFICIENT_EVIDENCE",
  "answer": null,
  "citations": [],
  "clarifying_question": null,
  "escalation": {
    "type": "CUSTOMER_SUPPORT",
    "title": "매뉴얼에서 확인하지 못했어요.",
    "message": "공식 고객 지원 채널에서 확인해 주세요.",
    "phone": null,
    "url": null
  }
}
```

| `result_status` | 필수 값 | 금지 값 |
|---|---|---|
| `GROUNDED` | `answer`, 인용 1개 이상 | 근거 없는 조치 |
| `AMBIGUOUS` | `clarifying_question` | 해결책 단정 |
| `INSUFFICIENT_EVIDENCE` | `escalation` | `answer`에 추정 해결책 |
| `SAFETY_ESCALATION` | 우선 안전 `escalation` | 일반 RAG 답변 |

### `POST /citations/{citationId}/document-url`

**인증 필요.** citation이 속한 차량·대화의 소유자에게만 private PDF의 짧은 만료 URL을 발급한다.

**200 response**

```json
{
  "url": "https://s3.example.com/...signed...#page=87",
  "expires_at": "2026-09-14T00:05:00Z",
  "pdf_page_number": 87
}
```

## 5. 사용자 삭제 API

### `DELETE /users/me`

**인증 필요.** 계정 삭제 요청을 접수한다. refresh token을 폐기하고 로그인 세션을 종료한다. 차량·상담 이력·백업 삭제는 제품 보존 정책의 기한 안에 비동기 처리한다. 응답은 `202 Accepted`다.

## 6. 관리자 카탈로그·매뉴얼 API — 초기 MVP

모든 endpoint는 **`ADMIN` 권한 필요**다. 관리 화면에는 `아반떼 2025` 같은 표시명만 반환하며 내부 코드·object key·bucket은 반환하지 않는다. 초기에는 변경 이력을 별도 DB에 쌓지 않고 구조화 애플리케이션 로그에 남긴다.

### 상태와 공개 조건

```text
차량 카탈로그: DRAFT → ACTIVE → ARCHIVED
매뉴얼:         DRAFT → UPLOADED → INDEXING → READY → ARCHIVED
                                  └──────→ FAILED → UPLOADED
```

`ACTIVE` 전환은 연결된 기본(`is_primary = true`) 매뉴얼이 하나이고 그 상태가 `READY`일 때만 허용한다. 초기에는 평가 결과 테이블을 만들지 않는다. 적재 후 정해 둔 평가 질문을 수동/스크립트로 확인한다.

### `GET /admin/vehicle-catalog?status={status}&cursor={cursor}`

차량 카탈로그 목록을 반환한다.

```json
{
  "items": [{
    "id": "uuid",
    "manufacturer": "HYUNDAI",
    "model_name": "아반떼",
    "model_year": 2025,
    "display_name": "아반떼 2025",
    "status": "DRAFT",
    "ready_manual_count": 0
  }],
  "next_cursor": null
}
```

### `POST /admin/vehicle-catalog`

차종·연식 한 행을 `DRAFT`로 만든다. `display_name`은 서버가 생성한다.

```json
{
  "manufacturer": "HYUNDAI",
  "model_name": "아반떼",
  "model_year": 2025
}
```

동일 제조사·차종·연식이면 `409`다.

### `GET /admin/vehicle-catalog/{catalogId}` / `PATCH /admin/vehicle-catalog/{catalogId}`

상세에는 연결된 매뉴얼의 제목·문서 종류·상태만 담는다. `PATCH`는 `DRAFT`/`ARCHIVED` 상태와 표시용 이름을 수정하거나, 공개 조건을 만족할 때 `ACTIVE`로 전환한다.

```json
{ "status": "ACTIVE" }
```

### `POST /admin/manuals`

PDF 업로드 전에 매뉴얼 초안을 만들고 적용 차량을 연결한다.

```json
{
  "title": "아반떼 2025 취급설명서",
  "manual_type": "OWNER_MANUAL",
  "locale": "ko-KR",
  "source_url": "https://source.example/manual",
  "catalog_ids": ["uuid"],
  "is_primary_for_catalog_ids": ["uuid"]
}
```

### `POST /admin/manuals/{manualId}/upload-url`

`DRAFT` 매뉴얼 하나에 대해 브라우저 직접 업로드용 1회성 private S3 `PUT` presigned URL을 발급한다. 파일명, PDF MIME, 크기, 예상 SHA-256을 검증한다. 응답에는 URL, 필요한 `Content-Type`, 만료 시각만 담고 object key·bucket은 담지 않는다.

### `POST /admin/manuals/{manualId}/upload-complete`

서버가 object 존재·MIME·크기·SHA-256·PDF 페이지 수를 재검증한 뒤 `UPLOADED`로 전환하고 worker를 요청한다. 응답은 `202 Accepted`다. 실패하면 `FAILED`와 안전한 오류 코드만 반환한다.

### `GET /admin/manuals/{manualId}` / `POST /admin/manuals/{manualId}/ingestions`

매뉴얼 메타데이터, 사람이 읽는 적용 차량명, 현재 상태, `ingestion_error`를 조회한다. 적재 실패는 재시도할 수 있다. `READY` 문서는 덮어쓰지 않으며 개정 PDF는 새 매뉴얼로 만든다.

### `POST /admin/manuals/{manualId}/archive`

새 등록·새 상담의 적용 대상에서 제외한다. 기존 답변은 `citation`에 저장한 매뉴얼·페이지 정보를 계속 표시한다.

## 7. worker 작업

관리자 API는 요청과 상태 조회만 담당한다. PDF 추출과 임베딩은 worker/CLI가 수행한다.

1. 업로드 object 검증
2. 목차 섹션과 페이지 번호가 포함된 청크 생성
3. 임베딩 생성과 `manual_chunk` 저장
4. 성공 시 `manual.status = READY`, 실패 시 `FAILED`와 `ingestion_error` 저장
