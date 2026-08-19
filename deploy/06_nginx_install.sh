#!/usr/bin/env bash
# 6단계: nginx 설정 적용 — 리버스 프록시 + 정적 파일 서빙 + SELinux 정책 조정 (Rocky Linux)
set -euo pipefail
source "$(dirname "$0")/00_vars.sh"
DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"

FRONTEND_DIST="$MAIN_DIR/frontend/dist"

echo "== nginx.conf 교체 (Rocky 기본 nginx.conf에 내장된 default_server와 충돌 방지) =="
if [ ! -f /etc/nginx/nginx.conf.orig ]; then
  cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.orig
fi
cp "$DEPLOY_DIR/nginx/nginx.conf" /etc/nginx/nginx.conf

echo "== 사이트 설정 적용 (conf.d — Rocky nginx는 sites-available/enabled가 없다) =="
cp "$DEPLOY_DIR/nginx/muhandojeon.conf" /etc/nginx/conf.d/muhandojeon.conf

echo "== SELinux 정책 조정 =="
if [ "$(getenforce 2>/dev/null || echo Disabled)" != "Disabled" ]; then
  echo "  -> httpd_can_network_connect: nginx가 127.0.0.1:8000으로 프록시 연결을 열 수 있게 허용"
  setsebool -P httpd_can_network_connect 1

  echo "  -> $FRONTEND_DIST 를 httpd_sys_content_t 로 라벨링 (안 하면 정적 파일 403)"
  semanage fcontext -a -t httpd_sys_content_t "${FRONTEND_DIST}(/.*)?" 2>/dev/null \
    || semanage fcontext -m -t httpd_sys_content_t "${FRONTEND_DIST}(/.*)?"
  restorecon -Rv "$FRONTEND_DIST" || echo "  (경고: $FRONTEND_DIST 가 아직 없다면 04_build_frontend.sh 먼저 실행 후 다시 이 스크립트를 돌릴 것)"
else
  echo "  SELinux가 Disabled 상태 — 정책 조정 건너뜀"
fi

nginx -t
systemctl reload nginx

echo "== nginx 적용 완료 =="
