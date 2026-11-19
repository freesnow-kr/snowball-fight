// Blender 맵 GLB(SLOPE_SNOWFIGHT_MAPS/glb/maps) 불러오기.
// - 맵마다 한 번만 내려받아 캐싱(같은 맵 동시 요청은 같은 Promise). 실패하면 캐시에서 빼서 다시 시도 가능
// - 반복 소품(나무·바위·눈벽·울타리·가로등…)은 GLB 안에서 지오메트리를 공유하지만 메시마다 draw call 이 나감
//   → 같은 (지오메트리, 재질) 짝을 모아 InstancedMesh 하나로. 각 인스턴스의 위치·회전·크기는 원래 월드 행렬 그대로
//   서로 다른 재질·모양은 합치지 않음(재질 하나 = 묶음 하나)
// - 맵을 떠나면 releaseGPU 로 GPU 버퍼·셰이더를 놓아줌. 객체는 캐시에 남아 다시 오면 three 가 다시 올림
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js'; // 맵 GLB 는 Meshopt 압축(EXT_meshopt_compression)

const cache = new Map(); // url → Promise<{ root, stats }>
// 개발용 비교: ?cell=25|50|100 로 칸 크기를 바꿔 볼 수 있음(없으면 기본값)
const CELL = Number(typeof location !== 'undefined' && new URLSearchParams(location.search).get('cell')) || 1e9; // 칸을 나누지 않음: 측정상 1칸 draw call −73~89%(삼각형 +15~35%), 2×2 −45~55%, 3×3 −40~50%. ponytail: 폰 GPU 가 삼각형에 막히면 CELL=50
const NO_SHADOW = /^(terrain|backdrop_hills|ice_lake_surface|ice_cliff|aurora|string_lights|lift_cables|cliff_icicles)/; // 땅·하늘 장식은 그림자를 드리우지 않음(받기만)

export function loadMap(url, onProgress) {
  if (!cache.has(url)) {
    const p = new Promise((res, rej) => new GLTFLoader().setMeshoptDecoder(MeshoptDecoder).load(url, (g) => res(instance(g)), (e) => e.total && onProgress?.(e.loaded / e.total), rej));
    p.catch(() => cache.delete(url));
    cache.set(url, p);
  }
  return cache.get(url);
}

const nodeName = (o) => (o.parent && !o.parent.isScene && o.parent.parent?.isScene ? o.parent.name : o.name); // 재질이 여럿인 노드는 부모 그룹 이름
function instance(gltf) {
  const src = gltf.scene; src.updateMatrixWorld(true);
  const groups = new Map(); let meshes = 0;
  src.traverse((o) => {
    if (!o.isMesh) return; meshes++;
    const p = o.getWorldPosition(new THREE.Vector3()), cell = Math.floor((p.x + 50) / CELL) + ',' + Math.floor((p.z + 50) / CELL);
    const k = o.geometry.uuid + '|' + o.material.uuid + '|' + cell;
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(o);
  });
  const root = new THREE.Group(); root.name = 'glb_map';
  let instanced = 0, instances = 0;
  for (const list of groups.values()) {
    const m0 = list[0], cast = !NO_SHADOW.test(nodeName(m0));
    let m;
    if (list.length === 1) { // 하나뿐: 월드 행렬을 그대로 굳힌 메시
      m = new THREE.Mesh(m0.geometry, m0.material); m.matrixAutoUpdate = false; m.matrix.copy(m0.matrixWorld); m.name = m0.name;
    } else {
      m = new THREE.InstancedMesh(m0.geometry, m0.material, list.length); m.name = m0.name + '×' + list.length;
      list.forEach((o, i) => m.setMatrixAt(i, o.matrixWorld));
      m.instanceMatrix.needsUpdate = true; m.computeBoundingSphere(); // 화면 밖 판정: 인스턴스 전체를 감싸는 구
      instanced++; instances += list.length;
    }
    m.castShadow = cast; m.receiveShadow = true;
    root.add(m);
  }
  return { root, stats: { meshes, drawGroups: groups.size, instanced, instances } };
}

export function releaseGPU(root) {
  root.traverse((o) => {
    if (!o.isMesh) return;
    o.geometry.dispose(); if (o.isInstancedMesh) o.dispose(); // 인스턴스 행렬 버퍼
    o.material.dispose();
    for (const v of Object.values(o.material)) if (v?.isTexture) v.dispose();
  });
}
