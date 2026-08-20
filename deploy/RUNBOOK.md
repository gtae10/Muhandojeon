# 가비아 클라우드(Rocky Linux 8.10, 2vCore/4GB/100GB) 배포 런북

이 디렉터리의 스크립트는 서버에서 **root 권한으로** 순서대로 실행하는 걸 전제로 만들었다.
SSH 접속 자체는 각자 로컬에서 하고, 접속한 뒤 이 저장소를 clone하면 `deploy/` 가 같이 딸려온다
(레포가 public이라 서버에서 별도 인증 없이 clone 가능).

## 사전 결정 사항 (이미 확정됨)

| 항목 | 값 | 이유 |
|---|---|---|
| `app/` 포트 | 8000 | 통합 레이어, 기본값 |
| `backend/` 포트 | **8103** | 원래 `main.py`에 8000으로 하드코딩돼 있어 `app/`와 충돌 → `.env.example`의 `ASSET_BASE_URL` 관례에 맞춰 8103으로 변경 (아래 참고) |
| `backend/` 진입점 | **`app.main:app` (신형)** | 구형 `main:app`에는 계약 경로(`/assets/{id}`, `/fingerprint/match`, `/condition/score`)가 없어 http 전환 시 404가 난다. 신형은 계약+레거시 경로를 모두 서빙하고 `backend/README.md`도 신형을 권장 |
| `ai-clienteling/` 포트 | 8102 | 자체 문서에 이미 명시된 값 |
| `AI/server/`(AI1 인텐트) 포트 | 8101 | `.env.example` 의 `INTENT_BASE_URL` 기본값과 일치. 노트북 5절을 승격한 규칙 신호 모델(ML 런타임 불필요) |
| `ai-clienteling/` 소스 | `main` 단일 체크아웃 (`$MAIN_DIR/ai-clienteling`) | 2026-08-20 main 에 merge 됨 — 별도 브랜치 clone 불필요. 구 배포 전환은 아래 "단일 체크아웃 전환" |
| 코드 전달 | `git clone` (레포 public) | rsync보다 서버에서 갱신(`git pull`)이 쉬움 |
| OpenAI 키 | `backend/`와 `ai-clienteling/`가 동일 키 공유 | 사용자 확인 |
| 외부 노출 | 80/443만 (nginx) | 8000/8101/8102/8103은 firewalld로 차단 + 서비스 자체도 127.0.0.1에만 바인드 (이중 방어) |

**주의**: 소스에 하드코딩된 포트(구형 `main.py:73`의 8000, 신형 `app/main.py` 문서의 8001)는
systemd 유닛이 `uvicorn app.main:app --port 8103` 으로 직접 띄우기 때문에 실제로는 무시된다
(직접 실행할 때만 쓰인다). 코드를 고칠 필요는 없다. 헬스체크 경로는 신형 기준 `/api/health`다
(구형의 `/health`는 신형에 없다 — `08_healthcheck.sh`가 이미 반영).

## Rocky Linux 8.10에서 달라지는 부분 (Ubuntu 대비)

| 영역 | Ubuntu | Rocky 8.10 |
|---|---|---|
| 패키지 매니저 | `apt-get` | `dnf` |
| Python 3.11 | deadsnakes PPA | AppStream이 `python3.11` 패키지를 직접 제공 (모듈 스트림 아님). 혹시 이 포인트 릴리스에서 안 잡히면 `dnf module enable python3.11`로 재시도하도록 스크립트에 fallback을 넣어뒀다 |
| Node.js 20.x | `deb.nodesource.com` | `rpm.nodesource.com` (같은 NodeSource, RPM용 setup 스크립트) |
| nginx | `apt-get install nginx` | AppStream 모듈 스트림(`nginx:1.24`)일 수 있어 `dnf module enable`로 먼저 켜고 설치 |
| nginx 사이트 설정 구조 | `sites-available/` + `sites-enabled/` 심볼릭 링크 | 그런 구조 자체가 없음 — `/etc/nginx/conf.d/*.conf`가 자동으로 include됨. **또한 Rocky의 기본 `nginx.conf`는 `server{}` 기본 블록을 파일 안에 직접 내장하고 있어서, 우리 `default_server`와 충돌한다** → `nginx.conf` 자체를 (기본 서버 블록만 뺀) 버전으로 교체함 |
| 방화벽 | `ufw` | `firewalld` (`firewall-cmd`) |
| SELinux | 없음(해당 없음) | 기본 **enforcing**. nginx가 (1) 127.0.0.1로 프록시하는 것, (2) `/opt/...` 아래 정적 파일을 읽는 것 둘 다 기본 정책에 막힌다 → `setsebool httpd_can_network_connect` + `semanage fcontext`로 `frontend/dist`를 `httpd_sys_content_t`로 라벨링 |
| 서비스 계정 nologin 쉘 | `/usr/sbin/nologin` | `/sbin/nologin` (RHEL 관례, usrmerge로 실제로는 같은 바이너리) |

git clone, python venv/pip, npm, systemd 유닛 파일, `MemoryMax` 등 핵심 로직은 배포판과 무관해서
그대로다.

## 순서

### 0. 로컬에서 서버 접속

```bash
ssh <사용자>@<서버IP>
```

### 1. 레포 clone (deploy/ 스크립트를 얻기 위해 먼저 최소 clone)

```bash
sudo mkdir -p /opt/muhandojeon && sudo chown $(whoami) /opt/muhandojeon
git clone --branch main --single-branch https://github.com/gtae10/Muhandojeon.git /opt/muhandojeon/main
cd /opt/muhandojeon/main/deploy
```

(`git`이 아직 없다면: `sudo dnf install -y git`로 먼저 설치)

이후 모든 명령은 이 `deploy/` 안에서, **root로** (`sudo bash 스크립트명`) 실행한다.

### 2. 런타임 설치 (Python 3.11, Node LTS, nginx, git, firewalld, 서비스 계정 생성)

```bash
sudo bash 01_provision.sh
```

Ubuntu 버전, 메모리(`free -h`), 디스크(`df -h`)를 먼저 출력해서 사양을 확인하고,
python3.11, nodejs 20.x, nginx, git, firewalld, SELinux 관리 도구(`policycoreutils-python-utils`)를
설치한다. 서비스를 root가 아닌 별도 계정(`muhandojeon`, 로그인 불가)으로 돌리기 위해 시스템 계정도
만든다. 마지막에 `getenforce`로 SELinux 모드를 확인해준다(보통 `Enforcing`).

### 3. 레포 clone/최신화

```bash
sudo bash 02_clone.sh
```

`main` 브랜치 하나에 네 파트가 전부 들어 있다 (`app/ backend/ frontend/ ai-clienteling/`).
과거의 `AI-clienteling` 별도 브랜치 체크아웃은 merge 이후 폐지됐다.

### 4. 각 FastAPI 서비스 venv + 의존성 설치

```bash
sudo bash 03_setup_python.sh
```

`app/`, `backend/`, `ai-clienteling/` 각각 독립된 `.venv`를 만들고 의존성을 설치한다.
설치가 끝나면 `.env.example`을 `.env`로 복사만 해두고 **값은 채우지 않는다** — 스크립트 마지막에
직접 채워야 할 파일 3개의 경로를 출력해준다. API 키는 코드/스크립트에 넣지 않고 여기서 직접:

```bash
sudo -u muhandojeon nano /opt/muhandojeon/main/.env
sudo -u muhandojeon nano /opt/muhandojeon/main/backend/.env               # OPENAI_API_KEY 필수
sudo -u muhandojeon nano /opt/muhandojeon/main/ai-clienteling/.env        # OPENAI_API_KEY 필수 (backend와 동일 키)
```

### 5. 프론트엔드 프로덕션 빌드

```bash
sudo bash 04_build_frontend.sh
```

`npm run dev`는 쓰지 않는다. `npm run build`로 만든 `frontend/dist`를 nginx가 정적으로 서빙한다.
(이 디렉터리가 6단계에서 SELinux 라벨링 대상이 되므로, 6단계보다 반드시 먼저 실행돼 있어야 한다.)

### 6. systemd 서비스 등록 (재부팅해도 자동 기동, `--workers 1`로 메모리 절약)

```bash
sudo bash 05_systemd_install.sh
```

`deploy/systemd/*.service` 3개를 `/etc/systemd/system/`에 설치하고 `enable --now`로 즉시 기동 +
부팅 시 자동시작 설정. 세 서비스 모두 `127.0.0.1`에만 바인드하고(외부에서 직접 접근 불가),
`uvicorn ... --workers 1`로 프로세스 하나만 띄운다. `MemoryMax`도 유닛 파일에 걸어뒀다
(app 768M / backend 1024M / ai-clienteling 512M — 4GB 서버에서 nginx+OS 몫까지 감안한 상한).
systemd 유닛 문법 자체는 배포판과 무관해서 Ubuntu판과 완전히 동일하다.

### 7. nginx 리버스 프록시 설정 + SELinux 정책 조정

```bash
sudo bash 06_nginx_install.sh
```

`/` 는 `frontend/dist` 정적 파일, `/session /catalog /customers /sessions /demo /health /static
/lab /ops /intent /clienteling /assets /condition /fingerprint /docs` 는 전부 `app/`(:8000)로
프록시한다. `backend`(:8103)·`ai-clienteling`(:8102)·`ai-intent`(:8101)는 nginx 블록에 아예 없다 — 지금은 프론트가
`app/`만 호출하고, `app/`은 기본 mock 어댑터 모드로 동작하기 때문에 이 두 서비스를 외부에 노출할
이유가 없다 (아래 "다음 단계" 참고).

Rocky 특유의 두 가지를 이 단계에서 처리한다:

1. **nginx.conf 충돌**: Rocky 기본 `nginx.conf`에 내장된 `server{ listen 80 default_server; ... }`
   블록을 그대로 두면 우리 `conf.d/muhandojeon.conf`의 `default_server`와 충돌해서
   `nginx -t`가 "duplicate default server" 에러를 낸다. 그래서 원본을
   `/etc/nginx/nginx.conf.orig`로 백업해두고, 내장 서버 블록을 뺀 버전으로 교체한다.
2. **SELinux (enforcing 기본)**:
   - `setsebool -P httpd_can_network_connect 1` — nginx가 `127.0.0.1:8000`으로 프록시 연결을
     여는 걸 허용한다. 이거 없으면 프록시 경로에서 전부 `502 Bad Gateway`가 뜬다.
   - `semanage fcontext -a -t httpd_sys_content_t "$FRONTEND_DIST(/.*)?"` + `restorecon -Rv` —
     `/opt/muhandojeon/main/frontend/dist`를 nginx가 읽을 수 있는 타입으로 라벨링한다.
     이거 없으면 프론트 정적 파일이 전부 `403 Forbidden`.

   SELinux가 `Disabled`로 되어 있으면(권장하지 않지만) 이 단계는 자동으로 건너뛴다.

### 8. 방화벽 (firewalld)

```bash
sudo bash 07_firewall.sh
```

`ssh`, `http`, `https` 서비스만 허용하고 `8000/8101/8102/8103`은 rich rule로 명시적으로 거부한다.
**SSH 허용을 방화벽 규칙 중 제일 먼저 넣는다** — 순서를 바꾸면 원격 세션이 끊길 수 있다.
(firewalld는 기본 zone에서 명시적으로 안 연 포트는 원래 막혀있지만, ufw의 explicit deny와
동작·가시성을 맞추려고 reject rich rule을 따로 건다.)

### 9. 헬스체크 + 엔드투엔드 확인 + 메모리 확인

```bash
sudo bash 08_healthcheck.sh
```

세 systemd 서비스 상태, 내부 포트(127.0.0.1) 개별 health check, nginx를 경유한 `/health`·`/catalog`·
프론트 인덱스, 그리고 프론트가 실제로 누르는 것과 동일한 경로로 데모 시나리오 D1을 재생시켜본다
(`POST /demo/scenarios/D1/run`). `free -h`로 메모리 여유, `ss -tlnp`로 80/443 외의 포트가 외부에
안 열려 있는지, `firewall-cmd --list-all`과 `getenforce`로 방화벽·SELinux 상태까지 한 번에 확인한다.

브라우저로도 직접 확인하려면 `http://<서버IP>/` 접속 후 데모 시나리오 카드의 "이 시나리오 재생"을
눌러보면 된다.

## 흔한 실패 패턴 (Rocky 전용)

- **`nginx -t`가 "duplicate default server" 에러** → `06_nginx_install.sh`를 안 돌렸거나
  `/etc/nginx/nginx.conf`가 수동으로 원복된 경우. `/etc/nginx/nginx.conf.orig`와 비교해서
  기본 서버 블록이 다시 들어갔는지 확인.
- **프록시 경로(`/session`, `/catalog` 등)가 502** → SELinux가 `httpd_can_network_connect`를
  막고 있을 가능성이 크다. `getsebool httpd_can_network_connect`로 확인, `off`면
  `sudo setsebool -P httpd_can_network_connect 1`.
- **프론트 화면은 뜨는데 흰 화면/403** → `frontend/dist`가 아직 `httpd_sys_content_t`로
  라벨링 안 된 경우. `ls -Z /opt/muhandojeon/main/frontend/dist`로 컨텍스트 확인,
  `httpd_sys_content_t`가 아니면 `06_nginx_install.sh`를 (04 이후에) 다시 실행.
- **`journalctl -u muhandojeon-app -n 50`에서 SELinux denial처럼 보이는 실패** →
  `sudo ausearch -m avc -ts recent`로 실제 AVC 거부 로그 확인 (`audit2allow`로 임시 정책 생성 가능하나,
  가급적 위 두 setsebool/fcontext 설정만으로 해결되도록 구성했다).

## 다음 단계 (지금은 안 함 — 별도 판단 필요)

`app/`은 기본적으로 `ADAPTER_MODE=mock`으로 fixture 데이터를 쓴다. `backend/`와 `ai-clienteling/`을
실제로 붙이려면 `main/.env`에서 모듈별 어댑터를 `http`로 바꾸고 내부 주소를 가리키게 해야 한다:

```bash
# main/.env 에 추가
CLIENTELING_ADAPTER=http
CLIENTELING_BASE_URL=http://127.0.0.1:8102
ASSET_ADAPTER=http
ASSET_BASE_URL=http://127.0.0.1:8103
# AI1 인텐트 (노트북 로직 실서버 — INTENT_BASE_URL 기본값이 이미 :8101)
INTENT_ADAPTER=http
# 지문·컨디션도 같은 백엔드 프로세스가 서빙한다 (신형 app.main:app 기준 — 구형이면 404)
FINGERPRINT_ADAPTER=http
FINGERPRINT_BASE_URL=http://127.0.0.1:8103
CONDITION_ADAPTER=http
CONDITION_BASE_URL=http://127.0.0.1:8103
```

`docs/BACKEND_INTEGRATION.md`에 필드 매핑은 이미 돼 있지만, `cited_asset_ids`가 아직 채워지지
않는다는 알려진 갭이 있다(문서에 명시됨) — 이 레포의 정체성상 인용 없는 상담 응답은 "제품 실패"로
취급하므로, 전환 전에 그 문서부터 다시 확인할 것을 권한다. 발표에서 이 전환이 꼭 필요한 게 아니라면
mock 모드로 두는 편이 안전하다(데모가 결정적이고, LLM 크레딧도 안 든다).

## 발표 전 서버 데모 모드 전환 (권장)

현재 배포는 `DEMO_MODE=false` 다. 발표 전에 켜두면 통합 레이어의 LLM 응답이
`.cache/llm/` 에 디스크 캐시돼, 발표 중 같은 시나리오 재생이 과금 없이·흔들림 없이 돈다
(AI2 가 죽어도 어댑터 폴백 + 캐시로 화면은 정상). 서버에서:

```bash
# 1) main/.env 의 DEMO_MODE 를 true 로 (줄이 없으면 추가)
sudo -u muhandojeon sed -i 's/^DEMO_MODE=.*/DEMO_MODE=true/' /opt/muhandojeon/main/.env
grep DEMO_MODE /opt/muhandojeon/main/.env   # DEMO_MODE=true 확인

# 2) 시나리오 3종 예비 실행으로 캐시 채우기 (Lab 은 건너뜀 — 과금 방지)
cd /opt/muhandojeon/main
sudo -u muhandojeon sh -c 'DEMO_MODE=true .venv/bin/python -m scripts.warm_cache --skip-lab'

# 3) 재시작 + 확인
sudo systemctl restart muhandojeon-app
curl -s localhost:8000/health/detail | python3 -c "import sys,json; d=json.load(sys.stdin); print('demo_mode:', d['demo']['demo_mode'], '/ cache:', d['llm'].get('cache_entries'))"
```

발표가 끝나면 원복은 같은 방법으로 `DEMO_MODE=false`.

## 코드 갱신할 때 (재배포)

```bash
cd /opt/muhandojeon/main && sudo -u muhandojeon git pull
sudo systemctl restart muhandojeon-app muhandojeon-backend muhandojeon-ai-clienteling muhandojeon-ai-intent
sudo bash /opt/muhandojeon/main/deploy/04_build_frontend.sh   # 프론트 변경 시에만
sudo systemctl reload nginx
```

`deploy/` 밑의 systemd 유닛·nginx 설정이 바뀐 커밋을 받았다면 `git pull` 만으로는 반영되지
않는다 — `05_systemd_install.sh`(유닛 복사+재시작), `06_nginx_install.sh`(설정 복사+reload)를
다시 실행한다.

## 단일 체크아웃 전환 (구 배포에서 1회)

ai-clienteling 이 main 에 merge 되기 전에 배포한 서버는 아직
`/opt/muhandojeon/ai-clienteling-src` 체크아웃으로 서비스가 돌고 있다. 전환은 1회:

```bash
cd /opt/muhandojeon/main && sudo -u muhandojeon git pull      # ai-clienteling/ 이 들어온다
sudo bash /opt/muhandojeon/main/deploy/03_setup_python.sh     # main/ai-clienteling/.venv 생성
# 기존 .env 를 그대로 가져온다 (키 재입력 불필요)
sudo -u muhandojeon cp /opt/muhandojeon/ai-clienteling-src/ai-clienteling/.env \
                       /opt/muhandojeon/main/ai-clienteling/.env
sudo bash /opt/muhandojeon/main/deploy/05_systemd_install.sh  # 새 경로 유닛 반영 + 재시작
bash /opt/muhandojeon/main/deploy/08_healthcheck.sh           # :8102 OK 확인
# 정상 확인 후에만 구 체크아웃 제거 (확인 전엔 지우지 않는다)
sudo rm -rf /opt/muhandojeon/ai-clienteling-src
```
