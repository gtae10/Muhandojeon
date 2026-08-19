#!/usr/bin/env bash
# 4단계: 프론트엔드 프로덕션 빌드. npm run dev는 절대 서버에서 실행하지 않는다 —
# 빌드 결과(정적 파일)만 nginx가 서빙한다.
set -euo pipefail
source "$(dirname "$0")/00_vars.sh"

FRONTEND_DIR="$MAIN_DIR/frontend"

sudo -u "$SERVICE_USER" bash -c "cd '$FRONTEND_DIR' && npm ci && npm run build"

echo "== 완료: $FRONTEND_DIR/dist 에 정적 파일 생성됨 =="
ls -la "$FRONTEND_DIR/dist"
