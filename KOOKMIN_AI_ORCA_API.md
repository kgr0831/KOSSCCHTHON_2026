# 국민대학교 소프트웨어융합대학 AI: Orca와 프로그램에서 사용하기

확인일: 2026-09-19 · 대상: `https://ai.cs.kookmin.ac.kr/dashboard/overview`

## 먼저 구분할 주소

| 용도 | 주소 |
| --- | --- |
| 웹 관리 화면 | `https://ai.cs.kookmin.ac.kr/dashboard/overview` |
| API 기본 주소 | `https://ai.cs.kookmin.ac.kr/v1` |
| 모델 목록 | `GET https://ai.cs.kookmin.ac.kr/v1/models` |
| 대화 API | `POST https://ai.cs.kookmin.ac.kr/v1/chat/completions` |

관리 화면 주소는 API 주소가 아니다. 이 사이트의 HTML 제목과 설명에서 **New API 게이트웨이**임을 확인했다. Orca 내장 브라우저에서 관리 화면을 열자 `/sign-in?redirect=%2Fdashboard%2Foverview`로 이동했고, 키 없이 `GET /v1/models`를 호출하자 HTTP 401을 받았다. 따라서 아래의 키 발급과 실제 모델 호출은 계정 소유자가 로그인한 뒤 완료해야 한다. New API의 [API 사용 안내](https://docs.newapi.pro/en/docs/guide/feature-guide/user/api)는 `/v1` 기본 주소, Bearer 인증 및 위 엔드포인트를 설명한다.

## 1. 사이트에서 API 키 준비

1. [대시보드](https://ai.cs.kookmin.ac.kr/dashboard/overview)에 본인 계정으로 로그인한다.
2. 왼쪽 메뉴의 **API Keys** 또는 `/keys`에서 애플리케이션용 키를 만든다. 키의 사용량 한도, 만료일, 허용 모델과 IP 제한을 용도에 맞게 지정한다. 메뉴 이름과 사용 가능 여부는 이 서버의 설정에 따라 다를 수 있다. [New API 키 관리 안내](https://docs.newapi.pro/en/docs/guide/feature-guide/user/token)
3. 사용 가능한 **정확한 모델 ID**를 사이트의 모델 목록에서 확인하거나, 발급한 키로 아래의 모델 목록 API를 조회한다. 예제의 `<모델_ID>`를 임의의 모델명으로 대체하지 않는다.
4. 키는 프로젝트 파일, Git, 채팅, 스크린샷에 저장하지 않는다. 웹 로그인 세션이나 관리용 access token 대신 **API Keys 화면에서 발급한 모델 호출용 키**를 사용한다. [New API 키 안내](https://docs.newapi.pro/en/docs/guide/feature-guide/user/token), [access token 구분](https://docs.newapi.pro/en/docs/guide/feature-guide/user/personal-setting)

Windows PowerShell에서 키를 명령 기록에 남기지 않고 현재 터미널의 환경 변수에 넣는 예시는 다음과 같다. 이 변수는 터미널을 닫으면 사라진다.

```powershell
$secret = Read-Host 'Kookmin AI API key' -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
    $env:KOSS_AI_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    Remove-Variable secret, ptr
}

$headers = @{ Authorization = "Bearer $env:KOSS_AI_API_KEY" }
(Invoke-RestMethod 'https://ai.cs.kookmin.ac.kr/v1/models' -Headers $headers).data |
    Select-Object -ExpandProperty id
```

Orca 터미널이 Bash라면 같은 세션에서 다음처럼 키를 입력할 수 있다. 입력한 값은 화면과 명령 기록에 표시되지 않는다.

```bash
read -r -s -p 'Kookmin AI API key: ' KOSS_AI_API_KEY
printf '\n'
export KOSS_AI_API_KEY
curl -fsS -H "Authorization: Bearer $KOSS_AI_API_KEY" \
  'https://ai.cs.kookmin.ac.kr/v1/models'
```

## 2. Orca에서 사용

### 웹 관리 화면을 Orca 브라우저에 열기

현재 `C:\koss2026` 폴더는 Orca에 `koss2026` 프로젝트로 등록되어 있다. 해당 프로젝트의 내장 브라우저 탭도 이 문서 작성 중에 생성했다. Orca에서 `koss2026`을 선택하고 브라우저 탭을 열어 로그인하면 된다. Chrome의 로그인 상태가 Orca 내장 브라우저로 자동 이전된다고 가정하지 않는다.

Orca 터미널에서는 같은 작업을 다음처럼 할 수 있다. `orca` 명령이 인식되지 않으면 Orca의 **Settings → General → Orca CLI**에서 셸 명령 등록 상태를 확인한다.

```powershell
orca status --json
orca tab list --json
# 탭이 없을 때만 실행
orca tab create --url 'https://ai.cs.kookmin.ac.kr/dashboard/overview' --json
orca snapshot --json
```

이 등록은 **사이트를 프로젝트의 브라우저 탭으로 여는 것**이다. 이를 실행해도 New API가 Orca 에이전트의 모델 공급자로 자동 지정되지는 않는다. `snapshot`에서 로그인 화면이 보이면 Orca 브라우저에서 직접 로그인한다. Orca CLI 명령의 최신 사용법은 실행 중인 버전에서 `orca skills get orca-cli`로 확인할 수 있다.

### Orca에서 실행하는 Codex에 모델 공급자로 연결하기

Orca 1.4.197의 **Settings → AI provider accounts**는 주로 에이전트 계정을 관리하는 화면이다. Codex가 이 게이트웨이를 쓰게 하려면 **Codex의 사용자별 설정**에 사용자 정의 공급자를 등록하고, Orca 터미널에서 그 프로필로 Codex를 실행한다. OpenAI 공식 문서에 따르면 공급자 설정은 프로젝트의 `.codex/config.toml`에 넣어도 무시되므로, 실제 Codex가 사용하는 `CODEX_HOME/config.toml`에 넣어야 한다. `CODEX_HOME`이 없으면 기본 위치는 사용자 홈의 `.codex/config.toml`이다. Orca가 관리하는 Codex 계정에서는 `CODEX_HOME`이 다른 폴더를 가리킬 수 있으므로 **Codex를 실행할 Orca 터미널에서** `$env:CODEX_HOME`을 먼저 확인한다. [OpenAI Docs: 고급 설정](https://developers.openai.com/codex/config-advanced)

기존 사용자 설정의 다른 항목은 유지하면서 다음 예시를 추가한다. `<모델_ID>`는 앞 단계에서 확인한 실제 값이다.

```toml
[model_providers.kookmin_ai]
name = "Kookmin AI"
base_url = "https://ai.cs.kookmin.ac.kr/v1"
env_key = "KOSS_AI_API_KEY"
wire_api = "responses"

[profiles.kookmin_ai]
model_provider = "kookmin_ai"
model = "<모델_ID>"
```

같은 Orca 터미널에서 위 환경 변수를 설정한 뒤 `codex --profile kookmin_ai`를 실행한다. Orca가 이미 실행 중인 다른 Codex 세션에는 이 터미널의 환경 변수가 자동 전달되지 않을 수 있다. Orca 채팅의 모델 선택에 표시되는지 여부도 이 문서 작성 시에는 확인하지 않았다. [OpenAI Docs: 사용자 정의 공급자](https://developers.openai.com/codex/config-advanced), [설정 항목](https://developers.openai.com/codex/config-reference)

Codex는 현재 사용자 정의 공급자에 **Responses API**를 사용한다. New API 문서에도 `POST /v1/responses`가 있지만, 이 서버의 키와 선택한 모델이 Codex에 필요한 스트리밍·도구 호출까지 지원하는지는 인증된 테스트가 필요하다. `GET /v1/models`와 아래의 대화 API가 성공하더라도 Codex 호환성이 확정되는 것은 아니다. [New API API 안내](https://docs.newapi.pro/en/docs/guide/feature-guide/user/api), [OpenAI Docs: `wire_api`](https://developers.openai.com/codex/config-reference)

## 3. 프로그램에서 API 호출

아래 Python 예제는 추가 패키지 없이 표준 라이브러리만 쓴다. `KOSS_AI_API_KEY`는 앞에서 설정한 환경 변수에서 읽고, `KOSS_AI_MODEL`에는 모델 목록에서 확인한 ID를 넣는다. 코드와 키를 함께 저장하지 않는다.

```powershell
$env:KOSS_AI_MODEL = '<모델_ID>'
python .\example.py
```

`example.py`의 내용:

```python
import json
import os
import urllib.error
import urllib.request

url = "https://ai.cs.kookmin.ac.kr/v1/chat/completions"
payload = {
    "model": os.environ["KOSS_AI_MODEL"],
    "messages": [{"role": "user", "content": "안녕하세요. 한 문장으로 답해주세요."}],
}
request = urllib.request.Request(
    url,
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Authorization": f"Bearer {os.environ['KOSS_AI_API_KEY']}",
        "Content-Type": "application/json",
    },
    method="POST",
)

try:
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    print(result["choices"][0]["message"]["content"])
except urllib.error.HTTPError as error:
    # 응답 본문에는 계정 정보가 들어갈 수 있으므로 상태 코드만 출력한다.
    raise SystemExit(f"API 요청 실패: HTTP {error.code}") from error
```

실행 파일을 프로젝트에 추가할 필요가 없다면 위 내용을 임시 파일이나 애플리케이션 코드에 적용하면 된다. 대화 API의 `model`·`messages` 형식과 Bearer 인증은 [New API 공식 사용 예시](https://docs.newapi.pro/en/docs/guide/feature-guide/user/api)에 따른다. 401이면 키와 인증 헤더, 403이면 키의 모델·그룹·IP 제한, `model_not_found`라면 모델 ID를 먼저 확인한다.

## 확인한 범위

- Orca 내장 브라우저 탭 등록 및 로그인 화면 표시: 확인함.
- 사이트의 API 기본 경로 `GET /v1/models`: 인증 없이 HTTP 401 반환 확인함.
- API 키 발급, 인증된 모델 목록·대화 호출, Codex 프로필의 실제 모델 응답: 사용자 키가 없어 실행하지 않음.
