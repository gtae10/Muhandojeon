#!/usr/bin/env bash
# 3단계: 3개 FastAPI 서비스 각각 독립 venv 생성 + 의존성 설치
#   app/            -> $MAIN_DIR/.venv
#   backend/        -> $MAIN_DIR/backend/.venv
#   ai-clienteling/ -> $AI_CLIENTELING_DIR/.venv
# 서비스 계정으로 실행 (경로 소유권을 맞추기 위해 sudo -u 사용)
set -euo pipefail
source "$(dirname "$0")/00_vars.sh"

run_as_service() {
  sudo -u "$SERVICE_USER" bash -c "$1"
}

echo "== app/ (통합 레이어) venv =="
run_as_service "cd '$MAIN_DIR' && $PYTHON_BIN -m venv .venv && .venv/bin/pip install --quiet --upgrade pip && .venv/bin/pip install --quiet ."
run_as_service "test -f '$MAIN_DIR/.env' || cp '$MAIN_DIR/.env.example' '$MAIN_DIR/.env'"

echo "== backend/ venv =="
run_as_service "cd '$MAIN_DIR/backend' && $PYTHON_BIN -m venv .venv && .venv/bin/pip install --quiet --upgrade pip && .venv/bin/pip install --quiet -r requirements.txt"
run_as_service "test -f '$MAIN_DIR/backend/.env' || cp '$MAIN_DIR/backend/.env.example' '$MAIN_DIR/backend/.env'"

echo "== ai-clienteling/ venv =="
run_as_service "cd '$AI_CLIENTELING_DIR' && $PYTHON_BIN -m venv .venv && .venv/bin/pip install --quiet --upgrade pip && .venv/bin/pip install --quiet -r requirements.txt"
run_as_service "test -f '$AI_CLIENTELING_DIR/.env' || cp '$AI_CLIENTELING_DIR/.env.example' '$AI_CLIENTELING_DIR/.env'"

cat <<'EOF'

== 완료. 이제 .env 3개를 채워야 한다 (에디터로 직접 열어서 값만 채우기) ==

  sudo -u muhandojeon nano /opt/muhandojeon/main/.env
    - LLM_API_KEY (비워두면 결정적 템플릿 폴백 — 필수 아님)

  sudo -u muhandojeon nano /opt/muhandojeon/main/backend/.env
    - OPENAI_API_KEY (필수)

  sudo -u muhandojeon nano /opt/muhandojeon/ai-clienteling-src/ai-clienteling/.env
    - OPENAI_API_KEY (필수, backend와 같은 키 공유하기로 함)
    - OPENAI_MODEL=gpt-4o

.env 파일은 .gitignore 대상이라 git에는 안 올라간다. 채운 뒤 04_systemd_install.sh 로 진행.
EOF
