#!/usr/bin/env bash
# 모든 deploy/*.sh 스크립트가 공유하는 변수. 여기만 고치면 경로/포트가 전부 바뀐다.
set -euo pipefail

REPO_URL="https://github.com/gtae10/Muhandojeon.git"
BASE_DIR="/opt/muhandojeon"
MAIN_DIR="$BASE_DIR/main"                 # main 브랜치: app/ backend/ frontend/
AI_CLIENTELING_SRC_DIR="$BASE_DIR/ai-clienteling-src"  # AI-clienteling 브랜치 전용 체크아웃
AI_CLIENTELING_DIR="$AI_CLIENTELING_SRC_DIR/ai-clienteling"

SERVICE_USER="muhandojeon"

APP_PORT=8000
BACKEND_PORT=8103
AI_CLIENTELING_PORT=8102

PYTHON_BIN="python3.11"
