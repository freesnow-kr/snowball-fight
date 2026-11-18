// 게임 캐릭터: 펭귄 보더. 모두 같은 모델이고 목도리 색만 다르다(게임에서는 팀 색).
// 큰 머리·짧은 몸 SD 비율, 굵은 외곽선. 앞쪽 = +z, 발바닥 = y 0, 키 약 2m (명중 판정 높이와 맞춤).
const LINE = '#2b2b33', INK = '#1d1d24', BLUSH = '#f7a8b4', NAVY = '#2a2d3a', BELLY = '#fbfbfd', BEAK = '#ffa940';

export function buildPenguin(THREE, scarfColor = '#ff7a2f') {
  const root = new THREE.Group();
  const OUT = new THREE.MeshBasicMaterial({ color: LINE, side: THREE.BackSide });
  const mats = new Map();
  const toon = (c) => { if (!mats.has(c)) mats.set(c, new THREE.MeshToonMaterial({ color: c })); return mats.get(c); };
  const sphere = (r, ...a) => new THREE.SphereGeometry(r, 22, 16, ...a);
  const light = '#' + new THREE.Color(scarfColor).offsetHSL(0, 0, 0.18).getHexString();

  // 외곽선: 같은 모양을 뒤집어 살짝 크게(축마다 두께가 같아 보이게 크기에 맞춰 키움)
  function part(parent, geo, c, x = 0, y = 0, z = 0, o = {}) {
    const m = new THREE.Mesh(geo, o.flat ? new THREE.MeshBasicMaterial({ color: c }) : toon(c));
    m.position.set(x, y, z);
    m.scale.set(o.sx ?? 1, o.sy ?? 1, o.sz ?? 1);
    m.rotation.set(o.rx ?? 0, o.ry ?? 0, o.rz ?? 0);
    m.castShadow = true;
    if (o.outline !== false) {
      geo.computeBoundingBox();
      const s = geo.boundingBox.getSize(new THREE.Vector3()), t = 0.035;
      const line = new THREE.Mesh(geo, OUT);
      line.scale.set(1 + 2 * t / s.x, 1 + 2 * t / s.y, 1 + 2 * t / s.z);
      m.add(line);
    }
    parent.add(m);
    return m;
  }

  // 발·몸·흰 배·날개
  for (const s of [-1, 1]) part(root, sphere(0.16), BEAK, s * 0.18, 0.05, 0.12, { sy: 0.35, sz: 1.5 });
  part(root, sphere(0.5), NAVY, 0, 0.64, 0, { sy: 1.08 });
  part(root, sphere(0.44), BELLY, 0, 0.58, 0.1, { outline: false }); // 몸보다 앞으로 나와 큰 타원으로 보이게
  for (const s of [-1, 1]) part(root, sphere(0.17), NAVY, s * 0.5, 0.7, 0, { sx: 0.4, sy: 1.5, rz: s * 0.3 });

  // 머리: 남색 + 흰 얼굴, 눈·하이라이트·볼터치·부리
  const R = 0.52, head = part(root, sphere(R), NAVY, 0, 1.34, 0);
  const FR = 0.44, FY = -0.05, FZ = 0.12; // 흰 얼굴: 머리보다 앞으로 나온 구
  part(head, sphere(FR), BELLY, 0, FY, FZ, { outline: false });
  // 얼굴 표면 z: 머리·흰 얼굴 중 더 앞쪽(눈·볼·부리가 흰 얼굴 위에 붙게)
  const fz = (x, y) => Math.max(Math.sqrt(Math.max(0, R * R - x * x - y * y)),
    FZ + Math.sqrt(Math.max(0, FR * FR - x * x - (y - FY) ** 2)));
  for (const s of [-1, 1]) {
    const ex = s * 0.18;
    part(head, sphere(0.075), INK, ex, 0, fz(ex, 0) - 0.015, { outline: false, sz: 0.55, flat: true });
    part(head, sphere(0.024), '#fff', ex + 0.022, 0.026, fz(ex, 0) + 0.02, { outline: false, flat: true });
    const bx = s * 0.31, by = -0.13;
    part(head, new THREE.CircleGeometry(0.075, 18), BLUSH, bx, by, fz(bx, by) + 0.006,
      { outline: false, flat: true, ry: Math.asin(bx / R), rx: -Math.asin(by / R) });
  }
  part(head, sphere(0.09), BEAK, 0, -0.1, fz(0, -0.1) - 0.01, { sx: 1.3, sy: 0.6 });

  // 이마에 건 고글: 렌즈는 무채색 미러(팀 색과 헷갈리지 않게)
  const cv = document.createElement('canvas'); cv.width = 64; cv.height = 32;
  const c = cv.getContext('2d'), g = c.createLinearGradient(0, 0, 0, 32);
  g.addColorStop(0, '#e6edf5'); g.addColorStop(0.5, '#8aa0b8'); g.addColorStop(1, '#3d4b5c');
  c.fillStyle = g; c.fillRect(0, 0, 64, 32);
  c.fillStyle = '#ffffffaa'; c.fillRect(34, 0, 5, 32); c.fillRect(42, 0, 2, 32);
  const tex = new THREE.CanvasTexture(cv); tex.colorSpace = THREE.SRGBColorSpace;
  const arc = (r, h, a0, len, mat) => {
    const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, 32, 1, true, a0, len), mat);
    m.position.y = 0.3; head.add(m);
  };
  arc(R + 0.03, 0.25, -1.1, 2.2, toon('#26262c'));
  arc(R + 0.045, 0.18, -1.02, 2.04, new THREE.MeshBasicMaterial({ map: tex }));
  arc(R + 0.02, 0.08, 1.1, Math.PI * 2 - 2.2, toon('#26262c'));

  // 목도리: 이 캐릭터의 색. 앞으로 한 자락, 등 뒤로 한 자락(뒤에서도 색이 보이게)
  part(root, new THREE.TorusGeometry(0.36, 0.11, 10, 28), scarfColor, 0, 1.0, 0.02, { rx: Math.PI / 2 });
  for (const y of [0.97, 1.03]) part(root, new THREE.TorusGeometry(0.4, 0.018, 6, 28), light, 0, y, 0.02, { rx: Math.PI / 2, outline: false });
  part(root, new THREE.BoxGeometry(0.17, 0.36, 0.08), scarfColor, 0.2, 0.82, 0.4, { rz: -0.15 });
  part(root, new THREE.BoxGeometry(0.2, 0.5, 0.08), scarfColor, -0.12, 0.75, -0.44, { rz: 0.12, rx: -0.15 });
  return root;
}
