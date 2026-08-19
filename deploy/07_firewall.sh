#!/usr/bin/env bash
# 7단계: 방화벽 — 80/443(nginx)만 외부 노출, 내부 포트(8000/8102/8103)는 접근 차단. (firewalld)
# 서비스들은 이미 127.0.0.1에만 바인드하지만(systemd 유닛 참고), firewalld로 한 번 더 막는다(심층 방어).
set -euo pipefail

# SSH부터 먼저 허용 — 순서를 바꾸면 원격 세션이 끊길 수 있다.
firewall-cmd --permanent --add-service=ssh
firewall-cmd --permanent --add-service=http
firewall-cmd --permanent --add-service=https

# 내부 전용 포트는 명시적으로 거부 규칙을 걸어둔다.
# (기본 zone은 명시적으로 열지 않은 포트는 어차피 막혀 있지만, ufw의 explicit deny와
#  동작을 맞추고 `firewall-cmd --list-all`에서 눈에 보이게 하기 위해 rich rule로 명시한다.)
for port in 8000 8102 8103; do
  firewall-cmd --permanent --add-rich-rule="rule family=\"ipv4\" port port=\"${port}\" protocol=\"tcp\" reject"
done

firewall-cmd --reload
firewall-cmd --list-all
