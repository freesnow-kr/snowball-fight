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
for (const m of MAPS) m.obstacles = makeObstacles(m);

// ponytail: 장애물 전체를 매번 훑음(맵당 최대 ~170개). 느려지면 격자로 나눠 근처만 보기
// 눈덩이가 장애물에 막혔나
export function blocksBall(m, x, y, z) {
  for (const o of m.obstacles) if (y < o.y + o.top && (x - o.x) ** 2 + (z - o.z) ** 2 < o.ball ** 2) return true;
  return false;
}
// 몸(반지름 rad)이 장애물과 겹치면 바깥으로 밀어낸 위치
export function pushOut(m, x, z, rad = 0.4) {
  for (const o of m.obstacles) {
    const dx = x - o.x, dz = z - o.z, d = Math.hypot(dx, dz), min = o.body + rad;
    if (d < min && d > 1e-6) { x = o.x + (dx / d) * min; z = o.z + (dz / d) * min; }
  }
  return [x, z];
}
