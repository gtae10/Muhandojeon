#!/usr/bin/env bash
# 1단계: 런타임 설치 — Python 3.11, Node.js LTS, nginx, git (Rocky Linux 8.10)
# root로 실행 (sudo bash deploy/01_provision.sh)
set -euo pipefail
source "$(dirname "$0")/00_vars.sh"

echo "== OS 버전 확인 =="
cat /etc/os-release | grep -E "^(NAME|VERSION)="
free -h
df -h /

echo "== dnf 갱신 =="
dnf upgrade -y

echo "== 기본 도구 =="
dnf install -y git curl ca-certificates gnupg2 dnf-plugins-core policycoreutils-python-utils
dnf groupinstall -y "Development Tools"

echo "== Python 3.11 =="
# Rocky 8.10 AppStream은 python3.11을 일반 패키지로 직접 제공한다(모듈 스트림 아님).
# 혹시 이 포인트 릴리스에서 모듈로만 잡히는 경우를 대비해 실패 시 모듈 활성화로 재시도한다.
if ! command -v python3.11 >/dev/null 2>&1; then
  if ! dnf install -y python3.11 python3.11-pip python3.11-devel; then
    echo "직접 설치 실패 — 모듈 스트림으로 재시도"
    dnf module reset -y python311 2>/dev/null || true
    dnf module enable -y python3.11 2>/dev/null || true
    dnf install -y python3.11 python3.11-pip python3.11-devel
  fi
fi
python3.11 --version

echo "== Node.js LTS (NodeSource RPM, 20.x) =="
if ! command -v node >/dev/null 2>&1; then
  curl -fsSL https://rpm.nodesource.com/setup_20.x | bash -
  dnf install -y nodejs
fi
node --version
npm --version

echo "== nginx =="
# Rocky 8 AppStream의 nginx는 모듈 스트림으로 배포된다. 스트림이 있으면 최신(1.24)을 켜고,
# 이미 비모듈 형태로 설치 가능하면(향후 포인트 릴리스) 그냥 install만으로 통과한다.
if ! command -v nginx >/dev/null 2>&1; then
  dnf module reset -y nginx 2>/dev/null || true
  dnf module enable -y nginx:1.24 2>/dev/null || true
  dnf install -y nginx
fi
nginx -v
systemctl enable nginx

echo "== firewalld 확인 (Rocky 기본 포함 — 없으면 설치) =="
if ! command -v firewall-cmd >/dev/null 2>&1; then
  dnf install -y firewalld
fi
systemctl enable --now firewalld

echo "== SELinux 상태 확인 (기본 enforcing — 06 단계에서 nginx용 정책 조정 예정) =="
getenforce || true

echo "== 서비스 실행용 시스템 계정 생성 (로그인 불가, 홈은 $BASE_DIR) =="
if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "$BASE_DIR" --shell /sbin/nologin "$SERVICE_USER"
fi

mkdir -p "$BASE_DIR"
chown "$SERVICE_USER:$SERVICE_USER" "$BASE_DIR"

echo "== 완료: python3.11, node, nginx, git, firewalld 설치됨. 서비스 계정 '$SERVICE_USER' 준비됨 =="
