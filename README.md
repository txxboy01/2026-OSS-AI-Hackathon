# 🛡️ RPM (Reverse-trace, Password-isolate, Mitigate)
> 스팸 메일 한 통으로 유출 진원지를 역추적하고, 연쇄 해킹을 즉시 잠그는 AI 능동 방어 플랫폼

## 1. 프로젝트 배경 (Background)
* **실화 기반 위협 해결:** 티빙 3,954만 계정 유출 사태로 촉발된 크리덴셜 스터핑(연쇄 탈취) 원천 차단
* 핵심 동작 원리:
  1. R (Reverse-trace): RFC 5233 서브어드레싱 및 비정형 헤더 AI 심층 분석을 통한 침해 진원지 식별
  2. P (Password-isolate):** Web Crypto API(PBKDF2)를 활용한 브라우저 로컬 암호 격리 도출
  3. M (Mitigate):** 서버 DB 저장 없는 Zero-Knowledge 설계를 통한 2차 피해 전면 차단

## 2. 프로젝트 문서 바로가기
* [시스템 아키텍처 및 API 명세서](docs/architecture.md)
* [팀 협업 프로세스](docs/collaboration.md)
* [팀 협업 그라운드 룰](docs/ground-rules.md)

## 3. 디렉토리 구조
* `frontend/`: Next.js SPA 대시보드
* `backend/`: FastAPI & OpenAI 분석 서버
* `docs/`: 시스템 명세 및 협업 규칙