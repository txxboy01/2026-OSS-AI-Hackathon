"""Optional manual evaluation: synthetic fixtures only, no payload logging."""

import argparse
import asyncio
import json
from pathlib import Path

from pydantic import ValidationError

from app.config import Settings
from app.errors import ExtractionFailure
from app.extractor import GeminiExtractor
from app.logging_config import configure_logging
from app.prompts import SYSTEM_INSTRUCTION
from app.redactor import detect_sensitive
from app.validator import validate


async def evaluate():
    settings = Settings()
    configure_logging(settings.log_level)
    cases = json.loads(
        (Path(__file__).resolve().parent.parent / "tests/fixtures/gold_cases.json").read_text(encoding="utf-8")
    )
    extractor = GeminiExtractor(settings)
    results = []
    try:
        for case in cases:
            assert not detect_sensitive(case["messageText"])
            for run in range(3 if case["id"].startswith("SAMPLE_") else 1):
                try:
                    envelope = await extractor.extract(case["messageText"])
                    evidence = validate(case["messageText"], envelope)
                    types = {e.type for e in evidence}
                    required, allowed = (
                        set(case["requiredTypes"]),
                        set(case["requiredTypes"] + case["optionalTypes"]),
                    )
                    passed = required <= types <= allowed
                    row = {
                        "caseId": case["id"],
                        "run": run + 1,
                        "passed": passed,
                        "actualTypes": sorted(types),
                        "quoteValidation": "passed" if evidence else "not_applicable",
                        "missingTypes": sorted(required - types),
                        "unexpectedTypes": sorted(types - allowed),
                    }
                except ExtractionFailure as error:
                    row = {
                        "caseId": case["id"],
                        "run": run + 1,
                        "passed": False,
                        "actualTypes": [],
                        "quoteValidation": "failed",
                        "reasonCode": error.reason,
                    }
                results.append(row)
                print(json.dumps(row, ensure_ascii=False))
    finally:
        await extractor.aclose()
    # No source, quote, provider response or API key is printed or persisted.
    print(
        json.dumps(
            {
                "cases": len(results),
                "passed": sum(r["passed"] for r in results),
                "promptVersion": "1.0",
                "promptCharacters": len(SYSTEM_INSTRUCTION),
            },
            ensure_ascii=False,
        )
    )
    return 0 if all(r["passed"] for r in results) else 1


def main():
    parser = argparse.ArgumentParser(description="비식별 fixture 13회 실제 Gemini 평가 (API 비용 발생 가능)")
    parser.add_argument("--allow-external-ai", action="store_true")
    args = parser.parse_args()
    if not args.allow_external_ai:
        parser.error("샘플 외부 전송과 13회 호출에 동의하면 --allow-external-ai를 지정하세요.")
    try:
        return asyncio.run(evaluate())
    except (ValidationError, ValueError):
        print("설정 오류입니다. .env의 모델과 API 키를 확인하세요.")
        return 2
    except Exception:  # noqa: BLE001 - privacy boundary: never print provider traceback
        print("평가 중 예기치 못한 오류가 발생했습니다. 상세 입력은 출력하지 않았습니다.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
