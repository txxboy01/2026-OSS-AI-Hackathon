# 🏗️ RPM 시스템 아키텍처 및 인터페이스 명세서 (Architecture & API Spec)

본 문서는 **RPM (근거 검증형 AI 피싱 메시지 분석·대응 서비스)**의 시스템 구성, 데이터 흐름, 프론트엔드-백엔드 인터페이스, 배포 구성을 정리합니다.
필드 제약·오류 코드·검증 알고리즘의 상세 규격은 [백엔드 개발 명세서](../rpm-backend/docs/backend-spec-v1.0.md)와 [OpenAPI](../rpm-backend/docs/openapi-v1.yaml)가 기준입니다.

---

## 1. 시스템 개념 구조도 (System Architecture)

RPM은 **AI가 추출하고, 서버가 원문으로 검증하는** 구조입니다. AI 출력을 그대로 보여주지 않고, 원문에서 정확히 찾을 수 있는 인용만 근거로 표시합니다. 피싱 여부나 위험도 점수를 판정하지 않습니다.

```text
[ 사용자 브라우저 (Next.js 정적 페이지) ]
  │
  ├─ 1. 의심 메시지 본문 + 외부 AI 전송 동의
  │    ▼
  │  [ 백엔드 API (FastAPI) ]  POST /analyze
  │    ├─ 요청 검증 (JSON·길이·동의·입력 정책)
  │    ├─ 개인정보 패턴 탐지 ─ 발견 시 400, AI 호출 없음
  │    ├─ 요청 제한 (IP별·전체·동시 실행)
  │    ├─ Gemini API 1회 호출 ─ 요구 행동 유형 + 원문 인용 추출
  │    └─ 인용 검증 ─ 원문과 정확히 일치하지 않으면 전체 폐기 (FALLBACK)
  │    ▼
  ├─ 2. 근거 카드 렌더링 (행동 유형 라벨 + 원문 인용)
  │
  ├─ 3. 사용자가 실제로 한 행동 선택
  │    ▼
  │  [ 백엔드 API (FastAPI) ]  POST /guidance
  │    └─ 고정 정책 매핑 (AI 호출 없음)
  │    ▼
  └─ 4. 상황별 대응 안내 표시
```

---

## 2. 데이터 흐름 (End-to-End Data Flow)

1. **메시지 입력:** 사용자가 개인정보를 지운 의심 메시지를 붙여넣거나 샘플(지원금 사칭, 로그인 유도, 앱 설치 유도)을 고르고, 외부 AI 전송에 동의합니다.
2. **사전 차단:** 백엔드가 입력 형식과 개인정보 패턴(비밀번호·OTP·전화번호·이메일·계좌·주민번호·카드)을 검사합니다. 의심값이 있으면 Gemini를 호출하지 않고 탐지 유형만 반환합니다.
3. **AI 추출:** 원문을 바꾸지 않고 Gemini에 한 번 보내 요구 행동 유형과 인용문을 JSON으로 받습니다. 자동 재시도는 하지 않습니다.
4. **원문 검증:** 모든 인용이 원문의 연속 문자열과 정확히 일치해야 통과합니다. 하나라도 틀리면 정상 인용까지 모두 버리고 `FALLBACK`을 반환합니다. 통과하면 인용 위치(UTF-16)와 서버 고정 라벨을 붙입니다.
5. **대응 안내:** 사용자가 이미 한 행동(링크 열기, 계정 입력, 송금 등)을 고르면 고정 정책에 따라 안내 단계를 반환합니다. 분석 없이도 사용할 수 있습니다.
6. **비저장:** 원문·AI 응답·선택한 행동은 요청 처리 중 메모리에만 있고 DB·로그·브라우저 저장소에 남기지 않습니다.

---

## 3. 모듈별 상세 인터페이스 규격

### Module A: 프론트엔드 (Next.js 16 / React 19 / Tailwind CSS)
* **역할:** 메시지 입력·샘플·동의 UI, 분석 상태별 결과 분기, 근거 카드 렌더링, 행동 선택과 대응 안내 표시
* **빌드:** `output: "export"` 정적 빌드(`frontend/out/`). 백엔드 주소는 빌드 시 `NEXT_PUBLIC_API_BASE_URL`로 주입
* **원칙:** 원문·인용은 일반 텍스트로만 렌더링, 결과는 화면 메모리에만 유지(새로고침 시 사라짐), API 키를 프론트에 두지 않음
* **통신:** REST API (HTTPS / JSON)

### Module B: 백엔드 분석 엔진 (Python 3.12 / FastAPI / Gemini)
| 메서드 | 경로 | 역할 | AI 호출 |
|---|---|---|---|
| GET | `/health` | 프로세스 상태 확인 | 없음 |
| POST | `/analyze` | 요구 행동 추출·인용 검증 | 1회 |
| POST | `/guidance` | 실제 행동별 고정 대응 안내 | 없음 |

배포 환경에서는 프록시가 `/api` 접두어를 떼고 전달합니다. 예: `https://a1.scnuoss.net/api/analyze` → 백엔드 `/analyze`.

#### `POST /analyze`
요청 규격 (Request Payload):

```json
{
  "messageText": "오늘 안에 계정을 확인하지 않으면 이용이 제한됩니다. 아래 링크에서 로그인하세요.",
  "consentToExternalAi": true
}
```

응답 규격 (Response Payload):

```json
{
  "requestId": "00000000-0000-4000-8000-000000000001",
  "apiVersion": "1.0",
  "offsetUnit": "utf16",
  "limitation": "이 결과만으로 피싱 또는 실제 침해 여부를 확정할 수 없습니다.",
  "mode": "ai",
  "status": "VERIFIED",
  "evidence": [
    {
      "id": "e1",
      "type": "PRESSURE",
      "label": "긴급성·불이익 강조",
      "quote": "오늘 안에 계정을 확인하지 않으면 이용이 제한됩니다.",
      "spans": [{ "start": 0, "end": 29 }]
    },
    {
      "id": "e2",
      "type": "ACT_LOGIN",
      "label": "로그인 요구",
      "quote": "아래 링크에서 로그인하세요.",
      "spans": [{ "start": 30, "end": 45 }]
    }
  ],
  "reasonCode": null,
  "notice": "원문에서 확인된 행동 요구입니다. 인용 일치는 의미 해석의 정확성을 보장하지 않습니다."
}
```

| status | mode | 의미 |
|---|---|---|
| `VERIFIED` | `ai` | 1개 이상 인용이 원문과 일치. 행동 유형 해석이나 피싱 여부를 보장하지 않음 |
| `NO_ACTION_FOUND` | `ai` | 추출된 요구 행동 없음. 안전하다는 의미가 아님 |
| `FALLBACK` | `fallback` | AI 장애·타임아웃·차단·출력 오류·인용 불일치. `evidence`는 빈 배열, `reasonCode`에 원인 |

행동 유형(`type`): `ACT_LOGIN`(로그인 요구), `ACT_PAYMENT`(송금·결제 요구), `ACT_APP`(앱 설치 요구), `ACT_LINK`(링크 접속 요구), `ACT_PERSONAL`(개인정보·금융정보 입력 요구), `PRESSURE`(긴급성·불이익 강조)

#### `POST /guidance`
요청 규격:

```json
{ "actions": ["OPENED_LINK", "SUBMITTED_CREDENTIALS"] }
```

* `actions`: `NOT_INTERACTED`, `OPENED_LINK`, `SUBMITTED_CREDENTIALS`, `SUBMITTED_PERSONAL`, `SENT_MONEY`, `INSTALLED_APP`, `UNKNOWN` (`NOT_INTERACTED`, `UNKNOWN`은 단독 선택만 가능)
* 응답: `urgency`(`routine` < `prompt` < `urgent`)와 우선순위 순으로 정렬된 고정 안내 `steps[]`(`code`, `priority`, `title`, `body`)

#### 오류 응답
4xx/5xx는 공통 형식 `{ requestId, apiVersion, error: { code, message, fields, detectedTypes } }`로 반환합니다.
주요 코드: `SENSITIVE_DATA_DETECTED`, `CONSENT_REQUIRED`(400), `PAYLOAD_TOO_LARGE`(413), `INVALID_REQUEST`(422), `RATE_LIMITED`(429, `Retry-After`), `SERVICE_BUSY`(503)

---

## 4. 개인정보 보호 및 제한 (Privacy by Design)

* **무저장:** DB·로그인·분석 이력이 없습니다. 운영 로그에는 원문·인용·IP 없이 정형 필드(시간, requestId, 경로, 상태 코드, 지연 시간)만 남깁니다.
* **사전 차단:** 개인정보 패턴이 보이면 400으로 거절하고 AI를 호출하지 않습니다. 자동 마스킹으로 원문을 바꾸지 않습니다. 정규식 기반이라 모든 개인정보를 잡지는 못합니다.
* **동의:** `consentToExternalAi`가 실제 `true`일 때만 Gemini로 보냅니다.
* **AI 출력 통제:** 추가 필드(`isPhishing`, `riskScore` 등)가 오면 전체를 폐기합니다. 화면 문구(`label`, `notice`, 안내 문구)는 모두 서버 상수입니다.
* **제한:** 메시지 최대 5,000자, 본문 32 KiB, AI 호출 12초 제한. 동시 분석 4개, 분석 IP별 분당 5회·전체 분당 60회, 안내 IP별 분당 30회.

---

## 5. 인프라 및 배포 구성 (Module C)

* **서버 호스팅:** 멘토 제공 서버 `a1.scnuoss.net` (HTTPS·리버스 프록시는 서버 측 제공)
* **배포 브랜치:** `DEV` (현재 배포본 `64551ff`)

```text
브라우저 ─▶ https://a1.scnuoss.net/       ─▶ 서버 ~/html/ (프론트 정적 파일)
        └▶ https://a1.scnuoss.net/api/*  ─▶ 127.0.0.1:3101 (FastAPI, /api 제거 후 전달)
                                                 └▶ Google Gemini API (gemini-3.5-flash-lite)
```

| 구성 | 배포 방법 |
|---|---|
| 프론트엔드 | 내 PC에서 `bash deploy/deploy.sh` → `next build` 정적 파일을 SSH로 `~/html/`에 교체 업로드. 접속 정보와 `NEXT_PUBLIC_API_BASE_URL=https://a1.scnuoss.net/api`는 루트 `.env` |
| 백엔드 | 서버 `~/rpm`에 `DEV` 클론 → Python 3.12 가상환경 → `python -m app --host 127.0.0.1 --port 3101 --trusted-proxies 127.0.0.1` (nohup, 로그 `~/rpm.log`) |
| 비밀 설정 | 서버 `~/rpm/rpm-backend/.env`에 `APP_ENV`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `CORS_ALLOW_ORIGINS` 4개만. 저장소에는 `.env.example`만 커밋 |

단계별 명령은 [README 배포 구성](../README.md#5-배포-구성)을 참고하세요. Docker 배포용 `rpm-backend/Dockerfile`, `compose.yaml`, nginx·systemd 예시도 저장소에 있지만, 현재 a1 서버에서는 위의 가상환경 방식으로 실행합니다.

---

## 6. 개발·검증 파이프라인

* **브랜치:** `feature/파트-기능명` → `DEV`로 PR, 1인 이상 Approve 후 머지 → 배포 후 `DEV`를 `main`에 반영 ([협업 규칙](collaboration.md))
* **테스트:** CI(GitHub Actions)는 아직 없으며 로컬에서 실행합니다.
  * 백엔드 단위·API 테스트: `rpm-backend/tests` (Pytest)
  * FE↔BE 계약 통합 테스트: `qa/integration` (Pytest, [실행 방법](../qa/integration/README.md))
  * 브라우저 회귀 테스트: `frontend/tests/browser` (Playwright + `node --test`)
  * 테스트에서는 Gemini만 테스트용 추출기로 바꾸고, 나머지 검증 로직은 실제 코드를 사용합니다.
