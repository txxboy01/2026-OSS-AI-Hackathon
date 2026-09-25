#!/usr/bin/env bash
# a1.scnuoss.net 배포: 프론트를 정적 파일로 빌드해 서버의 /home/a1/html/ 에 업로드
# 사용법: ./deploy/deploy.sh            (기본 접속: a1@a1.scnuoss.net)
set -euo pipefail
TARGET="${1:-a1@a1.scnuoss.net}"
REMOTE_DIR="${REMOTE_DIR:-/home/a1/html}"

cd "$(dirname "$0")/../frontend"
npm ci --no-audit --no-fund
npm run build            # → frontend/out/

# 기존 안내 페이지를 지우고 빌드 결과로 교체
ssh "$TARGET" "mkdir -p '$REMOTE_DIR' && find '$REMOTE_DIR' -mindepth 1 -delete"
scp -r out/. "$TARGET:$REMOTE_DIR/"
echo "배포 완료 → https://a1.scnuoss.net/"
