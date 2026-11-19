// deno test server_test.ts
import { blocksBall, BRAWL, pushOut } from "./maps.js";
import { BREAK_MS, createRoom, dev, handle, issueFrom, join, leave, pickRoom, ranking, rewindFor, round, ROUND_MS, rooms, takeReport, tick } from "./server.ts";
import type { P, Room } from "./server.ts";

const sock = { send() {} };
const assert = (ok: boolean, msg: string) => { if (!ok) throw new Error(msg); };
const place = (p: P, x: number, z: number, yaw = 0) => Object.assign(p, { x, z, y: p.room.map.h(x, z), yaw });
const throwAt = (a: P, now: number) => { // a 가 정면(-z)으로 던지고 0.5초 흐름
  handle(a, { t: "th", vx: 0, vy: 0, vz: -20 }, now);
  for (let j = 0; j < 15; j++) tick(a.room, now);
};
const team = (room: Room, t: number, bot: boolean) => [...room.players.values()].filter((p) => p.team === t && p.bot === bot).length;

Deno.test("봇이 팀마다 4명을 채우고, 사람이 들어오면 봇이 빠진다", () => {
  const room = createRoom("slope");
  const a = join(room, sock, "a");
  assert(team(room, 0, false) + team(room, 0, true) === 4 && team(room, 1, false) + team(room, 1, true) === 4, "팀 인원");
  const b = join(room, sock, "b");
  assert(a.team !== b.team, "사람은 적은 팀으로");
  assert(team(room, b.team, true) === 3, `봇 ${team(room, b.team, true)}`);
  leave(b);
  assert(team(room, b.team, true) === 4, "나가면 봇이 다시 채움");
});

Deno.test("다른 팀은 맞고(점수·체력), 3번 맞으면 눈사람. 같은 팀은 안 맞는다", () => {
  const room = createRoom("slope");
  const a = join(room, sock, "a"), b = join(room, sock, "b"), c = join(room, sock, "c"); // c 는 a 와 같은 팀
  assert(c.team === a.team, "c 는 a 팀");
  for (const p of room.players.values()) if (p.bot) place(p, 45, -45); // 봇은 멀리 치움
  place(a, 0, 10, Math.PI);
  place(c, 0, 6);
  throwAt(a, 1000);
  assert(c.hp === 3 && a.score === 0, "같은 팀은 안 맞음");
  place(c, 30, 30);
  place(b, 0, 6);
  for (let i = 0; i < 3; i++) throwAt(a, 2000 + i * 1000);
  assert(a.score === 3 && room.game.scores[a.team] === 3, `점수 ${a.score} 팀 ${room.game.scores}`);
  assert(a.ammo === 6, `탄약 ${a.ammo}`);
  assert(b.frozenUntil === 4000 + 3000 && b.hp === 3, `frozen ${b.frozenUntil} hp ${b.hp}`);
  assert(b.freezes === 1 && a.freezes === 0, `언 횟수 ${b.freezes}`);
});

Deno.test("3분이 지나면 판이 끝나고, 쉬는 시간 뒤 점수가 0으로", () => {
  const room = createRoom("lake");
  const a = join(room, sock, "a");
  room.game.scores = [5, 2];
  a.freezes = 2;
  round(room, 1000);
  round(room, 1000 + ROUND_MS);
  assert(room.game.breakUntil === 1000 + ROUND_MS + BREAK_MS, "쉬는 시간 시작");
  handle(a, { t: "th", vx: 0, vy: 0, vz: -20 }, 1000 + ROUND_MS + 10);
  assert(a.ammo === 10, "쉬는 동안은 못 던짐");
  round(room, room.game.breakUntil);
  assert(room.game.scores[0] === 0 && room.game.scores[1] === 0 && room.game.breakUntil === 0, "새 판");
  assert(a.freezes === 0, "새 판이면 언 횟수도 0");
});

Deno.test("눈덩이 3개를 같은 자리에 놓으면 3단 눈사람", () => {
  const room = createRoom("forest");
  const c = join(room, sock, "c");
  place(c, 20, 20, 0);
  for (let i = 0; i < 4; i++) { handle(c, { t: "r", on: true }); handle(c, { t: "r", on: false }); }
  assert(room.piles.length === 2 && room.piles[0].parts.length === 3 && room.piles[1].parts.length === 1, JSON.stringify(room.piles));
});

Deno.test("방 고르기: 원하는 맵 방, 자동은 사람 많은 방. 맵마다 땅 높이가 다르다", () => {
  assert(pickRoom("lake") === rooms.get("lake"), "원하는 맵");
  const p = join(rooms.get("forest")!, sock, "x");
  assert(pickRoom("auto") === rooms.get("forest"), "자동은 사람 있는 방");
  assert(p.y === rooms.get("forest")!.map.h(p.x, p.z), "출발 높이는 그 맵 지형");
  leave(p);
  assert(rooms.get("lake")!.map.h(0, 0) === 0 && rooms.get("slope")!.map.h(0, -30) > 7, "맵별 지형");
});

Deno.test("장애물: 나무는 눈덩이를 막고, 몸은 나무 밖으로 밀려난다", () => {
  const room = createRoom("forest");
  const t = room.map.obstacles.find((o) => o.kind === "tree" && Math.hypot(o.x, o.z) < 38)!;
  const a = join(room, sock, "a");
  for (const p of room.players.values()) if (p !== a) place(p, 45, -45);
  place(a, t.x, t.z + 6, Math.PI); // 나무 6m 앞에서 나무 쪽(-z)으로
  throwAt(a, 1000);
  assert(room.balls.length === 0 && room.events.some((e) => (e as unknown[])[0] === "splat"), "나무에 막혀 사라짐");
  const [x, z] = pushOut(room.map, t.x + 0.1, t.z);
  assert(Math.hypot(x - t.x, z - t.z) >= t.body + 0.4 - 1e-9, "몸이 나무 밖으로");
});

Deno.test("위치 보고: 정상 이동은 받고, 순간이동은 거절해 되돌리고, 땅 밑·장애물 안은 바로잡는다", () => {
  const room = createRoom("forest");
  const sent: string[] = [];
  const a = join(room, { send: (s: string) => sent.push(s) }, "a");
  place(a, 0, 0);
  const move = (x: number, z: number, now: number, y = room.map.h(x, z)) => handle(a, { t: "p", x, y, z, yaw: 0 }, now);
  a.moveT = 0;
  for (let i = 1; i <= 15; i++) move(i * 0.48, 0, i * 66); // 달리기(초당 7.2m) 1초
  assert(Math.abs(a.x - 7.2) < 0.01, `달리기 ${a.x}`);
  sent.length = 0;
  move(a.x + 3.5, 0, 15 * 66 + 66); // 한 번에 3.5m
  assert(Math.abs(a.x - 7.2) < 0.01 && JSON.parse(sent.at(-1)!).t === "pos", "순간이동 거절 + 되돌림");
  move(a.x, 0, 3000, -5);
  assert(a.y === room.map.h(a.x, 0), `땅 밑 ${a.y}`);
  const tree = room.map.obstacles.find((o) => o.kind === "tree")!;
  place(a, tree.x + tree.body + 1, tree.z);
  move(tree.x, tree.z, 5000);
  assert(Math.hypot(a.x - tree.x, a.z - tree.z) >= tree.body + 0.39, "나무 안으로 못 들어감");
});

Deno.test("사람이 던진 공은 상대의 0.2초 전 위치(내 화면에 보이던 자리)도 맞는다. 봇 공은 지금 위치만", () => {
  const room = createRoom("slope");
  const a = join(room, sock, "a"), b = join(room, sock, "b");
  for (const p of room.players.values()) if (p.bot) place(p, 45, -45);
  place(a, 0, 10, Math.PI);
  place(b, 0, 6);
  tick(room, 10_000); // b 가 (0,6) 에 있던 기록
  place(b, 1.5, 6); // 0.2초 사이 옆으로 1.5m 피함
  throwAt(a, 10_200);
  assert(b.hp === 2 && a.score === 1, `사람 공 hp ${b.hp}`); // 0.2초 전 자리 = 되감기 구간(0.25초) 안
  a.bot = true; // 같은 상황, 봇이 던지면 빗나감
  place(b, 0, 6); tick(room, 20_000); place(b, 1.5, 6);
  handle(a, { t: "th", vx: 0, vy: 0, vz: -20 }, 20_200);
  for (let j = 0; j < 15; j++) tick(room, 20_200);
  assert(b.hp === 2, `봇 공 hp ${b.hp}`);
});

// 눈덩이 하나를 (target 기준) 옆 dx, 발 위 dy 높이로 정면에서 날려 보내 맞았는지
function shoot(dx: number, dy: number, opts: { speed?: number; jump?: number } = {}) {
  const room = createRoom("lake"); // 가운데가 평평한 빙판
  const a = join(room, sock, "a"), b = join(room, sock, "b");
  for (const p of room.players.values()) if (p.bot) place(p, 45, -45);
  place(a, 0, 8);
  place(b, 0, 0);
  b.y += opts.jump ?? 0; // 점프 중이면 발이 공중에
  const sp = opts.speed ?? 25, g = room.map.h(0, 0);
  room.balls.push({ id: 999, owner: a.id, team: a.team, x: dx, y: g + (opts.jump ?? 0) + dy, z: 3, vx: 0, vy: 7.5 * (3 / sp), vz: -sp, age: 0, rewind: null }); // vy: 날아가는 동안 떨어지는 만큼 미리 올려 높이 유지
  for (let j = 0; j < 30; j++) tick(room, 1000);
  return b.hp < 3;
}
Deno.test("명중 판정: 몸·머리·발은 맞고, 바로 옆·머리 위로 지나가면 안 맞는다", () => {
  const cases: [string, number, number, boolean][] = [
    ["정면 가운데", 0, 1.0, true], ["왼쪽 경계(몸통)", 0.7, 0.6, true], ["오른쪽 경계(몸통)", -0.7, 0.6, true],
    ["머리 높이", 0, 1.6, true], ["모자 꼭대기", 0, 1.95, true], ["발 근처", 0.3, 0.15, true],
    ["몸통 옆 1.0m 통과", 1.0, 0.6, false], ["머리 옆 0.95m 통과", 0.95, 1.3, false], ["머리 위 2.3m 통과", 0, 2.3, false],
  ];
  for (const [name, dx, dy, want] of cases) assert(shoot(dx, dy) === want, `${name}: ${want ? "맞아야" : "안 맞아야"} 함`);
});
Deno.test("명중 판정: 점프 중엔 발이 뜬 높이 기준, 빠른 공(초속 28m)도 몸을 뚫고 지나가지 않는다", () => {
  assert(shoot(0, 1.0, { jump: 1.2 }), "점프한 펭귄 몸에 맞음");
  assert(!shoot(0, -0.9, { jump: 1.2 }), "점프한 펭귄 발 아래로 지나감");
  for (const dx of [0, 0.4, 0.7]) assert(shoot(dx, 1.0, { speed: 28 }), `빠른 공 옆 ${dx}m`);
});

Deno.test("개발용 '판 끝내기'는 DEV 서버에서만 되고, 고른 팀이 이긴다", () => {
  const room = createRoom("slope"), a = join(room, sock, "a");
  dev.on = false;
  handle(a, { t: "dev", win: "me" }, 1000); round(room, 1000);
  assert(!room.events.some((e) => (e as unknown[])[0] === "over"), "배포 서버에선 무시");
  dev.on = true;
  handle(a, { t: "dev", win: "me" }, 2000); round(room, 2000);
  const over = room.events.find((e) => (e as unknown[])[0] === "over") as unknown[];
  assert(over?.[1] === a.team, `이긴 팀 ${over?.[1]} (내 팀 ${a.team})`);
  dev.on = false;
});

Deno.test("되감기: 던진 사람 화면에 상대가 보였던 시점 위치로 판정(지금 위치가 아니라)", () => {
  const room = createRoom("lake");
  const a = join(room, sock, "a"), b = join(room, sock, "b");
  for (const p of room.players.values()) if (p.bot) place(p, 45, -45);
  place(a, 0, 8, Math.PI);
  for (let k = 0; k <= 6; k++) { place(b, -1.5 + k * 0.5, 0); tick(room, 10_000 + k * 33); } // 0.2초 동안 x -1.5 → +1.5 로 지나감(x=0 은 10_099)
  for (let k = 1; k <= 6; k++) { place(b, 1.5 + k * 0.5, 0); tick(room, 10_198 + k * 33); } // 계속 멀어짐 → 지금은 x=4.5
  // 0.25초 뒤 공이 x=0 을 지남: 던진 사람(rtt 100) 화면엔 그때 상대가 x≈0 에 보였음 → 맞음. 지금 위치(x=4.5)엔 안 닿음
  const shot = (x: number, at: number) => { b.hp = 3; room.balls.push({ id: 7, owner: a.id, team: a.team, x, y: room.map.h(0, 0) + 1, z: 3, vx: 0, vy: 0.9, vz: -25, age: 0, rewind: rewindFor(a) }); for (let j = 0; j < 10; j++) tick(room, at); return b.hp < 3; };
  assert(shot(0, 10_349), "화면에 보였던 자리 명중");
  assert(!shot(4.5, 10_350), "화면에선 아직 거기 없던 지금 위치는 빗나감");
});

Deno.test("되감기 구간은 그 사람 왕복 시간(ping)에 맞춰지고, 봇은 없음, 최대 0.45초", () => {
  const room = createRoom("slope"), a = join(room, sock, "a");
  for (let i = 0; i < 30; i++) handle(a, { t: "pong", ts: 10_000 - 160 }, 10_000); // 왕복 0.16초
  const [lo, hi] = rewindFor(a)!;
  assert(Math.abs(lo - 230) < 3 && Math.abs(hi - 376) < 3, `rewind ${lo}~${hi}`);
  for (let i = 0; i < 60; i++) handle(a, { t: "pong", ts: 10_000 - 900 }, 10_000);
  assert(rewindFor(a)![1] === 450, `상한 ${rewindFor(a)}`);
  const bot = [...room.players.values()].find((p) => p.bot)!;
  assert(rewindFor(bot) === null, "봇은 되감기 없음");
});

Deno.test("Blender 맵: 스폰은 메타데이터 자리·지면 위·장애물 밖, 회전 상자는 몸과 눈덩이를 막는다", () => {
  for (const id of ["base_camp", "slope_field", "ice_lake", "forest_village", "night_resort"]) {
    const room = createRoom(id);
    for (let i = 0; i < 6; i++) {
      const p = join(room, sock, "s" + i);
      const near = room.map.spawns!.flat().some(([x, z]) => Math.hypot(x - p.x, z - p.z) < 1.6);
      assert(near, `${id} 스폰 자리 (${p.x.toFixed(1)}, ${p.z.toFixed(1)})`);
      assert(Math.abs(p.y - room.map.h(p.x, p.z)) < 1e-9, `${id} 스폰 높이`);
      const [qx, qz] = pushOut(room.map, p.x, p.z);
      assert(qx === p.x && qz === p.z, `${id} 스폰이 장애물 안`);
    }
  }
  const map = createRoom("base_camp").map;
  const box = map.obstacles.find((o) => o.kind === "snow_wall_low" && (o as { hw?: number }).hw) as unknown as { x: number; y: number; z: number; hw: number; hd: number; rot: number; top: number };
  assert(!!box, "눈벽은 회전 상자");
  const [x, z] = pushOut(map, box.x, box.z); // 상자 한가운데 → 밖으로
  const c = Math.cos(box.rot), s = Math.sin(box.rot), lx = (x - box.x) * c - (z - box.z) * s, lz = (x - box.x) * s + (z - box.z) * c;
  assert(Math.abs(lx) >= box.hw + 0.39 || Math.abs(lz) >= box.hd + 0.39, `상자 밖으로 밀려남 (${lx.toFixed(2)}, ${lz.toFixed(2)})`);
  assert(blocksBall(map, box.x, box.y + 0.5, box.z) && !blocksBall(map, box.x, box.y + box.top + 0.1, box.z), "눈덩이: 벽 높이까지만 막음");
});

Deno.test("낮은 눈벽: 서 있으면 막히고, 충분히 뛰면 넘고, 낮게 뛰면 막힌다. 높은 벽은 뛰어도 막힌다", () => {
  const room = createRoom("base_camp"), map = room.map;
  type Box = { kind: string; x: number; y: number; z: number; hw: number; hd: number; rot: number; top: number; hop?: number };
  const boxes = map.obstacles as unknown as Box[];
  // 화면처럼: 60fps 로 벽을 가로질러(로컬 z) 달리며 매 프레임 pushOut(발 높이), 4프레임마다 서버에 보고.
  // 서버가 받은 위치를 고치지 않아야(화면 = 서버) 하고, 결과(막힘/넘음)도 같아야 함. jump(t) = 발이 땅보다 뜬 높이
  const cross = (b: Box, jump: (t: number) => number) => {
    const a = join(room, sock, "h"), c = Math.cos(b.rot), s = Math.sin(b.rot);
    let [x, z] = [b.x - (b.hd + 2.4) * s, b.z - (b.hd + 2.4) * c]; place(a, x, z); a.moveT = 0;
    for (let f = 1; f <= 60; f++) {
      const y = map.h(x, z) + jump(f / 60);
      [x, z] = pushOut(map, x + 0.12 * s, z + 0.12 * c, 0.4, y);
      if (f % 4) continue;
      handle(a, { t: "p", x, y, z, yaw: 0 }, f * 16.7);
      assert(Math.hypot(a.x - x, a.z - z) < 1e-6, `서버가 화면 위치를 고침 (${b.kind}, ${f}프레임)`);
    }
    const lz = (a.x - b.x) * s + (a.z - b.z) * c; leave(a); return lz;
  };
  const clear = (b: Box) => !boxes.some((o) => o !== b && Math.hypot(o.x - b.x, o.z - b.z) < 5);
  const low = boxes.find((o) => o.kind === "snow_wall_low" && o.hop && o.hw !== undefined && clear(o))!;
  const high = boxes.find((o) => o.kind === "snow_wall_high" && o.hw !== undefined && clear(o))!;
  assert(!!low && !!high, "시험할 벽");
  const jump = (t: number) => Math.max(0, 8 * t - 12 * t * t); // 초속 8m, 중력 24 → 최고 1.33m, 0.33초에 벽 위
  assert(cross(low, () => 0) < 0, "서서는 낮은 벽에 막힘");
  assert(cross(low, jump) > low.hd, "점프로 낮은 벽 넘음");
  assert(cross(low, (t) => jump(t) * 0.5) < 0, "낮게 뛰면 막힘");
  assert(cross(high, jump) < 0, "높은 벽은 점프해도 막힘");
});

// ── 이동 보안: 화면(index.html)과 같은 이동 계산을 하는 가짜 클라이언트. 60fps 로 굴리고 4프레임(0.066초)마다 서버에 보고
import { GRAVITY as G_, JUMP_V as JV, rampLaunch, sweep as sweep_ } from "./maps.js";
type In = { vx: number; vz: number; jump?: boolean };
function sim(room: Room, x: number, z: number, jitter: (k: number) => number = () => 0) {
  const sent: string[] = [];
  const a = join(room, { send: (s: string) => sent.push(s) }, "sim");
  for (const p of room.players.values()) if (p.bot) Object.assign(p, { x: 49, z: 49 });
  place(a, x, z); a.moveT = 0;
  const m = room.map, c = { x, z, y: m.h(x, z), vy: 0, mvx: 0, mvz: 0, onGround: true };
  let f = 0, maxDiff = 0, firstBad = '', lastT = 0; const trace: string[] = [];
  const frame = (inp: In) => {
    const dt = 1 / 60, gy0 = m.h(c.x, c.z), air = c.y > gy0 + 0.05, acc = Math.min(1, 16 * (air ? 0.35 : 1) * dt);
    c.mvx += (inp.vx - c.mvx) * acc; c.mvz += (inp.vz - c.mvz) * acc;
    const px = c.x, pz = c.z;
    [c.x, c.z] = sweep_(m, px, pz, Math.max(-50, Math.min(50, c.x + c.mvx * dt)), Math.max(-50, Math.min(50, c.z + c.mvz * dt)), c.y);
    let gy = m.h(c.x, c.z); const grounded = c.y <= gy + 0.05;
    c.vy -= G_ * dt; c.y += c.vy * dt;
    const step = Math.hypot(c.mvx, c.mvz) * dt;
    if (c.onGround && c.vy <= 0 && c.y > gy && c.y - gy <= step + 0.02) c.y = gy;
    [c.x, c.z] = pushOut(m, c.x, c.z, 0.4, c.y); gy = m.h(c.x, c.z);
    if (c.y <= gy) { c.y = gy; c.vy = 0; }
    c.onGround = c.y <= gy + 1e-3;
    const ramp = c.onGround ? rampLaunch(m, c.x, c.z, c.mvx, c.mvz) : 0;
    if (ramp) c.vy = ramp;
    if (inp.jump && grounded) c.vy = Math.max(JV, ramp);
    if (++f % 4 === 0) {
      lastT = Math.max(lastT, f * 1000 / 60 + jitter(f / 4)); // 웹소켓(TCP)은 순서가 안 바뀜: 늦게 온 뒤엔 몰려 옴
      handle(a, { t: "p", x: c.x, y: c.y, z: c.z, yaw: 0 }, lastT);
      const d = Math.hypot(a.x - c.x, a.y - c.y, a.z - c.z);
      trace.push(`f${f}:c${c.y.toFixed(2)}/s${a.y.toFixed(2)}${a.ground ? 'G' : ''}(vy0 ${a.airVy.toFixed(1)} t${((f * 1000 / 60 - a.airT) / 1000).toFixed(2)})`); if (trace.length > 8 && !firstBad) trace.shift();
      if (d > 0.36 && !firstBad) firstBad = `f${f} 화면(${c.x.toFixed(2)},${c.y.toFixed(2)},${c.z.toFixed(2)} vy${c.vy.toFixed(1)}) 서버(${a.x.toFixed(2)},${a.y.toFixed(2)},${a.z.toFixed(2)}) 땅${m.h(c.x, c.z).toFixed(2)} ground${a.ground}`;
      maxDiff = Math.max(maxDiff, d);
    }
  };
  const run = (sec: number, inp: In | ((t: number) => In)) => { for (let i = 0; i < sec * 60; i++) frame(typeof inp === "function" ? inp(i / 60) : inp); };
  const send = (x: number, y: number, z: number) => { f += 4; handle(a, { t: "p", x, y, z, yaw: 0 }, f * 1000 / 60); };
  return { a, c, run, send, sent, corrections: () => sent.filter((s) => JSON.parse(s).t === "pos").length, maxDiff: () => maxDiff, bad: () => firstBad + ' | ' + trace.slice(0, 10).join(' '), now: () => f * 1000 / 60 };
}

Deno.test("정상 플레이: 걷기·달리기·대각선·연속 점프·벽 따라 미끄러지기·눈벽 넘기 — 서버가 한 번도 위치를 고치지 않음", () => {
  const room = createRoom("base_camp");
  const s = sim(room, 0, 10);
  s.run(1.5, { vx: 0, vz: -4.4 }); // 걷기
  s.run(1.5, { vx: 5.1, vz: 5.1 }); // 대각선 달리기(7.2)
  for (let i = 0; i < 4; i++) s.run(0.8, { vx: -3, vz: 0, jump: true }); // 연속 점프(땅에 닿을 때마다)
  assert(s.corrections() === 0 && s.maxDiff() < 0.36, `보정 ${s.corrections()}회, 화면과 차이 ${s.maxDiff().toFixed(2)}m ${s.bad()}`);
  // 높은 눈벽에 비스듬히 달려들기 → 벽을 따라 미끄러짐(멈추지 않음)
  const wall = room.map.obstacles.find((o) => o.kind === "snow_wall_high" && o.hw !== undefined)!;
  const w = sim(room, wall.x - 3, wall.z - 0.6);
  const x0 = w.c.x;
  w.run(1.2, { vx: 6, vz: 3.5 });
  assert(w.corrections() === 0, `벽 따라가기 보정 ${w.corrections()}회`);
  assert(Math.abs(w.a.x - x0) > 1, "벽에 막혀 멈추지 않고 미끄러짐");
});

Deno.test("벽 통과 시도: 얇은 울타리·높은 벽 너머 좌표는 거절, 벽 앞까지만. 맵 밖 좌표는 경계까지", () => {
  const room = createRoom("base_camp");
  const fence = room.map.obstacles.find((o) => o.kind === "fence_wood")!; // 두께 0.3m
  const s = sim(room, fence.x, fence.z - 1.0);
  s.run(0.3, { vx: 0, vz: 0 });
  for (let k = 0; k < 5; k++) s.send(fence.x, room.map.h(fence.x, fence.z + 1), fence.z + 1); // 울타리 1m 너머를 계속 보냄
  assert(s.a.z < fence.z - 0.15 - 0.39, `울타리 앞에 머묾 z=${s.a.z.toFixed(2)} (울타리 ${fence.z})`);
  assert(s.corrections() > 0, "서버 위치로 되돌리라고 알림");
  const high = room.map.obstacles.find((o) => o.kind === "snow_wall_high")!;
  const nx = Math.sin(high.rot!), nz = Math.cos(high.rot!); // 벽 두께 방향(로컬 z)
  const t = sim(room, high.x - 1.2 * nx, high.z - 1.2 * nz); // 벽 앞 1.2m
  const [ox, oz] = [t.a.x, t.a.z];
  t.send(high.x + 1.2 * nx, t.a.y, high.z + 1.2 * nz); // 반대편 1.2m (이동 한도 안의 거리)
  const side = (px: number, pz: number) => Math.sign((px - high.x) * nx + (pz - high.z) * nz);
  assert(side(t.a.x, t.a.z) === side(ox, oz), "높은 벽 너머로 못 감");
  const e = sim(room, 48, 0);
  e.send(55, 0, 0);
  assert(e.a.x <= 50 + 1e-9, `맵 경계 ${e.a.x}`);
});

Deno.test("공중 부양 시도: 계속 높은 좌표를 보내도 점프 곡선을 못 벗어나고(높이·체공), 가짜 점프대 속도는 무시", () => {
  const room = createRoom("base_camp");
  const s = sim(room, 0, 10);
  const gy = room.map.h(s.a.x, s.a.z);
  // 계속 땅+1.5m 를 보내면 서버는 '점프를 반복한 것'으로만 봄 → 점프 높이를 못 넘고, 1m 위에 0.8초 넘게 연달아 머물 수 없음
  let maxY = 0, above = 0, longest = 0, sinceGround = 0, longestUp = 0;
  for (let k = 0; k < 45; k++) { // 3초
    s.send(s.a.x, gy + 1.5, s.a.z);
    const hgt = s.a.y - gy;
    maxY = Math.max(maxY, hgt);
    above = hgt > 1 ? above + 66 : 0; longest = Math.max(longest, above);
    sinceGround = hgt < 0.3 ? 0 : sinceGround + 66; longestUp = Math.max(longestUp, sinceGround);
  }
  assert(maxY <= JV * JV / (2 * G_) + 0.36, `최고 ${maxY.toFixed(2)}m (점프 1.33m + 여유 0.35)`);
  assert(longest <= 800, `1m 위에 연달아 ${longest}ms`); // 실제 점프는 0.31초, 서버 허용폭(시간 0.37초·높이 0.35m) 포함 최대 약 0.73초
  assert(longestUp <= 1100, `땅 근처(0.3m)로 안 내려오고 버틴 시간 ${longestUp}ms`); // 점프 한 번 체공 0.67초 + 허용폭
  // 땅+2m(예전 상한 안)·땅+5m 를 한 번에: 점프 곡선까지만
  const t = sim(room, 5, 10); const g2 = room.map.h(t.a.x, t.a.z);
  t.run(0.2, { vx: 0, vz: 0 });
  t.send(t.a.x, g2 + 5, t.a.z);
  assert(t.a.y - g2 < 1.2, `한 번에 5m: ${(t.a.y - g2).toFixed(2)}m`); // 막 뛴 순간 점프 곡선 높이(뜬 시각 0.12초 여유 포함 약 0.8m)까지만
  // 점프대 위에 서 있다가 엄청난 높이를 보냄 → 서버가 잰 속도(0)로는 점프 높이까지만
  const sf = createRoom("slope_field"), r = (sf.map as unknown as { ramps: { x: number; z: number; hd: number }[] }).ramps[0];
  const u = sim(sf, r.x, r.z + r.hd - 0.3); u.run(0.3, { vx: 0, vz: 0 });
  const gr = sf.map.h(u.a.x, u.a.z);
  for (let k = 0; k < 6; k++) u.send(u.a.x, gr + 3 + k, u.a.z);
  assert(u.a.y - gr <= JV * JV / (2 * G_) + 0.36, `점프대 위 가짜 발사 ${(u.a.y - gr).toFixed(2)}m`);
});

Deno.test("점프대: 달려서 지나가면 튀어 오르고(서버도 인정), 느리게·옆·반대로는 안 튐, 정면에선 턱에 막힘", () => {
  const room = createRoom("slope_field"), m = room.map as unknown as { ramps: { x: number; z: number; hd: number; hw: number }[]; h: (x: number, z: number) => number };
  const r = m.ramps[0];
  const go = (x: number, z: number, vx: number, vz: number, sec = 1.4) => {
    const s = sim(room, x, z); let top = 0;
    for (let i = 0; i < sec * 60; i++) { s.run(1 / 60, { vx, vz }); top = Math.max(top, s.c.y - m.h(s.c.x, s.c.z)); }
    return { s, top };
  };
  const run = go(r.x, r.z - r.hd - 1, 0, 7.2); // 뒤에서 앞으로 달려 입술을 지남
  assert(run.top > 1.0, `달리기 점프대 공중 높이 ${run.top.toFixed(2)}m`);
  assert(run.s.corrections() === 0 && run.s.maxDiff() < 0.36, `서버 보정 ${run.s.corrections()}회, 차이 ${run.s.maxDiff().toFixed(2)}m`);
  const walk = go(r.x, r.z - r.hd - 1, 0, 4.4);
  assert(walk.top > 0.5 && walk.top < run.top, `걷기 ${walk.top.toFixed(2)}m < 달리기`);
  assert(walk.s.corrections() === 0, `걷기 보정 ${walk.s.corrections()}회`);
  const slow = go(r.x, r.z - r.hd - 1, 0, 1.0, 5);
  assert(slow.top < 1.6, `느리게 ${slow.top.toFixed(2)}m: 입술에서 그냥 떨어짐(1.4m 턱 높이 이하)`);
  const front = go(r.x, r.z + r.hd + 2, 0, -5);
  assert(front.s.a.z > r.z + r.hd, `정면에서 턱에 막힘 z=${front.s.a.z.toFixed(2)}`);
  const side = go(r.x - r.hw - 1.5, r.z + r.hd - 0.4, 5, 0, 1.2); // 옆으로 가로질러
  assert(side.s.corrections() === 0, `옆으로 지나기 보정 ${side.s.corrections()}회`);
  const again = go(r.x, r.z - r.hd - 1, 0, 7.2); // 다시 한 번(연속 사용)
  assert(again.top > 1.0 && again.s.corrections() === 0, "연속 사용");
});

Deno.test("절벽·턱·급경사(테스트 전용 지형): 떨어질 때 서버도 중력으로 따라오고, 착지 후 정상", () => {
  // 운영 맵은 그대로 두고 방의 맵만 바꿔 끼움: x<0 높은 평지(4m) → x=0 수직 낙차 → 급경사(45°) → 낮은 평지
  const room = createRoom("slope");
  const h = (x: number, _z: number) => x < 0 ? 4 : x < 4 ? Math.max(0, 2 - x) : x < 8 ? 0 : x < 10 ? (x - 8) * 0.9 : 1.8;
  room.map = { ...room.map, id: "test_cliff", h, obstacles: [], ramps: undefined } as unknown as Room["map"];
  const s = sim(room, -3, 0);
  s.run(2.5, { vx: 4.4, vz: 0 }); // 높은 평지 → 절벽에서 떨어짐 → 아래 → 오르막 → 높은 턱
  assert(s.corrections() === 0, `보정 ${s.corrections()}회`);
  assert(s.maxDiff() < 0.36, `떨어지는 동안 화면과 서버 차이 ${s.maxDiff().toFixed(2)}m`);
  assert(s.a.y >= h(s.a.x, 0) - 1e-6, "땅 밑으로 안 감");
  const t = sim(room, -0.5, 0); // 절벽 끝에서 점프
  t.run(1.6, { vx: 3, vz: 0, jump: true });
  assert(t.corrections() === 0 && t.maxDiff() < 0.36, `절벽 점프 차이 ${t.maxDiff().toFixed(2)}m ${t.bad()}`);
  // 떨어지는 중 던진 눈덩이도 서버 위치(공중)에서 나감
  const u = sim(room, -0.6, 0); u.run(0.15, { vx: 4.4, vz: 0 });
  u.run(0.1, { vx: 4.4, vz: 0 });
  const yAir = u.a.y;
  handle(u.a, { t: "th", vx: 10, vy: 0, vz: 0 }, u.now());
  const b = room.balls.at(-1)!;
  assert(Math.abs(b.y - (yAir + 1.5)) < 1e-6 && yAir > h(u.a.x, 0) + 0.1, `낙하 중 투척 높이 ${b.y.toFixed(2)} (발 ${yAir.toFixed(2)})`);
});

Deno.test("지연: 보고가 0.09~0.12초 늦었다가 몰려 와도 정상 점프·점프대·이동을 고치지 않음", () => {
  // 도착 시각을 앞뒤로 흔들되 순서는 유지(한 번 늦게 온 다음 몰려 옴)
  const jit = (k: number) => [0, 90, 120, 0, 0, 60, 0, 30][k % 8]; // 0.09~0.12초 늦었다가 몰려 옴
  const room = createRoom("base_camp");
  const s = sim(room, 0, 10, jit);
  for (let i = 0; i < 4; i++) s.run(0.8, { vx: 4, vz: 0, jump: true });
  s.run(1, { vx: 5, vz: 5 });
  assert(s.corrections() === 0, `보정 ${s.corrections()}회 ${s.bad()} ${s.sent.filter((x) => x.includes("pos")).slice(0, 2).join(" ")}`);
  const sf = createRoom("slope_field"), r = (sf.map as unknown as { ramps: { x: number; z: number; hd: number }[] }).ramps[0];
  const u = sim(sf, r.x, r.z - r.hd - 1, jit);
  u.run(1.4, { vx: 0, vz: 7.2 });
  assert(u.corrections() === 0, `점프대 보정 ${u.corrections()}회 ${u.bad()}`);
});

Deno.test("버그 제보: 글은 1000자까지 남고, 빈 글은 거절, 같은 IP 는 1분에 3건까지", () => {
  const ok = takeReport({ kind: "버그", text: "  점프대에서 끼여요 " + "x".repeat(2000), info: { map: "slope_field", name: "가".repeat(50) } }, "1.1.1.1", 0);
  assert(ok.ok && JSON.parse(ok.line).text.length === 1000 && JSON.parse(ok.line).name.length === 12, "자르기");
  assert(!takeReport({ text: " " }, "2.2.2.2", 0).ok, "빈 글 거절");
  assert(!takeReport(null, "2.2.2.2", 0).ok && !takeReport({ text: 5 }, "2.2.2.2", 0).ok, "이상한 본문 거절");
  takeReport({ text: "둘째" }, "1.1.1.1", 1000); takeReport({ text: "셋째" }, "1.1.1.1", 2000);
  const r4 = takeReport({ text: "넷째" }, "1.1.1.1", 3000);
  assert(!r4.ok && r4.status === 429, "1분에 3건");
  assert(takeReport({ text: "1분 뒤" }, "1.1.1.1", 61_000).ok, "1분 지나면 다시");
});

Deno.test("제보 → GitHub 이슈: 제목은 [종류] 첫 줄, 사용자 글은 코드 블록(멘션·코드펜스 무력화)", () => {
  const r = takeReport({ kind: "조작", text: "@octocat 점프대 이상해요\n```\n<script>", info: { map: "slope_field", name: "@bad|name" } }, "9.9.9.9", 0);
  assert(r.ok, "제보");
  const { title, body } = issueFrom((r as { line: string }).line);
  assert(title === "[조작] octocat 점프대 이상해요", title);
  assert(body.includes("```\n@octocat 점프대 이상해요\nʼʼʼ\n<script>\n```"), "본문 코드 블록");
  assert(!/\| @/.test(body) && body.includes("| 맵 | slope_field |") && body.includes(" bad name"), "표 칸에 @·| 없음");
});

// ── 싸다구 ──────────────────────────────────────────────
import { SLAP, SLIDE, slideMove, slideOver, slideNose } from "./maps.js";
import { resolveSlap } from "./server.ts";
const evs = (room: Room, k: string) => room.events.filter((e) => (e as unknown[])[0] === k) as unknown[][];
// 평평한 눈밭(테스트 전용 지형). 장애물 없음
const flat = (id = "slope", h = (_x: number, _z: number) => 0) => {
  const room = createRoom(id);
  room.map = { ...room.map, id: "test_flat", h, obstacles: [], ramps: undefined, ice: undefined, onIce: undefined } as unknown as Room["map"];
  return room;
};
// a 가 (0,0)에서 -z 를 보고 싸다구, t = 0.25초 뒤 임팩트까지 굴림
const duel = (room = flat()) => {
  const a = join(room, sock, "a"), b = join(room, sock, "b");
  for (const p of room.players.values()) if (p.bot) place(p, 45, 45);
  place(a, 0, 0, Math.PI); place(b, 0, -1.6);
  return { room, a, b };
};
const slap = (a: P, now: number) => { handle(a, { t: "sl" }, now); for (let k = 0; k <= 8; k++) tick(a.room, now + k * 33); };

Deno.test("싸다구: 앞 2.3m·정면 ±45° 안의 상대만 맞음(체력·점수·경직·넉백), 0.25초 임팩트에 판정", () => {
  const { room, a, b } = duel();
  handle(a, { t: "sl" }, 1000);
  assert(evs(room, "sl").length === 1, "휘두르기 이벤트(다른 화면 동작)");
  tick(room, 1200);
  assert(b.hp === 3, "임팩트 전엔 안 맞음");
  tick(room, 1250);
  const e = evs(room, "slap")[0];
  assert(b.hp === 2 && a.score === 1 && room.game.scores[a.team] === 1, `명중 hp ${b.hp} 점수 ${a.score}`);
  assert(e?.[1] === a.id && e?.[2] === b.id && (e[4] as number) < 0, `이벤트 ${JSON.stringify(e)} (넉백은 -z)`);
  assert(b.stunUntil === 1250 + SLAP.stun, "0.3초 경직");
  const cases: [string, number, number, boolean][] = [
    ["2.2m 앞", 0, -2.2, true], ["2.5m 앞(거리 밖)", 0, -2.5, false], ["40° 옆", -Math.sin(0.7) * 1.8, -Math.cos(0.7) * 1.8, true],
    ["60° 옆(각도 밖)", -Math.sin(1.05) * 1.8, -Math.cos(1.05) * 1.8, false], ["바로 뒤", 0, 1.2, false], ["높이 차 2m(점프 위)", 0, -1.5, false],
  ];
  for (const [name, x, z, want] of cases) {
    const d = duel();
    place(d.b, x, z);
    if (name.startsWith("높이")) d.b.y += 2;
    d.b.hist = []; slap(d.a, 5000);
    assert((d.b.hp < 3) === want, `${name}: ${want ? "맞아야" : "안 맞아야"} 함`);
  }
});

Deno.test("싸다구: 쿨다운 1.2초, 같은 팀은 맞지만 점수 없음, 얼어 있는 상대 안 맞음, 한 번에 한 명만, 클라이언트가 보낸 대상은 무시", () => {
  const { room, a, b } = duel();
  slap(a, 1000); slap(a, 1600);
  assert(b.hp === 2 && evs(room, "sl").length === 1, `쿨다운 중 무시 hp ${b.hp}`);
  slap(a, 2300);
  assert(b.hp === 1, "쿨다운 뒤 다시");
  const c = join(room, sock, "c"); place(c, 0.6, -1.4); c.team = b.team; b.hp = 3; // 둘 다 사정거리 안
  slap(a, 4000);
  assert(evs(room, "slap").length === 3 && (b.hp < 3 ? 1 : 0) + (c.hp < 3 ? 1 : 0) === 1, `한 번에 한 명 b ${b.hp} c ${c.hp}`);
  const mate = join(room, sock, "m"); mate.team = a.team; place(mate, 0, -1); b.hp = c.hp = 3; place(b, 30, 30); place(c, 30, 31);
  const sa = a.score, ts = [...room.game.scores];
  slap(a, 6000);
  assert(mate.hp === 2 && mate.stunUntil > 6000, `같은 팀도 맞음(체력·경직) hp ${mate.hp}`);
  assert(a.score === sa && room.game.scores.join() === ts.join(), "같은 팀을 때리면 개인·팀 점수 없음");
  place(mate, 30, 32);
  place(b, 0, -1.5); b.frozenUntil = 99_999; slap(a, 8000);
  assert(b.hp === 3, "얼어 있는 상대 안 맞음");
  b.frozenUntil = 0; place(b, 20, 20);
  handle(a, { t: "sl", target: b.id, hit: true }, 10_000); for (let k = 0; k < 10; k++) tick(room, 10_000 + k * 33);
  assert(b.hp === 3, "멀리 있는 대상을 보내도 서버가 직접 찾음");
});

Deno.test("싸다구: 벽 너머·울타리 너머는 막히고, 휘두르는 중 맞거나 얼거나 슬라이딩·판 끝이면 취소", () => {
  for (const kind of ["snow_wall_high", "snow_wall_low", "fence_wood"]) {
    const room = createRoom("base_camp"), w = room.map.obstacles.find((o) => o.kind === kind)!;
    const nx = Math.sin(w.rot!), nz = Math.cos(w.rot!), off = (w.hd ?? 0.2) + 0.45;
    const a = join(room, sock, "a"), b = join(room, sock, "b");
    for (const p of room.players.values()) if (p.bot) place(p, 45, 45);
    place(a, w.x - off * nx, w.z - off * nz, Math.atan2(nx, nz)); place(b, w.x + off * nx, w.z + off * nz); b.hist = [];
    assert(Math.hypot(a.x - b.x, a.z - b.z) < SLAP.range, `${kind} 거리 ${Math.hypot(a.x - b.x, a.z - b.z).toFixed(2)}`);
    slap(a, 1000);
    assert(b.hp === 3, `${kind} 너머는 안 맞음`);
  }
  const { room, a, b } = duel();
  handle(a, { t: "sl" }, 1000);
  room.balls.push({ id: 5, owner: b.id, team: b.team, x: 0, y: 1, z: -0.8, vx: 0, vy: 0.5, vz: 12, age: 0, rewind: null }); // 휘두르는 중 눈덩이에 맞음
  for (let k = 0; k <= 8; k++) tick(room, 1000 + k * 33);
  assert(a.hp === 2 && b.hp === 3, `맞으면 싸다구 취소 a ${a.hp} b ${b.hp}`);
  handle(a, { t: "bs", on: true }, 3000); handle(a, { t: "sl" }, 3100);
  assert(!a.slapPend, "슬라이딩 중엔 싸다구 못 함");
  a.slideT = 0; handle(a, { t: "sl" }, 6000); room.game.breakUntil = 12_000; resolveSlap(room, a, 6250); // 휘두르는 사이 판이 끝나 쉬는 중
  assert(b.hp === 3, "판이 끝나면 취소");
});

Deno.test("싸다구: 사람이 휘두르면 내 화면에 보이던(조금 전) 상대 자리도 인정", () => {
  const { room, a, b } = duel();
  tick(room, 10_000); // b 가 1.6m 앞에 있던 기록
  place(b, 0, -3.5); // 0.2초 사이 물러남
  handle(a, { t: "sl" }, 10_000); tick(room, 10_100); tick(room, 10_250);
  assert(b.hp === 2, "보이던 자리 명중");
});

// ── 배 슬라이딩: 화면과 같은 함수(maps.js slideMove)로 굴리는 가짜 클라이언트, 4프레임마다 보고 ──────────
// cheat: 보고 위치를 실제 미끄러진 거리의 몇 배로 부풀려 보냄(속도 조작 클라이언트)
function slider(room: Room, x: number, z: number, yaw: number, opts: { cheat?: number; want?: number | null; jitter?: (k: number) => number } = {}) {
  const sent: string[] = [];
  const a = join(room, { send: (s: string) => sent.push(s) }, "sl");
  for (const p of room.players.values()) if (p.bot) Object.assign(p, { x: 49, z: 49 });
  place(a, x, z, yaw); a.moveT = 1000;
  const s = { v: SLIDE.v0, yaw, t: 0, hit: false }, k = opts.cheat ?? 1;
  handle(a, { t: "p", x, y: a.y, z, yaw }, 1000);
  handle(a, { t: "bs", on: true }, 1000);
  let f = 0, maxDiff = 0, cx = x, cz = z, lastT = 1000;
  while (!slideOver(s) && f < 300) {
    [cx, cz] = slideMove(room.map, s, cx, cz, room.map.h(cx, cz), opts.want ?? null, 1 / 60);
    if (++f % 4 === 0) {
      const rx = x + (cx - x) * k, rz = z + (cz - z) * k;
      lastT = Math.max(lastT, 1000 + f * 1000 / 60 + (opts.jitter?.(f / 4) ?? 0)); // 늦게 왔다가 몰려 옴(순서는 그대로)
      handle(a, { t: "p", x: rx, y: room.map.h(rx, rz), z: rz, yaw: s.yaw }, lastT); maxDiff = Math.max(maxDiff, Math.hypot(a.x - rx, a.z - rz));
    }
  }
  handle(a, { t: "bs", on: false }, 1000 + f * 1000 / 60);
  const pos = sent.filter((m) => JSON.parse(m).t === "pos").length;
  return { a, s, sec: f / 60, dist: Math.hypot(cx - x, cz - z), pos, maxDiff };
}

Deno.test("배 슬라이딩: 평지 약 1.2초·8m, 내리막은 더 길게, 오르막은 짧게, 빙판은 오래 — 서버가 한 번도 위치를 안 고침", () => {
  const f = slider(flat(), 0, 0, 0);
  assert(Math.abs(f.sec - 1.22) < 0.05 && f.dist > 7.5 && f.dist < 9.5, `평지 ${f.sec.toFixed(2)}초 ${f.dist.toFixed(1)}m`);
  assert(f.pos === 0 && f.maxDiff < 1e-6, `평지 보정 ${f.pos}회`);
  const down = slider(flat("slope", (_x, z) => -0.25 * z), 0, -20, 0), up = slider(flat("slope", (_x, z) => 0.25 * z), 0, -20, 0);
  assert(down.dist > f.dist + 2 && up.dist < f.dist - 2, `내리막 ${down.dist.toFixed(1)}m 오르막 ${up.dist.toFixed(1)}m`);
  assert(down.pos === 0 && up.pos === 0, `경사 보정 ${down.pos}/${up.pos}`);
  const steep = slider(flat("slope", (_x, z) => -0.8 * z), 0, -30, 0);
  assert(steep.pos === 0 && steep.s.t > SLIDE.maxT && steep.dist > 20, `급경사 내리막: 빨라짐 ${steep.dist.toFixed(1)}m 보정 ${steep.pos}`);
  const ice = slider(createRoom("lake"), -10, 0, Math.PI / 2); // 가운데 빙판(반지름 24) 평지
  assert(ice.sec > SLIDE.maxT - 0.05 && ice.dist > f.dist + 5 && ice.pos === 0, `빙판 ${ice.sec.toFixed(2)}초 ${ice.dist.toFixed(1)}m 보정 ${ice.pos}`);
  const lag = slider(flat("slope", (_x, z) => -0.25 * z), 0, -20, 0, { jitter: (k) => [0, 90, 120, 0, 0, 60, 0, 30][k % 8] });
  assert(lag.pos === 0, `지연 흔들림(0.09~0.12초) 내리막 보정 ${lag.pos}회`);
  const turn = slider(flat(), 0, 0, 0, { want: Math.PI / 2 });
  assert(turn.s.yaw > 1.4 && turn.pos === 0, `조향 ${turn.s.yaw.toFixed(2)}rad`);
});

Deno.test("배 슬라이딩: 눈벽·나무에 박으면 멈추고 관통 안 함, 머리 쪽도 안 박힘, 맵 경계 밖으로 안 나감", () => {
  const room = createRoom("base_camp"), w = room.map.obstacles.find((o) => o.kind === "snow_wall_high" && o.hw !== undefined)!;
  const nx = Math.sin(w.rot!), nz = Math.cos(w.rot!);
  const side = (px: number, pz: number) => Math.sign((px - w.x) * nx + (pz - w.z) * nz);
  const r = slider(room, w.x - 5 * nx, w.z - 5 * nz, Math.atan2(nx, nz));
  assert(r.s.hit && side(r.a.x, r.a.z) < 0 && r.pos === 0, `눈벽 앞에서 멈춤 hit ${r.s.hit} 보정 ${r.pos}`);
  const [hx, hz] = slideNose(room.map, r.a.x, r.a.z, r.s.yaw, r.a.y);
  assert(Math.hypot(hx - r.a.x, hz - r.a.z) < 1e-6, "머리 원도 벽 밖");
  const forest = createRoom("forest"), t = forest.map.obstacles.find((o) => o.kind === "tree" && Math.hypot(o.x, o.z) < 30)!;
  const tr = slider(forest, t.x, t.z - 6, 0);
  assert(tr.s.hit && Math.hypot(tr.a.x - t.x, tr.a.z - t.z) >= t.body + 0.39 && tr.pos === 0, `나무 앞에서 멈춤 hit ${tr.s.hit}`);
  const e = slider(flat(), 0, 45, 0);
  assert(e.a.z <= 50 + 1e-9, `맵 경계 ${e.a.z}`);
});

Deno.test("배 슬라이딩 보안: 속도 부풀리기는 거절, 시작 조건(쿨다운·공중·얼음·굴리기·모으기·판 끝), 슬라이딩 중 던지기·모으기 불가", () => {
  const fast = slider(flat(), 0, 0, 0, { cheat: 1.6 });
  assert(fast.pos > 0 && fast.a.z < 8.6 + 3.2, `1.6배 속도는 서버가 되돌림 (보정 ${fast.pos}회, 서버 z ${fast.a.z.toFixed(1)}; 정상 8.6m + 기존 이동 여유 3m)`);
  const noStart = flat(), q = join(noStart, sock, "q"); place(q, 0, 0); q.moveT = 1000;
  for (let i = 1; i <= 30; i++) handle(q, { t: "p", x: 0, y: 0, z: i, yaw: 0 }, 1000 + i * 66); // 슬라이딩 승인 없이 초속 15m 로 2초
  assert(q.z < 20, `승인 없는 빠른 이동은 거절 z ${q.z.toFixed(1)} (보낸 30m)`);
  const room = flat(), a = join(room, sock, "a"); place(a, 0, 0);
  handle(a, { t: "bs", on: true }, 1000); const t0 = a.slideT;
  handle(a, { t: "bs", on: false }, 1500); handle(a, { t: "bs", on: true }, 2000);
  assert(t0 === 1000 && a.slideT === 0, "쿨다운 2.5초 안엔 다시 못 함");
  handle(a, { t: "bs", on: true }, 3500);
  assert(a.slideT === 3500, "쿨다운 뒤 다시");
  const ammo = a.ammo; handle(a, { t: "th", vx: 0, vy: 0, vz: 10 }, 3600); handle(a, { t: "g", on: true }, 3600); handle(a, { t: "r", on: true }, 3600);
  assert(a.ammo === ammo && !a.gather && !a.roll, "슬라이딩 중 던지기·모으기·굴리기 안 됨");
  for (const [name, set] of [["공중", (p: P) => { p.y += 1; }], ["얼음", (p: P) => { p.frozenUntil = 1e12; }], ["굴리기", (p: P) => { p.roll = 0.3; }], ["모으기", (p: P) => { p.gather = true; }], ["판 끝", (p: P) => { p.room.game.breakUntil = 1e12; }]] as [string, (p: P) => void][]) {
    const r = flat(), p = join(r, sock, "p"); place(p, 0, 0); set(p);
    handle(p, { t: "bs", on: true }, 5000);
    assert(!p.slideT, `${name} 중엔 시작 못 함`);
  }
  handle(a, { t: "bs", on: true }, 9000); room.game.roundEnd = 9100; round(room, 9100);
  assert(!a.slideT, "판이 끝나면 슬라이딩 멈춤");
});

Deno.test("배 슬라이딩 중 피격: 누운 판정 구(머리 위로 지나가면 안 맞고 몸통은 맞음), 싸다구 맞으면 멈춤, 3번 맞으면 얼면서 멈춤", () => {
  const shot = (dy: number) => {
    const room = flat(), a = join(room, sock, "a"), b = join(room, sock, "b");
    for (const p of room.players.values()) if (p.bot) place(p, 45, 45);
    place(b, 0, 0, Math.PI / 2); handle(b, { t: "bs", on: true }, 900); // +x 방향으로 누움
    room.balls.push({ id: 9, owner: a.id, team: a.team, x: 0, y: dy, z: 5, vx: 0, vy: 1.5, vz: -25, age: 0, rewind: null }); // vy: 0.2초 동안 떨어지는 만큼
    for (let j = 0; j < 20; j++) tick(room, 1000);
    return b.hp < 3;
  };
  assert(shot(0.5) && shot(1.1), "몸통·머리 높이는 맞음");
  assert(!shot(1.95), "서 있으면 머리(1.95m)였을 높이는 누우면 지나감");
  const { room, a, b } = duel();
  handle(b, { t: "bs", on: true }, 900); slap(a, 1000);
  assert(b.hp === 2 && !b.slideT, "싸다구 맞으면 경직 + 슬라이딩 멈춤");
  b.hp = 1; handle(b, { t: "bs", on: true }, 5000);
  room.balls.push({ id: 10, owner: a.id, team: a.team, x: 0, y: 0.5, z: 1, vx: 0, vy: 0, vz: -25, age: 0, rewind: null });
  for (let j = 0; j < 10; j++) tick(room, 5100);
  assert(b.frozenUntil > 5100 && !b.slideT, "얼면 슬라이딩 끝");
});

// ── SNOW BRAWL(개인전) ──
const arena = () => createRoom("snow_brawl_arena");
const roll = (p: P, now: number, hold = 0) => { handle(p, { t: "r", on: true }, now); handle(p, { t: "r", on: false }, now + hold); };
const run = (room: Room, from: number, ms: number) => { for (let t = 0; t <= ms; t += 33) tick(room, from + t); };

Deno.test("개인전: 봇 없음, 8명까지 색이 모두 다름, 9번째는 못 들어감, 나간 색은 다시 쓰고 재접속은 예전 색", () => {
  const room = arena(); rooms.set(room.map.id, room);
  const ps = Array.from({ length: 8 }, (_, i) => join(room, sock, "p" + i));
  assert(![...room.players.values()].some((p) => p.bot), "봇 없음");
  assert(new Set(ps.map((p) => p.team)).size === 8 && ps.every((p) => p.team >= 2 && p.team < 2 + BRAWL.colors.length), `색 ${ps.map((p) => p.team)}`);
  assert(pickRoom("snow_brawl_arena") === null, "8명이면 꽉 참(팀전으로 안 보냄)");
  assert(pickRoom("auto")?.map.mode !== "brawl", "자동은 팀전 방만");
  const c = ps[3].team - 2; leave(ps[3]);
  const back = join(room, sock, "p3", c);
  assert(back.team === 2 + c, "재접속하면 예전 색");
  leave(ps[5]); const other = join(room, sock, "x", c);
  assert(other.team === ps[5].team, "비어 있는 색을 줌(이미 쓰는 색 요청은 무시)");
  rooms.set(room.map.id, createRoom(room.map.id));
});

Deno.test("개인전: 스폰 8곳이 서로 다르고 장애물 밖, 모두가 적(싸다구 1점·팀 점수 없음)", () => {
  const room = arena(), ps = Array.from({ length: 8 }, (_, i) => join(room, sock, "p" + i));
  for (let i = 0; i < 8; i++) for (let j = i + 1; j < 8; j++) assert(Math.hypot(ps[i].x - ps[j].x, ps[i].z - ps[j].z) > 15, "스폰 간격");
  for (const p of ps) { const [x, z] = pushOut(room.map, p.x, p.z); assert(x === p.x && z === p.z, "장애물과 안 겹침"); }
  const [a, b] = ps; place(a, 0, 0, Math.PI); place(b, 0, -1.6);
  handle(a, { t: "sl" }, 1000); run(room, 1000, 300);
  assert(b.hp === 2 && a.score === BRAWL.slapPts && room.game.scores.join() === "0,0", `싸다구 hp ${b.hp} score ${a.score}`);
});

Deno.test("개인전: 던지기·모으기는 서버가 거절, 팀전은 그대로", () => {
  const room = arena(), a = join(room, sock, "a");
  handle(a, { t: "th", vx: 0, vy: 0, vz: -20 }, 1000); handle(a, { t: "g", on: true }, 1000);
  assert(room.balls.length === 0 && a.ammo === 10 && !a.gather, "개인전 던지기·모으기 거절");
  const t = createRoom("slope"), b = join(t, sock, "b");
  handle(b, { t: "th", vx: 0, vy: 0, vz: -20 }, 1000);
  assert(t.balls.length === 1, "팀전 던지기는 됨");
});

Deno.test("개인전 굴린 눈: 앞으로 굴러가 맞히면 2점·체력 -1·한 명만, 쿨다운 2초, 13m 넘으면·벽에 닿으면 부서짐, 점프로 넘으면 안 맞음", () => {
  const room = flat("snow_brawl_arena"), a = join(room, sock, "a"), b = join(room, sock, "b"), c = join(room, sock, "c");
  place(a, 0, 0, Math.PI); place(b, 0, -6); place(c, 0, -8); // a 는 -z 를 봄, b 가 앞, c 는 b 뒤
  roll(a, 1000);
  assert(evs(room, "rl").length === 1 && room.rolls.length === 1, "굴려 보냄");
  run(room, 1000, 1500);
  assert(b.hp === 2 && c.hp === 3 && a.score === BRAWL.rollPts && evs(room, "rlh").length === 1, `한 명만 b ${b.hp} c ${c.hp} score ${a.score}`);
  roll(a, 2500); assert(evs(room, "rl").length === 1, "2초 안에는 다시 못 굴림");
  place(b, 30, 30); place(c, 30, 31);
  roll(a, 3100); run(room, 3100, 2000);
  assert(evs(room, "rlx").length === 1 && room.rolls.length === 0, "13m 끝에서 부서짐");
  // 점프로 넘기: b 가 공중 1.2m(눈 지름 0.5m 위)
  place(b, 0, -5); b.y = 1.2; b.hp = 3; roll(a, 6000); run(room, 6000, 900);
  assert(b.hp === 3 && evs(room, "rlh").length === 1, `눈 위로 뛰면 안 맞음 hp ${b.hp}`);
  // 벽: 실제 경기장 링 바깥 벽 쪽으로
  const r2 = arena(), w = join(r2, sock, "w"); place(w, 0, 27, 0); roll(w, 1000); run(r2, 1000, 1000);
  assert(evs(r2, "rlx").length === 1 && r2.rolls.length === 0 && Math.hypot(...(evs(r2, "rlx")[0].slice(2, 4) as [number, number])) < 30.5, "바깥 눈벽에 부딪혀 부서짐");
});

Deno.test("개인전 판 끝: 개인 순위(같은 점수는 같은 순위), 새 판은 모두 다른 스폰", () => {
  const room = arena(), ps = Array.from({ length: 4 }, (_, i) => join(room, sock, "p" + i));
  ps[0].score = 5; ps[1].score = 7; ps[2].score = 7; ps[3].score = 1;
  round(room, 1000); room.game.roundEnd = 2000; round(room, 2000);
  const ev = evs(room, "ffa")[0], rk = ev[1] as number[][];
  assert(evs(room, "over").length === 0 && rk.map((r) => r[1]).join() === "1,1,3,4" && rk[0][2] === 7, `순위 ${JSON.stringify(rk)}`);
  assert(JSON.stringify(ranking(room)) === JSON.stringify(rk), "ranking 함수와 같음");
  round(room, 2000 + BREAK_MS);
  assert(ps.every((p) => p.score === 0), "새 판 점수 0");
  for (let i = 0; i < 4; i++) for (let j = i + 1; j < 4; j++) assert(Math.hypot(ps[i].x - ps[j].x, ps[i].z - ps[j].z) > 15, "새 판 스폰 간격");
});
