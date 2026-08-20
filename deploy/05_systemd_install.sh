#!/usr/bin/env bash
# 5단계: systemd 서비스 등록 — 재부팅해도 자동 기동.
set -euo pipefail
source "$(dirname "$0")/00_vars.sh"
DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"

cp "$DEPLOY_DIR/systemd/muhandojeon-app.service" /etc/systemd/system/
cp "$DEPLOY_DIR/systemd/muhandojeon-backend.service" /etc/systemd/system/
cp "$DEPLOY_DIR/systemd/muhandojeon-ai-clienteling.service" /etc/systemd/system/
cp "$DEPLOY_DIR/systemd/muhandojeon-ai-intent.service" /etc/systemd/system/

systemctl daemon-reload
systemctl enable --now muhandojeon-app.service
systemctl enable --now muhandojeon-backend.service
systemctl enable --now muhandojeon-ai-clienteling.service
systemctl enable --now muhandojeon-ai-intent.service

sleep 2
systemctl --no-pager status muhandojeon-app.service muhandojeon-backend.service muhandojeon-ai-clienteling.service muhandojeon-ai-intent.service
