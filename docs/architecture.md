# 🏗️ RPM 시스템 아키텍처 및 인터페이스 명세서 (Architecture & API Spec)

본 문서는 **RPM (Reverse-trace, Password-isolate, Mitigate)**의 시스템 계층 구조, 데이터 파이프라인 흐름, 프론트엔드-백엔드 간 상호작용 규격을 정의합니다.

---

## 1. 시스템 개념 구조도 (System Architecture)

RPM은 **서버 측 AI 비정형 분석 파이프라인**과 **클라이언트 측 Zero-Knowledge 암호학 엔진**이 완전히 분리된 하이브리드 아키텍처를 채택합니다.

```text
[ 사용자 브라우저 (Next.js) ]
  │
  ├─ 1. 의심 메일 데이터 (수신 메일 주소 + 본문/헤더)
  │    ▼
  │  [ 백엔드 API (FastAPI) ]
  │    │
  │    ├─ RFC 5233 서브어드레싱 파서 (1차 규칙 기반 필터)
  │    └─ OpenAI API (GPT-4o-mini) 침해 헤더/패턴 역추적
  │    │
  │    ▼ (구조화된 JSON 리포트 응답)
  │
  ├─ 2. 진원지 판정 결과 렌더링 ("TVING 유출로 인한 2차 공격 식별")
  │
  └─ 3. 로컬 능동 방어 (Web Crypto API)
       ├─ 사용자 마스터 PIN + 진원지 도메인(Salt) 입력
       └─ 브라우저 내 PBKDF2 10만 회 연산 ➔ 고유 격리 암호 즉시 도출
          ※ 서버로 PIN 및 도출 암호 전송 절대 차단 (Zero-Knowledge)


2. 데이터 흐름 (End-to-End Data Flow)
침해 메일 유입 및 수집: 사용자가 수신한 의심 이메일 주소(예: user+tving@gmail.com) 및 본문/헤더를 프론트엔드에 입력합니다.

비동기 AI 역추적 (Reverse-trace): 백엔드(FastAPI)가 서브어드레싱 태그를 1차 정규화하고, LLM을 통해 스팸 발송 도메인과 매칭하여 침해 진원지(Leak Source)를 확정합니다.

위협 분석 리포트 전달: 확정된 진원지, 신뢰도, 권고 대응 절차가 담긴 JSON 리포트가 프론트엔드로 반환됩니다.

무저장 격리 암호 생성 (Password-isolate): 프론트엔드는 도출된 진원지 식별값과 사용자의 마스터 PIN을 결합하여, 서버 전송 없이 브라우저 단독으로 암호를 재생성합니다.

연쇄 피해 원천 완화 (Mitigate): 티빙 등 단일 서비스가 침해되더라도 타 서비스 계정으로의 연쇄 탈취(크리덴셜 스터핑) 위협을 수학적으로 차단합니다.

3. 모듈별 상세 인터페이스 규격
Module A: 프론트엔드 대시보드 (Next.js 14 / TailwindCSS)
역할: 스팸 입력 폼 제공, 실시간 위협 리포트 렌더링, 클라이언트 암호 연산 오케스트레이션

통신 프로토콜: REST API (HTTPS / JSON)

Module B: 백엔드 역추적 엔진 (FastAPI / OpenAI)
엔드포인트: POST /api/v1/analyze

요청 규격 (Request Payload):

JSON
{
  "recipient_email": "hong+tving@gmail.com",
  "raw_email_body": "회원님의 네이버 계정 해외 로그인 시도가 감지되었습니다...",
  "received_headers": "Received: from mail.attacker-server.com ..."
}
응답 규격 (Response Payload):

JSON
{
  "status": "success",
  "analysis": {
    "leak_source": "tving.com",
    "confidence_score": 0.98,
    "leak_tag": "tving",
    "threat_type": "CREDENTIAL_STUFFING",
    "summary": "티빙 가입 시 사용된 서브어드레싱 태그가 스팸 발신처와 연계되어 유출 진원지로 판정되었습니다.",
    "recommended_actions": [
      "티빙 계정 비밀번호 즉시 갱신",
      "유사 암호를 사용 중인 타 서비스 암호 격리 분리"
    ]
  },
  "timestamp": "2026-09-20T17:00:00Z"
}
4. Module C: 클라이언트 보안 모듈 (Zero-Knowledge Web Crypto)
핵심 철학: Zero-Storage, Zero-Transmission (서버에 암호나 마스터키를 저장하지 않음)

알고리즘 규격:

Function: PBKDF2-HMAC-SHA256

Iterations: 100,000 회 (W3C 권장 브라우저 보안 표준)

Salt: 진원지 도메인 문자열 (leak_source, 예: tving.com)

Key Material: 사용자가 입력한 Master PIN (6자리 이상)

Output: 16자리 영문 대소문자/숫자/특수문자 조합 격리 패스워드

5. 인프라 및 배포 파이프라인 (Module D)
컨테이너 환경: Docker / Docker Compose

서버 호스팅: AWS 

CI/CD 파이프라인:

feature/* 브랜치 단위 테스트 통과

dev 브랜치 PR 머지 시 통합 빌드 검증

main 브랜치 머지 시 AWS 서버 자동 배포 (GitHub Actions CD)