#!/usr/bin/env bash
# 모든 deploy/*.sh 스크립트가 공유하는 변수. 여기만 고치면 경로/포트가 전부 바뀐다.
set -euo pipefail

REPO_URL="https://github.com/gtae10/Muhandojeon.git"
BASE_DIR="/opt/muhandojeon"
MAIN_DIR="$BASE_DIR/main"                 # main 브랜치: app/ backend/ frontend/ ai-clienteling/
# ai-clienteling 이 main 에 머지되어(2026-08-20) 별도 브랜치 체크아웃이 더는 필요 없다.
# 구 배포(/opt/muhandojeon/ai-clienteling-src)에서 넘어오는 절차는 RUNBOOK "단일 체크아웃 전환" 참조.
AI_CLIENTELING_DIR="$MAIN_DIR/ai-clienteling"

SERVICE_USER="muhandojeon"

APP_PORT=8000
BACKEND_PORT=8103
AI_CLIENTELING_PORT=8102

PYTHON_BIN="python3.11"
