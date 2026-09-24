"""Safe analysis response shared by Gemini and validation failure paths."""

LIMITATION = "이 결과만으로 피싱 또는 실제 침해 여부를 확정할 수 없습니다."
FALLBACK_MESSAGE = (
    "자동 분석 결과를 원문 근거로 검증하지 못했습니다. "
    "메시지 속 링크를 누르거나 정보를 입력하지 말고, "
    "주장하는 서비스의 공식 앱 또는 직접 입력한 주소에서 확인하세요."
)


def fallback_result() -> dict:
    """Return a fresh object so callers cannot mutate shared fallback state."""
    return {
        "mode": "fallback",
        "evidence": [],
        "limitation": LIMITATION,
        "message": FALLBACK_MESSAGE,
    }
