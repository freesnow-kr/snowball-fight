#!/bin/sh
# Blender 원본 GLB(glb/maps_raw) → Meshopt 압축 GLB(glb/maps, 게임이 받는 파일). 게임은 MeshoptDecoder 로 풂(mapglb.js)
# 측정(2026-11): 전송 0.88–1.37MB → 0.28–0.38MB, 4G 근사 로딩 0.9–1.35초 → 0.42–0.50초, 화면·구조 동일
set -e
cd "$(dirname "$0")/.."
for f in glb/maps_raw/*.glb; do
  npx --yes @gltf-transform/cli@4 meshopt "$f" "glb/maps/$(basename "$f")" --level medium
done
