#!/usr/bin/env bash
# a1.scnuoss.net 배포: 프론트를 정적 파일로 빌드해 서버 작업 경로(/home/a1/html/)에 업로드
# 사용법 (저장소 루트에서):  bash deploy/deploy.sh
# 접속 정보는 저장소 루트의 .env 에서 읽습니다 (USER_ID, PASSWORD, HOST, WORK_PATH). .env 는 커밋 금지.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/.env" ] || { echo ".env 가 없습니다. 멘토님이 준 접속 정보로 저장소 루트에 .env 를 만드세요."; exit 1; }
set -a; . "$ROOT/.env"; set +a
TARGET="${USER_ID:?}@${HOST:?}"
REMOTE_DIR="${WORK_PATH:?}"

# 1) 정적 파일 빌드 → frontend/out/
cd "$ROOT/frontend"
npm ci --no-audit --no-fund
npm run build
[ -f out/index.html ] || { echo "빌드 결과(out/index.html)가 없습니다."; exit 1; }

# 2) .env 의 PASSWORD 로 자동 로그인 (없으면 ssh 가 비밀번호를 직접 물어봄)
if [ -n "${PASSWORD:-}" ]; then
  ASKPASS="$(mktemp)"; trap 'rm -f "$ASKPASS"' EXIT
  printf '#!/bin/sh\nprintf "%%s" "$DEPLOY_PASSWORD"\n' > "$ASKPASS"; chmod +x "$ASKPASS"
  export DEPLOY_PASSWORD="$PASSWORD" SSH_ASKPASS="$ASKPASS" SSH_ASKPASS_REQUIRE=force DISPLAY="${DISPLAY:-:0}"
fi

# 3) 한 번의 접속으로 기존 파일을 지우고 새 빌드로 교체
echo "업로드 → $TARGET:$REMOTE_DIR"
tar -C out -cf - . | ssh -o StrictHostKeyChecking=accept-new "$TARGET" \
  "mkdir -p '$REMOTE_DIR' && find '$REMOTE_DIR' -mindepth 1 -delete && tar -xf - -C '$REMOTE_DIR'"

# 4) 확인
code="$(curl -s -o /dev/null -w '%{http_code}' "${DEPLOY_ADDRESS:-https://a1.scnuoss.net/}")"
echo "배포 완료 → ${DEPLOY_ADDRESS:-https://a1.scnuoss.net/} (HTTP $code)"
