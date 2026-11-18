// deno test server_test.ts
import { pushOut } from "./maps.js";
import { BREAK_MS, createRoom, handle, join, leave, pickRoom, round, ROUND_MS, rooms, tick } from "./server.ts";
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
