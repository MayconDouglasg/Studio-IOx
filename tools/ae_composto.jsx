// =====================================================================
//  Composed scenes ("composto") for tools/ae_builder.jsx — inserted by build_ae.py at //__COMPOSTO__.
//  A composed scene is a list of elements (texto, icone, caixa, circulo, linha, media, grupo, moeda,
//  segmentos) placed in px from the approved still, each with its own entrance on a spoken word, extra
//  keyed actions (anim) and a camera (deriva = arrive / drift / push, viagem = travel between stops on the
//  world). Layout mode: everything in place, no keyframes. Motion mode: 3D depth, entrances, camera.
//  Rules kept: one POS null per element (un-keyed), animation on the children; gradients (accent-gradient type, icon
//  strokes) live inside their own small comps where the Gradient Ramp points are exact; one blur per move
//  (layer motion blur only); the last scene of the film ends on a gentle pull-out.
// =====================================================================
var FLAT = 0;                                                     // >0 while building inside a 2D sub-comp
function is3D() { return MOTION && FLAT === 0; }
function m3(l) { if (is3D()) { try { l.threeDLayer = true; } catch (x) {} } }
function mb(l) { if (MOTION) { try { l.motionBlur = true; } catch (x) {} } }
function EP(l) { return l.property('ADBE Effect Parade'); }
function lastFx(l) { return EP(l).property(EP(l).numProperties); }
function rampFx(l, x, y0, y1, c0, c1, radial) {                  // points in comp px: the layer must be unparented, untransformed
  EP(l).addProperty('ADBE Ramp'); var r = lastFx(l);
  r.property(1).setValue([x, y0]); r.property(2).setValue(hex(c0)); r.property(3).setValue(radial ? [x + y1, y0] : [x, y1]); r.property(4).setValue(hex(c1));
  if (radial) { try { r.property(5).setValue(2); } catch (e) {} }
  return r;
}
// A client's soft accent glow (when its STYLE.md overrides "no glow") = coloured shadows with no distance, BEHIND the layer,
// like CSS drop-shadow(0 0 r colour). Not the Glow effect: it adds light on top and turns a blue accent into cyan
// (measured 2026-11: a mid-blue accent fill rendered as near-cyan 51,231,255).
function glowFx(l, kind, color) {
  try {
    var C2 = D.cols, sets;
    if (kind === 'suave') sets = [[C2.accL, 28, 26], [C2.acc, 22, 70]];
    else if (kind === 'forte') sets = [[color || C2.accL, 75, 14], [color || C2.acc, 45, 40]];
    else sets = [[color || C2.acc, 55, 45]];
    for (var i = 0; i < sets.length; i++) dropFx(l, sets[i][1], 0, sets[i][2], sets[i][0]);
  } catch (x) { log('  ! glow: ' + x.toString()); }
}
function dropFx(l, op, d, soft, color) {
  try { EP(l).addProperty('ADBE Drop Shadow'); var e = lastFx(l); if (color) e.property(1).setValue(hex(color)); e.property(2).setValue(op * 2.55); e.property(4).setValue(d); e.property(5).setValue(soft); } catch (x) {}
}
function isGrad(c) { return c === 'grad' || c === 'blue'; }      // accent gradient (accent_light -> accent_deep)
function shapeLayer(comp, name) { var l = comp.layers.addShape(); l.name = name; TG(l).property('ADBE Anchor Point').setValue([0, 0]); TG(l).property('ADBE Position').setValue([0, 0]); return l; }
function RV(l) { return l.property('ADBE Root Vectors Group'); }
// one vector group: paths (AE shapes) + stroke / fill
function addVec(l, paths, st) {
  var g = RV(l).addProperty('ADBE Vector Group'), gi = RV(l).numProperties, i;
  var G = function () { return RV(l).property(gi).property('ADBE Vectors Group'); };
  for (i = 0; i < paths.length; i++) {
    G().addProperty('ADBE Vector Shape - Group');
    var s = new Shape(), P = paths[i];
    s.vertices = P.v; s.inTangents = P.i; s.outTangents = P.o; s.closed = !!P.c;
    G().property(G().numProperties).property('ADBE Vector Shape').setValue(s);
  }
  if (st.fill) { G().addProperty('ADBE Vector Graphic - Fill'); var f = G().property('ADBE Vector Graphic - Fill'); f.property('ADBE Vector Fill Color').setValue(hex(st.fill)); f.property('ADBE Vector Fill Opacity').setValue(st.fop === undefined || st.fop === null ? 100 : st.fop); }
  if (st.stroke) {
    G().addProperty('ADBE Vector Graphic - Stroke'); var k = G().property('ADBE Vector Graphic - Stroke');
    k.property('ADBE Vector Stroke Color').setValue(hex(st.stroke)); k.property('ADBE Vector Stroke Width').setValue(st.sw || 2);
    try { k.property('ADBE Vector Stroke Line Cap').setValue(2); k.property('ADBE Vector Stroke Line Join').setValue(2); } catch (x) {}
    if (st.op !== undefined && st.op !== null) k.property('ADBE Vector Stroke Opacity').setValue(st.op);
    if (st.dash) {
      try { var ds = k.property('ADBE Vector Stroke Dashes'); ds.addProperty('ADBE Vector Stroke Dash 1'); ds.addProperty('ADBE Vector Stroke Gap 1');
        k = G().property('ADBE Vector Graphic - Stroke'); k.property('ADBE Vector Stroke Dashes').property('ADBE Vector Stroke Dash 1').setValue(st.dash[0]);
        k.property('ADBE Vector Stroke Dashes').property('ADBE Vector Stroke Gap 1').setValue(st.dash[1]); } catch (xd) { log('  ! dashes: ' + xd.toString()); }
    }
  }
  if (st.gop !== undefined && st.gop !== null && st.gop < 1) { try { RV(l).property(gi).property('ADBE Vector Transform Group').property('ADBE Vector Group Opacity').setValue(st.gop * 100); } catch (x) {} }
  return g;
}
function addTrim(l) { RV(l).addProperty('ADBE Vector Filter - Trim'); return RV(l).property(RV(l).numProperties); }
function rrPaths(x, y, w, h, r) { var s = rectShape(x + w / 2, y + h / 2, w, h, Math.min(r || 0, w / 2, h / 2)); return [{ v: s.vertices, i: s.inTangents, o: s.outTangents, c: true }]; }
function elPaths(cx, cy, rx, ry) { var k = 0.5523; return [{ v: [[cx, cy - ry], [cx + rx, cy], [cx, cy + ry], [cx - rx, cy]], i: [[-rx * k, 0], [0, -ry * k], [rx * k, 0], [0, ry * k]], o: [[rx * k, 0], [0, ry * k], [-rx * k, 0], [0, -ry * k]], c: true }]; }
function tr(paths, sx, sy, dx, dy) {                             // scale + move AE paths (vb -> px)
  var o = [], i, j;
  for (i = 0; i < paths.length; i++) {
    var P = paths[i], v = [], a = [], b = [];
    for (j = 0; j < P.v.length; j++) { v.push([P.v[j][0] * sx + dx, P.v[j][1] * sy + dy]); a.push([P.i[j][0] * sx, P.i[j][1] * sy]); b.push([P.o[j][0] * sx, P.o[j][1] * sy]); }
    o.push({ v: v, i: a, o: b, c: P.c });
  }
  return o;
}
function subComp(name, w, h, dur, folder) {
  var c = app.project.items.addComp(name, Math.max(4, Math.round(w)), Math.max(4, Math.round(h)), 1, dur, FPS);
  c.parentFolder = folder; try { c.renderer = 'ADBE Ernst'; } catch (x) {} if (MOTION) { c.motionBlur = true; c.shutterAngle = 180; }
  return c;
}
// ---- time helpers (times are scene-comp seconds)
function kz(prop, t0, t1, v0, v1, ease) { keys(prop, [t0, Math.max(t0 + 0.04, t1)], [v0, v1], ease || 'out'); }
// ---- entrances on one layer (non-text)
function enterLayer(l, en, kind, scale3) {
  if (!MOTION || !en) return;
  var t = en.t, d = en.dur || (RIT.entrada_s || 0.45), tg = TG(l), op = tg.property('ADBE Opacity'), o1 = op.value;
  var how = en.como;
  if (how === 'pop' || how === 'cascata') {
    var s1 = tg.property('ADBE Scale').value, s0 = []; for (var q = 0; q < s1.length; q++) s0.push(s1[q] * 0.84);
    kz(tg.property('ADBE Scale'), t, t + d * 1.25, s0, s1, 'out'); kz(op, t, t + d * 0.45, 0, o1, 'io');
  } else if (how === 'voa') {
    var p1 = tg.property('ADBE Position').value, de = en.de || [0, 120], p0 = p1.length === 3 ? [p1[0] + de[0], p1[1] + de[1], p1[2]] : [p1[0] + de[0], p1[1] + de[1]];
    kz(tg.property('ADBE Position'), t, t + d * 1.35, p0, p1, 'out'); kz(op, t, t + d * 0.4, 0, o1, 'io');
  } else if (how === 'sobe') {
    var r1 = tg.property('ADBE Position').value, r0 = r1.length === 3 ? [r1[0], r1[1] + 60, r1[2]] : [r1[0], r1[1] + 60];
    kz(tg.property('ADBE Position'), t, t + d * 1.2, r0, r1, 'out'); kz(op, t, t + d * 0.5, 0, o1, 'io');
  } else { kz(op, t, t + Math.max(0.2, d * 0.6), 0, o1, 'io'); }   // fade, desenha (the draw itself is keyed inside), acende
}
// ---- text entrances (per character)
function textEnter(l, en, kd, size) {
  if (!MOTION || !en) return;
  var t = en.t, how = en.como || 'sobe', n = 12;
  try { n = l.property('ADBE Text Properties').property('ADBE Text Document').value.text.length; } catch (x) {}
  if (how === 'escreve') {                                        // typewriter: characters appear left to right
    var an = ANIMS(l).addProperty('ADBE Text Animator'); an.name = 'ESCREVE';
    var P = function () { return ANIMS(l).property('ESCREVE').property('ADBE Text Animator Properties'); };
    P().addProperty('ADBE Text Opacity'); P().property('ADBE Text Opacity').setValue(0);
    ANIMS(l).property('ESCREVE').property('ADBE Text Selectors').addProperty('ADBE Text Selector');
    var st = ANIMS(l).property('ESCREVE').property('ADBE Text Selectors').property(1).property('ADBE Text Percent Start');
    keys(st, [t, t + (en.dur || Math.min(0.9, 0.04 * n))], [0, 100], 'lin');
    return;
  }
  if (how === 'fade' || how === 'pop') { var op = TG(l).property('ADBE Opacity'), o1 = op.value; kz(op, t, t + 0.3, 0, o1, 'io'); return; }
  var d = Math.max(RIT.entrada_s || 0.45, Math.min(0.85, 0.3 + 0.03 * n)), spec;
  if (how === 'serifa') { spec = { pos: [0, size * 0.12, is3D() ? -size * 1.4 : 0] }; d = Math.max(d, 0.6); if (is3D()) { try { l.threeDPerChar = true; } catch (x1) { spec.pos[2] = 0; } } }
  else spec = { pos: [0, size * 0.55, 0] };
  var off = addAnimator(l, 'ENTRADA', spec, 1, 2, 10, 100);
  off.setValueAtTime(t, -100); off.setValueAtTime(t + d, 100);
  setEase(off, 1, [0, 20], [0, 20]); setEase(off, 2, [0, 70], [0, 20]);
}
// ---- one element -> {h: POS null, ls: [child layers], box: [x0,y0,x1,y1]}
function elHandle(comp, name, ax, ay) { var h = comp.layers.addNull(); h.name = 'POS · ' + name; h.label = 9; m3(h); TG(h).property('ADBE Anchor Point').setValue(is3D() ? [0, 0, 0] : [0, 0]); TG(h).property('ADBE Position').setValue(is3D() ? [0, 0, 0] : [0, 0]); return { h: h, ax: ax, ay: ay }; }
function child(H, l, x, y) { H.n = (H.n || 0) + 1; m3(l); l.parent = H.h; TG(l).property('ADBE Position').setValue(is3D() ? [x - H.ax, y - H.ay, -0.4 * H.n] : [x - H.ax, y - H.ay]); mb(l); }
var ZSTEP = 0;                                                   // per-element depth step (no two 3D layers coplanar)
function placeEl(H, z) {
  if (is3D()) { ZSTEP += 1; z = (z || 0) - 1.5 * ZSTEP; }
  if (is3D()) { var d = depthFix(H.ax, H.ay, z || 0); TG(H.h).property('ADBE Position').setValue([d.x, d.y, z || 0]); TG(H.h).property('ADBE Scale').setValue([d.g * 100, d.g * 100, d.g * 100]); }
  else TG(H.h).property('ADBE Position').setValue([H.ax, H.ay]);
  H.h.moveToBeginning();
}
function styleBox(l, E, paths) {                                  // caixa / circulo looks
  var s = E.estilo || 'cheio', C2 = D.cols;
  if (s === 'vidro') { addVec(l, paths, { fill: C2.ink, fop: 9, stroke: C2.ink, sw: 2, op: 18 }); }
  else if (s === 'vidro-escuro') { addVec(l, paths, { fill: C2.paper, fop: 80, stroke: C2.ink, sw: 2, op: 20 }); }
  else if (s === 'no') { addVec(l, paths, { fill: C2.acc, stroke: C2.ink, sw: 2, op: 35 }); glowFx(l, 'cor', C2.acc); }
  else if (s === 'contorno') { addVec(l, paths, { stroke: E.cor || C2.ink, sw: E.largura || 2, dash: E.tracejado }); }
  else addVec(l, paths, { fill: E.cor || C2.paper });
  if (E.borda) addVec(l, paths, { stroke: E.borda[0], sw: E.borda[2] || 2, op: E.borda[1] });
  if (E.brilho) glowFx(l, 'cor', typeof E.brilho === 'string' ? E.brilho : (E.cor || C2.accL));
}
function buildEl(comp, E, ctx) {
  var T = E.tipo, nm = E.id || T, H, l, i, j, out = { ls: [] }, b = E.box;
  if (T === 'caixa') {
    var cx = b[0] + b[2] / 2, cy = b[1] + b[3] / 2, left = E.ancoraEsq;
    H = elHandle(comp, nm, left ? b[0] : cx, cy);
    if (E.pluma || E.forma === 'elipse') {                         // soft zone: a solid with a feathered mask (fog, light trail)
      l = comp.layers.addSolid(hex(E.cor || D.cols.paper), nm, Math.round(b[2] + 2 * (E.pluma || 0)), Math.round(b[3] + 2 * (E.pluma || 0)), 1);
      var mk = l.property('ADBE Mask Parade').addProperty('ADBE Mask Atom'), pw = E.pluma || 0, ms = new Shape();
      var P0 = E.forma === 'elipse' ? elPaths(pw + b[2] / 2, pw + b[3] / 2, b[2] / 2, b[3] / 2)[0] : rrPaths(pw, pw, b[2], b[3], 0)[0];
      ms.vertices = P0.v; ms.inTangents = P0.i; ms.outTangents = P0.o; ms.closed = true; mk.property('ADBE Mask Shape').setValue(ms);
      mk.property('ADBE Mask Feather').setValue([pw, pw]);
    } else {
      l = shapeLayer(comp, nm); styleBox(l, E, rrPaths(left ? 0 : -b[2] / 2, -b[3] / 2, b[2], b[3], E.raio || 0));
    }
    child(H, l, left ? b[0] : cx, cy);
    if (E.sombra) dropFx(l, 45, 18, 50, D.cols.paper);
  } else if (T === 'circulo') {
    H = elHandle(comp, nm, E.c[0], E.c[1]); l = shapeLayer(comp, nm); styleBox(l, E, elPaths(0, 0, E.r, E.r)); child(H, l, E.c[0], E.c[1]);
  } else if (T === 'linha') {
    var bx = E.bbox; H = elHandle(comp, nm, (bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2);
    l = shapeLayer(comp, nm); addVec(l, E.paths, { stroke: E.cor, sw: E.largura || 3, dash: E.tracejado, fill: E.fill || null });
    var tm = addTrim(l); out.trim = tm;
    if (E.trim !== undefined && !MOTION) tm.property('ADBE Vector Trim End').setValue(E.trim);
    child(H, l, 0, 0); TG(l).property('ADBE Anchor Point').setValue(is3D() ? [H.ax, H.ay, 0] : [H.ax, H.ay]); TG(l).property('ADBE Position').setValue(is3D() ? [0, 0, 0] : [0, 0]);
    if (E.brilho) glowFx(l, 'cor', typeof E.brilho === 'string' ? E.brilho : E.cor);
    if (E.sombra) dropFx(l, 55, 6, 12, D.cols.paper);
  } else if (T === 'icone') {
    var vb = E.vb, sx = b[2] / vb[2], sy = E.estica ? b[3] / vb[3] : sx, ox = E.estica ? 0 : 0, oy = E.estica ? 0 : (b[3] - vb[3] * sx) / 2;
    var pad = Math.round(30 + 0.18 * Math.max(b[2], b[3])), W = b[2] + 2 * pad, Hh = b[3] + 2 * pad;
    var ic = subComp('ICO · ' + nm, W, Hh, ctx.dur, ctx.folders.elements);
    var sl = shapeLayer(ic, 'traço (' + (E.from || nm) + ')'), swk = (sx + sy) / 2;
    for (i = 0; i < E.els.length; i++) {
      var e = E.els[i], P = tr(e.paths, sx, sy, pad + ox - vb[0] * sx, pad + oy - vb[1] * sy), colr = E.cor === 'grad' ? D.cols.ink : (E.cor || D.cols.ink);
      if (e.paint === 'stroke') addVec(sl, P, { stroke: e.stroke || colr, sw: (e.sw || E.traco || 4) * swk, gop: e.op, fill: e.fill || null, fop: e.fop });
      else addVec(sl, P, { fill: e.fill || colr, fop: e.fop, gop: e.op, stroke: e.stroke || null, sw: (e.sw || 0) * swk });
    }
    if (E.cor === 'grad') rampFx(sl, W / 2, pad, pad + b[3], D.cols.ink, D.cols.acc);
    if (E.brilho) glowFx(sl, 'forte', typeof E.brilho === 'string' ? E.brilho : null);
    var tri = null; if (E.entra && E.entra.como === 'desenha') tri = addTrim(sl);
    var ax0 = E.ancora ? pad + E.ancora[0] * sx : W / 2, ay0 = E.ancora ? pad + oy + E.ancora[1] * sy : Hh / 2;
    var wx = b[0] - pad + ax0, wy = b[1] - pad + ay0;
    H = elHandle(comp, nm, wx, wy); l = comp.layers.add(ic); l.name = 'ícone · ' + nm;
    TG(l).property('ADBE Anchor Point').setValue([ax0, ay0]); child(H, l, wx, wy);
    if (E.rot) TG(l).property('ADBE Rotate Z').setValue(E.rot);
    if (tri && MOTION) kz(tri.property('ADBE Vector Trim End'), E.entra.t, E.entra.t + (E.entra.dur || 0.6), 0, 100, 'io');
    if (E.pulsa && MOTION) { var tp = E.entra ? E.entra.t + 0.5 : 0; TG(l).property('ADBE Position').expression = 'var k = Math.max(0, time - ' + tp + ');\nvalue + [0, ' + E.pulsa[1] + ' * Math.abs(Math.sin(k * 4.2))' + (is3D() ? ', 0' : '') + '];'; }
  } else if (T === 'media') {
    var it = imp(E.src, ctx.folders.footage);
    H = elHandle(comp, nm, b[0] + b[2] / 2, b[1] + b[3] / 2);
    if (it) {
      l = comp.layers.add(it); l.name = nm; mute(l);
      var sc = Math.max(b[2] / it.width, b[3] / it.height) * 100, dy = E.dy;
      if (dy !== undefined && dy !== null) sc = b[2] / it.width * 100;            // fixed-width crop (CSS width + margin-top)
      var vw = it.width * sc / 100, vh = it.height * sc / 100, offy = (dy !== undefined && dy !== null) ? dy : (b[3] - vh) / 2, offx = (b[2] - vw) / 2;
      // mask in layer px: the visible box
      var mx = (0 - offx) / (sc / 100), my = (0 - offy) / (sc / 100);
      roundMask(l, mx, my, b[2] / (sc / 100), b[3] / (sc / 100), (E.raio || 0) / (sc / 100));
      TG(l).property('ADBE Anchor Point').setValue([mx + b[2] / (sc / 100) / 2, my + b[3] / (sc / 100) / 2]);
      TG(l).property('ADBE Scale').setValue(is3D() ? [sc, sc, sc] : [sc, sc]);
      child(H, l, b[0] + b[2] / 2, b[1] + b[3] / 2);
      if (it.duration > 0 && it.frameDuration && it.duration < 60) { l.startTime = 0; if (it.duration < ctx.dur) loopFootage(l, it, comp); l.outPoint = comp.duration; }
      if (E.brilho) glowFx(l, 'suave', typeof E.brilho === 'string' ? E.brilho : null);
    } else { l = shapeLayer(comp, nm + ' (FALTA: ' + E.src + ')'); addVec(l, rrPaths(-b[2] / 2, -b[3] / 2, b[2], b[3], E.raio || 0), { stroke: D.cols.accL, sw: 3, dash: [10, 8] }); child(H, l, b[0] + b[2] / 2, b[1] + b[3] / 2); }
  } else if (T === 'texto') {
    return buildText(comp, E, ctx);
  } else if (T === 'grupo') {
    var gc = subComp('GRUPO · ' + nm, b[2], b[3], ctx.dur, ctx.folders.elements);
    FLAT++;
    var bgE = { estilo: E.estilo, cor: E.cor, borda: E.borda, raio: E.raio };
    if (E.estilo) { var bl = shapeLayer(gc, 'fundo'); styleBox(bl, bgE, rrPaths(0, 0, b[2], b[3], E.raio || 0)); }
    var kids = [];
    for (i = 0; i < E.els.length; i++) { try { kids.push(buildEl(gc, E.els[i], ctx)); } catch (xk) { log('  ! ' + nm + ' / ' + (E.els[i].id || E.els[i].tipo) + ': ' + xk.toString() + ' line ' + xk.line); } }
    stack(kids);
    for (i = 0; i < kids.length; i++) finishEl(kids[i], ctx, true);
    FLAT--;
    H = elHandle(comp, nm, b[0] + b[2] / 2, b[1] + b[3] / 2); l = comp.layers.add(gc); l.name = 'grupo · ' + nm;
    roundMask(l, 0, 0, b[2], b[3], E.raio || 0);
    child(H, l, b[0] + b[2] / 2, b[1] + b[3] / 2);
    if (E.rot) TG(l).property('ADBE Rotate Z').setValue(E.rot);
    if (E.brilho) glowFx(l, 'cor', E.brilho);
    dropFx(l, 50, 30, 80, D.cols.paper);
  } else if (T === 'moeda') {
    var r = E.r, pd = 70, cw = 2 * (r + pd), cc = subComp('MOEDA · face', cw, cw, ctx.dur, ctx.folders.elements);
    var disc = shapeLayer(cc, 'face'); addVec(disc, elPaths(cw / 2, cw / 2, r, r), { fill: D.cols.ink });
    rampFx(disc, cw / 2 - r * 0.3, cw / 2 - r * 0.4, r * 1.55, D.cols.accL, D.cols.accD, true);
    glowFx(disc, 'cor', D.cols.acc);
    var rim = shapeLayer(cc, 'serrilhado'); addVec(rim, elPaths(cw / 2, cw / 2, r - 16 - 2.5, r - 16 - 2.5), { stroke: D.cols.ink, sw: 5, op: 55, dash: [0.1, 13] });
    var rng = shapeLayer(cc, 'anel'); addVec(rng, elPaths(cw / 2, cw / 2, r - 44 - 2, r - 44 - 2), { stroke: D.cols.ink, sw: 4, op: 85 });
    var eu = textLayer(cc, '€', F.key, 170, hex(D.cols.ink), 0), em = met(eu);
    TG(eu).property('ADBE Anchor Point').setValue([em.left + em.w / 2, -em.above / 2]); TG(eu).property('ADBE Position').setValue([cw / 2, cw / 2 + 4]);
    dropFx(eu, 80, 4, 0, D.cols.accD);
    H = elHandle(comp, nm, E.c[0], E.c[1]);
    var face = comp.layers.add(cc); face.name = 'moeda · face'; child(H, face, E.c[0], E.c[1]);
    out.coin = { face: face, edges: [] };
    if (is3D()) {                                                   // real thickness: stacked edge discs behind the face
      var nE = 9, esp = E.espessura || 24;
      for (j = 1; j <= nE; j++) { var ed = shapeLayer(comp, 'moeda · espessura ' + j); addVec(ed, elPaths(0, 0, r, r), { fill: D.cols.accD }); child(H, ed, E.c[0], E.c[1]); TG(ed).property('ADBE Position').setValue([0, 0, esp * j / nE]); out.coin.edges.push(ed); out.ls.push(ed); }
      face.moveToBeginning();
      H.spin = true;
    }
  } else if (T === 'segmentos') {
    var n = E.n, gw = E.gap || 12, sw2 = (b[2] - gw * (n - 1)) / n;
    H = elHandle(comp, nm, b[0] + b[2] / 2, b[1] + b[3] / 2); out.segs = []; out.lit = [];
    for (i = 0; i < n; i++) {
      var sx0 = b[0] + i * (sw2 + gw) + sw2 / 2, sg = shapeLayer(comp, nm + ' · ' + (i + 1));
      addVec(sg, rrPaths(-sw2 / 2, -b[3] / 2, sw2, b[3], E.raio || 8), { fill: D.cols.paper, fop: 50, stroke: D.cols.ink, sw: 2, op: 25 });
      child(H, sg, sx0, b[1] + b[3] / 2); out.segs.push(sg); out.ls.push(sg);
      if (i < (E.acesos || 0)) { var lt = shapeLayer(comp, nm + ' · ' + (i + 1) + ' aceso'); addVec(lt, rrPaths(-sw2 / 2, -b[3] / 2, sw2, b[3], E.raio || 8), { fill: D.cols.acc }); glowFx(lt, 'cor', D.cols.acc); child(H, lt, sx0, b[1] + b[3] / 2); out.lit.push(lt); out.ls.push(lt); }
    }
    placeEl(H, E.z || 0); out.h = H; out.E = E; return out;
  }
  if (l) { if (E.op !== undefined && E.op !== null && T !== 'linha') TG(l).property('ADBE Opacity').setValue(E.op); else if (T === 'linha' && E.op !== undefined) TG(l).property('ADBE Opacity').setValue(E.op); out.ls.unshift(l); }
  placeEl(H, E.z !== undefined ? E.z : ctx.zOf(T));
  out.h = H; out.E = E; out.l = l; return out;
}
function buildText(comp, E, ctx) {
  var parts = E.partes, i, items = [], x = 0, nm = E.id || parts[0].t;
  for (i = 0; i < parts.length; i++) {
    var p = parts[i], font = p.f === 'ser' ? F.ser : F.key, tl = textLayer(comp, p.t, font, p.size, hex(isGrad(p.cor) ? D.cols.ink : p.cor), p.track !== undefined ? p.track : (p.f === 'ser' ? TRK.ser : TRK.key));
    var m = met(tl); x += (i ? (p.gap || 0) : 0); items.push({ l: tl, x: x, w: m.w, m: m, p: p }); x += m.w;
  }
  var total = x, x0 = E.alinha === 'centro' ? E.x - total / 2 : E.x, base = E.base, H = elHandle(comp, nm, E.x, base), out = { ls: [], texts: [] };
  for (i = 0; i < items.length; i++) {
    var it = items[i], px = x0 + it.x, L = it.l;
    if (isGrad(it.p.cor)) {                                     // gradient type: its own comp, ramp points exact (comp px)
      var tp = Math.round(40 + it.p.size * 0.5), tw = it.m.w + 2 * tp, th = it.m.above + it.m.below + 2 * tp, bx0 = tp, by0 = tp + it.m.above;
      var tc = subComp('TXT · ' + it.p.t, tw, th, ctx.dur, ctx.folders.elements);
      L.copyToComp(tc); L.remove(); L = tc.layer(1);
      TG(L).property('ADBE Anchor Point').setValue([it.m.left, 0]); TG(L).property('ADBE Position').setValue([bx0, by0]);
      var rc = L.sourceRectAtTime(0, false);
      rampFx(L, bx0 + rc.left - it.m.left + rc.width / 2, by0 + rc.top, by0 + rc.top + rc.height, D.cols.accL, D.cols.accD);
      glowFx(L, 'forte', null);
      var pl = comp.layers.add(tc); pl.name = 'texto azul · ' + it.p.t;
      TG(pl).property('ADBE Anchor Point').setValue([bx0, by0]); child(H, pl, px, base);
      FLAT++; textEnter(L, it.p.entra || E.entra, 'ser', it.p.size); FLAT--;
      out.ls.push(pl); out.texts.push({ l: L, outer: pl, t: (it.p.entra || E.entra || {}).t });
    } else {
      L.name = (it.p.f === 'ser' ? 'serifa · ' : 'texto · ') + it.p.t;
      TG(L).property('ADBE Anchor Point').setValue([it.m.left, 0]); child(H, L, px, base);
      if (it.p.op !== undefined) TG(L).property('ADBE Opacity').setValue(it.p.op);
      if (E.brilho && E.brilho !== 'nenhum') glowFx(L, E.brilho === 'forte' ? 'forte' : 'suave', null);
      if (E.sombra) dropFx(L, 45, 3, 22, D.cols.paper);
      textEnter(L, it.p.entra || E.entra, it.p.f, it.p.size);
      out.ls.push(L); out.texts.push({ l: L, outer: L, t: (it.p.entra || E.entra || {}).t });
    }
  }
  if (E.pilula) {                                                   // pill behind the measured row (partner path chip)
    var pp = E.pilula, pb = shapeLayer(comp, 'pílula · ' + nm), pw = total + pp.esq + pp.dir;
    addVec(pb, rrPaths(x0 - pp.esq - E.x, pp.y - base, pw, pp.h, pp.raio || pp.h / 2), { fill: pp.cor });
    child(H, pb, E.x, base); out.pill = pb; enterLayer(pb, E.entra, 'pill');
  }
  if (E.cursor) {
    var last = items[items.length - 1], ch = last.p.size * 0.84, cu = shapeLayer(comp, 'cursor do prompt');
    addVec(cu, rrPaths(0, -ch, 6, ch, 0), { fill: D.cols.accL }); glowFx(cu, 'cor', D.cols.accL);
    child(H, cu, x0 + total + 6, base);
    if (MOTION) TG(cu).property('ADBE Opacity').expression = 'Math.floor(time * 2.4) % 2 == 0 ? 100 : 0;';
    out.ls.push(cu);
  }
  if (out.pill) out.ls.push(out.pill);                              // the pill sits behind the words
  placeEl(H, E.z !== undefined ? E.z : 0);
  out.h = H; out.E = E; out.isText = true; return out;
}
// entrances + actions of a built element
function finishEl(o, ctx, inGroup) {
  var E = o.E, i;
  if (!MOTION) return;
  if (!o.isText && E.entra) {
    if (o.segs) { for (i = 0; i < o.segs.length; i++) enterLayer(o.segs[i], { t: E.entra.t + i * 0.035, como: 'pop', dur: 0.35 }); }
    else for (i = 0; i < o.ls.length; i++) {
      if (o.trim && (E.entra.como === 'desenha' || E.entra.como === 'desenha-centro')) {
        var d = E.entra.dur || 0.6, te = o.trim.property('ADBE Vector Trim End');
        if (E.entra.como === 'desenha-centro') { kz(o.trim.property('ADBE Vector Trim Start'), E.entra.t, E.entra.t + d, 50, 0, 'out'); kz(te, E.entra.t, E.entra.t + d, 50, 100, 'out'); }
        else kz(te, E.entra.t, E.entra.t + d, 0, 100, 'io');
        kz(TG(o.ls[i]).property('ADBE Opacity'), E.entra.t, E.entra.t + 0.08, 0, TG(o.ls[i]).property('ADBE Opacity').value, 'lin');
      } else enterLayer(o.ls[i], E.entra);
    }
  }
  if (o.lit && E.acende) for (i = 0; i < o.lit.length; i++) { var op = TG(o.lit[i]).property('ADBE Opacity'); kz(op, E.acende.t - 0.05, E.acende.t + 0.25, 0, 100, 'io'); }
  if (o.h.spin && o.coin) { TG(o.h.h).property('ADBE Rotate Y').expression = '// slow turn: the coin shows its thickness\nMath.sin(time * 0.9 + 0.6) * 24;'; }
  var A = E.anim || [];
  for (i = 0; i < A.length; i++) {
    var a = A[i], targets = o.ls, q;
    try {
      if (a.prop === 'trim' && o.trim) { kz(o.trim.property('ADBE Vector Trim End'), a.t0, a.t1, a.v[0], a.v[1], a.ease); continue; }
      for (q = 0; q < targets.length; q++) {
        var tg = TG(targets[q]);
        if (a.prop === 'opac') kz(tg.property('ADBE Opacity'), a.t0, a.t1, a.v[0], a.v[1], a.ease || 'io');
        else if (a.prop === 'escala' || a.prop === 'escalaX') {
          var sp = tg.property('ADBE Scale'), s0 = sp.numKeys ? sp.keyValue(sp.numKeys) : sp.value, f0 = a.v[0] / 100, f1 = a.v[1] / 100;
          var A0 = a.prop === 'escalaX' ? [s0[0] * f0, s0[1]] : [s0[0] * f0, s0[1] * f0], A1 = a.prop === 'escalaX' ? [s0[0] * f1, s0[1]] : [s0[0] * f1, s0[1] * f1];
          if (s0.length === 3) { A0.push(s0[2]); A1.push(s0[2]); }
          kz(tg.property('ADBE Scale'), a.t0, a.t1, A0, A1, a.ease);
        } else if (a.prop === 'pos') {
          var pp = tg.property('ADBE Position'), p1 = pp.numKeys ? pp.keyValue(pp.numKeys) : pp.value, P0 = [p1[0] + a.v[0][0], p1[1] + a.v[0][1]], P1 = [p1[0] + a.v[1][0], p1[1] + a.v[1][1]];
          if (p1.length === 3) { P0.push(p1[2]); P1.push(p1[2]); }
          if (tg.property('ADBE Position').numKeys > 0) { tg.property('ADBE Position').setValueAtTime(a.t0, P0); tg.property('ADBE Position').setValueAtTime(a.t1, P1); }
          else kz(tg.property('ADBE Position'), a.t0, a.t1, P0, P1, a.ease);
        } else if (a.prop === 'rot') kz(tg.property('ADBE Rotate Z'), a.t0, a.t1, tg.property('ADBE Rotate Z').value + a.v[0], tg.property('ADBE Rotate Z').value + a.v[1], a.ease || 'io');
        else if (a.prop === 'rotX' && is3D() && !inGroup) kz(tg.property('ADBE Rotate X'), a.t0, a.t1, a.v[0], a.v[1], a.ease);
        else if (a.prop === 'rotY' && is3D() && !inGroup) kz(tg.property('ADBE Rotate Y'), a.t0, a.t1, a.v[0], a.v[1], a.ease);
      }
    } catch (xa) { log('  ! anim ' + (E.id || E.tipo) + ' ' + a.prop + ': ' + xa.toString()); }
  }
}
// ---- backgrounds
function gridLayer(comp, name, color, op, w, step, span) {        // shape grid: one line + repeater each way (exact colour, no effect quirks)
  var l = shapeLayer(comp, name), n = Math.ceil(span / step);
  var mk = function (pts, ax) {
    var g = addVec(l, [{ v: pts, i: [[0, 0], [0, 0]], o: [[0, 0], [0, 0]], c: false }], { stroke: color, sw: w });
    var gi = RV(l).numProperties, G = RV(l).property(gi).property('ADBE Vectors Group');
    G.addProperty('ADBE Vector Filter - Repeater'); var rp = RV(l).property(gi).property('ADBE Vectors Group').property('ADBE Vector Filter - Repeater');
    rp.property('ADBE Vector Repeater Copies').setValue(2 * n + 1);
    rp.property('ADBE Vector Repeater Transform').property('ADBE Vector Repeater Position').setValue(ax === 'x' ? [step, 0] : [0, step]);
  };
  mk([[-n * step, -span], [-n * step, span]], 'x'); mk([[-span, -n * step], [span, -n * step]], 'y');
  TG(l).property('ADBE Opacity').setValue(op);
  return l;
}
function featherMask(l, P, feather, inv, mode) {
  var m = l.property('ADBE Mask Parade').addProperty('ADBE Mask Atom'), s = new Shape(); s.vertices = P.v; s.inTangents = P.i; s.outTangents = P.o; s.closed = true;
  m.property('ADBE Mask Shape').setValue(s); m.property('ADBE Mask Feather').setValue([feather, feather]); if (inv) m.inverted = true; if (mode) m.maskMode = mode; return m;
}
function buildWorld(comp, S, dur) {
  var far = is3D() ? 1400 : 0, g = (Z0 + far) / Z0, cover = is3D() ? 2.6 : 1, bgs = [];
  var bg = solid(comp, hex(D.cols.paper), 'fundo (papel)'); bgs.push(bg);
  var gl = solid(comp, hex(D.cols.glow), 'brilho dos cantos'); featherMask(gl, elPaths(CW, 0, 900, 620)[0], 520); featherMask(gl, elPaths(0, CH, 900, 620)[0], 520, false, MaskMode.ADD); TG(gl).property('ADBE Opacity').setValue(85); bgs.push(gl);
  if (S.grelha) { var gr = gridLayer(comp, 'grelha', D.cols.grid, 100 * S.grelha, 2, 180, 4000); TG(gr).property('ADBE Position').setValue([CX + 60, CY + 90]); bgs.push(gr); }
  for (var i = bgs.length - 1; i >= 0; i--) {
    if (is3D() && i >= 2) { m3(bgs[i]); var p = TG(bgs[i]).property('ADBE Position').value; TG(bgs[i]).property('ADBE Position').setValue([CX + (p[0] - CX) * g, CY + (p[1] - CY) * g, far]); TG(bgs[i]).property('ADBE Scale').setValue([g * 100 * (i < 2 ? cover : 1), g * 100 * (i < 2 ? cover : 1), 100]); }
    bgs[i].moveToEnd();
  }
  if (S.chao) {                                                   // grid floor in real perspective (static camera in the layout file)
    var fl = gridLayer(comp, 'chão de grelha', S.chao.cor || D.cols.line2, S.chao.op || 100, 3, 180, 7000);
    fl.threeDLayer = true; TG(fl).property('ADBE Rotate X').setValue(90); TG(fl).property('ADBE Position').setValue([CX, S.chao.y || 1250, 2600]);
    featherMask(fl, rrPaths(-7000, -4200, 14000, 6800, 0)[0], 2600);
    fl.moveBefore(bgs[1]);
    if (!MOTION) { var cam0 = comp.layers.addCamera('CÂMERA (fixa, só para o chão)', [CX, CY]); try { cam0.property('ADBE Camera Options Group').property('ADBE Camera Zoom').setValue(Z0); } catch (x) {} }
  }
  return bgs;
}
function buildShades(comp, S, dur) {
  var out = [], k, n = S.sombras || [];
  for (k = 0; k < n.length; k++) {
    var s = n[k], l;
    if (s === 'edgegrid') { l = gridLayer(comp, 'grelha nas bordas', D.cols.accL, 10, 1, 180, 2400); TG(l).property('ADBE Position').setValue([CX + 60, CY + 90]); featherMask(l, elPaths(CX - 60, CY * 0.8 - 90, CW * 0.31, CH * 0.35)[0], 260, true); }
    else {
      l = solid(comp, hex(D.cols.paper), 'sombra · ' + s);
      if (s === 'vig') { featherMask(l, elPaths(CX, CH * 0.4, CW * 0.36, CH * 0.42)[0], 420, true); TG(l).property('ADBE Opacity').setValue(70); }
      if (s === 'low') { featherMask(l, rrPaths(-200, CH - 330, CW + 400, 700, 0)[0], 300); TG(l).property('ADBE Opacity').setValue(85); }
      if (s === 'lado-esq') { featherMask(l, rrPaths(-700, -200, 1250, CH + 400, 0)[0], 520); TG(l).property('ADBE Opacity').setValue(72); }
      if (s === 'lado-dir') { featherMask(l, rrPaths(CW - 550, -200, 1250, CH + 400, 0)[0], 520); TG(l).property('ADBE Opacity').setValue(72); }
    }
    l.moveToEnd(); out.push(l);
    if (MOTION) { var op = TG(l).property('ADBE Opacity'), v = op.value; keys(op, [0, 0.25, dur - 0.22, dur], [0, v, v, 0], 'io'); }
  }
  return out;
}
// ---- cameras (motion)
function camViagem(comp, sc, dur, spec) {
  var cam = comp.layers.addCamera('CÂMERA 3D', [CX, CY]);
  try { cam.property('ADBE Camera Options Group').property('ADBE Camera Zoom').setValue(Z0); } catch (x) {}
  cam.autoOrient = AutoOrientType.NO_AUTO_ORIENT; TG(cam).property('ADBE Position').setValue([CX, CY, -Z0]);
  var rig = handle(comp, 'RIG · rota da câmera (mover a câmera aqui)'); cam.parent = rig;
  TG(cam).property('ADBE Position').expression = '// constant drift: the camera never stops\nvalue + [9*Math.sin(time*0.9), 7*Math.sin(time*0.7+1), 0];';
  var S = spec.paragens, K = [], i, tv = RIT.viagem_s || 0.45, mid = spec.meio || 0, f = spec.forca || 1;
  var at = function (s) { return [(s.x - CX) * f, (s.y - CY) * f, (s.z || 0) * f]; };
  K.push([Math.max(0, S[0].t), at(S[0]), 'start']);
  for (i = 1; i < S.length; i++) {
    var ta = Math.max(K[K.length - 1][0] + 0.12, S[i].t), tl = Math.max(K[K.length - 1][0] + 0.08, ta - tv), pa = at(S[i - 1]), pb = at(S[i]);
    var hold = [pa[0], pa[1], pa[2] + 30 * f];
    if (tl > K[K.length - 1][0] + 0.05) K.push([tl, hold, 'leave']);
    if (mid) K.push([(tl + ta) / 2, [(pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2, (pa[2] + pb[2]) / 2 + mid * Z0 * f], 'mid']);
    K.push([ta, pb, 'arrive']);
  }
  var last = K[K.length - 1][1], fin = sc.close ? Math.min(RIT.fim_s || 0.8, dur * 0.4) : 0.35;
  if (dur - fin > K[K.length - 1][0] + 0.1) K.push([dur - fin, [last[0], last[1], last[2] + 50 * f], 'leave']);
  K.push([dur, [last[0], last[1], sc.close ? last[2] - 0.16 * Z0 : last[2] + 240 * f], sc.close ? 'end' : 'push']);
  var rp = TG(rig).property('ADBE Position');
  for (i = 0; i < K.length; i++) rp.setValueAtTime(K[i][0], K[i][1]);
  linearPath(rp);
  for (i = 1; i <= rp.numKeys; i++) {
    var kd = K[i - 1][2];
    try {
      if (kd === 'mid') { rp.setTemporalContinuousAtKey(i, true); rp.setTemporalAutoBezierAtKey(i, true); continue; }
      var vin = i > 1 ? dist(K[i - 1][1], K[i - 2][1]) / Math.max(0.05, K[i - 1][0] - K[i - 2][0]) : 0;
      var vout = i < K.length ? dist(K[i][1], K[i - 1][1]) / Math.max(0.05, K[i][0] - K[i - 1][0]) : 0;
      if (kd === 'arrive') setEase(rp, i, [0, 85], [vout, 30]);            // decelerates INTO the stop, on the word
      else if (kd === 'leave' || kd === 'start') setEase(rp, i, [vin, 30], [0, 40]);
      else if (kd === 'end') setEase(rp, i, [0, 85], [0, 20]);              // gentle pull-out, no whip
      else if (kd === 'push') setEase(rp, i, [vin * 2, 22], [0, 20]);
    } catch (xe) { log('  ! rig ease: ' + xe.toString()); }
  }
  return cam;
}
function stack(built) {                                          // list order = stacking order: first element at the back
  for (var i = 0; i < built.length; i++) { var o = built[i]; for (var q = o.ls.length - 1; q >= 0; q--) o.ls[q].moveToBeginning(); o.h.h.moveToBeginning(); }
}
function buildComposto(comp, sc, dur, folders) {
  ZSTEP = 0;
  var S = sc.comp, i, built = [], ctx = { dur: dur, folders: folders, zOf: function (T) { return 0; } };
  var bgs = S.fundo === 'mundo' ? buildWorld(comp, S, dur) : buildShades(comp, S, dur);
  for (i = 0; i < S.els.length; i++) {
    try { built.push(buildEl(comp, S.els[i], ctx)); }
    catch (xe) { log('  ! element ' + (S.els[i].id || S.els[i].tipo) + ': ' + xe.toString() + ' line ' + xe.line); }
  }
  stack(built);
  // markers: when each element / line enters (the editor times by hand on them)
  for (i = 0; i < built.length; i++) { var en = built[i].E.entra || (built[i].E.partes && built[i].E.partes[0].entra); if (en && en.t !== undefined) { try { comp.markerProperty.setValueAtTime(Math.min(dur - 0.05, Math.max(0, en.t)), new MarkerValue('entra: ' + (built[i].E.id || built[i].E.tipo))); } catch (xm) {} } }
  if (!MOTION) return;
  for (i = 0; i < built.length; i++) { try { finishEl(built[i], ctx, false); } catch (xf) { log('  ! anim ' + (built[i].E.id || built[i].E.tipo) + ': ' + xf.toString() + ' line ' + xf.line); } }
  // exit: over the face the overlay fades in the last 0.2 s; in the world the camera pushes through (the next scene cuts in)
  if (S.fundo === 'cara' && !sc.close) for (i = 0; i < built.length; i++) for (var k = 0; k < built[i].ls.length; k++) fadeOut(built[i].ls[k], dur, 0.2);
  if (S.fecho) { var fe = solid(comp, hex(S.fecho.cor || D.cols.paper), 'fecho (corta para o separador seguinte)'); fe.moveToBeginning(); keys(TG(fe).property('ADBE Opacity'), [dur - (S.fecho.dur || 0.28) - TAIL, dur - TAIL], [0, 100], 'in'); }
  // camera
  var cs = S.camera || { tipo: 'deriva' };
  if (cs.tipo === 'viagem') camViagem(comp, sc, dur, cs);
  else {
    var f = cs.forca || 1, sg = cs.lado || ((sc.id % 2) ? -1 : 1);
    sc.cam = { S: [sg * 360 * f, -80 * f, -520 * f], A: [sg * 40 * f, -8 * f, -30 * f], B: [-sg * 50 * f, 8 * f, 110 * f], push: 240 * f };
    var first = 99; for (i = 0; i < built.length; i++) { var e0 = built[i].E.entra || (built[i].E.partes && built[i].E.partes[0].entra); if (e0 && e0.t !== undefined) first = Math.min(first, e0.t); }
    sc.t1 = Math.max(RIT.viagem_s || 0.45, Math.min(first + 0.45, dur * 0.4));
    if (sc.open && cs.foco) sc.focus = cs.foco;
    var ext = []; for (i = 0; i < S.els.length; i++) if (S.els[i].bbox) ext.push(S.els[i].bbox);
    addCamera(comp, sc, dur, ext);
  }
}
