# 슬로프 눈싸움 ⛷️

브라우저에서 바로 하는 3D 팀 눈싸움. 펭귄 보더가 되어 💗 핑크팀 vs 🔵 블루팀으로 3분씩 겨룹니다. PC·모바일 모두 지원.

## 실행

[Deno](https://deno.com) 가 필요합니다.

```sh
deno run --allow-net --allow-read --allow-env server.ts   # http://localhost:8000
PORT=8791 deno run --allow-net --allow-read --allow-env server.ts   # 포트 바꾸기
deno test server_test.ts   # 서버 규칙 테스트
```

같은 와이파이의 친구는 `http://<내 IP>:8000` 으로 들어옵니다.

### 개발용 (배포 서버에선 꺼져 있음)

```sh
DEV=1 deno run --allow-net --allow-read --allow-env server.ts           # 개발 명령(판 바로 끝내기) 허용
DEV=1 LAG=80 deno run --allow-net --allow-read --allow-env server.ts    # 주고받는 메시지마다 0.08초 지연(왕복 0.16초) 흉내
```

`http://localhost:8000/?debug` 로 열면 디버그 패널(`debug.js`)이 뜹니다: 명중 판정 구·모델 경계·눈덩이 궤적·명중 위치 표시, 화면↔서버 명중 일치 통계, 판 끝내기(우리 승·상대 승·무승부)·내 승리 동작, 캐릭터 수·눈덩이·파티클 부하, 5초 성능 측정(fps·1% low·JS·GPU 시간·draw call·삼각형·메모리). localhost 가 아니면 `?debug` 를 붙여도 안 뜹니다.

## 배포 (Render)

`Dockerfile` 과 `render.yaml` 이 들어 있습니다. Render 대시보드에서 **New → Blueprint** 로 이 저장소를 고르면 무료 웹 서비스(싱가포르)로 배포되고, `main` 에 올릴 때마다 자동으로 다시 배포됩니다. 게임 상태는 서버 메모리에만 있어서 재시작하면 판이 초기화됩니다.

## 조작

| 동작 | PC | 모바일 |
|---|---|---|
| 이동 (카메라 기준) | WASD, 방향키 | 조이스틱 |
| 시점 · 확대 | 마우스 끌기·트랙패드 두 손가락 · 휠 | 화면 드래그 · 두 손가락 벌리기 |
| 던지기 | 클릭한 곳으로, E·J는 앞의 상대 자동 조준 | 화면 탭한 곳으로, ❄️ 던지기는 자동 조준 |
| 눈 모으기 | F 꾹 | 🤲 꾹 |
| 굴려서 놓기 (3단이면 눈사람) | R 꾹 → 떼기 | ⚪ 꾹 → 떼기 |
| 점프 · 달리기 | Space · Shift | ⬆️ · 조이스틱 끝까지 |
| 이모트 · 맵 바꾸기 | 1~6 · M | 😀 · 🗺️ |

## 규칙

- 3번 맞으면 3초 동안 얼음에 갇힘. 같은 팀은 맞지 않음
- 착지 원 근처에 거의 멈춘 상대가 있으면 조준 보정(원이 빨갛게)
- 팀마다 최소 4명이 되도록 봇이 채움. 3분이 지나면 팀 점수로 승패
- 맵: 슬로프, 숲속 공터, 꽁꽁 언 호수(빙판에서 미끄러짐) + Blender 맵 베이스 캠프, 슬로프 필드, 아이스 레이크(빙판), 포레스트 빌리지, 나이트 리조트. 맵마다 방이 따로

## 구조

- `server.ts` — 방(맵)별 게임 상태, 명중 판정, 봇, 판 진행, WebSocket
- `index.html` — 화면(three.js), 조작, 예측(내 눈덩이는 바로 보임)
- `maps.js` — 지형 높이·장애물(원기둥 + 회전 상자). 서버와 화면이 같은 파일을 써서 어긋나지 않음
- `maps_glb.js` — Blender 맵의 걸을 수 있는 높이(1m 격자)·장애물·스폰·조명 (생성 파일: `python3 SLOPE_SNOWFIGHT_MAPS/scripts/export_game_data.py`)
- `mapglb.js` — Blender 맵 GLB 불러오기·캐싱, 반복 소품 InstancedMesh, 맵을 떠나면 GPU 해제
- `SLOPE_SNOWFIGHT_MAPS/` — Blender 맵 원본·GLB·메타데이터·스크립트 (자세한 건 그 폴더 README)
- `penguin.js` + `assets/penguin_blue.glb` — 펭귄 캐릭터(GLB 1개로 팀 색·표정 6종·동작 9종). 모델은 `blender/build_penguin.py` 로 다시 만듦, `blender/glb-check.html` 에서 검증·미리보기
- `chars.js` — 예전 코드 펭귄(지금 게임에선 안 씀, `characters.html` 미리보기용)
