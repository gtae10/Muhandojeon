#!/usr/bin/env bash
# 8~9단계: 각 서비스 health check + 프론트→nginx→app 엔드투엔드 시나리오 재생 확인 + 메모리 체크
set -euo pipefail
source "$(dirname "$0")/00_vars.sh"

check() {
  local name="$1" url="$2"
  local code
  code=$(curl -s -o /tmp/hc_body -w "%{http_code}" "$url" || echo "000")
  if [ "$code" = "200" ]; then
    echo "OK   $name  ($url)"
  else
    echo "FAIL $name  ($url) -> HTTP $code"
    cat /tmp/hc_body
  fi
}

echo "== systemd 서비스 상태 =="
systemctl is-active muhandojeon-app muhandojeon-backend muhandojeon-ai-clienteling

echo
echo "== 내부 포트 직접 확인 (127.0.0.1) =="
check "app        :8000" "http://127.0.0.1:8000/health"
check "backend    :8103" "http://127.0.0.1:8103/health"
check "ai-clienteling :8102" "http://127.0.0.1:8102/health"

echo
echo "== nginx 경유 확인 (외부에서 실제로 타는 경로) =="
check "nginx -> app /health"        "http://127.0.0.1/health"
check "nginx -> app /catalog"       "http://127.0.0.1/catalog"
check "nginx -> frontend index"     "http://127.0.0.1/"

echo
echo "== 엔드투엔드: 데모 시나리오 D1 재생 (프론트가 실제로 부르는 것과 동일 경로) =="
curl -s -X POST http://127.0.0.1/demo/scenarios/D1/run -H "Content-Type: application/json" -o /tmp/hc_scenario -w "HTTP %{http_code}\n"
head -c 500 /tmp/hc_scenario; echo

echo
echo "== 메모리 사용량 (4GB 한도 확인) =="
free -h

echo
echo "== 외부 노출 포트 확인 (80/443만 열려야 정상) =="
ss -tlnp | grep -E ":80|:443|:8000|:8102|:8103" || true

echo
echo "== firewalld 규칙 확인 =="
firewall-cmd --list-all

echo
echo "== SELinux 상태 =="
getenforce || true
