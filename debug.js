// 개발용 디버그 (localhost?debug 에서만 index.html 이 불러옴. 배포 화면엔 안 실림)
// - 히트박스(서버 판정 구 2개)·모델 경계·눈덩이 판정 구·실제 궤적·명중 위치
// - 화면 예측 명중 ↔ 서버 명중 일치 통계
// - 판 끝내기(DEV=1 서버만 받아 줌)·내 승리 동작, 캐릭터 수·눈덩이·파티클 부하, 성능 측정
import { BALL_R, HIT_SPHERES, SLIDE_SPHERES } from './maps.js';

export function initDebug(api) {
  const { THREE, scene, renderer, ents, balls, send, puff } = api;
  const st = { show: true, maxChars: 0, ballLoad: false, partLoad: false, frames: [], gpu: [], measuring: 0, stats: { pred: 0, both: 0, serverOnly: 0, predOnly: 0 }, all: { pred: 0, both: 0, serverOnly: 0, predOnly: 0 } };
  const wire = (color) => new THREE.MeshBasicMaterial({ color, wireframe: true, transparent: true, opacity: 0.55, depthTest: false });
  const hitM = wire('#ff3b30'), ballM = wire('#ffcc00'), bodyColM = wire('#00e676'), ballColM = wire('#ff9100');
  const colGroup = new THREE.Group(); colGroup.renderOrder = 10; scene.add(colGroup); // 장애물 충돌 영역(서버와 같은 maps.js 데이터)
  const group = new THREE.Group(); group.renderOrder = 10; scene.add(group);
  const helpers = new Map(); // ent → { spheres, box }
  const trails = new Map(); // ball id → { line, pts, sphere, dead }
  const marks = []; // [mesh, until]
  const pending = new Map(); // 예측 명중 id → 시각

  // ── 패널
  const panel = document.createElement('div');
  panel.style.cssText = 'position:fixed;left:50%;top:44px;transform:translateX(-50%);z-index:50;background:#0b1a2ce6;color:#fff;font:12px/1.4 system-ui;padding:8px 10px;border-radius:10px;max-width:96vw;display:grid;gap:6px';
  const row = (...els) => { const d = document.createElement('div'); d.style.cssText = 'display:flex;gap:4px;flex-wrap:wrap;align-items:center'; d.append(...els); rows.append(d); return d; };
  const btn = (label, fn) => { const b = document.createElement('button'); b.textContent = label; b.style.cssText = 'font:12px system-ui;padding:4px 7px;border-radius:6px;border:0;cursor:pointer'; b.onclick = (e) => { e.stopPropagation(); fn(b); }; return b; };
  const out = document.createElement('div'); out.style.whiteSpace = 'pre'; out.style.fontFamily = 'ui-monospace,monospace';
  const fold = btn('🛠 접기', () => { const open = rows.style.display === 'none'; rows.style.display = open ? 'grid' : 'none'; fold.textContent = open ? '🛠 접기' : '🛠 디버그'; });
  panel.append(fold);
  const rows = document.createElement('div'); rows.style.cssText = 'display:grid;gap:6px'; panel.append(rows);
  row(
    btn('히트박스 끄기', (b) => { setShow(!st.show); b.textContent = st.show ? '히트박스 끄기' : '히트박스 켜기'; }),
    btn('판 끝: 우리 승', () => send({ t: 'dev', win: 'me' })), btn('상대 승', () => send({ t: 'dev', win: 'them' })), btn('무승부', () => send({ t: 'dev', win: 'draw' })),
    btn('내 승리 동작', () => { const e = api.getMe(); if (e) e.victoryUntil = performance.now() + 5500; }));
  row(document.createTextNode('부하'),
    ...[-1, 1, 4, 0].map((n) => btn(n < 0 ? '맵만' : n ? `캐릭터 ${n}` : '캐릭터 전부', () => { st.maxChars = n; })),
    btn('눈덩이 50개 유지', (b) => { st.ballLoad = !st.ballLoad; b.style.background = st.ballLoad ? '#ffd166' : ''; }),
    btn('파티클 폭탄', (b) => { st.partLoad = !st.partLoad; b.style.background = st.partLoad ? '#ffd166' : ''; }),
    btn('5초 측정', () => measure(5000)),
    btn('장애물 충돌 끄기', (b) => { colGroup.visible = !colGroup.visible; b.textContent = colGroup.visible ? '장애물 충돌 끄기' : '장애물 충돌 켜기'; }));
  rows.append(out);
  document.body.append(panel);
  if (innerWidth < 700) fold.click(); // 좁은 화면(폰)에선 접어 둠: 입장·조작 버튼을 가리지 않게
  for (const t of ['pointerdown', 'pointerup', 'wheel']) panel.addEventListener(t, (e) => e.stopPropagation());

  // ── 캐릭터: 판정 구 2개(발 기준)·모델 경계 상자
  function onEnt(e) {
    if (!e || helpers.has(e)) return;
    const spheres = HIT_SPHERES.map(([h, r]) => { const m = new THREE.Mesh(new THREE.SphereGeometry(r, 14, 10), hitM); m.position.y = h; m.renderOrder = 10; e.c.g.add(m); return m; });
    const box = new THREE.Box3Helper(new THREE.Box3(), '#00e5ff'); box.renderOrder = 10; group.add(box);
    helpers.set(e, { spheres, box, n: 0 });
  }
  for (const e of ents.values()) onEnt(e);
  const allowed = () => { // 캐릭터 수 제한: 나 + 앞에서부터 n-1 명
    if (!st.maxChars) return null;
    if (st.maxChars < 0) return new Set(); // 맵만 (캐릭터 전부 숨김)
    const me = api.getMe(), list = [me, ...[...ents.values()].filter((e) => e !== me)].filter(Boolean);
    return new Set(list.slice(0, st.maxChars));
  };
  let allow = null;
  const hidden = (e) => !!allow && !allow.has(e);

  // ── 눈덩이: 실제(서버와 같은) 위치의 판정 구 + 지나간 길
  function onBall(id, b) {
    let t = trails.get(id);
    if (!t) {
      const pts = new Float32Array(3 * 240), geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.BufferAttribute(pts, 3)); geo.setDrawRange(0, 0);
      const line = new THREE.Line(geo, new THREE.LineBasicMaterial({ color: '#ff9500', depthTest: false })); line.renderOrder = 10; line.frustumCulled = false;
      const sphere = new THREE.Mesh(new THREE.SphereGeometry(BALL_R, 10, 8), ballM); sphere.renderOrder = 10;
      group.add(line, sphere);
      t = { line, pts, n: 0, sphere, seen: 0, mine: b.owner === api.myId() }; trails.set(id, t);
    }
    t.seen = performance.now();
    t.sphere.position.set(b.x, b.y, b.z);
    if (t.n < 240) { t.pts.set([b.x, b.y, b.z], t.n * 3); t.n++; t.line.geometry.setDrawRange(0, t.n); t.line.geometry.attributes.position.needsUpdate = true; }
  }
  const mark = (x, y, z, color) => { const m = new THREE.Mesh(new THREE.OctahedronGeometry(0.12), new THREE.MeshBasicMaterial({ color, depthTest: false })); m.position.set(x, y, z); m.renderOrder = 11; group.add(m); marks.push([m, performance.now() + 3000]); };
  // 통계: stats = 내가 던진 공만, all = 봇 공 포함 전체
  const bump = (mine, k) => { st.all[k]++; if (mine) st.stats[k]++; };
  function onPredict(id, b) { const mine = b.owner === api.myId(); bump(mine, 'pred'); pending.set(id, [performance.now(), mine]); mark(b.x, b.y, b.z, '#ffcc00'); }
  function onHit(id, x, y, z) {
    mark(x, y, z, '#ff3b30');
    const p = pending.get(id), mine = p ? p[1] : !!trails.get(id)?.mine;
    if (p) { pending.delete(id); bump(mine, 'both'); } else bump(mine, 'serverOnly');
  }
  function rekey(from, to) { // 내 예측 눈덩이(-번호)가 서버 번호를 받음
    if (pending.has(from)) { pending.set(to, pending.get(from)); pending.delete(from); }
    if (trails.has(from)) { trails.set(to, trails.get(from)); trails.delete(from); }
  }

  // ── 성능: 프레임 간격·한 프레임 JS 시간·GPU 시간(지원 시)·렌더 통계
  const gl = renderer.getContext(), tq = gl.getExtension('EXT_disjoint_timer_query_webgl2'), queries = [];
  let t0 = 0, last = 0, q = null, bseq = 0;
  function frameStart(now) {
    t0 = performance.now();
    if (last) st.frames.push([now - last, 0]);
    last = now;
    if (tq && !q) { q = gl.createQuery(); gl.beginQuery(tq.TIME_ELAPSED_EXT, q); }
    allow = allowed();
    if (st.ballLoad) { // 눈덩이 50개 유지 (화면 전용, 서버로 안 감)
      const me = api.getMe(); let n = 0; for (const k of balls.keys()) if (String(k).startsWith('dbg')) n++;
      for (; me && n < 50; n++) balls.set('dbg' + bseq++, { mesh: api.add(scene, api.ballGeo, api.ballM ?? api.M.white), x: me.x + (Math.random() - 0.5) * 10, y: me.y + 2 + Math.random() * 2, z: me.z + (Math.random() - 0.5) * 10, vx: (Math.random() - 0.5) * 16, vy: 4 + Math.random() * 6, vz: (Math.random() - 0.5) * 16, age: 0 });
    }
    if (st.partLoad && Math.random() < 0.5) { const me = api.getMe(); if (me) puff(me.x + (Math.random() - 0.5) * 8, me.y + 1, me.z + (Math.random() - 0.5) * 8, 20); }
  }
  function frameEnd(now) {
    if (q) { gl.endQuery(tq.TIME_ELAPSED_EXT); queries.push(q); q = null; }
    while (queries.length && gl.getQueryParameter(queries[0], gl.QUERY_RESULT_AVAILABLE)) {
      const r = queries.shift(); if (!gl.getParameter(tq.GPU_DISJOINT_EXT)) st.gpu.push(gl.getQueryParameter(r, gl.QUERY_RESULT) / 1e6); gl.deleteQuery(r);
    }
    if (st.frames.length) st.frames.at(-1)[1] = performance.now() - t0;
    if (st.frames.length > 2000) st.frames.splice(0, 1000);
    if (st.gpu.length > 2000) st.gpu.splice(0, 1000);
    // 경계 상자는 20프레임마다(스킨 메시 정점 계산이 무거움), 사라진 눈덩이 궤적은 2초 뒤 지움, 표시는 3초
    for (const [e, h] of helpers) {
      if (!e.c.g.parent) { h.box.removeFromParent(); h.box.geometry.dispose(); h.spheres.forEach((m) => m.geometry.dispose()); helpers.delete(e); continue; } // 나간 캐릭터: 표시용 지오메트리도 해제
      h.box.visible = st.show && !!e.c.peng && e.c.g.visible;
      if (h.box.visible && h.n++ % 20 === 0) h.box.box.setFromObject(e.c.peng.root, true);
      h.spheres.forEach((m, i) => { // 배 슬라이딩 중엔 누운 판정 구(앞뒤로)
        const [f, y, r] = e.slide ? SLIDE_SPHERES[i] : [0, ...HIT_SPHERES[i]];
        m.position.set(0, y, f); m.scale.setScalar(r / HIT_SPHERES[i][1]);
      });
    }
    for (const [id, t] of trails) if (now - t.seen > 2000) { t.line.geometry.dispose(); t.sphere.geometry.dispose(); group.remove(t.line, t.sphere); trails.delete(id); } else if (now - t.seen > 50) t.sphere.visible = false;
    for (let i = marks.length - 1; i >= 0; i--) if (now > marks[i][1]) { marks[i][0].geometry.dispose(); group.remove(marks[i][0]); marks.splice(i, 1); }
    for (const [id, [t, mine]] of pending) if (now - t > 1500) { pending.delete(id); bump(mine, 'predOnly'); } // 화면에선 맞았는데 서버는 빗나감
    if (now - (st.drawn ?? 0) > 250) { st.drawn = now; draw(); }
  }
  // ── 장애물 충돌 영역: 초록 = 몸을 막는 범위(body / 회전 상자), 주황 = 눈덩이를 막는 범위(ball, 나무는 가지까지)
  function onMap(m) {
    for (const c of [...colGroup.children]) { c.geometry.dispose(); colGroup.remove(c); }
    const put = (geo, mat, o, rot = 0) => { const x = new THREE.Mesh(geo, mat); x.position.set(o.x, o.y + o.top / 2, o.z); x.rotation.y = rot; x.renderOrder = 10; colGroup.add(x); };
    for (const o of m.obstacles) {
      if (o.hw !== undefined) put(new THREE.BoxGeometry(o.hw * 2, o.top, o.hd * 2), bodyColM, o, o.rot);
      else {
        put(new THREE.CylinderGeometry(o.body, o.body, o.top, 16, 1, true), bodyColM, o);
        if (o.ball > o.body + 0.05) put(new THREE.CylinderGeometry(o.ball, o.ball, o.top, 16, 1, true), ballColM, o);
      }
    }
  }
  function setShow(v) { st.show = v; group.visible = v; for (const h of helpers.values()) h.spheres.forEach((m) => { m.visible = v; }); }
  const pct = (a, p) => { const s = [...a].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(s.length * p))] ?? 0; };
  function snapshot(frames, gpu) {
    const iv = frames.map((f) => f[0]), cpu = frames.map((f) => f[1]), avg = (a) => a.reduce((x, y) => x + y, 0) / Math.max(1, a.length);
    const info = renderer.info, mem = performance.memory;
    let chars = 0; for (const e of ents.values()) if (e.c.g.visible && e.c.peng) chars++;
    return {
      chars, balls: balls.size, fps: +(1000 / avg(iv)).toFixed(1), low1: +(1000 / pct(iv, 0.99)).toFixed(1),
      frameMs: +avg(iv).toFixed(2), cpuMs: +avg(cpu).toFixed(2), cpuP99: +pct(cpu, 0.99).toFixed(2),
      gpuMs: gpu.length ? +avg(gpu).toFixed(2) : null,
      calls: info.render.calls, tris: info.render.triangles, geos: info.memory.geometries, texs: info.memory.textures,
      heapMB: mem ? +(mem.usedJSHeapSize / 1048576).toFixed(1) : null,
    };
  }
  function measure(ms) {
    st.frames.length = 0; st.gpu.length = 0; st.measuring = performance.now() + ms;
    return new Promise((res) => setTimeout(() => { st.result = snapshot(st.frames, st.gpu); st.measuring = 0; window.__perfResult = st.result; draw(); res(st.result); }, ms));
  }
  function draw() {
    const s = st.stats, a = st.all, live = snapshot(st.frames.slice(-120), st.gpu.slice(-120));
    out.textContent = `내 공  화면예측 ${s.pred} · 서버도 맞음 ${s.both} · 화면만 ${s.predOnly} · 서버만 ${s.serverOnly}   (봇 포함 전체 ${a.pred}/${a.both}/${a.predOnly}/${a.serverOnly})\n`
      + `지금  ${live.fps}fps · JS ${live.cpuMs}ms · GPU ${live.gpuMs ?? '측정불가'}ms · draw ${live.calls} · 삼각형 ${live.tris} · 지오 ${live.geos} · 텍스처 ${live.texs} · 힙 ${live.heapMB ?? '?'}MB · 캐릭터 ${live.chars} · 눈덩이 ${live.balls}`
      + (st.measuring ? '\n측정 중…' : st.result ? `\n측정  ${JSON.stringify(st.result)}` : '');
  }
  window.__dbg = { st, api, measure, setShow, colGroup, onMap, setChars: (n) => { st.maxChars = n; }, setLoad: (b, p) => { st.ballLoad = b; st.partLoad = p; } };
  return { onEnt, onBall, onHit, onPredict, rekey, hidden, frameStart, frameEnd, onMap };
}
