# SLOPE SNOWFIGHT — Blender 맵 5종

`map.png`(맵 컨셉 시안)를 기준으로 Blender 5.3 (bpy)에서 실제 메시로 만든 맵입니다. 게임 코드·서버·`maps.js`는 건드리지 않았습니다.

## 다시 만들기

```sh
blender --background --python scripts/generate_props.py            # 소품 39종 → glb/props, renders/props, metadata/props.json
blender --background --python scripts/generate_maps.py             # 맵 5종 전부 (blend, glb, metadata, renders)
blender --background --python scripts/generate_maps.py -- base_camp --no-render   # 한 맵만, 렌더 생략
```

| 파일 | 역할 |
|---|---|
| `scripts/common.py` | 재질 라이브러리, 메시 빌더, SDF→Quadriflow 메싱 |
| `scripts/generate_props.py` | 소품(나무 4종, 산장 3종, 눈벽, 리프트, 얼음 소품 …) |
| `scripts/generate_maps.py` | 지형·배치·스폰·충돌 메타데이터·환경 프리셋 |
| `scripts/export_glb.py` | glTF 2.0 (GLB) 내보내기 — 조명·카메라 미포함 |
| `scripts/render_preview.py` | EEVEE 1920×1080 렌더(렌더 전용 조명·하늘) |
| `scripts/export_game_data.py` | 메타데이터 → 게임 데이터 모듈 `../maps_glb.js` (Blender 불필요) |

## 개인전 맵 Snow Brawl Arena

```sh
blender --background --python scripts/generate_maps.py -- snow_brawl_arena   # blend · glb · metadata · renders
blender --background --python scripts/brawl_deliverables.py                 # → snow_brawl_arena/ 결과물 7종 + validation_report.json
```

`snow_brawl_arena/` 에 `snow_brawl_arena.blend`·`.glb`(압축 전)·`terrain_collision.json`(높이·경사 101×101)·`colliders.json`(장애물·바깥 눈벽 링)·`spawn_points.json`(12곳)·`map_config.json`·`preview.png`. 검증 스크립트가 GLB 를 다시 불러와 메시·재질, 지형 정점 ↔ 높이 격자, 오브젝트 위치, 스폰 ↔ 장애물 거리, 나무 없음을 확인. 지름 60m 원형(높은 눈벽 링), 안쪽 경사 1.3° 이하, 낮은 눈벽·눈더미·눈사람 엄폐물

## 게임에 넣기

맵을 다시 만든 뒤에는 게임 데이터도 다시 뽑습니다(서버·화면이 같이 씀):

```sh
blender --background --python scripts/generate_maps.py        # blend · glb · metadata · renders
sh scripts/compress_maps.sh                                    # glb/maps_raw → glb/maps (Meshopt 압축, 게임이 받는 파일)
python3 scripts/export_game_data.py                            # → ../maps_glb.js (높이 격자·장애물·스폰·조명)
```

- 게임은 `glb/maps/<id>.glb`(Meshopt 압축본)를 `/assets/maps/<id>.glb` 로 받고(`mapglb.js` 가 MeshoptDecoder 로 풀고 InstancedMesh 로 묶음), 판정은 `maps_glb.js` 로 합니다. Blender 원본은 `glb/maps_raw/`
- 높이는 **걸을 수 있는 면**(지형·얼음판·절벽 턱 중 위쪽)을 1m 격자로. 아이스 레이크 절벽은 오를 수 없게 상자 하나로 막음
- 원본 백업: `_backup_v1/` (최적화·통합 전), `_backup_v2/` (야간 조명 베이크·압축 전)

## 좌표

- GLB·메타데이터 좌표는 three.js 기준(+Y 위). 플레이 영역 x, z ∈ [-50, 50], 맵 중심 (0, 0, 0)
- 지형 오브젝트 `terrain`이 정확히 100×100 m. 그 밖(배경 언덕 `backdrop_hills`, 먼 나무, 오로라)은 장식
- 펭귄 키 2 m 기준 (눈벽 낮음 1.0 m / 높음 2.2 m, 나무 5–8.6 m, 산장 약 7–8 m)

## 메타데이터 (`metadata/<map>.json`)

- `terrain.heightfield.heights[r][c]` = 높이(three y), x = -50 + c, z = -50 + r (1 m 격자 101×101)
- `spawns.pink / spawns.blue` = 팀별 스폰 후보 4곳 (평탄, 장애물에서 2.5 m 이상)
- `objects[]` = 이름·소품·위치·회전(y)·크기·장식 여부·충돌 형상
  - `collider.shape`: `cylinder` | `box` | `cylinders`
  - `collider.cylinders`: 현재 서버(`maps.js` 의 `body/ball/top`)에 그대로 넣을 수 있는 세운 원기둥 근사
- `environment` = 게임에서 따로 설정해야 할 하늘·안개·반구광·태양/달·노출. **GLB에는 조명이 없습니다.**
  야간 맵은 발광 재질(창문·전구·가로등·오로라)만 GLB에 있고, 가로등·조명탑·산장 불빛용 라이트 목록이 `environment.lights` 에 있습니다.
- `ice_lake.json` 의 `ice_zone` = 미끄러지는 빙판 영역(타원)

## 참고

- 같은 소품은 GLB 안에서 지오메트리를 공유합니다(예: 나무 46그루 = 메시 4개). 게임에서 `InstancedMesh` 로 묶으면 draw call 이 크게 줍니다.
- LOD 없음: 데스크톱·모바일 에뮬레이션에서 60fps 를 유지해 만들지 않았습니다(실기기 측정 전).
