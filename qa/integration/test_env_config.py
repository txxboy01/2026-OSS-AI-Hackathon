"""FE·BE·배포 설정이 서로 같은 이름과 값을 쓰는지 검증한다."""

import re

from app.config import Settings
from conftest import BACKEND, REPO

REQUIRED_BACKEND_KEYS = {"GEMINI_API_KEY", "GEMINI_MODEL", "CORS_ALLOW_ORIGINS"}


def env_keys(path):
    return set(re.findall(r"^([A-Z_][A-Z0-9_]*)=", path.read_text(encoding="utf-8"), re.M))


def test_fe_api_url_env_var_is_documented(fe):
    """page.tsx가 읽는 환경변수 이름이 .env.example에 있어야 배포 시 BE 주소가 주입된다."""
    documented = env_keys(REPO / ".env.example")
    missing = fe.api_env_vars - documented
    assert not missing, f"FE가 읽지만 .env.example에 없는 변수: {missing} (문서에는 {documented & {'NEXT_PUBLIC_API_URL'} or '없음'})"


def test_backend_env_example_exists():
    """rpm-backend/README.md는 `cp .env.example .env`로 시작하라고 안내한다."""
    assert (BACKEND / ".env.example").exists()


def test_backend_required_keys_are_documented():
    templates = [p for p in (REPO / ".env.example", BACKEND / ".env.example") if p.exists()]
    documented = set().union(*(env_keys(p) for p in templates))
    assert REQUIRED_BACKEND_KEYS <= documented, f"누락: {REQUIRED_BACKEND_KEYS - documented}"


def test_backend_template_does_not_crash_settings():
    """Settings는 extra='forbid'라서 .env에 모르는 키가 하나라도 있으면 서버가 기동하지 않는다."""
    template = BACKEND / ".env.example"
    if not template.exists():
        template = REPO / ".env.example"
    known = {name.upper() for name in Settings.model_fields}
    unknown = env_keys(template) - known
    assert not unknown, f"{template.relative_to(REPO)}를 .env로 복사하면 기동 실패: {sorted(unknown)}"
    # 키·모델만 채우면 템플릿 그대로 설정이 로드되어야 한다 (CORS 값 형식 등 포함)
    Settings(_env_file=template, gemini_api_key="test-key", gemini_model="gemini-test")
