# 두드리 · 로컬 실행

작업 기준은 `C:\koss2026\Architecture.md`, 디자인 기준은 Figma **Page 1**입니다.

## 실행

`C:\koss2026\start-local.bat`를 실행하세요. 64비트 Windows와 인터넷 연결이 필요합니다. Node.js·uv·Python을 미리 설치하지 않아도 프로젝트의 `.runtime/tools`에 고정 버전을 준비합니다. 시스템 PATH와 Python 등록 정보는 변경하지 않습니다.

하나의 터미널에서 DB 마이그레이션·더미 데이터 준비, 프런트엔드, API, AI 작업 실행기, 생성 사이트 제공기를 시작합니다. 실제 DB 연결까지 확인한 뒤 브라우저를 자동으로 엽니다. 처음 실행할 때 백엔드·프런트 패키지를 lock 파일 기준으로 설치합니다. `.env`의 빠진 항목은 빈 템플릿에서 보완하고 기존 값은 유지합니다. 설치가 중단되면 BAT를 다시 실행하세요. 실패한 창은 오류를 읽을 수 있도록 열린 상태로 남습니다.

Python 백엔드를 pip로 설치하려면 루트에서 `python -m pip install -r requirement.txt`를 실행하세요. Python 3.11 이상이 필요하며, `backend/uv.lock`의 실행·개발 의존성 버전을 고정한 목록입니다. 프런트 의존성은 `npm --prefix frontend ci`로 설치합니다. BAT 실행은 기존처럼 uv를 사용합니다.

| 구성 | 주소·저장 위치 |
| --- | --- |
| 서비스 | http://localhost:3000 |
| API | http://127.0.0.1:8000 |
| 공개 문서 제공기 | http://127.0.0.1:8001 |
| 영속 SQLite DB | `backend/.data/dudri.db` |
| Supabase PostgreSQL | `.env`의 `DUDRI_DATABASE_URL`이 설정된 경우 사용 |
| 서버 비밀 설정 | 루트 `.env` |

터미널을 닫거나 `Ctrl+C`를 누르면 이 실행에서 시작한 프로세스가 종료됩니다. Windows Job Object로 자식·손자 프로세스도 함께 관리합니다. DB와 저장된 문서는 유지됩니다.

같은 폴더·포트·DB 설정의 두드리가 이미 실행 중이면 BAT는 `ALREADY RUNNING`을 표시하고 기존 앱을 브라우저로 엽니다. 이때 의존성을 다시 설치하지 않습니다. 종료하려면 처음 서버를 켠 터미널을 닫으세요. 같은 폴더에서 다른 포트로 실행하려면 기존 실행을 먼저 종료해야 합니다. 다른 프로그램이 포트를 사용하거나 아직 서버가 준비 중이면 안내를 표시하며 기존 프로세스는 유지합니다.

```bat
start-local.bat --no-browser
start-local.bat --port 3002 --api-port 8002 --site-port 8003
```

## Supabase DB 연결과 기존 데이터 이전

Supabase의 **Connect → Direct → Session pooler**에서 URI(5432)를 확인하고 루트 `.env`의 `DUDRI_DATABASE_URL`에 입력합니다. 비밀번호의 특수문자는 URL 인코딩해야 합니다. 비워 두면 기존 SQLite를 사용합니다. 서버만 PostgreSQL에 접근하며 Data API는 필요하지 않습니다. 앱 테이블에는 RLS를 적용하고 Data API 역할의 접근 권한을 회수합니다.

기존 SQLite를 옮길 때는 앱을 종료하고 **앱 데이터가 없는 대상 DB**에 한 번만 실행합니다.

```bat
start-local.bat --import-sqlite
```

이전은 단일 트랜잭션이며 원본 SQLite를 보존합니다. 이미 데이터가 있는 대상은 덮어쓰지 않습니다. 기존 인증 세션·인증 링크·외부 계정 비밀은 이전하지 않으므로 다시 로그인하고 외부 계정을 다시 연결해야 합니다. 이미 이전했다면 일반 BAT로 실행하세요.

## 바로 체험하기

로그인 화면의 **로컬 체험 · 가상 인물**에서 계정을 선택하세요. 8명의 가상 사용자, 기술·관심사, 경력, 프로젝트 모집, 커피챗 요청과 약속이 로컬 DB에 준비됩니다. 다시 실행해도 수정한 데이터는 덮어쓰지 않습니다. 데모 로그인은 development 모드·명시적 로컬 실행·허용된 더미 계정으로 제한됩니다.

- **AI 스튜디오:** 포트폴리오 / 자기 PR 프로필 / CV·이력서 / 자기소개서 선택 → 디자인 예시 비교 → 공개 입력 확인·AI 전송 동의 → 생성. 저장된 버전을 다시 열고 내용·디자인·코드를 편집할 수 있습니다.
- **디자인 추가:** AI 스튜디오의 ‘내 디자인 MD 추가’에서 UTF-8 MD(64KB 이하)를 업로드합니다. 개인 라이브러리에 원문을 저장하고 Claude가 같은 가상 인물의 PC·모바일 예시 PNG를 생성합니다. 작업 상태·실패·재시도가 표시되며 새 스타일은 수정본에도 적용할 수 있습니다. `Design/`의 MD도 자동으로 읽습니다.
- **스타일 만들기:** ‘원하는 스타일 만들기’에서 분위기·레이아웃·폰트·간격·색상과 추가 요구를 선택합니다. 동의 후 개인 Design MD로 저장하고 예시 이미지 작업을 시작합니다. 확대 이미지와 입력 팝업은 PC·모바일 화면 중앙에 표시됩니다.
- **자료·AI 검토:** 텍스트 또는 PDF/TXT/MD 등록 → 선택한 자료만 분석 → 원문 근거 확인 → 수정 승인·제외. 승인 전에는 프로필·공개 생성 입력에 반영되지 않습니다.
- **프로젝트:** 비공개 프로젝트와 모집 초안 저장 → 프로젝트 공개 → 모집 글 게시. 지원과 수락도 실제 DB에 반영됩니다.
- **커피챗:** 질문 초안 적용, 요청, 상대의 일정 선택, 캘린더, 변경 동의 흐름을 사용할 수 있습니다.
- **커리어맵:** 실제 경험을 확인하고 AI 미래 계획을 별도로 저장합니다.

현재 동문 추천은 사용자 요청에 따라 **임의 순서**로 제공합니다. 적합도 점수나 AI 매칭 결과로 표시하지 않습니다.

앱 안의 메뉴는 주소를 유지하며 본문만 전환합니다. 직접 링크는 해당 화면으로 진입하고 이후 `/`에서 내부 이력을 관리하여 뒤로·앞으로 가기와 새로고침을 지원합니다. 로그인은 현재 화면 위의 대화상자로 열립니다. PC 사이드바와 모바일 5개 메뉴는 고정되며 ‘나의 공간’ 세부 메뉴와 현재 위치를 함께 표시합니다. 낮은 PC 화면에서는 메뉴 배치를 줄여 사이드바 스크롤 없이 사용할 수 있습니다.

입력 오류와 저장 전 화면 이동은 앱 대화상자로 안내합니다. 프로필 소개 및 문서 편집 초안은 같은 탭의 새로고침에서 복구합니다. 정식 저장은 서버 DB에 남으며, 탭을 닫기 전에는 저장 버튼을 눌러 주세요.

## AI와 비밀 설정

`token.txt`의 키를 루트 `.env`의 `DUDRI_AI_API_KEY`로 옮긴 뒤 `token.txt`는 삭제했습니다. 키는 서버에서만 읽습니다. `.env`, `.env.*`, `token.txt`, `.runtime/`, `.data/`는 Git에서 제외되며, 실제 비밀 값이 없는 `.env.example`만 공유합니다. SMTP 비밀번호·GitHub secret·암호화 키도 같은 `.env`에서 설정합니다. 키 변경 후에는 실행 터미널을 다시 시작하세요.

국민대 API 연동 방식은 `KOOKMIN_AI_ORCA_API.md`를 따릅니다. `/models`에서 실제 사용 가능한 모델 ID를 확인해 `/chat/completions`로 요청합니다.

- 복잡한 문서·HTML/CSS/JS·커리어 설계: **Claude Sonnet 우선**.
- 간단한 초안·질문·검색 조건·자료 분석: **Gemini Flash 우선**. 현재 국민대 제공 목록에는 Flash가 없어, 사용자가 허용한 **Claude Haiku**를 사용합니다.
- 실패한 AI 응답을 더미 생성물로 바꾸지 않습니다. 오류와 입력을 유지하고 새 버전으로 재시도합니다.

`마이 → AI 연결 설정`에서 API, 공식 CLI, 혼합(API + Claude CLI)을 선택할 수 있습니다. 구독 CLI는 해당 제공자의 로그인과 사용량 제한을 따릅니다.

현재 운영 모드는 API를 사용합니다. 여러 사용자가 서버의 구독 CLI 세션을 공유하지 않도록 제한하며, 배포 환경의 사용자별 구독 연결은 아직 미구현입니다.

실행 터미널에서 `C`는 Claude 로그인, `G`는 Gemini 로그인을 엽니다. Gemini는 `.runtime/cli-home/gemini`의 전용 공간에서 로그인한 후 `/quit`으로 돌아옵니다. 앱은 다른 도구의 인증 파일을 읽거나 복사하지 않습니다. 생성 시 도구·MCP·확장 접근을 제한하고 프롬프트를 셸 문자열에 넣지 않습니다. CLI 인증 파일은 CLI가 직접 관리하며 Git에서 제외됩니다.

공식 설명: [Claude headless](https://code.claude.com/docs/en/headless), [Gemini headless](https://geminicli.com/docs/cli/headless/).

## 저장·편집·공개

문서 종류별 사이트와 변경할 때마다 새 버전을 DB에 저장합니다. 생성 요청과 작업 기록은 한 트랜잭션으로 저장하고 별도 worker가 실행합니다. 실행 중 종료된 작업은 임대 만료 후 다시 가져옵니다. 여러 화면에서 충돌하면 덮어쓰지 않고 충돌 상태를 보여줍니다.

포트폴리오는 대표 작업·실제 역할·문제 해결 과정을 보여주는 웹사이트, CV는 학력·경력·기술을 정리한 인쇄 문서로 각각 생성합니다. 생성된 프로젝트 그리드와 섹션의 원래 컨테이너를 유지하며, GUI 정렬은 같은 컨테이너 안에서 적용합니다.

GUI는 `data-field`와 `data-section`으로 표시한 제목·소개·본문·목록·섹션 순서와 색상·글꼴·간격을 편집합니다. 자유 코드 영역을 전체 재생성하지 않습니다. 코드 편집도 새 버전으로 저장하며 JS 문법 오류가 있으면 게시를 막고 초안을 보존합니다.

미리보기는 `sandbox="allow-scripts"` iframe에서 실행합니다. 공개 문서는 별도 출처의 신뢰된 상위 문서 안에서 제공하며, CSP로 외부 네트워크·문서 이동을 제한합니다. 게시 버튼을 눌러야 공개됩니다. 공개 프로필 변경 또는 게시 중지 시 이전 공개 주소에서도 더 이상 제공하지 않습니다.

HTML 다운로드는 스크립트를 제외한 정적 문서입니다. 브라우저로 열어 **인쇄 → PDF로 저장**하면 CV를 PDF로 보관할 수 있습니다. 서버에서 직접 PDF를 내보내는 기능은 없습니다.

## 확인한 동작

2026-09-20 Windows/Edge 기준:

- 백엔드 테스트 41개 통과. 별도 환경이 필요한 PostgreSQL 테스트는 기본 실행에서 1개 생략하며, 로컬 PostgreSQL 17.11에서 따로 실행하여 통과했습니다. TypeScript와 변경된 실행 스크립트의 Ruff·PowerShell 구문 검사도 통과했습니다.
- Playwright 25개: 320–1440px 반응형·낮은 PC 사이드바·메뉴·주소 유지·로그인·MD 업로드·캘린더·저장본 편집·팝업 중앙 정렬·스타일 폼 저장·외부 iframe 이동 차단·계정 변경 중 요청 재전송 방지.
- 새 Supabase에 원본의 128개 레코드를 이전하고 전체 필드 일치, RLS·역할 권한, 앱 API 저장·재조회·소유권 경계를 검증했습니다. 원본 SQLite는 보존했습니다.
- 비밀값 없는 별도 폴더에서 개발 도구 PATH 없이 시작, 중단된 Node 설치 복구, 중복 BAT 재사용과 실행 중 환경 보존을 검증했습니다. 완전히 초기화한 다른 PC의 실기기 검증은 별도로 남습니다.
- 실제 로컬 더미 로그인, 새 화면 6종의 모바일·PC API 연동, 실제 생성본 표시 확인.
- 국민대 API 인증, Haiku 초안, Sonnet 포트폴리오·CV 생성 및 DB 저장 성공. 더미 김민준 계정의 각 문서 최신 버전에서 실제 생성 예시를 볼 수 있습니다.
- Claude CLI 설치·옵션 확인. 이 PC는 Claude CLI 로그인이 필요하므로 구독 계정의 실제 생성 성공까지 확인한 상태는 아닙니다.

```powershell
uv run --directory backend pytest -q
uv run --directory backend ruff check app tests ../scripts
npm --prefix frontend run build
npm --prefix frontend run test:e2e
# 실행 중인 로컬 터미널을 닫은 뒤 Windows 종료 검증
uv run --directory backend python ../scripts/verify_launcher.py
```

디자인 예시 이미지를 다시 만들려면 `uv run --directory backend python ../scripts/generate_style_previews.py`, 이어서 `node frontend/scripts/render-style-previews.mjs`를 실행하세요. 렌더링에는 Edge가 필요합니다.

실제 이메일 인증에는 `.env`의 SMTP 또는 HTTPS 메일 설정이 필요합니다. Brevo는 `DUDRI_MAIL_PROVIDER=brevo`, `DUDRI_MAIL_API_KEY`, 인증된 발신 주소인 `DUDRI_SMTP_SENDER`를 사용합니다. 키는 서버에서만 읽으며 로컬 체험에는 메일 설정이 필요 없습니다. Figma 댓글별 반영은 [디자인 기록](docs/design/README.md), 전체 Architecture 범위의 남은 항목은 [구현 기록](IMPLEMENTATION.md)을 참고하세요.

## 배포 준비 상태

무료 배포 구성은 **Vercel Hobby(프런트) + Render Free(API·worker·문서 제공기 한 개 인스턴스) + Supabase Free(DB·Auth)**입니다. `Dockerfile`, `scripts/run_deployed.py`, `render.yaml`, `frontend/vercel.json`, GitHub Actions의 `Deployment check`를 준비했습니다. 로컬 `.env`·DB·런타임·인계 문서는 이미지에 포함하지 않습니다.

Vercel 프로젝트 루트는 `frontend`로 지정하고 `API_ORIGIN`과 `DUDRI_SITE_ORIGIN`을 Render 공개 URL로 설정합니다. Render에는 `DUDRI_APP_ORIGIN`으로 Vercel의 고정 배포 주소를 설정합니다. 인증 쿠키는 프런트 도메인의 API 프록시에서만 사용하고 생성 코드는 별도 출처의 sandbox iframe에서 실행합니다.

유료 플랜·무료 체험 후 자동 유료 전환은 사용하지 않습니다. Render 무료 서비스는 유휴 시 절전되므로 첫 요청에 시간이 걸리고, 작업은 재기동 후 DB에서 복구합니다. 일반 SMTP 포트가 차단되어 Brevo 무료 HTTPS 메일 발송을 연결했습니다. 계정 인증·발신자 설정과 연결 확인 메일의 배달을 검증했으며, 학교 인증 링크의 실제 사용 검증은 남아 있습니다. 플랫폼별 무료 사용량을 넘기지 않도록 결제 수단·추가 과금 설정을 확인해야 합니다.

실제 배포·공개 URL 검증, Google Supabase Auth, 로그인 후 별도 학교 이메일 인증은 아직 미완료입니다. 현재 파일이 있다는 사실만으로 배포나 인증이 완료된 것은 아닙니다.
