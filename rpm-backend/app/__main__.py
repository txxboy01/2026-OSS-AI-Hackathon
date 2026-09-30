import argparse
import ipaddress
import sys

import uvicorn
from pydantic import ValidationError

from .config import Settings
from .logging_config import configure_logging
from .main import create_app


def main():
    parser = argparse.ArgumentParser(description="RPM backend (single worker, no raw access logs)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--trusted-proxies", default="", help="Comma-separated exact proxy IPs/CIDRs; no wildcard"
    )
    args = parser.parse_args()
    try:
        for value in filter(None, args.trusted_proxies.split(",")):
            ipaddress.ip_network(value.strip(), strict=False)
        settings = Settings()
        if settings.app_env == "test":
            raise ValueError("test mode is only available through explicit test injection")
        application = create_app(settings)
    except (ValidationError, ValueError):
        print(
            "설정 오류: .env의 필수 키·모델·origin 및 실행 옵션을 확인하세요. README의 실행 절차를 참고하세요.",
            file=sys.stderr,
        )
        return 1
    configure_logging(settings.log_level)
    uvicorn.run(
        application,
        host=args.host,
        port=args.port,
        workers=1,
        access_log=False,
        log_config=None,
        proxy_headers=bool(args.trusted_proxies),
        forwarded_allow_ips=args.trusted_proxies,
        timeout_graceful_shutdown=15,
        timeout_keep_alive=5,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
