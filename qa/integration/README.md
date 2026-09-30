# FE ↔ BE 통합 테스트

`frontend/src/app/page.tsx`가 실제로 보내는 요청(경로·필드·샘플 메시지·행동 버튼 값)을 코드에서 읽어서
실제 백엔드 앱(`rpm-backend/app`)에 보내고, FE가 읽는 응답 필드·오류 형식·CORS가 맞는지 검증합니다.
Gemini 호출만 가짜 추출기로 대체하므로 API 키와 비용이 필요 없습니다.

백엔드 내부 로직(추출·검증·개인정보 탐지 등) 단위 테스트는 `rpm-backend/tests`에 있습니다.

## 실행

Python **3.12**가 필요합니다. 저장소 루트에서 전용 가상환경을 만들고,
설치와 테스트에 같은 Python 실행 파일을 사용합니다. 시스템 Python의 패키지에
의존하면 `google-genai` 누락이나 FastAPI·pydantic-settings 버전 불일치로
테스트 수집 단계부터 실패할 수 있습니다.

### Windows PowerShell

```powershell
py -3.12 -m venv rpm-backend/.venv
.\rpm-backend\.venv\Scripts\python.exe -m pip install --require-hashes -r rpm-backend/requirements-dev.txt
.\rpm-backend\.venv\Scripts\python.exe -m pytest qa/integration -q -ra

# 백엔드 회귀 테스트
Push-Location rpm-backend
try {
    .\.venv\Scripts\python.exe -m pytest -q -ra
} finally {
    Pop-Location
}
```

### macOS / Linux

```bash
python3.12 -m venv rpm-backend/.venv
rpm-backend/.venv/bin/python -m pip install --require-hashes -r rpm-backend/requirements-dev.txt
rpm-backend/.venv/bin/python -m pytest qa/integration -q -ra

# 백엔드 회귀 테스트
(cd rpm-backend && .venv/bin/python -m pytest -q -ra)
```

의존성 버전과 해시는 `rpm-backend/requirements-dev.txt`를 따릅니다.
가상환경은 Git에서 제외되며 커밋하지 않습니다.

- 현재 브랜치의 `page.tsx`에 API 연동 코드가 없으면 FE 관련 테스트는 skip 됩니다.
- 다른 브랜치의 FE로 검증하려면:
  ```bash
  git show origin/feature/fe-api-integration:frontend/src/app/page.tsx > /tmp/page.tsx
  RPM_FE_PAGE=/tmp/page.tsx rpm-backend/.venv/bin/python -m pytest qa/integration -q
  ```
- 배포 도메인의 CORS를 검증하려면 `RPM_FE_ORIGINS=https://a1.scnuoss.net`처럼 지정합니다.

## 검사 항목

| 파일 | 내용 |
|---|---|
| `test_fe_be_contract.py` | FE 호출 경로·요청 필드가 BE 스키마와 일치, FE 샘플이 개인정보 차단에 안 걸림, VERIFIED/NO_ACTION_FOUND/FALLBACK·타임아웃 응답에 FE가 읽는 필드 존재, 모든 행동 버튼이 안내를 받음, 400/404/422/429 오류가 JSON+`error.message`+CORS 헤더를 가짐, CORS preflight |
| `test_env_config.py` | FE가 읽는 환경변수 이름, 백엔드 필수 설정 키가 `.env.example`에 있는지, 템플릿을 그대로 복사해도 백엔드가 기동하는지 |
