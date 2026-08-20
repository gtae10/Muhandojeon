#!/usr/bin/env bash
# 2단계: 레포 클론 — public repo라 인증 불필요.
#   main 브랜치 하나로 전부 배포한다 (app/ backend/ frontend/ ai-clienteling/).
# root 또는 sudo로 실행
set -euo pipefail
source "$(dirname "$0")/00_vars.sh"

clone_or_update() {
  local dir="$1" branch="$2"
  if [ -d "$dir/.git" ]; then
    echo "== $dir 이미 존재 — $branch로 갱신 =="
    git -C "$dir" fetch origin "$branch"
    git -C "$dir" checkout "$branch"
    git -C "$dir" reset --hard "origin/$branch"
  else
    echo "== $dir 클론 ($branch) =="
    git clone --branch "$branch" --single-branch "$REPO_URL" "$dir"
  fi
}

clone_or_update "$MAIN_DIR" "main"

chown -R "$SERVICE_USER:$SERVICE_USER" "$BASE_DIR"

echo "== 완료 =="
echo "  main:            $MAIN_DIR"
echo "  ai-clienteling:  $AI_CLIENTELING_DIR"
