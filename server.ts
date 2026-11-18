// 실행: deno run --allow-net --allow-read --allow-env server.ts  →  http://localhost:8000
// 맵마다 방이 하나씩 있고(maps.js), 방마다 플레이어·눈덩이·눈사람·점수·판이 따로 돈다.
import { blocksBall, MAPS, mapById, pushOut } from "./maps.js";

const ARENA = 50, MAX_HUMANS = 30, MAX_AMMO = 10, HP = 3, G = -15, DT = 1 / 30, MAX_PILES = 40;
const MOVE_SPEED = 8, MOVE_BURST = 3; // 위치 보고 검사: 초당 8m(달리기 7.2+여유)씩 쌓이는 이동 한도, 최대 3m까지 모아 둠(넉백·전송 지연)
// 사람이 던진 공은 상대의 이 시간 전 위치로도 맞았는지 본다. 내 화면 속 남들은 그리기 지연(0.11초)+통신 시간만큼 과거 모습이라서
const REWIND_MS = 200;
const TEAM_SIZE = 4; // 팀마다 사람+봇 최소 인원. 모자라면 봇이 채우고, 사람이 들어오면 봇이 빠진다
export const ROUND_MS = 180_000, BREAK_MS = 6_000; // 한 판 3분, 결과 보여 주는 시간 6초
const BOT_NAMES = ["눈송이", "고드름", "함박", "싸락", "서리", "눈보라", "진눈깨비", "얼음꽃", "눈꽃", "포근"];

type Sock = { send(s: string): void };
const NOSOCK: Sock = { send() {} };
type Obstacle = { kind: string; x: number; y: number; z: number; s: number; ball: number; body: number; top: number };
type MapDef = { id: string; name: string; emoji: string; spawnX: number[]; h: (x: number, z: number) => number; obstacles: Obstacle[] };
export type Room = {
  map: MapDef; players: Map<number, P>; balls: Ball[]; piles: Pile[]; events: unknown[];
  game: { scores: number[]; roundEnd: number; breakUntil: number };
};
export type P = {
  id: number; name: string; team: number; bot: boolean; room: Room;
  x: number; y: number; z: number; yaw: number;
  // score = 상대를 맞힌 횟수, freezes = 내가 언 횟수 (둘 다 한 판마다 0부터)
  hp: number; ammo: number; score: number; freezes: number; frozenUntil: number; gather: boolean; gatherT: number;
  lastThrow: number; roll: number; sock: Sock;
  hist: number[][]; // 최근 0.5초 위치 기록 [시각, x, y, z]
  moveBudget: number; moveT: number; // 이번 보고에서 움직여도 되는 거리(m)와 마지막 보고 시각
  strafe: number; strafeUntil: number; throwAt: number; // 봇 전용
};
type Ball = { id: number; owner: number; team: number; x: number; y: number; z: number; vx: number; vy: number; vz: number; age: number; rewind: number };
export type Pile = { id: number; x: number; z: number; parts: number[] };

let nextId = 1, ballId = 1, pileId = 1;
export function createRoom(mapId: string): Room {
  return { map: mapById(mapId) as MapDef, players: new Map(), balls: [], piles: [], events: [], game: { scores: [0, 0], roundEnd: 0, breakUntil: 0 } };
}
export const rooms = new Map(MAPS.map((m) => [m.id, createRoom(m.id)]));

const r2 = (v: number) => Math.round(v * 100) / 100;
const num = (v: unknown, lo: number, hi: number) =>
  typeof v === "number" && Number.isFinite(v) ? Math.max(lo, Math.min(hi, v)) : null;
const clampA = (v: number) => Math.max(-ARENA, Math.min(ARENA, v));
const pick = <T>(a: T[]) => a[Math.floor(Math.random() * a.length)];
const meta = (p: P) => [p.id, p.name, p.team, p.bot ? 1 : 0];
const count = (room: Room, team: number, bot?: boolean) =>
  [...room.players.values()].filter((p) => p.team === team && (bot === undefined || p.bot === bot)).length;
export const humanCount = (room: Room) => count(room, 0, false) + count(room, 1, false);

// 원하는 맵 방에 자리가 있으면 그 방. 아니면(자동 포함) 사람이 가장 많은 방(같이 놀게), 다 비었으면 아무 방. 다 차면 null
export function pickRoom(want: unknown): Room | null {
  const asked = rooms.get(String(want));
  if (asked && humanCount(asked) < MAX_HUMANS) return asked;
  const open = [...rooms.values()].filter((r) => humanCount(r) < MAX_HUMANS);
  if (!open.length) return null;
  const most = Math.max(...open.map(humanCount));
  return pick(open.filter((r) => humanCount(r) === most));
}

// 팀 0(오렌지)은 서쪽, 팀 1(블루)은 동쪽에서 서로 마주 보고 시작
function spawnAt(p: P) {
  const side = p.team === 0 ? -1 : 1, [a, b] = p.room.map.spawnX;
  p.x = side * (a + Math.random() * (b - a));
  p.z = Math.random() * 20 - 5;
  p.y = p.room.map.h(p.x, p.z);
  p.yaw = -side * Math.PI / 2;
  p.moveBudget = MOVE_BURST;
  p.hist = []; // 부활하면 예전 자리로는 못 맞게
  p.moveT = Date.now();
}

function addPlayer(room: Room, sock: Sock, name: string, team: number, bot: boolean): P {
  const p: P = {
    id: nextId++, name, team, bot, room, x: 0, y: 0, z: 0, yaw: 0, hp: HP, ammo: MAX_AMMO, score: 0, freezes: 0,
    frozenUntil: 0, gather: false, gatherT: 0, lastThrow: 0, roll: 0, sock, hist: [], moveBudget: MOVE_BURST, moveT: 0,
    strafe: 1, strafeUntil: 0, throwAt: Date.now() + 1000 + Math.random() * 2000,
  };
  spawnAt(p);
  room.players.set(p.id, p);
  room.events.push(["join", ...meta(p)]);
  return p;
}

function remove(p: P) {
  p.room.players.delete(p.id);
  p.room.events.push(["leave", p.id]);
}

export function fillBots(room: Room) {
  for (const t of [0, 1]) {
    while (count(room, t) < TEAM_SIZE) addPlayer(room, NOSOCK, `🤖 ${pick(BOT_NAMES)}`, t, true);
    while (count(room, t) > TEAM_SIZE) {
      const b = [...room.players.values()].find((p) => p.team === t && p.bot);
      if (!b) break;
      remove(b);
    }
  }
}

// 사람 수가 적은 팀으로. 같으면 전체 인원이 적은 팀으로
export function join(room: Room, sock: Sock, name: unknown): P {
  const h0 = count(room, 0, false), h1 = count(room, 1, false);
  const team = h0 !== h1 ? (h0 < h1 ? 0 : 1) : count(room, 0) <= count(room, 1) ? 0 : 1;
  const p = addPlayer(room, sock, String(name ?? "").trim().slice(0, 12) || "익명", team, false);
  fillBots(room);
  sock.send(JSON.stringify({ t: "welcome", id: p.id, map: room.map.id, players: [...room.players.values()].map(meta), piles: room.piles }));
  return p;
}

export function leave(p: P) {
  remove(p);
  fillBots(p.room);
}

// 굴린 눈덩이를 앞에 놓는다. 근처 더미가 3단 미만이면 위에 쌓아 눈사람을 만든다.
function place(p: P) {
  const { piles, events } = p.room;
  const x = clampA(p.x + Math.sin(p.yaw) * 1.6), z = clampA(p.z + Math.cos(p.yaw) * 1.6);
  let pile = piles.find((q) => Math.hypot(q.x - x, q.z - z) < 1.6 && q.parts.length < 3);
  if (pile) pile.parts.push(r2(Math.min(p.roll, pile.parts.at(-1)!)));
  else {
    pile = { id: pileId++, x: r2(x), z: r2(z), parts: [r2(p.roll)] };
    piles.push(pile);
    if (piles.length > MAX_PILES) events.push(["pilex", piles.shift()!.id]);
  }
  events.push(["pile", pile]);
}

// deno-lint-ignore no-explicit-any
export function handle(p: P, m: any, now = Date.now()) {
  const frozen = p.frozenUntil > now, room = p.room;
  switch (m?.t) {
    case "p": {
      const x = num(m.x, -ARENA, ARENA), y = num(m.y, -10, 60), z = num(m.z, -ARENA, ARENA), yaw = num(m.yaw, -1e4, 1e4);
      if (frozen || x === null || y === null || z === null || yaw === null) return;
      // 마지막 보고 뒤 흐른 시간만큼 이동 한도가 쌓인다. 한도보다 멀리 가면 거절하고 서버 위치로 되돌림
      p.moveBudget = Math.min(MOVE_BURST, p.moveBudget + MOVE_SPEED * Math.max(0, now - p.moveT) / 1000);
      p.moveT = now;
      const [cx, cz] = pushOut(room.map, x, z); // 나무·바위·오두막 안으로는 못 들어감
      const step = Math.hypot(cx - p.x, cz - p.z);
      if (step > p.moveBudget) {
        p.sock.send(JSON.stringify({ t: "pos", x: p.x, y: p.y, z: p.z }));
        return;
      }
      p.moveBudget -= step;
      // ponytail: 장애물은 끝점만 밀어냄. 한 번에 최대 3m라 얇은 통나무를 건너뛸 수는 있음. 막으려면 이동 선분으로 검사
      if (p.roll) p.roll = Math.min(1.2, p.roll + step * 0.03);
      const gy = room.map.h(cx, cz); // 땅 밑·공중 부양 방지 (점프 최고 높이는 약 1.3m)
      Object.assign(p, { x: cx, y: Math.min(Math.max(y, gy), gy + 2), z: cz, yaw });
      return;
    }
    case "g":
      p.gather = !!m.on;
      p.gatherT = now;
      return;
    case "th": {
      let vx = num(m.vx, -40, 40), vy = num(m.vy, -40, 40), vz = num(m.vz, -40, 40);
      const seq = num(m.s, 0, 65535) ?? 0; // 던진 사람 화면의 예측 눈덩이와 짝 맞추기용
      if (vx === null || vy === null || vz === null || frozen || p.roll || p.ammo < 1 || now - p.lastThrow < 250 || now < room.game.breakUntil) return;
      const s = Math.hypot(vx, vy, vz), k = s > 28 ? 28 / s : 1;
      vx *= k, vy *= k, vz *= k;
      p.ammo--;
      p.lastThrow = now;
      const b = { id: ballId++, owner: p.id, team: p.team, x: p.x + Math.sin(p.yaw) * 0.6, y: p.y + 1.5, z: p.z + Math.cos(p.yaw) * 0.6, vx, vy, vz, age: 0, rewind: p.bot ? 0 : REWIND_MS };
      room.balls.push(b);
      room.events.push(["th", b.id, b.owner, r2(b.x), r2(b.y), r2(b.z), r2(vx), r2(vy), r2(vz), seq]);
      return;
    }
    case "r":
      if (m.on && !frozen && !p.roll) p.roll = 0.25;
      else if (!m.on && p.roll) { place(p); p.roll = 0; }
      return;
    case "emo": {
      const e = num(m.e, 0, 5);
      if (e !== null) room.events.push(["emo", p.id, Math.floor(e)]);
      return;
    }
  }
}

export function tick(room: Room, now = Date.now()) {
  const { players, piles, events, game } = room, h = room.map.h;
  for (const p of players.values()) {
    if (p.gather && p.ammo < MAX_AMMO && p.frozenUntil <= now && now - p.gatherT >= 500) { p.ammo++; p.gatherT = now; }
  }
  for (const p of players.values()) {
    p.hist.push([now, p.x, p.y, p.z]);
    while (p.hist.length > 1 && p.hist[0][0] < now - 500) p.hist.shift();
  }
  room.balls = room.balls.filter((b) => {
    const ax = b.x, ay = b.y, az = b.z;
    b.vy += G * DT; b.x += b.vx * DT; b.y += b.vy * DT; b.z += b.vz * DT; b.age += DT;
    for (const p of players.values()) {
      if (p.team === b.team || p.frozenUntil > now) continue; // 같은 팀은 안 맞음
      // 이번 틱에 공이 지나간 선분으로 판정(빠른 공이 몸을 건너뛰지 않게). 사람 공은 상대의 조금 전 위치도 인정
      const old = b.rewind ? posAt(p, now - b.rewind) : null;
      if (segDist(ax, ay, az, b.x, b.y, b.z, p.x, p.y + 1, p.z) < 0.9 || (old && segDist(ax, ay, az, b.x, b.y, b.z, old[1], old[2] + 1, old[3]) < 0.9)) {
        const s = Math.hypot(b.vx, b.vz) || 1, owner = players.get(b.owner);
        if (owner) owner.score++;
        if (now >= game.breakUntil) game.scores[b.team]++;
        p.hp--;
        events.push(["hit", b.id, r2(b.x), r2(b.y), r2(b.z), p.id, r2((b.vx / s) * 6), r2((b.vz / s) * 6)]);
        if (p.hp <= 0) Object.assign(p, { hp: HP, frozenUntil: now + 3000, gather: false, roll: 0, freezes: p.freezes + 1 });
        return false;
      }
    }
    const intoPile = piles.some((q) =>
      Math.hypot(b.x - q.x, b.z - q.z) < q.parts[0] && b.y < h(q.x, q.z) + q.parts.reduce((a, r) => a + r * 1.8, 0)
    );
    if (intoPile || b.y < h(b.x, b.z) || blocksBall(room.map, b.x, b.y, b.z)) { // 땅·눈사람·장애물(나무·바위·오두막)
      events.push(["splat", b.id, r2(b.x), r2(b.y), r2(b.z)]);
      return false;
    }
    return b.age < 4 && Math.abs(b.x) < 80 && Math.abs(b.z) < 80;
  });
}

// 선분 a→b 와 점 c 사이 최단 거리
function segDist(ax: number, ay: number, az: number, bx: number, by: number, bz: number, cx: number, cy: number, cz: number) {
  const dx = bx - ax, dy = by - ay, dz = bz - az, l2 = dx * dx + dy * dy + dz * dz;
  const t = l2 ? Math.max(0, Math.min(1, ((cx - ax) * dx + (cy - ay) * dy + (cz - az) * dz) / l2)) : 0;
  return Math.hypot(ax + dx * t - cx, ay + dy * t - cy, az + dz * t - cz);
}
// 시각 t 무렵 위치 (기록 중 t 이전 마지막 것)
function posAt(p: P, t: number) {
  let r = p.hist[0];
  for (const h of p.hist) if (h[0] <= t) r = h;
  return r;
}

// 판 진행: 3분이 끝나면 점수가 높은 팀이 이기고, 6초 쉰 뒤 모두 제자리에서 새 판
export function round(room: Room, now = Date.now()) {
  const game = room.game;
  if (!game.roundEnd) game.roundEnd = now + ROUND_MS;
  if (game.breakUntil && now >= game.breakUntil) {
    Object.assign(game, { scores: [0, 0], roundEnd: now + ROUND_MS, breakUntil: 0 });
    for (const p of room.players.values()) {
      Object.assign(p, { score: 0, freezes: 0, hp: HP, ammo: MAX_AMMO, frozenUntil: 0, roll: 0, gather: false });
      spawnAt(p);
    }
    room.events.push(["round"]);
  } else if (!game.breakUntil && now >= game.roundEnd) {
    const [a, b] = game.scores;
    room.events.push(["over", a === b ? -1 : a > b ? 0 : 1, a, b]);
    game.breakUntil = now + BREAK_MS;
  }
}

// 눈덩이가 목표 지점에 떨어지는 속도 (index.html 의 launch 와 같은 식)
export function launch(p: P, tx: number, ty: number, tz: number) {
  const ox = p.x + Math.sin(p.yaw) * 0.6, oy = p.y + 1.5, oz = p.z + Math.cos(p.yaw) * 0.6;
  const dx = tx - ox, dz = tz - oz, t = Math.max(0.15, Math.hypot(dx, dz) / 22);
  return { vx: dx / t, vy: (ty - oy - 0.5 * G * t * t) / t - 0.5 * G * DT, vz: dz / t };
}

// 봇: 가장 가까운 적과 10~20m 거리를 두고 옆으로 움직이며 던진다. 눈이 떨어지면 멈춰서 모은다
// ponytail: 엄폐·길찾기 없는 단순 봇. 장애물이 생기면 그때 길찾기 추가
export function bots(room: Room, now = Date.now()) {
  if (!humanCount(room)) return; // 사람이 없는 방은 쉰다
  const { players, game } = room, h = room.map.h;
  for (const b of players.values()) {
    if (!b.bot) continue;
    if (b.frozenUntil > now || now < game.breakUntil) { b.gather = false; continue; }
    if (b.ammo === 0 || (b.gather && b.ammo < 6)) {
      if (!b.gather) { b.gather = true; b.gatherT = now; }
      continue;
    }
    b.gather = false;
    let target: P | null = null, d = Infinity;
    for (const p of players.values()) {
      const pd = Math.hypot(p.x - b.x, p.z - b.z);
      if (p.team !== b.team && p.frozenUntil <= now && pd < d) { target = p; d = pd; }
    }
    if (!target) continue;
    const ux = (target.x - b.x) / d, uz = (target.z - b.z) / d;
    if (now > b.strafeUntil) { b.strafe = Math.random() < 0.5 ? -1 : 1; b.strafeUntil = now + 1500 + Math.random() * 2000; }
    const fwd = d > 20 ? 1 : d < 10 ? -1 : 0;
    const mx = ux * fwd - uz * b.strafe * 0.6, mz = uz * fwd + ux * b.strafe * 0.6, ml = Math.hypot(mx, mz) || 1;
    // ponytail: 길찾기 없이 장애물에서 밀려나기만 함. 나무 사이에 끼면 옆걸음 방향이 바뀔 때 빠져나옴
    [b.x, b.z] = pushOut(room.map, clampA(b.x + (mx / ml) * 4 * DT), clampA(b.z + (mz / ml) * 4 * DT));
    b.y = h(b.x, b.z);
    b.yaw = Math.atan2(ux, uz);
    if (d < 28 && now >= b.throwAt) {
      const err = 1 + d * 0.06; // 멀수록 덜 정확
      const v = launch(b, target.x + (Math.random() - 0.5) * 2 * err, target.y + 1, target.z + (Math.random() - 0.5) * 2 * err);
      handle(b, { t: "th", ...v }, now);
      b.throwAt = now + 1500 + Math.random() * 2000;
    }
  }
}

export function broadcast(room: Room, now = Date.now()) {
  const { players, game } = room;
  const msg = JSON.stringify({
    t: "s",
    p: [...players.values()].map((p) => [p.id, r2(p.x), r2(p.y), r2(p.z), r2(p.yaw), p.frozenUntil > now ? 1 : 0, r2(p.roll), p.hp, p.ammo, p.score, p.freezes, p.gather ? 1 : 0]), // 마지막: 눈 모으는 중(동작 표시용)
    ts: game.scores,
    tl: Math.max(0, Math.ceil((game.roundEnd - now) / 1000)),
    br: game.breakUntil ? 1 : 0,
    ev: room.events,
  });
  room.events = [];
  for (const p of players.values()) {
    try { p.sock.send(msg); } catch { /* 끊긴 소켓은 onclose 가 정리 */ }
  }
}

if (import.meta.main) {
  setInterval(() => { for (const r of rooms.values()) { tick(r); bots(r); round(r); } }, 1000 / 30);
  setInterval(() => { for (const r of rooms.values()) broadcast(r); }, 1000 / 15);
  const FILES: Record<string, [string, string]> = {
    "/chars.js": ["./chars.js", "text/javascript"],
    "/maps.js": ["./maps.js", "text/javascript"],
    "/favicon.png": ["./favicon.png", "image/png"],
  };
  Deno.serve({ port: Number(Deno.env.get("PORT") ?? 8000) }, async (req) => {
    const path = new URL(req.url).pathname;
    if (path === "/rooms") { // 입장 화면용: 맵별 사람 수
      return Response.json([...rooms.values()].map((r) => ({ id: r.map.id, name: r.map.name, emoji: r.map.emoji, humans: humanCount(r) })));
    }
    if (FILES[path]) {
      const [file, type] = FILES[path];
      return new Response(await Deno.readFile(new URL(file, import.meta.url)), { headers: { "content-type": type.startsWith("image/") ? type : `${type}; charset=utf-8` } });
    }
    if (path !== "/ws") {
      return new Response(await Deno.readFile(new URL("./index.html", import.meta.url)), {
        headers: { "content-type": "text/html; charset=utf-8" },
      });
    }
    const { socket, response } = Deno.upgradeWebSocket(req);
    let p: P | null = null;
    socket.onmessage = (e) => {
      if (typeof e.data !== "string" || e.data.length > 500) return;
      let m;
      try { m = JSON.parse(e.data); } catch { return; }
      if (p) return handle(p, m);
      if (m?.t !== "hello") return;
      const room = pickRoom(m.map);
      if (!room) { socket.send(JSON.stringify({ t: "full" })); return socket.close(); }
      p = join(room, socket, m.name);
    };
    socket.onclose = () => { if (p) leave(p); };
    return response;
  });
}
