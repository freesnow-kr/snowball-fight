import { GLB_MAPS } from './maps_glb.js';
// 맵: 서버(server.ts)와 화면(index.html)이 같은 파일을 쓴다 → 땅 높이·장애물 자리가 서로 어긋나지 않는다.
// 장식 소품(리프트·낚시 구멍 등)은 화면 전용이라 index.html 의 buildMap 에 있다.
// spawnX: 팀 출발 위치 x 범위(오렌지는 -, 블루는 +). ice: 이 반지름 안은 빙판(미끄러짐).
export const MAPS = [
  {
    id: 'slope', name: '슬로프', emoji: '⛷️', spawnX: [30, 40],
    h: (x, z) => 8 * Math.exp(-(x * x + (z + 30) ** 2) / 600) + 0.8 * Math.sin(x * 0.12) * Math.cos(z * 0.1),
  },
  {
    id: 'forest', name: '숲속 공터', emoji: '🌲', spawnX: [26, 36],
    h: (x, z) => 1.1 * Math.sin(x * 0.07) * Math.cos(z * 0.06) + 0.5 * Math.sin((x + z) * 0.13) + 0.0015 * (x * x + z * z),
  },
  {
    id: 'lake', name: '꽁꽁 언 호수', emoji: '🧊', spawnX: [14, 22], ice: 24,
    h: (x, z) => { const r = Math.hypot(x, z); return r < 24 ? 0 : 0.015 * (r - 24) ** 2; },
  },
];
// Blender 로 만든 맵 5종(SLOPE_SNOWFIGHT_MAPS). 높이·장애물·스폰은 maps_glb.js(메타데이터에서 생성)를 서버와 화면이 같이 씀.
// 모양은 GLB(glb), 땅 높이는 1m 격자를 이중선형으로(GLB 지형 정점과 같은 값), 장애물은 원기둥 + 회전 상자
function gridHeight(b64, n) {
  const bin = atob(b64), a = new Int16Array(n * n), half = (n - 1) / 2;
  for (let i = 0; i < a.length; i++) a[i] = (bin.charCodeAt(2 * i) | (bin.charCodeAt(2 * i + 1) << 8)) << 16 >> 16;
  return (x, z) => {
    const fx = Math.max(0, Math.min(n - 1, x + half)), fz = Math.max(0, Math.min(n - 1, z + half));
    const c = Math.min(n - 2, Math.floor(fx)), r = Math.min(n - 2, Math.floor(fz)), u = fx - c, v = fz - r, k = r * n + c;
    return ((a[k] * (1 - u) + a[k + 1] * u) * (1 - v) + (a[k + n] * (1 - u) + a[k + n + 1] * u) * v) / 100;
  };
}
for (const g of GLB_MAPS) {
  const ice = g.ice ? (x, z) => ((x - g.ice.x) / g.ice.rx) ** 2 + ((z - g.ice.z) / g.ice.rz) ** 2 < 1 : null;
  MAPS.push({ id: g.id, name: g.name, emoji: g.emoji, glb: g.glb, h: gridHeight(g.heights, g.n), obstacles: g.obstacles,
    spawns: g.spawns, spawnX: [36, 44], sky: g.sky, fog: g.fog, env: g.env, onIce: ice });
}
export const mapById = (id) => MAPS.find((m) => m.id === id) ?? MAPS[0];

// 고정 시드 난수: 서버와 화면이 같은 순서로 부르면 같은 자리가 나온다
const rng = (seed) => () => (seed = (seed * 16807) % 2147483647) / 2147483647;

// 장애물(세운 원기둥으로 판정). kind: tree|rock|log|hut, s: 크기, rot: 눕힌 방향(통나무)
// ball: 눈덩이를 막는 반지름, body: 몸을 막는 반지름(나무는 줄기 쪽만), top: 땅에서부터 높이
function makeObstacles(m) {
  const r = rng(11), out = [];
  const inSpawn = (x, z) => Math.abs(x) > m.spawnX[0] - 4 && Math.abs(x) < m.spawnX[1] + 4 && z > -9 && z < 19;
  const put = (o) => out.push({ ...o, y: m.h(o.x, o.z) });
  const tree = (x, z, s) => put({ kind: 'tree', x, z, s, ball: 0.9 * s, body: 0.35 * s, top: 4.5 * s });
  const scatter = (n, r0, r1, ok = () => true) => {
    for (let i = 0; i < n; i++) {
      const a = r() * Math.PI * 2, d = r0 + r() * (r1 - r0), x = Math.cos(a) * d, z = Math.sin(a) * d, s = 0.8 + r() * 0.9;
      if (ok(x, z)) tree(x, z, s);
    }
  };
  if (m.id === 'slope') {
    scatter(14, 14, 40, (x, z) => Math.abs(x + 20) > 4 && !inSpawn(x, z)); // 리프트 줄은 비움
    scatter(66, 44, 58);
    put({ kind: 'hut', x: -16, z: 40, s: 1, ball: 2.3, body: 2.3, top: 4 });
  }
  if (m.id === 'forest') {
    scatter(40, 10, 38, (x, z) => !inSpawn(x, z));
    scatter(120, 40, 58);
    for (let i = 0; i < 6; i++) {
      const x = (r() - 0.5) * 50, z = (r() - 0.5) * 50, rot = r() * 3;
      if (!inSpawn(x, z)) put({ kind: 'log', x, z, s: 1, rot, ball: 1.1, body: 1.0, top: 0.7 });
    }
    for (let i = 0; i < 10; i++) {
      const x = (r() - 0.5) * 60, z = (r() - 0.5) * 60, s = 0.6 + r() * 0.9;
      if (!inSpawn(x, z)) put({ kind: 'rock', x, z, s, ball: s, body: s * 0.9, top: s * 1.2 });
    }
  }
  if (m.id === 'lake') {
    scatter(90, 32, 58);
    put({ kind: 'hut', x: 8, z: -14, s: 0.7, ball: 1.6, body: 1.6, top: 3 });
  }
  return out;
}
for (const m of MAPS) m.obstacles ??= makeObstacles(m); // Blender 맵은 메타데이터의 장애물을 그대로 씀

// ── 이동 물리 상수 (index.html 의 내 이동과 server.ts 의 검증이 같은 값을 씀)
export const GRAVITY = 24, JUMP_V = 8, BODY_R = 0.4;
// ── 점프대(jump_ramp): 장애물이 아니라 걸어 올라가는 비탈. 앞(입술, 로컬 +z)으로 갈수록 높이 1.4m 까지 오름.
// 입술 근처(끝 0.7m)를 앞으로 달려 지나가면 위로 튀어 오름. 앞에서 정면으로는 1.4m 턱이라 못 올라감(얇은 벽)
export const RAMP_EDGE = 0.7, RAMP_MIN_V = 1.5, RAMP_VY_MAX = 9;
export const rampVy = (along) => along < RAMP_MIN_V ? 0 : Math.min(RAMP_VY_MAX, 2.5 + 0.9 * along); // 달리기 7.2m/s → 9, 걷기 4.4 → 6.5
function setupRamps(m) {
  const ramps = m.obstacles.filter((o) => o.kind === 'jump_ramp');
  if (!ramps.length) return;
  const base = m.h;
  m.ramps = ramps.map((o) => ({ ...o, H: o.top, dir: [Math.sin(o.rot), Math.cos(o.rot)] }));
  m.obstacles = m.obstacles.filter((o) => o.kind !== 'jump_ramp');
  for (const r of m.ramps) { // 입술 앞면: 땅에서 다가오면 막고, 비탈 위(발이 꼭대기 근처)면 통과
    const [lx, lz] = [r.x + r.dir[0] * (r.hd + 0.06), r.z + r.dir[1] * (r.hd + 0.06)];
    m.obstacles.push({ kind: 'ramp_lip', x: lx, z: lz, y: base(lx, lz), hw: r.hw, hd: 0.06, rot: r.rot, top: r.H - 0.15, ball: 0, hop: 1 });
  }
  m.h = (x, z) => { const g = base(x, z), r = rampAt(m, x, z); return r ? g + r.H * (r.lz + r.hd) / (2 * r.hd) : g; };
}
// (x,z) 가 점프대 위면 { ...점프대, lz: 로컬 앞뒤 위치 }
export function rampAt(m, x, z) {
  for (const r of m.ramps ?? []) {
    const [lx, lz] = toLocal(r, x, z);
    if (Math.abs(lx) <= r.hw && Math.abs(lz) <= r.hd) return { ...r, lz };
  }
  return null;
}
// 점프대 입술 근처를 앞으로 지나가는 중이면 튀어 오르는 속도, 아니면 0
export function rampLaunch(m, x, z, vx, vz) {
  const r = rampAt(m, x, z);
  if (!r || r.lz < r.hd - RAMP_EDGE) return 0;
  return rampVy(vx * r.dir[0] + vz * r.dir[1]);
}
// 몸(반지름 BODY_R)을 (ax,az)→(bx,bz) 로 쓸고 지나가며 장애물을 비켜 간 끝 위치. 0.2m 씩 나눠 밀어냄 →
// 가장 얇은 벽(반폭 0.06 + 몸 0.4)도 건너뛰지 못하고, 벽에 비스듬히 부딪히면 벽을 따라 미끄러짐
// 발 높이도 출발 y → 도착 y1 로 이어서 봄(낮은 눈벽은 그 순간 발이 꼭대기 위일 때만 통과)
export function sweep(m, ax, az, bx, bz, y, y1 = y) {
  const d = Math.hypot(bx - ax, bz - az), n = Math.max(1, Math.ceil(d / 0.2));
  let x = ax, z = az;
  for (let i = 1; i <= n; i++) [x, z] = pushOut(m, x + (bx - ax) / n, z + (bz - az) / n, BODY_R, y + (y1 - y) * i / n);
  return [x, z];
}

// ponytail: 장애물 전체를 매번 훑음(맵당 최대 ~170개). 느려지면 격자로 나눠 근처만 보기
// 눈덩이가 장애물에 막혔나
// 회전 상자(hw·hd: 반폭, rot: three.js rotation.y)의 로컬 좌표 ↔ 월드
export const toLocal = (o, x, z) => { const dx = x - o.x, dz = z - o.z, c = Math.cos(o.rot), s = Math.sin(o.rot); return [dx * c - dz * s, dx * s + dz * c]; };
const toWorld = (o, lx, lz) => { const c = Math.cos(o.rot), s = Math.sin(o.rot); return [o.x + lx * c + lz * s, o.z - lx * s + lz * c]; };
export function blocksBall(m, x, y, z) {
  for (const o of m.obstacles) {
    if (y >= o.y + o.top) continue;
    if (o.hw !== undefined) { const [lx, lz] = toLocal(o, x, z); if (Math.abs(lx) < o.hw + o.ball && Math.abs(lz) < o.hd + o.ball) return true; }
    else if ((x - o.x) ** 2 + (z - o.z) ** 2 < o.ball ** 2) return true;
  }
  return false;
}
// 몸(반지름 rad)이 장애물과 겹치면 바깥으로 밀어낸 위치. y(발바닥 높이)를 주면 낮은 장애물(hop)은 발이 꼭대기보다 높을 때 통과
// (서버는 보고받은 최종 위치로, 화면은 수직 이동까지 마친 최종 위치로 같은 판정)
export function pushOut(m, x, z, rad = 0.4, y) {
  // 장애물이 서로 겹친 곳(산장+울타리, 절벽 상자들)에선 한 번 밀어낸 자리가 앞 장애물 안일 수 있음 → 더 안 바뀔 때까지 최대 4번
  for (let pass = 0; pass < 4; pass++) {
    const [nx, nz] = pushOnce(m, x, z, rad, y);
    const done = Math.abs(nx - x) < 1e-6 && Math.abs(nz - z) < 1e-6;
    x = nx; z = nz;
    if (done) break;
  }
  return [x, z];
}
function pushOnce(m, x, z, rad, y) {
  for (const o of m.obstacles) {
    if (o.hop && y !== undefined && y >= o.y + o.top) continue; // 점프로 넘는 중
    if (o.hw !== undefined) { // 회전 상자: 가장 가까운 상자 위 점에서 rad 만큼 떨어지게
      let [lx, lz] = toLocal(o, x, z);
      const qx = Math.max(-o.hw, Math.min(o.hw, lx)), qz = Math.max(-o.hd, Math.min(o.hd, lz)), ex = lx - qx, ez = lz - qz, d = Math.hypot(ex, ez);
      if (d >= rad) continue;
      if (d > 1e-6) { lx = qx + (ex / d) * rad; lz = qz + (ez / d) * rad; }
      else if (o.hw - Math.abs(lx) < o.hd - Math.abs(lz)) lx = (lx < 0 ? -1 : 1) * (o.hw + rad); // 상자 안: 가장 얕은 쪽으로
      else lz = (lz < 0 ? -1 : 1) * (o.hd + rad);
      [x, z] = toWorld(o, lx, lz);
      continue;
    }
    let dx = x - o.x, dz = z - o.z, d = Math.hypot(dx, dz);
    const min = o.body + rad;
    if (d < 1e-6) { dx = d = 1e-6; dz = 0; } // 정확히 한가운데면 아무 쪽으로나
    if (d < min) { x = o.x + (dx / d) * min; z = o.z + (dz / d) * min; }
  }
  return [x, z];
}

// ── 눈덩이 ↔ 펭귄 명중 판정 (서버가 판정, 화면은 같은 식으로 미리 터뜨리고 디버그로 그림)
// 2m 펭귄(penguin.js)을 높이별로 잰 반폭 + 눈덩이 반지름 0.18 에 맞춘 구 두 개 [발 위 높이, 반지름]
// 몸통·점퍼(반폭 0.74@0.4m, 0.49@0.8m) / 머리·고글·모자(0.68@1.3m, 모자 꼭대기 2.0m)
export const BALL_R = 0.18;
export const HIT_SPHERES = [[0.6, 0.8], [1.25, 0.82]]; // 후보 비교(0.9/0.7/0.65/0.6 구 1개)보다 평균 오차 0.19→0.07m
// 선분 a→b 와 점 c 사이 최단 거리
export function segDist(ax, ay, az, bx, by, bz, cx, cy, cz) {
  const dx = bx - ax, dy = by - ay, dz = bz - az, l2 = dx * dx + dy * dy + dz * dz;
  const t = l2 ? Math.max(0, Math.min(1, ((cx - ax) * dx + (cy - ay) * dy + (cz - az) * dz) / l2)) : 0;
  return Math.hypot(ax + dx * t - cx, ay + dy * t - cy, az + dz * t - cz);
}
// 이번 틱에 눈덩이가 지나간 선분 a→b 가 (px,py,pz)에 선 펭귄에 닿았나 (py = 발바닥 높이)
export function hitsPenguin(ax, ay, az, bx, by, bz, px, py, pz) {
  for (const [h, r] of HIT_SPHERES) if (segDist(ax, ay, az, bx, by, bz, px, py + h, pz) < r) return true;
  return false;
}

// 점프대 준비는 판정 함수(toLocal·pushOut)가 다 정의된 뒤에
for (const m of MAPS) setupRamps(m);
