# CarMe 화면 API 매핑서

기준일: 2026-09-16  
기준 원본: `docs/submission/PG7반_P232_임채현_CarMe_API.yml`

아래 표는 현재 OpenAPI에 정의된 30개 operation만 담는다. 과거의 내 차량 수정, 삭제, 매뉴얼 상세 조회, `ingestions`, `archive` 경로는 포함하지 않는다.

## 매핑 원칙

- 화면 진입 시 API는 화면을 처음 렌더링할 때 호출한다.
- `GET /auth/me`는 access token을 받은 직후 호출해 현재 역할과 온보딩 완료 여부를 갱신한다.
- 연결 매뉴얼 조회는 채팅 세션 생성 직후 호출한다. 응답은 채팅 좌측의 연결 PDF 목록으로 표시한다.
- 공식 소스는 사용자에게 개별 원문을 나열하지 않는다. 관리자의 차량 카탈로그에서 준비된 보조 안내 건수와 갱신 결과만 표시한다.

| # | API | 화면 ID | 호출 시점과 화면 반영 |
|---:|---|---|---|
| 1 | `GET /health` | `SCR-AUTH-001` | 웹 앱 초기 렌더링 시 API 상태를 확인한다. 실패해도 로그인 진입은 유지한다. |
| 2 | `GET /auth/kakao/start` | `SCR-AUTH-001` | 카카오 로그인 버튼을 누르면 인가 화면으로 이동한다. |
| 3 | `GET /auth/kakao/callback` | `SCR-AUTH-001` | 카카오가 인가 코드를 전달하는 callback 경로다. 성공 시 콜백 화면으로 이동한다. |
| 4 | `POST /auth/access-token` | `SCR-AUTH-001` | 앱 진입 시 refresh cookie로 access token을 발급받는다. |
| 5 | `GET /auth/me` | `SCR-AUTH-001` | access token 발급 직후 현재 이름, 역할, 온보딩 완료 여부를 갱신한다. |
| 6 | `POST /auth/onboarding` | `SCR-AUTH-001` | 최초 로그인 역할 선택을 저장한다. |
| 7 | `POST /auth/logout` | `SCR-AUTH-001` | 상단 로그아웃 버튼에서 세션을 종료하고 로그인 화면으로 이동한다. |
| 8 | `GET /vehicle-catalog` | `SCR-VEHICLE-001` | 질문 가능한 차량의 제조사, 차종, 연식 드롭다운을 채운다. |
| 9 | `GET /vehicles` | `SCR-VEHICLE-001` | 현재 계정에 이미 선택된 차량을 확인해 중복 등록을 막는다. |
| 10 | `POST /vehicles` | `SCR-VEHICLE-001` | `매뉴얼로 질문하기` 선택 시 선택 차량을 계정에 처음 연결하거나 기존 연결을 재사용한다. |
| 11 | `POST /chat-sessions` | `SCR-CHAT-001` | 선택 차량으로 비영구 채팅 세션을 연다. |
| 12 | `GET /chat-sessions/{session_id}/manuals` | `SCR-CHAT-001` | 세션 생성 직후 현재 READY 연결 매뉴얼을 갱신해 PDF 목록에 표시한다. |
| 13 | `POST /chat-sessions/{session_id}/manuals/{manual_id}/download-url` | `SCR-CHAT-002` | PDF 열기 클릭 시 짧은 만료 다운로드 URL을 발급한다. |
| 14 | `POST /chat-sessions/{session_id}/messages` | `SCR-CHAT-002` | 질문을 전송하고 같은 채팅 레이아웃에서 근거 답변, 보완 질문, 근거 부족, 안전 안내 상태를 표시한다. |
| 15 | `DELETE /chat-sessions/{session_id}` | `SCR-CHAT-003` | 차량 다시 선택, 로그아웃, 화면 이탈 시 단기 기억을 삭제한다. |
| 16 | `GET /admin/vehicle-catalog` | `SCR-ADMIN-001` | 관리자 카탈로그 목록과 READY 매뉴얼 수를 표시한다. |
| 17 | `POST /admin/vehicle-catalog` | `SCR-ADMIN-001` | 제조사, 차종, 연식으로 차량 초안을 만든다. |
| 18 | `PATCH /admin/vehicle-catalog/{catalog_id}` | `SCR-ADMIN-001` | 초안 차량의 제조사, 차종, 연식을 수정한다. |
| 19 | `DELETE /admin/vehicle-catalog/{catalog_id}` | `SCR-ADMIN-001` | 초안 차량을 보관 처리한다. |
| 20 | `PATCH /admin/vehicle-catalog/{catalog_id}/official-manual-url` | `SCR-ADMIN-001` | 현대 공식 웹 매뉴얼 시작 URL을 등록 또는 수정한다. |
| 21 | `GET /admin/vehicle-catalog/{catalog_id}/official-sources` | `SCR-ADMIN-001` | 개별 원문은 노출하지 않고, 공식 보조 안내의 준비 건수만 표시한다. |
| 22 | `POST /admin/vehicle-catalog/{catalog_id}/official-sources/sync` | `SCR-ADMIN-001` | 관리자 버튼으로 공식 보조 안내를 갱신하고 완료 건수만 알린다. |
| 23 | `GET /admin/manuals` | `SCR-ADMIN-002`, `SCR-ADMIN-003` | 매뉴얼 목록, 상태, 페이지 수, 임베딩 진행률을 표시한다. |
| 24 | `POST /admin/manuals` | `SCR-ADMIN-002` | PDF 메타데이터와 적용 차량으로 매뉴얼 초안을 만든다. |
| 25 | `PATCH /admin/manuals/{manual_id}` | `SCR-ADMIN-002` | 수정 가능한 상태의 제목, 종류, 언어, 적용 차량, 대표 여부를 변경한다. |
| 26 | `DELETE /admin/manuals/{manual_id}` | `SCR-ADMIN-003` | 더 이상 쓰지 않는 매뉴얼을 보관 처리한다. |
| 27 | `POST /admin/manuals/{manual_id}/upload-url` | `SCR-ADMIN-002` | 브라우저가 PDF를 올릴 수 있는 짧은 만료 URL을 받는다. |
| 28 | `POST /admin/manuals/{manual_id}/upload-complete` | `SCR-ADMIN-002` | PDF 전송 뒤 해시, 크기, 쪽수 검증과 UPLOADED 전환을 요청한다. |
| 29 | `POST /admin/manuals/{manual_id}/prepare-rag-test` | `SCR-ADMIN-003` | UPLOADED PDF를 추출, 청킹하고 비동기 임베딩을 시작한다. |
| 30 | `POST /admin/manuals/{manual_id}/rebuild-rag-index` | `SCR-ADMIN-003` | READY PDF를 최신 검색 규칙으로 다시 추출, 청킹, 임베딩한다. |

## 점검 결과

- 최신 OpenAPI operation: 30개
- 화면 또는 화면 공통 동작에 매핑된 operation: 30개
- 미사용 operation: 없음
- API가 화면에 보이는 방식: 공식 소스 API만 개별 원문 대신 운영 상태와 건수로 축약해 표시한다.
