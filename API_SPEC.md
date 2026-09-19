# 두드리 API 명세 초안

- 기준 문서: [blueprint.md](./blueprint.md) 우선, [ERD.md](./ERD.md) 차순위
- 현행 구현: [alumni-coffeechat](https://github.com/schmedicalit24-star/alumni-coffeechat/tree/110fbad0f382e38c245b9cfdeb21ddcb9d114c88) 커밋 `110fbad`
- 문서 상태: 목표 계약 제안. API 코드 및 DB 변경 전 검토용
- 범위: 회원 인증부터 프로필·외부 자료·AI 승인·매칭·프로젝트·커피챗·신뢰·포트폴리오까지. 확정되지 않은 운영 정책은 별도 표시

## 1. 계약 원칙

| 항목 | 목표 계약 |
| --- | --- |
| 기본 경로 | `/api/v1` 제안. 현행 `/api`와 ID·요청 본문이 달라 병행 필요. 전환 시점은 [작성자 확인 필요] |
| ID | ERD 기준 UUID 문자열. 현행 정수 ID의 이관·매핑 방식은 [작성자 확인 필요] |
| 인증 | 로그인 후 `Authorization: Bearer <access_token>`. 대학 목록·인증 시작/확인·게시된 포트폴리오 외에는 인증 필요 |
| 시간 | ISO 8601, 타임존 포함. 응답은 UTC 사용 |
| 응답 | 단건은 객체, 목록은 `{ "items": [...], "next_cursor": null }`. 현행 API의 배열 응답과 구분 |
| 오류 | `{ "detail": "오류 설명" }`. 입력 오류 422, 미인증 401, 권한 없음 403, 없음 404, 상태 충돌 409 |
| 페이지 | 목록 조회 시 `limit`·`cursor`. 최대 건수와 정렬 기본값은 구현 시 확정 |
| 쓰기 재시도 | 예약·결제 등 중복 실행 피해가 있는 요청에는 `Idempotency-Key` 적용. 키 보관 기간은 [작성자 확인 필요] |
| 공개 범위 | 비공개 사실은 본인 조회와 내부 매칭에만 사용. 타인 프로필·추천 이유·포트폴리오 생성 입력에서 제외 |
| AI 결과 | 제안과 확정 사실을 분리. 사용자의 승인·수정 전에는 공개·매칭 반영 금지 |

`/api/v1` 경로는 아래 목표 계약의 제안 경로. 현행 `/api`의 응답 구조나 권한을 그대로 승인한 의미 아님. 표의 "현행 확장"은 유사 기능이 존재한다는 뜻이며, 목표 경로가 구현됐다는 뜻이 아님. 개발 순서와 무관하게 엔드포인트의 권한·상태 전이·응답 필터를 함께 구현할 필요.

### 현행 API와 목표 계약 대응

| 현행 경로 | 현행 기능 | 목표 처리 |
| --- | --- | --- |
| `GET /` | 상태 확인 | 유지. 업무 API 밖 |
| `POST /api/auth/verify-email` | 학교 메일 링크 발송 | `POST /api/v1/auth/school-email-verifications`로 확장. 선택 학교와 이메일 도메인 대조 |
| `GET /api/auth/verify-email/confirm` | 링크 확인·토큰 발급 | `GET /api/v1/auth/school-email-verifications/confirm`. 학교 메일 확인과 학적 자격 구분 |
| `POST /api/auth/verify-graduate` | 졸업생 수동 신청 | 운영 정책 확정 전 목표 계약 보류 |
| `PUT /api/auth/verify-graduate/{user_id}/approve` | 공개 승인 API | 공개 접근 차단. 운영자 권한·증빙 정책 확정 후 재설계 |
| `GET /api/users/me` / `PUT /api/users/me` | 내 프로필 조회·수정 | `GET /api/v1/me` / `PATCH /api/v1/me` |
| `GET /api/users/{user_id}` | 타인 프로필 조회 | `GET /api/v1/users/{user_id}`. 공개 필드만 반환 |
| `POST /api/users/me/careers` | 회사 경력 추가 | `POST /api/v1/me/career-events`. 활동·프로젝트·인턴까지 확장 |
| `PUT /api/users/me/opt-in` | 멘토 주제 태그 교체 | `PUT /api/v1/me/tags` 및 `PATCH /api/v1/me/preferences`로 분리 |
| `GET /api/users/mentors/search` | 열린 태그 기준 탐색 | `POST /api/v1/search/users`. 목적·필터·추천 이유 추가 |
| `POST /api/questions` / `GET /api/questions/{sent,received}` / `PUT /api/questions/{id}/answer` / `POST /api/questions/{id}/convert` | 비동기 Q&A와 커피챗 전환 | 현행 추가 기능. `ERD.md`에는 질문 엔티티 없음. 유지 여부 결정 시 ERD에 질문·전환 관계 추가 필요 |
| `POST /api/coffee-chats` / `GET /api/coffee-chats/{sent,received}` | 요청 생성·목록 | 구조화된 요청·커서 목록으로 확장 |
| `PUT /api/coffee-chats/{chat_id}/status` | 누구든 임의 상태 변경 가능 | 사용 중단 대상. 수신자 수락·거절, 예약·완료 흐름을 별도 행위 API로 분리 |

## 2. 회원·학교·인증

ERD: `USERS`, `PROFILES`, `UNIVERSITIES`, `UNIVERSITY_DOMAINS`, `SCHOOL_AFFILIATIONS`, `EMAIL_VERIFICATIONS`. 초기 지원 학교는 국민대학교·숭실대학교·순천향대학교. 학교 이메일 인증은 메일 접근 증명. `enrollment_status`는 사용자 입력이며 재학·졸업 자격의 자동 검증 결과로 표기하지 않음.

| 방법·경로 | 권한 | 요청 핵심 필드 → 응답 | 상태 |
| --- | --- | --- | --- |
| `GET /api/v1/universities` | 공개 | 지원 대학 목록, `id`·`name` | 신규 |
| `GET /api/v1/universities/{id}/domains` | 공개 | 허용 도메인 목록 | 신규 |
| `POST /api/v1/auth/school-email-verifications` | 공개 | `name`, `email`, `university_id`, `enrollment_status`, `department?`, `entry_year?` → 발송 접수 | 현행 확장 |
| `GET /api/v1/auth/school-email-verifications/confirm?token=…` | 링크 소지자 | 토큰 확인 → 계정 인증 기록, 로그인 토큰 | 현행 확장 |
| `POST /api/v1/auth/login-links` | 공개 | `email` → 로그인 링크 발송 접수 | 신규 |
| `GET /api/v1/auth/login-links/confirm?token=…` | 링크 소지자 | 유효한 링크 확인 → 로그인 토큰 | 신규 |
| `POST /api/v1/auth/company-email-verifications` | 본인 | `email`, `company_name` → 발송 접수 | 신규 |
| `GET /api/v1/auth/company-email-verifications/confirm?token=…` | 링크 소지자 | 회사 메일 확인 → `EMAIL_VERIFICATIONS` 기록 | 신규 |
| `GET /api/v1/me/verifications` | 본인 | 학교·회사 인증 종류, 확인 시점, 만료 시점 | 신규 |
| `POST /api/v1/admin/universities` / `POST /api/v1/admin/universities/{id}/domains` | 운영자 | 대학·도메인 추가 | 신규. 운영자 권한 모델 [작성자 확인 필요] |

학교 인증 요청 예시:

```json
{
  "name": "김학생",
  "email": "student@example.ac.kr",
  "university_id": "550e8400-e29b-41d4-a716-446655440000",
  "enrollment_status": "student",
  "department": "소프트웨어학부",
  "entry_year": 2024
}
```

- 서버에서 `email` 도메인이 `university_id`의 허용 도메인인지 확인 필요. 입력된 학교명 문자열만으로 인증 금지
- 메일 링크의 용도·만료·재사용 제한 구분. 액세스 토큰은 확인 완료 후 발급. 로그인 링크 요청 응답에는 계정 존재 여부 노출 금지
- 회사 메일 인증은 당시 소속 증빙. 직무·직급·과거 경력의 인증 표시는 제외
- 교류·프로젝트 생성에는 유효한 학교 소속 인증 또는 승인된 예외 인증 필요. 학교 이메일 없는 졸업생의 증빙·승인·로그인 절차, 회사 메일 없는 사용자의 대체 수단은 [작성자 확인 필요]. 기존 공개 승인 경로를 목표 계약으로 간주하지 않음
- 인증 링크·액세스 토큰의 서버 로그 출력 금지. 운영용 비밀키 누락 시 시작 거부

## 3. 프로필·학교 소속·경력

ERD: `PROFILES`, `SCHOOL_AFFILIATIONS`, `USER_PREFERENCES`, `TAGS`, `USER_TAGS`, `CAREER_EVENTS`. 프로필 수정은 본인만 가능. 타인 조회에는 공개 허용 필드만 포함.

| 방법·경로 | 권한 | 요청·응답 핵심 | 상태 |
| --- | --- | --- | --- |
| `GET /api/v1/me` / `PATCH /api/v1/me` | 본인 | 이름·소개·아바타 및 각 필드의 `is_public` | 현행 확장 |
| `GET /api/v1/users/{user_id}` | 로그인 사용자 | 공개 프로필·인증 표시·공개 경력·프로젝트. 로그인 이메일 제외 | 현행 수정 |
| `GET /api/v1/me/school-affiliations` / `POST /api/v1/me/school-affiliations` | 본인 | 학교, 학과, 학적 상태, 입학·졸업 연도, 공개 여부 | 신규 |
| `PATCH /api/v1/me/school-affiliations/{id}` / `DELETE /api/v1/me/school-affiliations/{id}` | 본인 | 소속 수정·철회 | 신규 |
| `GET /api/v1/me/career-events` / `POST /api/v1/me/career-events` | 본인 | 활동 종류, 제목, 조직, 기간, 설명, 공개 여부 | 현행 확장 |
| `PATCH /api/v1/me/career-events/{id}` / `DELETE /api/v1/me/career-events/{id}` | 본인 | 경력·활동 수정·철회 | 신규 |
| `GET /api/v1/tags?kind=…` | 공개 | `skill`·`role`·`interest` 분류 목록 | 신규 |
| `GET /api/v1/me/tags` / `PUT /api/v1/me/tags` | 본인 | 경험·희망 구분(`usage`), 공개 여부 | 현행 확장 |
| `GET /api/v1/me/preferences` / `PATCH /api/v1/me/preferences` | 본인 | 커피챗·프로젝트 가능 여부, 학습 단계, 목표, 활동 시간·방식 | 신규 |
| `GET /api/v1/users/{user_id}/timeline` | 로그인 사용자 | 공개가 허용된 소속·경력·프로젝트 참여를 시간순 조합 | 신규 |
| `GET /api/v1/users/{user_id}/career-path-graph` | 로그인 사용자 | 공개·승인된 경험 노드와 시간순 연결. 목표 회사·직무 탐색은 사용자 검색 필터 사용 | 신규 |

- `GET /me`에는 본인의 비공개·승인된 정보 포함. `GET /users/{id}`와 같은 응답 모델 재사용 금지
- `is_public=false`인 승인 사실은 내부 매칭 사용 가능. 추천 이유에는 비공개 프로젝트명·저장소명·경력 세부 내용 제외
- 삭제·사용 철회 시 공개와 매칭 모두 제외. AI 재분석은 사용자가 직접 수정한 값을 자동 덮어쓰지 않음
- `CAREER_EVENTS`는 실제 입력·승인된 경험만 보관. 타임라인의 빈 시기를 임의 생성하지 않음

## 4. 외부 자료·AI 제안 승인

ERD: `EXTERNAL_ACCOUNTS`, `SOURCE_MATERIALS`, `ANALYSIS_RUNS`, `ANALYSIS_INPUTS`, `AI_SUGGESTIONS`, `SUGGESTION_EVIDENCE`. GitHub 접근 허용, 서비스 내 자료 선택, AI 분석 동의, 결과 공개는 각각 별도 단계.

| 방법·경로 | 권한 | 요청·응답 핵심 | 상태 |
| --- | --- | --- | --- |
| `POST /api/v1/me/external-accounts/github/connect` | 본인 | GitHub 연동 시작 → 승인 페이지 주소. 세부 권한 범위 [작성자 확인 필요] | 신규 |
| `GET /api/v1/auth/github/callback` | 서명된 연동 state 소지자 | 제공자 승인 결과 확인 → 외부 계정 연결 | 신규 |
| `POST /api/v1/me/external-accounts/github/sync` | 본인 | 허용된 저장소 목록을 자료 메타데이터로 동기화 | 신규 |
| `GET /api/v1/me/external-accounts` / `DELETE /api/v1/me/external-accounts/{id}` | 본인 | 연동 계정 조회·해제 | 신규 |
| `GET /api/v1/me/source-materials?kind=github_repository` | 본인 | 접근 허용된 Public·Private 저장소 목록, 설명·언어·접근 상태 | 신규 |
| `POST /api/v1/me/source-materials` | 본인 | 프로젝트·포트폴리오 URL 또는 직접 자료 등록 → 자료 ID | 신규 |
| `POST /api/v1/me/source-materials/uploads` | 본인 | CV·이력서 파일 업로드 → 자료 ID. 파일 크기·형식·보관 기간 [작성자 확인 필요] | 신규 |
| `GET /api/v1/me/source-materials/{id}` / `DELETE /api/v1/me/source-materials/{id}` | 본인 | 자료 메타데이터 조회·사용 철회 | 신규 |
| `POST /api/v1/me/analysis-runs` | 본인 | `purpose`, `material_ids[]`, 분석 동의 → 실행 ID·상태 | 신규 |
| `GET /api/v1/me/analysis-runs/{id}` | 본인 | 진행 상태, 선택 자료, 완료·실패 정보 | 신규 |
| `GET /api/v1/me/analysis-runs/{id}/suggestions` | 본인 | 제안값, 근거 자료 위치, 승인 상태 | 신규 |
| `PATCH /api/v1/me/suggestions/{id}` | 본인 | `decision`에 `accepted` 또는 `rejected`, 수정 승인 시 `accepted_value` → 반영 결과 | 신규 |

분석 요청 예시:

```json
{
  "purpose": "profile",
  "material_ids": [
    "550e8400-e29b-41d4-a716-446655440001"
  ],
  "consent": {
    "ai_analysis": true
  }
}
```

- 분석 대상은 해당 사용자가 소유하거나 접근 가능한 `material_ids`로 한정. 다른 사용자의 자료 ID, 접근 만료 자료, 동의 없는 Private 자료는 403 또는 409
- `SOURCE_MATERIALS` 등록과 분석 실행은 별개. URL 등록만으로 비공개 저장소 접근 권한을 획득한 것으로 처리 금지. 연결된 외부 계정과 자료의 소유자 일치 확인
- 제안 카드의 `target_kind`, `field_key`, `proposed_value`, 근거 자료 표시. 없는 경력·기간·성과 생성 금지
- 승인·수정 적용과 정형 테이블 반영은 한 트랜잭션. 거절·미승인 정보는 공개·매칭·포트폴리오 입력 제외
- 수정 승인값을 보관할 `accepted_value` 또는 동등한 구조, 신규 대상 생성 시 `target_id`의 처리 규칙은 ERD 보완 필요
- LinkedIn은 URL 등록만 지원. OAuth 및 경력 자동 수집은 이 범위에서 제외

## 5. 사람 탐색·매칭

검색 조건 해석과 검색 실행을 분리. 정확 조건은 정형 필터로 검사하고, 유사 경험은 별도 기준으로 평가. Vector DB 채택 여부는 미정.

| 방법·경로 | 권한 | 요청·응답 핵심 | 상태 |
| --- | --- | --- | --- |
| `POST /api/v1/search/interpret` | 본인 | 자연어 문장 → 수정 가능한 구조화 조건. 검색 실행 없음 | 신규 |
| `POST /api/v1/search/users` | 본인 | `purpose`, 학교·학과·학적·회사·직무·기술·관심·활동 조건 → 사용자 목록·추천 이유 | 현행 확장 |
| `GET /api/v1/search/filters` | 본인 | GUI 필터 선택지 및 구분값 | 신규 |
| `POST /api/v1/projects/{id}/candidate-search` | 프로젝트 모집 권한자 | 모집 역할·기술·활동 조건에 맞는 후보와 이유 | 신규 |

검색 요청의 `purpose`: `coffee_chat`, `team_building`, `beginner_team_building`. 사용자가 기본 목적·유사·보완 방향을 변경 가능.

```json
{
  "purpose": "team_building",
  "filters": {
    "university_ids": [],
    "role_tag_ids": [],
    "skill_tag_ids": [],
    "project_available": true,
    "hours_per_week_min": 4
  },
  "match_direction": "complementary"
}
```

- 결과에는 공개 프로필 필드와 안전한 추천 이유만 포함. 비공개 사실의 고유명·세부 경력·자료 주소 노출 금지
- 초보자는 프로젝트 경험 없이도 선호 역할·관심사·학습 단계·목표·활동 조건으로 검색·추천 대상에 포함
- 근거 없는 실력 점수·성공 확률 제공 금지. 추천 점수의 저장과 검색 인덱스는 구현 방식 확정 후 검토

## 6. 프로젝트·모집·참여

ERD: `PROJECTS`, `PROJECT_SOURCES`, `PROJECT_MEMBERS`, `PROJECT_TAGS`, `RECRUITMENT_POSTS`, `ROLE_OPENINGS`, `OPENING_SKILLS`, `PROJECT_REQUESTS`. 포트폴리오용 프로젝트와 팀원 모집 공고를 별개 자원으로 취급.

| 방법·경로 | 권한 | 요청·응답 핵심 | 상태 |
| --- | --- | --- | --- |
| `POST /api/v1/projects` | 본인 | 제목·소개·상태·목표·공개 범위 → 프로젝트 | 신규 |
| `GET /api/v1/projects` / `GET /api/v1/projects/{id}` | 로그인 사용자 | 공개 프로젝트 검색·상세. 비공개 프로젝트는 참여 권한자만 | 신규 |
| `PATCH /api/v1/projects/{id}` / `DELETE /api/v1/projects/{id}` | 프로젝트 관리 권한자 | 수정·공개 철회 | 신규 |
| `POST /api/v1/projects/{id}/sources` / `DELETE /api/v1/projects/{id}/sources/{material_id}` | 프로젝트 관리 권한자 | 근거 자료 연결·해제 | 신규 |
| `GET /api/v1/projects/{id}/members` | 로그인 사용자 또는 참여 권한자 | 공개 허용된 역할·기여. 비공개 내용 필터 | 신규 |
| `POST /api/v1/projects/{id}/recruitment-posts` | 프로젝트 관리 권한자 | 별도 모집 공고·활동 조건·역할별 인원 생성 | 신규 |
| `GET /api/v1/recruitment-posts` / `GET /api/v1/recruitment-posts/{id}` | 로그인 사용자 | 게시된 공고 검색·상세 | 신규 |
| `PATCH /api/v1/recruitment-posts/{id}` / `POST /api/v1/recruitment-posts/{id}/publish` | 프로젝트 관리 권한자 | 공고 수정·명시적 게시 | 신규 |
| `POST /api/v1/recruitment-posts/drafts` | 프로젝트 관리 권한자 | 프로젝트 설명·선택 자료 → 수정 가능한 모집 문구 초안 | 신규 |
| `POST /api/v1/recruitment-posts/{id}/applications` | 본인 | 희망 `opening_id`, 메시지 → 지원 요청 | 신규 |
| `POST /api/v1/projects/{id}/invitations` | 프로젝트 관리 권한자 | `candidate_id`, `opening_id`, 메시지 → 초대 요청 | 신규 |
| `GET /api/v1/me/project-requests` | 본인 | 지원·초대 내역과 상태 | 신규 |
| `POST /api/v1/project-requests/{id}/decision` | 요청 수신자 또는 프로젝트 관리 권한자 | `accepted` 또는 `rejected` → 결정 결과 | 신규 |

- 프로젝트 등록·GitHub 분석만으로 모집 공고 자동 게시 금지. `publish`는 별도 사용자 행위
- 요청 수락 후에만 `PROJECT_MEMBERS` 생성. 요청자·후보자·프로젝트 권한 관계 확인
- 공동 프로젝트 URL 등록과 Private 저장소 접근 권한은 별개. 타인 소유 자료의 프로젝트 연결에는 자료 소유자 허용 필요. 참여자의 본인 역할·기여 기간만 해당 사용자 경험으로 반영
- AI 모집 문구는 수정·승인 전 게시 금지

## 7. 커피챗 요청·예약·참석

ERD: `COFFEE_REQUESTS`, `COFFEE_PROPOSED_SLOTS`, `COFFEE_BOOKINGS`, `BOOKING_CHANGES`, `ATTENDANCE_RECORDS`. 요청 수락과 일정 확정은 다른 사건. 현행 `message` 하나와 임의 상태 변경 API로는 목표 흐름 표현 불가.

| 방법·경로 | 권한 | 요청·응답 핵심 | 상태 |
| --- | --- | --- | --- |
| `POST /api/v1/coffee-chats` | 본인 | 수신자, 목적, 소개, 질문, 희망 시간 후보 1건 이상 → 요청 ID·`pending` | 현행 확장 |
| `GET /api/v1/coffee-chats?box=sent` 또는 `?box=received` / `GET /api/v1/coffee-chats/{id}` | 당사자 | 요청 목록·상세와 예약 여부 | 현행 확장 |
| `POST /api/v1/coffee-chats/{id}/decision` | 수신자 | `accepted` 또는 `rejected` → 결정 시점 | 현행 상태 API 대체 |
| `POST /api/v1/coffee-chats/{id}/booking` | 요청 수신자 | 요청자가 제안한 `slot_id`, 만남 방식·장소 → 확정 예약 | 신규 |
| `GET /api/v1/bookings/{id}` | 예약 당사자 | 현재 일정·상태·장소·변경 이력 | 신규 |
| `POST /api/v1/bookings/{id}/changes` | 예약 당사자 | `reschedule` 또는 `cancel`, 변경 후 값 → 변경 제안 | 신규 |
| `POST /api/v1/bookings/{id}/changes/{change_id}/decision` | 상대 당사자 | `accepted` 또는 `rejected` → 확정 또는 거절 | 신규. ERD 상태 필드 보완 필요 |
| `POST /api/v1/bookings/{id}/check-ins` | 예약 당사자 | 체크인 방식·시점 → 본인 참석 기록 | 신규 |
| `PUT /api/v1/bookings/{id}/attendance-claim` | 예약 당사자 | 참석·불참 주장 → 본인 기록 | 신규 |
| `GET /api/v1/bookings/{id}/attendance` | 예약 당사자 | 각 당사자의 확인 결과·분쟁 상태 | 신규 |
| `POST /api/v1/coffee-chat-drafts` | 본인 | 상대 공개 경력·요청 목적 → 선택형 질문·요청 문구 초안 | 신규 |

커피챗 생성 예시:

```json
{
  "recipient_id": "550e8400-e29b-41d4-a716-446655440002",
  "purpose": "커리어 상담",
  "introduction": "현재 백엔드 직무를 탐색 중입니다.",
  "questions": "첫 직무를 선택할 때 고려한 점이 궁금합니다.",
  "proposed_slots": [
    {
      "starts_at": "2026-10-01T19:00:00+09:00",
      "ends_at": "2026-10-01T19:30:00+09:00"
    }
  ]
}
```

- 요청자와 수신자는 서로 달라야 함. 수신자만 요청 수락·거절 가능. 본인 요청의 자체 수락·완료 처리 금지
- `COFFEE_REQUESTS` 상태: `pending → accepted|rejected`. 취소 가능 시점과 재요청 규칙은 [작성자 확인 필요]
- 예약은 수락된 요청에 한 건만 생성. 수신자가 요청자의 후보 중 선택한 슬롯으로 확정. 일정 변경·취소는 당사자 확인 후 현재 예약에 반영하고 `BOOKING_CHANGES`에 이력 저장
- 체크인 시각과 사후 참석 주장은 별도 기록. 상대방 기록을 대신 쓰거나 과거 체크인 시각을 사후 변경하는 행위 금지
- AI 질문 초안은 선택 기능. 사용자가 직접 작성한 질문도 그대로 전송 가능
- 기존 비동기 질문에서 커피챗으로 전환하는 기능을 계속 제공한다면 `COFFEE_REQUESTS.origin_question_id`와 질문 엔티티를 ERD에 추가 필요

## 8. 보증금·분쟁·신뢰·알림

보증금 기능은 기획 범위에 포함. 금액·납부 주체·결제 시점·환불 기준, 체크인 방식, 패널티 산식은 미확정. 아래 경로는 자원 단위 초안이며 결제 실행 계약은 정책과 공급자 확정 후 보완 필요.

| 방법·경로 | 권한 | 요청·응답 핵심 | 상태 |
| --- | --- | --- | --- |
| `GET /api/v1/bookings/{id}/deposits` | 예약 당사자 | 납부 의무·금액·통화·결제·환불 상태 | 정책 확정 후 |
| `POST /api/v1/deposits/{id}/payment-intents` | 납부 대상자 | 결제 시작 → 외부 결제 진행 정보 | 정책·공급자 확정 후 |
| `GET /api/v1/deposits/{id}/payment-events` | 납부 대상자·운영자 | 결제·취소·환불 처리 내역 | 정책 확정 후 |
| `POST /api/v1/bookings/{id}/disputes` / `GET /api/v1/bookings/{id}/disputes` | 예약 당사자 | 신고 사유·처리 상태 | 신규 |
| `POST /api/v1/admin/disputes/{id}/resolution` | 운영자 | 검토 결과·근거 → 처리 상태 | 운영 정책 확정 후 |
| `GET /api/v1/me/trust` / `GET /api/v1/me/trust-events` | 본인 | 현재 등급·근거 이력. 기술 실력과 구분 | 신규 |
| `GET /api/v1/me/notifications` / `PATCH /api/v1/me/notifications/{id}` | 본인 | 요청·응답·일정 알림 조회 및 읽음 처리 | ERD 보완 후 |

- `DEPOSITS`는 정책에 따라 예약별 납부 의무 생성. 정책 확정 전 금액·패널티를 API 기본값으로 고정 금지
- 중복 결제 웹훅은 `PAYMENT_EVENTS.provider_reference` 기준 중복 방지. 카드·간편결제 민감 원본 저장 금지
- 분쟁 중인 예약은 자동 제재·정산에서 제외. `TRUST_EVENTS`는 근거, `TRUST_STATES`는 현재 조회 상태
- 앱 안의 알림함·읽음 상태가 필요하다면 `NOTIFICATIONS` 등 영속 엔티티를 ERD에 추가 필요. 이메일 발송만으로 충족할지는 [작성자 확인 필요]

## 9. AI 포트폴리오

ERD: `STYLE_GUIDES`, `PORTFOLIO_SITES`, `PORTFOLIO_VERSIONS`, `PORTFOLIO_PUBLICATIONS`. 생성 입력은 사용자가 승인하고 공개 허용한 사실만 사용. 생성 결과는 미리보기·수정·승인 후 게시.

| 방법·경로 | 권한 | 요청·응답 핵심 | 상태 |
| --- | --- | --- | --- |
| `GET /api/v1/portfolio-styles` | 본인 | 시각적 예시 카드·스타일명·설명 | 신규 |
| `GET /api/v1/me/portfolio-site` / `POST /api/v1/me/portfolio-site` | 본인 | 사이트 주소용 slug·현재 게시 버전 | 신규 |
| `POST /api/v1/me/portfolio-site/versions` | 본인 | 스타일, 공개 허용 자료·섹션, 자연어 지시 → 생성 작업 ID | 신규 |
| `GET /api/v1/me/portfolio-site/versions/{id}` | 본인 | `queued`, `generating`, `preview_ready`, `failed` 등 진행 상태·미리보기 위치 | 신규 |
| `POST /api/v1/me/portfolio-site/versions/{id}/revisions` | 본인 | GUI 변경 또는 자연어 수정 요청 → 새 버전 | 신규 |
| `POST /api/v1/me/portfolio-site/versions/{id}/publish` | 본인 | 미리보기 승인 후 게시 기록 | 신규 |
| `POST /api/v1/me/portfolio-site/publication/revoke` | 본인 | 현재 게시 중지 | 신규 |
| `GET /api/v1/portfolios/{slug}` | 공개 | 공개된 사이트 메타데이터·게시 버전. 실제 페이지 제공 경로는 별도 | 신규 |

- `public_input_snapshot`은 생성 시점에 공개 허용된 정보만 포함. 비공개 자료 원문·토큰·결제 정보의 코드 포함 금지
- 디자인 수정과 프로필 사실 수정은 별도 처리. 자연어로 디자인을 바꿀 때 존재하지 않는 경력·성과 생성 금지
- 공개 설정 철회 시 기존 게시물 중지 후 허용 자료로 재생성·재게시 필요
- 생성된 HTML/CSS/JS는 서비스 본체와 분리된 실행 영역에서 제공. 임의 외부 전송 제한
- 스타일 가이드는 내부 `design.md`에 연결. 사용자 화면에는 파일명보다 예시 화면 표시

## 10. 공통 요청·응답 모델

응답 필드는 ERD의 논리 필드명을 기준으로 표기. `?`는 선택 입력 또는 값이 없는 경우 `null` 가능을 뜻함. 공개 API의 필드 제거 기준은 서버에서 적용.

| 모델 | 핵심 필드와 자료형 | 적용 |
| --- | --- | --- |
| `UserSelf` | `id: uuid`, `login_email: string`, `account_status: string`, `profile: object`, `school_affiliations: array`, `preferences: object` | `GET /me` 전용. 비공개 정보 포함 |
| `UserPublic` | `id: uuid`, `display_name: string`, 공개된 `bio?`·`avatar?`·`affiliations[]`·`career_events[]`·`project_members[]`, 인증 표시 | 타인 조회·검색 결과 전용. `login_email`과 비공개 사실 제외 |
| `CareerEvent` | `id: uuid`, `event_kind: string`, `title: string`, `organization_name?`, `started_on?`·`ended_on?`, `description?`, `is_public: boolean` | 입력·승인된 사실만 타임라인 구성 |
| `SourceMaterial` | `id: uuid`, `material_kind: string`, `display_name: string`, `canonical_url?`, `is_private: boolean`, `access_status: string` | 목록 조회는 메타데이터 중심. 원문은 별도 권한 대상 |
| `AnalysisRun` | `id: uuid`, `purpose: string`, `status: string`, `material_ids: uuid[]`, `consented_at: datetime` | 분석 실행별 선택 자료 고정 |
| `AISuggestion` | `id: uuid`, `target_kind: string`, `target_id?: uuid`, `field_key: string`, `proposed_value: any`, `decision: string`, `evidence[]` | 미승인 값은 공개·매칭 결과 제외 |
| `SearchCandidate` | `user: UserPublic`, `reason: string`, `matched_conditions[]` | 비공개 고유 정보 없이 이유 설명 |
| `Project` | `id: uuid`, `creator_id: uuid`, `title: string`, `summary?: string`, `project_status: string`, `goal?: string`, `visibility: string` | 경험 등록과 모집 공고 구분 |
| `RecruitmentPost` | `id: uuid`, `project_id: uuid`, `status: string`, `description: string`, `hours_per_week?`, `collaboration_mode?`, `role_openings[]` | 명시적 게시 전 공개 목록 제외 |
| `ProjectRequest` | `id: uuid`, `post_id: uuid`, `opening_id?: uuid`, `candidate_id: uuid`, `initiator_id: uuid`, `request_kind: string`, `status: string` | 지원·초대 구분, 수락 후 팀원 반영 |
| `CoffeeRequest` | `id: uuid`, `requester_id: uuid`, `recipient_id: uuid`, `purpose: string`, `introduction?: string`, `questions: string`, `status: string`, `proposed_slots[]` | 희망 슬롯은 `starts_at`·`ends_at` |
| `Booking` | `id: uuid`, `request_id: uuid`, `starts_at: datetime`, `ends_at: datetime`, `meeting_mode: string`, `meeting_location?: string`, `status: string` | 요청당 현재 예약 최대 한 건 |
| `AttendanceRecord` | `booking_id: uuid`, `user_id: uuid`, `checkin_method?`, `checked_in_at?`, `attendance_claim?`, `claimed_at?` | 예약 참여자당 한 건. 체크인과 사후 주장 구분 |
| `Deposit` | `id: uuid`, `booking_id: uuid`, `payer_id: uuid`, `amount: decimal`, `currency: string`, `status: string` | 금액·납부 조건 [작성자 확인 필요] |
| `PortfolioVersion` | `id: uuid`, `site_id: uuid`, `style_guide_id: uuid`, `version_number: integer`, `status: string`, `created_at: datetime` | 공개 허용 입력 스냅샷·생성 번들은 비공개 관리 |

| 응답 상황 | HTTP 상태 | 처리 |
| --- | --- | --- |
| 단건·목록 조회, 수정·결정 완료 | `200` | 응답 모델 반환 |
| 자원 생성 완료 | `201` | 생성된 자원과 ID 반환 |
| 메일 발송·AI 분석·생성 작업 접수 | `202` | 작업 ID 또는 접수 결과 반환. 완료로 표기 금지 |
| 삭제·연동 해제 완료 | `204` | 본문 없음 |
| 입력 형식·필수 필드 오류 | `422` | 필드별 오류 |
| 인증 누락·만료 | `401` | 인증 요청 |
| 소유권·접근 범위 위반 | `403` | 자료 내용 노출 없이 거부 |
| 잘못된 상태 전이·중복 요청 | `409` | 현재 상태 확인 가능하게 설명 |
| 호출 제한 | `429` | 인증 링크·AI 실행 등 남용 방지. 제한값 [작성자 확인 필요] |

## 11. 구현 전 확인 항목

| 항목 | 필요한 결정 또는 ERD 보완 |
| --- | --- |
| 인증 예외 | 학교·회사 이메일을 쓸 수 없는 사용자의 증빙, 운영자 권한, 승인 후 로그인 절차 |
| 기존 데이터 | 현행 정수 ID → UUID 전환 방식, `/api` 지원 종료·병행 기간 |
| AI 승인 | 사용자가 수정해 승인한 값의 저장 위치, 신규 대상 생성 시 `target_id` 처리 |
| 예약 변경 | `BOOKING_CHANGES`의 제안·승인·거절 상태와 상대방 결정 시점 |
| 비동기 질문 | 현행 질문 API 유지 여부. 유지 시 ERD 엔티티와 요청 전환 FK 추가 |
| 알림 | 앱 안 알림함·읽음 기록 제공 여부. 제공 시 영속 엔티티 추가 |
| 결제·신뢰 | 보증금 금액·시점·환불, 참석 방식, 지각·노쇼 기준, 등급 산식 |
| 원본 자료 | CV·Private 저장소 접근 권한·원본 보관·삭제 기간 및 외부 AI 처리 범위 |

명세의 우선 구현 순서: 인증·권한과 공개 범위 → 프로필·자료 승인 → 커피챗 요청·예약 → 프로젝트·탐색 → 신뢰·포트폴리오. 이는 의존 관계를 기준으로 한 제안이며, 기능 제외 결정은 아님.

