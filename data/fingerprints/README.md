# 개체 지문 등록 이미지

경로 규약: `data/fingerprints/{asset_id}/{부위}_{번호}.jpg` — `asset_id` 는 시드와 같은
**4자리**(`AS-0001`)다. 부위는 handle / corner / stitching / hardware 4종 × 2장
(촬영 가이드: `docs/FINGERPRINT_CAPTURE.md`).

- 이 폴더에 이미지가 있고 **시드에 존재하는** 개체만 `GET /demo/fingerprint-samples` 에
  노출된다 — 개체 식별 화면(`/identify`)의 "등록 개체로 시연" 갤러리가 이걸 쓴다.
- 이미지 경로는 `POST /fingerprint/match` 의 `image_path` 로 그대로 들어가고,
  백엔드 ORB 매칭(`backend/app/services/fingerprint_service.py`)의 등록 DB 이기도 하다.
- 미리보기는 통합 레이어가 `/static/fingerprints/...` 로 서빙한다.

## 레포에는 무엇이 들어가나

기본적으로 이 폴더는 gitignore 대상(로컬 보관)이고, **데모 등록 개체 `AS-0001/` 과
이 README 만 예외**로 레포에 포함한다 — 배포 서버·CI 가 git clone 으로 받아야
갤러리·매칭·테스트가 돌기 때문이다. 새 개체를 데모에 쓰려면 `.gitignore` 의 예외
목록에 그 폴더를 추가한다.

`AS-000001/`(구 6자리 규약 시절 촬영본)은 로컬에만 보관하고 레포에 넣지 않는다.
시드에 없는 폴더는 샘플 목록·목 매칭에서 **자동 제외**되므로 남아 있어도 데모에
영향이 없다. 새 등록은 반드시 4자리 규약으로.
