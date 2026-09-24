# RPM FastAPI 백엔드

기획서와 `RPM_백엔드_개발_명세서_v1.0.md`에 맞춰 만든 Python 3.12 백엔드입니다. 원문 행동 요구를 Gemini로 추출한 뒤 서버가 인용을 검증합니다. 피싱 여부나 실제 침해 여부를 판정하지 않습니다.

**포함:** 세 API, Gemini 실제 연동 코드, 엄격한 JSON/원문 검증, 개인정보 입력 차단, 고정 대응 안내, 요청·동시 실행 제한, 개인정보 없는 운영 로그, 자동 테스트, OpenAPI, 시연 샘플, 배포 설정 예제.

**범위:** 백엔드와 Next.js 연동 계약입니다. Next.js 화면은 포함하지 않습니다. DB·로그인·분석 이력 저장을 사용하지 않습니다. 실제 Gemini 서버 호출과 Docker/HTTPS 배포는 이 환경에서 실행하지 않았습니다. 자동 테스트 결과와 확인 범위는 `docs/QA_REPORT.md`에 있습니다.

## 1. 가장 빠른 실행

압축을 풀어 `rpm-backend` 폴더로 이동하세요. Python **3.12**가 필요합니다. 명령은 macOS/Linux 기준이며 Windows는 아래 별도 명령을 사용합니다.

```bash
cd rpm-backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements.txt
cp .env.example .env
```

`.env`를 편집해 다음 두 값을 입력합니다. API 키는 채팅·프론트 코드·Git 저장소에 넣지 않습니다.

```dotenv
GEMINI_API_KEY=본인의_Gemini_API_키
GEMINI_MODEL=본인_계정에서_사용_가능한_gemini_모델_ID
```

모델은 구조화 JSON 출력을 지원해야 하며 `gemini-`로 시작하는 실제 모델 ID를 사용합니다. 위 설명용 문자열을 그대로 실행하지 마세요. 모델을 임의로 지정하거나 가짜 AI 응답으로 대신하지 않습니다. 선택 모델의 가용성·쿼터·요금은 본인 계정에서 확인해야 합니다.

```bash
python -m app
```

- 서버: `http://127.0.0.1:8000`
- 상태 확인: `http://127.0.0.1:8000/health`
- 개발 API 문서: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

키·모델이 없으면 기동이 실패합니다. `/health`는 Gemini를 호출하지 않으므로 200 응답만으로 키·모델의 유효성이 확인되지는 않습니다. `APP_ENV=test`는 테스트 코드의 명시적인 추출기 주입에서만 사용하며 실행 서버 모드로 사용할 수 없습니다.

Windows PowerShell에서는 가상환경 활성화 대신 실행 경로를 직접 지정해도 됩니다.

```powershell
cd rpm-backend
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.txt
Copy-Item .env.example .env
# 편집기로 .env의 API 키와 모델을 입력한 뒤 실행
.venv\Scripts\python.exe -m app
```

`uv`를 쓰는 경우 `uv sync --frozen --no-dev`로 고정 의존성을 설치하고 `uv run --no-sync python -m app`으로 실행할 수 있습니다. `uv.lock`과 pip용 requirements 파일 모두 포함되어 있습니다.

## 2. API 사용

| 메서드 | 경로 | 역할 |
|---|---|---|
| GET | `/health` | 프로세스 상태 확인, Gemini 호출 없음 |
| POST | `/analyze` | 비식별 원문의 행동 요구 추출·인용 검증 |
| POST | `/guidance` | 사용자가 실제로 한 행동에 따른 고정 안내 |

### 분석

아래 본문은 가상 예시입니다. `consentToExternalAi: true`는 본문을 외부 Gemini API로 보내는 것에 동의한다는 의미입니다.

```bash
curl -sS http://127.0.0.1:8000/analyze \
  -H 'Content-Type: application/json' \
  --data-raw '{"messageText":"오늘 안에 계정을 확인하지 않으면 이용이 제한됩니다. 아래 링크에서 로그인하세요.","consentToExternalAi":true}'
```

200 응답은 `status`를 확인합니다.

| status | 의미 |
|---|---|
| VERIFIED | 한 개 이상 인용이 원문과 정확히 일치 |
| NO_ACTION_FOUND | 추출된 항목 없음. 안전하다는 의미가 아님 |
| FALLBACK | AI 장애·타임아웃·출력/인용 검증 실패. evidence는 빈 배열 |

인용이 한 개라도 틀리면 모든 근거를 폐기합니다. `VERIFIED`도 행동 유형 해석이나 실제 피싱 여부의 정확성을 보장하지 않습니다.

### 대응 안내

```bash
curl -sS http://127.0.0.1:8000/guidance \
  -H 'Content-Type: application/json' \
  --data-raw '{"actions":["OPENED_LINK","SUBMITTED_CREDENTIALS"]}'
```

`NOT_INTERACTED`, `OPENED_LINK`, `SUBMITTED_CREDENTIALS`, `SUBMITTED_PERSONAL`, `SENT_MONEY`, `INSTALLED_APP`, `UNKNOWN`을 지원합니다. NOT_INTERACTED와 UNKNOWN은 각각 단독으로만 선택합니다. 메시지가 요구한 행동과 사용자가 실제로 수행한 행동은 별개입니다. 이 API는 사전 분석이나 외부 AI 동의가 필요하지 않습니다.

### 입력과 제한

- 메시지 최대 5,000 Unicode 코드 포인트, JSON 본문 최대 32 KiB.
- 순수 UTF-8 `application/json`만 허용. 압축 본문과 추가 필드는 거절합니다.
- 개인정보 패턴 발견 시 400으로 거절하고 Gemini를 호출하지 않습니다. 자동 마스킹으로 원문을 바꾸지 않습니다.
- 개인정보 검사는 정규식 기반 보조 장치이며, 모든 이름·주소·난독화 정보를 검출하지 못합니다. 사용자가 비밀정보를 먼저 삭제해야 합니다.
- 외부 호출은 요청당 최대 한 번, 12초 제한. 자동 재시도 없음.
- 단일 프로세스에서 동시 분석 4개, 분석 IP별 분당 5개, 전체 분당 60개, 안내 IP별 분당 30개 token bucket.
- 429/503은 Retry-After를 제공하지만 사용자 확인 없이 메시지를 재전송하면 안 됩니다.
- 깊이 32를 넘는 중첩 JSON은 파싱 방어를 위해 거절합니다. 정상 요청 스키마는 이 깊이를 사용하지 않습니다.

자세한 필드·오류 코드는 `docs/openapi-v1.yaml`과 `docs/backend-spec-v1.0.md`를 참고하세요.

## 3. Next.js 연결

프론트 개발 서버의 origin을 `.env`에 등록합니다.

```dotenv
CORS_ALLOW_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]
```

프론트에서는 서버 주소만 공개 환경변수로 사용하고 Gemini 키를 넣지 않습니다. 요청은 다음처럼 연결할 수 있습니다.

```typescript
const submittedMessage = messageText; // 요청 당시 원문 스냅샷
const response = await fetch(`${API_BASE_URL}/analyze`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  cache: "no-store",
  body: JSON.stringify({
    messageText: submittedMessage,
    consentToExternalAi: true, // UI에서 실제 동의를 확인한 후에만
  }),
});
const contentType = response.headers.get("content-type") ?? "";
if (!contentType.includes("application/json")) {
  throw new Error("서버 연결 상태를 확인해 주세요.");
}
const result = await response.json();
if (!response.ok) {
  throw new Error(result.error?.message ?? "요청을 처리하지 못했습니다.");
}
// VERIFIED/NO_ACTION_FOUND/FALLBACK 별도로 처리
```

- `spans[].start/end`는 **UTF-16, 0 시작, end 제외**입니다. `submittedMessage.slice(start,end)`가 quote와 같아야 합니다.
- 원문·quote·notice는 React의 일반 텍스트 표현식으로 렌더링합니다. `dangerouslySetInnerHTML`, Markdown 자동 렌더링, URL 자동 링크화는 사용하지 않습니다.
- 편집 중인 최신 텍스트 대신 제출 당시 스냅샷을 하이라이트합니다. 이전 요청 응답이 늦게 도착하면 무시합니다.
- 분석 버튼 중복 클릭을 막고 취소 시 AbortController를 사용합니다.
- 원문·결과·actions를 localStorage, IndexedDB, URL, 콘솔 로그, 세션 리플레이 도구에 저장하지 않습니다.
- `mode=fallback`일 때 기존 근거 카드를 지웁니다. `/guidance`는 분석 실패 시에도 사용할 수 있습니다.

## 4. API 키 없이 자동 테스트

자동 테스트는 Gemini 대신 테스트 추출기 또는 모의 HTTP transport를 사용합니다. 실제 외부 AI 호출이나 비용이 발생하지 않습니다.

```bash
source .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.txt
python -m pytest -q
python -m pytest --cov=app --cov-report=term-missing
ruff check app tests scripts
```

테스트는 명세의 입력·오류·원문 일치·PII·안내·CORS·요청 제한·동시성·연결 취소·스키마를 확인합니다. 실제 SDK를 쓰는 모의 HTTP 테스트도 포함되어 있어 API 주소, 요청 body, 단일 호출, 차단/429/5xx/타임아웃 처리까지 검사합니다. 테스트 성공이 실제 모델의 추출 품질을 보장하지는 않습니다.

실제 모델 평가는 키·모델 설정 후 다음 명령으로 별도 실행합니다. 가상 fixture 7종을 사용하며 시연 샘플 3개는 각각 3회, 나머지 4개는 각각 1회, **총 13회 호출**합니다. API 비용이 발생할 수 있습니다.

```bash
python -m scripts.evaluate_live --allow-external-ai
```

이 명령은 정형 평가 결과만 출력하고 원문·인용·키·공급자 오류 본문은 출력하지 않습니다. 실패 fixture가 있으면 종료 코드 1입니다. 테스트용 고정 근거는 `tests/fixtures/expected_samples.json`, 실제 모델 평가 기준은 `tests/fixtures/gold_cases.json`에 있습니다.

## 5. 운영 실행

```dotenv
APP_ENV=production
GEMINI_API_KEY=운영_키
GEMINI_MODEL=실제_사용_모델_ID
CORS_ALLOW_ORIGINS=["https://실제-프론트-도메인"]
ENABLE_DOCS=false
```

운영 origin은 경로와 마지막 `/` 없이 정확한 HTTPS origin으로 입력합니다. `.env`는 저장소와 이미지에 포함하지 않습니다. 키는 가능하면 배포 환경의 비밀 변수로 주입합니다.

기본 실행 명령 `python -m app`은 단일 worker, access log 비활성화, 정형 이벤트 로그만 출력하도록 구성합니다. 기본 Uvicorn 명령으로 바꾸면 access log나 traceback 설정도 함께 검토해야 합니다. 사용자 IP·원문·AI 출력·사용자 행동은 로그에 포함하지 않습니다.

### HTTPS 프록시와 systemd

`deploy/nginx.conf.example`의 도메인·인증서 경로를 실제 값으로 바꿉니다. Nginx가 같은 호스트의 127.0.0.1에서 접근하는 경우 다음처럼 실행합니다.

```bash
python -m app --host 127.0.0.1 --port 8000 --trusted-proxies 127.0.0.1,::1
```

`deploy/rpm-backend.service.example`에는 `/opt/rpm-backend` 및 전용 `rpm` OS 계정을 사용하는 예제가 있습니다. 설치 경로·계정을 실제 서버에 맞춘 뒤 등록하세요. 운영 `CORS_ALLOW_ORIGINS`와 HTTPS 인증서는 별도 설정이 필요합니다.

임의 클라이언트의 X-Forwarded-For를 신뢰하지 않습니다. `--trusted-proxies`에는 실제 바로 앞 프록시 IP/CIDR만 입력하며 `*`는 금지합니다. 여러 worker나 인스턴스를 사용하려면 현재 메모리 한도를 게이트웨이 전체 한도로 옮겨야 합니다.

### Docker Compose

Python 3.12 환경을 만들기 어려운 서버에서는 Docker 배포 파일을 사용할 수 있습니다. GPU·NVIDIA 런타임이 필요하지 않습니다. 이 패키지는 Docker 엔진이 없는 환경에서 작성되어 실제 이미지 빌드는 별도 확인이 필요합니다.

`.env`에 키·모델·운영 HTTPS origin을 설정한 뒤 실행합니다.

```bash
docker compose up -d --build
```

API 포트는 호스트의 `127.0.0.1:8000`에만 바인딩됩니다. 외부 공개는 HTTPS 프록시를 통해 설정합니다. 컨테이너는 비root 사용자, 읽기 전용 파일 시스템, core dump 비활성화로 실행합니다.

Docker 앞 프록시를 쓸 때 Uvicorn에서 보이는 프록시 peer IP는 환경마다 다를 수 있습니다. 필요한 경우 **실제 확인한 IP만** 셸의 `TRUSTED_PROXY_IPS`에 설정해 Compose를 실행하세요. 미설정 상태에서는 전달 헤더를 신뢰하지 않아 프록시를 거친 사용자가 같은 rate bucket에 묶일 수 있습니다. 이 변수는 Compose 실행 셸용이며 앱 `.env`에 추가하지 않습니다.

### 로그 보존

앱은 로그 파일을 만들지 않고 허용 필드만 stdout으로 출력합니다. 7일 보존·삭제는 호스팅 플랫폼, journald 또는 로그 수집기에서 설정해야 합니다. 제공 Compose 설정은 **용량 기준 회전만** 적용하며 7일 만료를 대신하지 않습니다. 원문을 수집하는 APM·프록시 body logging·브라우저 세션 리플레이를 켜면 앱 비저장 설계만으로 보호할 수 없습니다.

## 6. 파일 구성

| 경로 | 내용 |
|---|---|
| `app/main.py` | FastAPI 생성, 세 API, 요청 취소·오류 처리 |
| `app/extractor.py`, `prompts.py` | Gemini 단일 호출, 고정 지시·출력 스키마 |
| `app/validator.py` | JSON·인용 검증, 중복 제거·UTF-16 위치 |
| `app/redactor.py` | 로컬 개인정보 탐지 |
| `app/guidance.py`, `fallback.py` | 고정 안내와 실패 응답 |
| `app/limits.py` | 메모리 token bucket·동시 실행 제한 |
| `app/config.py`, `schemas.py`, `errors.py` | 설정·전송 모델·정형 오류 |
| `app/json_io.py`, `middleware.py`, `logging_config.py` | 입력 경계·CORS 보조·비저장 로그 |
| `tests/`, `samples/` | 자동 테스트, 가상 샘플·평가 기준 |
| `scripts/evaluate_live.py` | 명시적으로 실행하는 실제 AI 평가 |
| `docs/` | 원본 명세·API 계약·검증 보고서 |
| `Dockerfile`, `compose.yaml`, `deploy/` | 운영 배포 예제 |
| `uv.lock`, `requirements*.txt` | 버전·해시가 고정된 의존성 |

## 7. 문제 해결

| 현상 | 확인할 내용 |
|---|---|
| 설정 오류로 기동 실패 | `.env`의 키·gemini 모델 ID·origin, Python 3.12, 오타가 있는 환경변수 |
| health 정상인데 AI_UNAVAILABLE | 키 권한·모델 ID·쿼터·외부 네트워크. health는 외부 AI를 확인하지 않음 |
| AI_TIMEOUT | API 응답 지연. 자동 재시도하지 않으며 사용자 수동 재시도 |
| EVIDENCE_INVALID | AI 인용 불일치. 검증을 끄지 말고 fixture로 프롬프트·모델 평가 |
| 400 SENSITIVE_DATA_DETECTED | 표시된 정보 유형의 실제 값을 삭제 후 재제출 |
| 422 INVALID_REQUEST | boolean/string 구분, 필수·추가 필드, 행동 조합 |
| 429 또는 503 | 요청 한도 또는 동시 분석 수 확인. Retry-After 이후 수동 재시도 |
| 브라우저에서 응답을 읽지 못함 | 실제 프론트 origin과 CORS 설정, 프록시·HTTPS 주소 |

## 8. 확인한 공식 문서

- [Google Gen AI Python SDK](https://googleapis.github.io/python-genai/) — 비동기 생성·구조화 출력 설정.
- [공식 SDK HTTP 클라이언트](https://github.com/googleapis/python-genai/blob/main/google/genai/_api_client.py) — attempts는 최초 호출 포함 횟수. 이 구현은 1회로 고정하며 모의 HTTP 테스트로 확인.
- [Gemini 데이터 처리 조건](https://ai.google.dev/gemini-api/terms) — RPM의 비저장 원칙과 외부 제공자의 데이터 처리는 별개.

버전 변경 시 lockfile, 실제 SDK 모의 HTTP 테스트, 수동 모델 평가를 함께 갱신하세요.
