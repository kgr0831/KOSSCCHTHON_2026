# 구현 및 검증 기록

기준 위치는 사용자 지정 `C:/koss2026`입니다. `Architecture.md`를 기능 기준으로, Figma Page 1을 디자인 기준으로 사용합니다.

## 이번 요청의 구현

| 요청 | 구현 |
| --- | --- |
| 단일 터미널 BAT, 준비 후 브라우저, 창 종료 시 프로세스 종료 | `start-local.bat`, `scripts/run_local.py`, Windows Job Object. API·Next·worker·사이트 제공기를 함께 관리 |
| BAT 재실행 시 포트 충돌 | `scripts/run_local.py`, `backend/app/dev.py`에서 폴더·포트 식별값과 프런트 프록시/API 상태를 확인. 같은 실행이면 기존 브라우저 재열기·정상 종료. 다른 프로그램은 유지 |
| 로컬 DB와 더미 사용자 | 영속 SQLite `backend/.data/dudri.db`, Alembic 마이그레이션, 8명의 가상 사용자·학교·태그·프로젝트·커피챗 seed. 재실행 시 수정값 유지 |
| 추천 임시 제공 | `/recommendations`에서 임의 순서로 조회. 적합도·AI 매칭 점수 없음 |
| 최신 Figma 및 기존 댓글 | 모바일 공통 디자인을 PC에도 적용, PC 사이드바. 커리어맵·모집·AI 화면 추가. 읽기 전용 댓글 확인 및 [반영표](docs/design/README.md) |
| 디자인 선택·레퍼런스 이미지 | Design MD 자동 탐색, 기본 PNG 예시, 개인 MD 업로드·DB 저장·Claude 예시 생성 작업·PC/모바일 PNG·재시도. 분위기·레이아웃·폰트·간격·색상 선택으로 개인 스타일 생성 |
| 앱 내비게이션·반응형 | 주소 유지하는 내부 화면 전환, 깊은 링크 진입·이력 복원, 로그인 대화상자, 본문 애니메이션, 고정 메뉴·나의 공간 현재 위치·낮은 PC 메뉴 배치 |
| GUI 경고와 프로젝트 레이아웃 | 공통 입력·저장 확인 대화상자, 같은 탭의 편집 초안 복구, 프로젝트 섹션 간격·긴 역할명 줄바꿈·로딩 처리 |
| 포트폴리오와 CV 구분 | 문서 종류별 프롬프트·안내·내보내기 분리. 프로젝트 상세·작업 카드와 인쇄 이력서를 구분하고 원래 섹션 부모·중첩 그리드 보존 |
| AI 포트폴리오·PR·CV·자기소개서 | 종류별 사이트·영속 버전·AI 작업 큐·이력·재시도·GUI/코드 수정·복구·게시·철회 |
| 실제 AI API | 국민대 OpenAI 호환 경로, 실제 모델 ID 조회. 현재 쉬운 기능 Haiku(사용자 허용), 복잡한 기능 Sonnet. Flash 제공 시 선택 가능 |
| 구독 CLI | 공식 Claude/Gemini 어댑터, 화면에서 API/CLI/혼합 선택, 같은 터미널에서 로그인. Gemini는 별도 로그인 공간 사용 |
| 키 보관 | 루트 .env로 키 이동 후 token.txt 삭제. .env·런타임·DB는 Git 제외, .env.example은 빈 비밀값 |
| 댓글의 문구 생성·CV·질문 | 자기소개·경험·모집·커피챗 질문 초안, 자료 분석·승인, 공개 CV 표시, 커리어 계획 저장 |

문서는 자동 게시하지 않습니다. 분석 제안은 사용자 승인 후에만 정형 프로필로 반영합니다. 공개 정보 변경 시 이전 사이트 게시를 중지하고 오래된 입력의 게시를 막습니다.

## 핵심 코드

| 위치 | 책임 |
| --- | --- |
| `backend/app/ai.py`, `ai_routes.py`, `cli_login.py`, `cli_runner.py` | 서버 .env, 국민대 API·모델 선택, 구독 CLI·로그인·제한된 실행 |
| `backend/app/sites.py`, `site_render.py`, `site_server.py`, `worker.py` | 문서·버전·충돌·작업 선점·복구·격리 제공·명시적 게시 |
| `backend/app/materials.py`, `pdf_extract.py`, `career.py` | 비공개 자료·제한된 PDF 추출·근거 검토·승인·커리어 계획·임시 추천 |
| `backend/app/seed.py`, `dev.py` | 가상 데이터와 로컬 전용 로그인 |
| `frontend/src/app/studio/`, `settings/ai/`, `materials/`, `career/`, `projects/` | 새 사용자 흐름 |
| `frontend/src/components/ai-draft.tsx`, `recommendations.tsx` | 명시적 초안 적용·임시 추천 |
| `frontend/public/styles/`, `scripts/generate_style_previews.py`, `frontend/scripts/render-style-previews.mjs` | 원문 스타일에 따른 레퍼런스 생성 |

## 검증 결과

- 백엔드 41개 테스트 통과, PostgreSQL 전용 테스트 1개는 기본 실행에서 생략. 별도 로컬 PostgreSQL 17.11에서 해당 테스트도 통과. 변경된 실행 스크립트 Ruff 통과.
- 프런트 TypeScript 검사 및 Playwright 25개 통과. 프로덕션 빌드는 중단 전 통과 기록이 있으며 최신 Linux 컨테이너 빌드는 CI로 확인할 예정.
- 새 Supabase로 128개 레코드 이전, 전체 필드·소유권·문서 연결 일치, 원본 보존, RLS·Data API 역할 차단, 실제 앱 API 저장·별도 DB 세션 재조회 검증 완료.
- 비밀값 없는 복제 폴더의 최초 설치·Node 압축 해제 중단 복구·중복 BAT 재사용·동작 중 의존성 보호 검증 완료. 실제 다른 초기화 PC 검증과 동일한 의미는 아님.
- 권한 분리, 미승인·비공개 입력 제외, 네 종류의 문서 저장, 오래된 입력 게시 차단, 만료 lease 회수, 동시 수정 충돌, 코드 오류 보관, 자유 코드/CSS·헤더 보존, 자료 철회 후 승인 차단, seed 재실행 보존 검증.
- 실제 로컬 계정으로 6개 새 화면의 모바일·PC, Haiku 초안, 종류를 분리한 Sonnet 포트폴리오·CV, 저장 후 재조회·표시 확인.
- Windows supervisor를 강제 종료한 뒤 프런트·API·사이트 제공기의 세 포트가 모두 닫히는 통합 검사 통과. 기존 사용자 프로세스를 이름으로 종료하지 않음.
- 국민대 API 인증·생성 성공. Claude CLI는 설치·옵션 확인까지 수행했으며 구독 로그인이 필요함.

## 전체 Architecture 기준으로 별도 남은 범위

이번 로컬 요청의 구현과 기존 Architecture 전체의 완료 상태를 구분합니다.

- 실서비스 이메일은 SMTP 또는 Brevo HTTPS API를 사용합니다. Brevo 무료 계정·발신자와 연결 확인 메일의 배달을 검증했습니다. 운영 학교 인증 권한 게이트 및 보조 인증 정책은 별도 검토 대상입니다.
- Supabase PostgreSQL 연결·이전·앱 저장 검증은 완료했습니다. Linux Docker/Render/CI 구성은 준비되어 있으며 실제 배포는 아직 미완료입니다. GitHub OAuth·저장소 동기화, 외부 URL 수집, Supabase Storage는 남아 있습니다.
- Google Supabase Auth 로그인과 같은 계정의 별도 학교 이메일 인증, 실제 인증 링크의 발송·사용 검증은 아직 미완료입니다. 순천향대(sch.ac.kr)·국민대(kookmin.ac.kr)·숭실대(soongsil.ac.kr) 인증 지원을 최종 FIFO 항목으로 확인할 예정입니다.
- 운영 환경의 사용자별 구독 CLI 연결은 미구현이며 현재 API 모드만 허용합니다.
- 소속 편집 전용 UI, 프로젝트 초대·팀원 기여 편집 UI·일부 목록의 다음 페이지 UI는 추가 범위입니다.
- CV는 영속 문서 생성과 정적 HTML 내보내기를 제공하며 PDF는 브라우저 인쇄로 저장합니다. 서버 PDF 내보내기·스캔 OCR은 없습니다.
- GUI는 선언한 편집 영역을 다룹니다. 임의 HTML 전체의 WYSIWYG 편집, 임의 이미지·외부 링크 관리 도구는 포함하지 않습니다.
- 자동 매칭 알고리즘은 현재 사용자 요청에 따라 임의 추천으로 대체했습니다.
- 보증금·정산·신뢰 등급·분쟁 결론 등의 정책은 임의로 정하지 않았습니다.
- 실제 모바일 기기·운영 환경 배포 검증은 별도입니다.

실행 방법과 필요한 설정은 [README](README.md)를 참고하세요.
