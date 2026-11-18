// 게임 캐릭터: Blender로 만든 블루 펭귄 GLB(assets/penguin_blue.glb) 한 벌로 팀 색·표정·동작을 모두 처리한다.
// - GLB는 한 번만 내려받아 캐싱. 캐릭터마다 SkeletonUtils.clone → 지오메트리는 공유, 뼈·애니메이션 상태는 따로
// - 팀 0 = 핑크(의상 재질 4개만 팀당 한 번 복제해 색만 바꿈), 팀 1 = 블루(GLB 원본 재질 그대로)
// - 키를 TARGET_HEIGHT(2m)에 맞춰 키움: 서버 명중 판정(발 위 1m 중심, 반지름 0.9m)과 같은 높이
// - 표정: GLB 안의 얼굴 부품 메시(extras.expressions 목록)를 켜고 끄기만 함. 다시 불러오지 않음
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { clone as cloneSkinned } from 'three/addons/utils/SkeletonUtils.js';

export const PENGUIN_URL = '/assets/penguin_blue.glb';
export const TARGET_HEIGHT = 2.0;
export const EXPRESSIONS = ['normal', 'excited', 'wink', 'surprised', 'focused', 'heart'];
// 바꿀 재질 이름 → 핑크 색. 나머지(몸·얼굴·눈·부리·발·고글 렌즈·흰 줄무늬·지퍼)는 블루와 같은 재질을 같이 씀
export const PINK_OUTFIT = { jacket_blue: '#ff65a8', jacket_trim_blue: '#e44d8f', beanie_blue: '#ff6fae', goggle_strap_blue: '#e8579a' };
// 동작 → [클립, 표정]
const MOODS = { idle: 'normal', walk: 'normal', run: 'focused', jump: 'excited', gather: 'focused', roll: 'focused', throw: 'focused', hit: 'surprised', frozen: 'surprised', victory: 'excited' };
const CLIP = { idle: 'Idle', walk: 'Walk', run: 'Run', jump: 'JumpInPlace', gather: 'Gather', roll: 'Roll', throw: 'Throw', hit: 'Hit', frozen: 'Hit', victory: 'Victory' };
const ONCE = new Set(['jump', 'throw', 'hit', 'frozen']);
const NO_SHADOW = /^(eye|expr_|goggle_lens|jacket_snowflake)/; // 작은 얼굴 부품은 그림자 그리기 생략(그림자 패스 draw call 절약)

let asset = null;
// onProgress(받은 바이트 비율 0~1 또는 null): 로딩 화면 진행률용. 실패하면 캐시를 비워 다시 시도할 수 있게
export function loadPenguin(url = PENGUIN_URL, onProgress = null) {
  asset ??= new GLTFLoader().loadAsync(url, (e) => onProgress?.(e.total ? e.loaded / e.total : null)).then((gltf) => {
    const rest = new THREE.Box3().setFromObject(gltf.scene, true);
    const h = rest.max.y - rest.min.y;
    const clips = Object.fromEntries(gltf.animations.map((c) => [c.name, c]));
    // 점프 높이는 게임 물리가 정하므로 GLB 점프의 루트 위아래 이동만 뺀 사본을 씀(웅크림·날개·발은 그대로)
    clips.JumpInPlace = new THREE.AnimationClip('JumpInPlace', clips.Jump.duration, clips.Jump.tracks.filter((t) => t.name !== 'root.position'));
    const root = gltf.scene.getObjectByName('penguin_blue');
    const expressions = root?.userData?.expressions;
    if (!expressions) throw new Error('penguin GLB: extras.expressions 가 없음');
    // 핑크 재질: 실제 GLB에 있는 재질만 복제(이름이 다르면 조용히 건너뛰지 않고 알림)
    const found = new Map();
    gltf.scene.traverse((o) => { if (o.isMesh) found.set(o.material.name, o.material); });
    const pink = {};
    for (const [name, hex] of Object.entries(PINK_OUTFIT)) {
      const m = found.get(name);
      if (!m) { console.warn('penguin: 재질 없음', name); continue; }
      pink[name] = m.clone(); pink[name].color.set(hex); pink[name].name = name.replace('blue', 'pink');
    }
    return { gltf, scale: TARGET_HEIGHT / h, footY: rest.min.y, clips, expressions, teamMats: [pink, null] };
  });
  asset.catch(() => { asset = null; });
  return asset;
}

export class Penguin {
  constructor(a, team) {
    this.root = new THREE.Group();
    this.model = cloneSkinned(a.gltf.scene);
    this.model.scale.setScalar(a.scale);
    this.model.position.y = -a.footY * a.scale; // 발바닥을 정확히 y=0 에
    const mats = a.teamMats[team] ?? null;
    this.parts = new Map(); // 얼굴 부품 이름 → 메시
    const face = new Set(Object.values(a.expressions).flat());
    this.model.traverse((o) => {
      if (!o.isMesh) return;
      if (mats?.[o.material.name]) o.material = mats[o.material.name];
      o.castShadow = !NO_SHADOW.test(o.name);
      if (face.has(o.name)) this.parts.set(o.name, o);
    });
    // GLB의 스킨 메시 24개가 같은 뼈 10개를 쓰는데 로더·clone 은 메시마다 Skeleton 을 따로 만든다 → 하나로 합쳐
    // 매 프레임 뼈 계산·뼈 텍스처 업로드를 캐릭터당 1번만 (bindMatrix·역바인드 행렬이 같을 때만)
    let shared = null;
    this.model.traverse((o) => {
      if (!o.isSkinnedMesh) return;
      if (!shared) { shared = o.skeleton; return; }
      const same = o.skeleton.bones.every((b, i) => b === shared.bones[i]) && o.skeleton.boneInverses.every((m, i) => m.equals(shared.boneInverses[i]));
      if (same) { o.skeleton.dispose(); o.skeleton = shared; }
    });
    this.root.add(this.model);
    this.a = a; this.mixer = new THREE.AnimationMixer(this.model); this.actions = {};
    this.state = null; this.action = null; this.expr = null; this.exprOverride = null; this.exprUntil = 0;
    this.setExpression('normal');
    this.play('idle');
  }
  // 표정: 'normal' | 'excited' | 'wink' | 'surprised' | 'focused' | 'heart'. ms 를 주면 그동안만(이모트), 아니면 동작에 맡김
  setExpression(name, ms = 0, now = performance.now()) {
    if (!this.a.expressions[name]) return;
    if (ms) { this.exprOverride = name; this.exprUntil = now + ms; }
    this.#show(ms ? name : this.exprOverride && now < this.exprUntil ? this.exprOverride : name);
  }
  #show(name) {
    if (name === this.expr) return;
    const on = new Set(this.a.expressions[name]);
    for (const [n, m] of this.parts) m.visible = on.has(n);
    this.expr = name;
  }
  // 던지는 날개(오른쪽, 모델 기준 -x) 끝의 지금 월드 위치 → v. 눈덩이가 날개에서 출발하는 것처럼 보이게 쓰임
  hand(v) {
    this.handBone ??= this.model.getObjectByName('hand_R');
    return this.handBone ? this.handBone.getWorldPosition(v) : null;
  }
  // 캐릭터를 지울 때: 뼈 텍스처(GPU)와 애니메이션 캐시 해제. 지오메트리·재질은 다른 캐릭터와 공유라 그대로 둠
  dispose() {
    this.mixer.stopAllAction(); this.mixer.uncacheRoot(this.model);
    const sk = new Set(); this.model.traverse((o) => o.isSkinnedMesh && sk.add(o.skeleton));
    for (const s of sk) s.dispose();
    this.root.removeFromParent();
  }
  #act(clipName) { return (this.actions[clipName] ??= this.mixer.clipAction(this.a.clips[clipName])); }
  // 동작 바꾸기. opts.from: 클립 시작 시각(초), opts.speed: 재생 속도, opts.hold: 그 시각에 멈춤
  play(state, opts = {}) {
    if (state === this.state && !opts.restart) return;
    const next = this.#act(CLIP[state]), once = ONCE.has(state);
    next.reset();
    next.setLoop(once ? THREE.LoopOnce : THREE.LoopRepeat, Infinity);
    next.clampWhenFinished = once;
    next.timeScale = opts.speed ?? 1;
    next.time = opts.from ?? 0;
    next.paused = !!opts.hold;
    if (this.action && this.action !== next) this.action.crossFadeTo(next, opts.fade ?? 0.15, false);
    next.play();
    this.action = next; this.state = state;
  }
  // 게임 상태 → 동작·표정. s: { moving, running, air, gather, roll, frozen, throwAt, hitAt, victory }
  drive(s, now, dt) {
    let st = 'idle';
    if (s.frozen) st = 'frozen';
    else if (now - s.hitAt < 700) st = 'hit';
    else if (now - s.throwAt < 380) st = 'throw'; // (0.9-0.4)/1.3 ≈ 0.38초
    else if (s.air) st = 'jump';
    else if (s.victory && !s.moving) st = 'victory'; // 판이 끝나도 움직이면 걷기·달리기가 우선
    else if (s.gather) st = 'gather';
    else if (s.roll) st = 'roll';
    else if (s.moving) st = s.running ? 'run' : 'walk';
    if (st === 'throw' && this.lastThrow !== s.throwAt) { // 새로 던질 때마다: 머리 위로 젖힌 자세부터 시작 → 눈덩이가 뜨자마자 앞으로 휘두름
      this.lastThrow = s.throwAt;
      this.play('throw', { from: 0.4, speed: 1.3, fade: 0, restart: true }); // 날개가 머리 위에서 앞으로 휘두르는 순간부터 → 눈덩이가 그 날개 끝에서 출발(index.html)
    } else if (st === 'hit' && this.lastHit !== s.hitAt) { this.lastHit = s.hitAt; this.play('hit', { fade: 0.05, restart: true }); }
    else if (st === 'frozen') this.play('frozen', { from: 0.1, hold: true }); // 맞은 순간 자세로 얼음
    else if (st === 'jump') this.play('jump', { from: 0.18 }); // 발을 뗀 순간부터
    else if (st !== 'throw' && st !== 'hit') this.play(st);
    if (st === 'walk' || st === 'run') this.action.timeScale = Math.max(0.6, Math.min(1.6, s.speedK ?? 1)); // 발걸음을 이동 속도에 맞춤
    this.setExpression(MOODS[st], 0, now);
    this.mixer.update(dt);
  }
}
