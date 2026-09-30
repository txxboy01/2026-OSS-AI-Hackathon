# 🛡️ RPM
> 근거 검증형 AI 피싱 메시지 분석·대응 서비스

**배포 주소:** https://a1.scnuoss.net

의심 메시지를 붙여넣으면 AI가 메시지가 요구하는 행동(링크 접속, 로그인, 송금, 앱 설치 등)을 찾아 **원문 인용과 함께** 보여줍니다. 서버는 AI가 낸 인용이 원문과 정확히 일치하는지 검증하고, 하나라도 틀리면 근거를 모두 버립니다. 피싱 여부를 판정하지 않고, 사용자가 멈추고 확인할 근거와 상황별 대응 방법을 제공합니다.

## 1. 주요 기능
* **행동 요구 추출 (`POST /analyze`):** Gemini가 메시지에서 요구 행동을 추출하고, 서버가 인용 위치를 원문과 대조해 검증합니다.
  * `VERIFIED`: 인용이 원문과 일치
  * `NO_ACTION_FOUND`: 요구 행동 없음 (안전하다는 뜻은 아님)
  * `FALLBACK`: AI 장애·타임아웃·인용 검증 실패. 근거 없이 기본 안내만 표시
* **상황별 대응 안내 (`POST /guidance`):** 사용자가 실제로 한 행동(링크 열기, 계정 입력, 송금, 앱 설치 등)에 맞는 고정 안내를 제공합니다.
* **개인정보 보호:** 개인정보 패턴이 있으면 AI를 호출하기 전에 서버가 요청을 거절합니다. DB·로그인이 없고 입력과 분석 결과를 저장하지 않습니다. 외부 AI 전송은 사용자 동의가 있을 때만 합니다.

## 2. 기술 스택
| 구분 | 사용 기술 |
|---|---|
| 프론트엔드 | Next.js 16, React 19, TypeScript, Tailwind CSS (정적 export) |
| 백엔드 | Python 3.12, FastAPI, Google Gemini API (`google-genai`) |
| 테스트 | Pytest (백엔드·FE↔BE 통합), Playwright + `node --test` (브라우저 회귀) |
| 배포 | 멘토 서버 `a1.scnuoss.net` (정적 파일 + 리버스 프록시) |

## 3. 디렉토리 구조
* `frontend/`: Next.js 화면. 정적 파일(`out/`)로 빌드해 배포
* `rpm-backend/`: FastAPI + Gemini 분석 서버 ([상세 README](rpm-backend/README.md), [OpenAPI](rpm-backend/docs/openapi-v1.yaml))
* `qa/integration/`: 프론트 요청 ↔ 백엔드 응답 계약 통합 테스트 ([실행 방법](qa/integration/README.md))
* `deploy/deploy.sh`: 프론트 빌드·업로드 스크립트
* `docs/`: 협업 규칙 문서

## 4. 로컬 실행
**백엔드** (Python 3.12 필요, 자세한 내용은 [rpm-backend/README.md](rpm-backend/README.md))
```bash
cd rpm-backend
python3.12 -m venv .venv
.venv/bin/pip install --require-hashes -r requirements.txt
cp .env.example .env   # GEMINI_API_KEY, GEMINI_MODEL 입력
.venv/bin/python -m app   # http://127.0.0.1:8000
```

**프론트엔드**
```bash
cd frontend
npm ci
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm run dev   # http://localhost:3000
```

## 5. 배포 구성
현재 `DEV` 브랜치(`64551ff`)가 배포되어 있습니다.

```text
브라우저 ─▶ https://a1.scnuoss.net/       ─▶ 서버 ~/html/ (프론트 정적 파일)
        └▶ https://a1.scnuoss.net/api/*  ─▶ 127.0.0.1:3101 (FastAPI 백엔드, /api 제거 후 전달)
```

**백엔드** (서버에서, 최초 1회)
```bash
git clone -b DEV https://github.com/txxboy01/2026-OSS-AI-Hackathon.git ~/rpm
cd ~/rpm/rpm-backend
python3.12 -m venv .venv && .venv/bin/pip install --require-hashes -r requirements.txt
```
`~/rpm/rpm-backend/.env`에는 아래 4줄만 넣습니다. 설정에 없는 키가 하나라도 있으면 서버가 시작하지 않습니다.
```dotenv
APP_ENV=production
GEMINI_API_KEY=<팀 Gemini 키>
GEMINI_MODEL=gemini-3.5-flash-lite
CORS_ALLOW_ORIGINS=["https://a1.scnuoss.net"]
```
실행과 재시작:
```bash
pkill -f "python -m app"
nohup .venv/bin/python -m app --host 127.0.0.1 --port 3101 --trusted-proxies 127.0.0.1 > ~/rpm.log 2>&1 &
curl -s http://127.0.0.1:3101/health
```

**프론트엔드** (내 PC, 저장소 루트)
1. `.env.example`을 복사해 `.env`를 만들고 서버 접속 정보(`USER_ID`, `PASSWORD`, `HOST`, `WORK_PATH`)와 API 주소를 채웁니다. `.env`는 커밋하지 않습니다.
   ```dotenv
   NEXT_PUBLIC_API_BASE_URL=https://a1.scnuoss.net/api
   ```
2. `bash deploy/deploy.sh`를 실행합니다. 서버의 기존 정적 파일을 지우고 새 빌드로 교체합니다.

API 주소는 빌드할 때 코드에 들어가므로, 바꾸면 다시 빌드해서 배포해야 합니다.

**배포 확인**
* `https://a1.scnuoss.net/api/health`가 JSON으로 응답하는지 확인합니다.
* 사이트에서 "로그인 유도" 샘플을 고르고 외부 AI 동의 후 분석해, 근거 카드가 나오는지 확인합니다.
* 예전 화면이 보이면 브라우저 캐시 때문입니다. `Ctrl+Shift+R`로 새로고침하세요.

## 6. 프로젝트 문서
* [시스템 아키텍처 및 API 명세서](docs/architecture.md)
* [백엔드 명세서](rpm-backend/docs/backend-spec-v1.0.md)
* [백엔드 QA 리포트](rpm-backend/docs/QA_REPORT.md)
* [팀 협업 프로세스](docs/collaboration.md)
* [팀 협업 그라운드 룰](docs/ground-rule.md)
