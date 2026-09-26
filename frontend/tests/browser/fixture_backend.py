"""Real FastAPI routes with a deterministic, explicitly test-only AI extractor."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "rpm-backend"))

import uvicorn
from app.config import Settings
from app.extractor import ExtractionEnvelope
from app.main import create_app


class DeterministicExtractor:
    async def extract(self, message: str) -> ExtractionEnvelope:
        rules = {
            "인증번호를 알려": "ACT_PERSONAL",
            "아래 주소": "ACT_LINK",
            "로그인해": "ACT_LOGIN",
            "앱을 설치": "ACT_APP",
            "오늘 안에": "PRESSURE",
        }
        evidence = [
            {"type": kind, "quote": line}
            for line in message.splitlines()
            for phrase, kind in rules.items()
            if phrase in line
        ]
        return ExtractionEnvelope("completed", json.dumps({"evidence": evidence}, ensure_ascii=False))

    async def aclose(self) -> None:
        pass


if __name__ == "__main__":
    settings = Settings(
        _env_file=None,
        app_env="test",
        cors_allow_origins=[sys.argv[2]],
        analyze_per_ip_per_minute=100,
        analyze_global_per_minute=100,
    )
    uvicorn.run(create_app(settings, DeterministicExtractor()), host="127.0.0.1", port=int(sys.argv[1]))
