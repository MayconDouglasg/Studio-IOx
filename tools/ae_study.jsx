// Read-only study of a FINISHED After Effects project (what the editor really did).
// Filled by tools/study_final.py: __AEP__ (project to open), __OUT__ (folder for study.txt).
// Never saves. Writes: items, footage paths, every comp, every layer, keyed / expression properties,
// effects, text (content, font, size, animators), markers. Ends with study_done.txt.
(function () {
var AEP = '__AEP__', OUT = '__OUT__';
var L = [];
function w(s) { L.push(s); }
function r2(v) { return Math.round(v * 100) / 100; }
function val(v) {
  if (v === null || v === undefined) return '-';
  if (v instanceof Array) { var o = []; for (var i = 0; i < v.length && i < 4; i++) o.push(r2(v[i])); return '[' + o.join(',') + ']'; }
  if (typeof v === 'number') return String(r2(v));
  if (typeof v === 'boolean') return String(v);
  try { if (v.text !== undefined) return 'txt'; } catch (e) {}
  try { if (v.vertices) return 'shape(' + v.vertices.length + 'pts)'; } catch (e2) {}
  return typeof v;
}
function clean(s, n) { s = String(s).replace(/[\r\n]+/g, ' / '); return s.length > n ? s.substr(0, n) + '…' : s; }
function ease(p, k) {
  var t = '';
  try {
    var it = p.keyInInterpolationType(k), ot = p.keyOutInterpolationType(k);
    t = (it === KeyframeInterpolationType.HOLD || ot === KeyframeInterpolationType.HOLD) ? 'H' : (it === KeyframeInterpolationType.LINEAR && ot === KeyframeInterpolationType.LINEAR) ? 'L' : 'B';
    if (t === 'B') { var ei = p.keyInTemporalEase(k)[0], eo = p.keyOutTemporalEase(k)[0]; t += Math.round(ei.influence) + '/' + Math.round(eo.influence); }
  } catch (e) {}
  return t;
}
function path(p) { var a = []; var q = p; while (q && q.parentProperty) { a.unshift(q.name); q = q.parentProperty; } return a.join('>'); }
function walk(g, layer, depth) {
  if (depth > 12) return;
  for (var i = 1; i <= g.numProperties; i++) {
    var p = g.property(i);
    if (!p) continue;
    if (p.propertyType === PropertyType.PROPERTY) {
      var keyed = false, expr = false;
      try { keyed = p.numKeys > 0; } catch (e) {}
      try { expr = p.canSetExpression && p.expressionEnabled && p.expression !== ''; } catch (e2) {}
      if (keyed) {
        var ks = [];
        for (var k = 1; k <= p.numKeys && k <= 8; k++) ks.push(r2(p.keyTime(k) - layer.inPoint + 0) + 's=' + val(p.keyValue(k)) + ':' + ease(p, k));
        w('      KEY ' + path(p) + ' n=' + p.numKeys + '  ' + ks.join('  ') + (p.numKeys > 8 ? ' …' : ''));
      }
      if (expr) w('      EXPR ' + path(p) + ' = ' + clean(p.expression, 220));
    } else {
      try { walk(p, layer, depth + 1); } catch (e3) {}
    }
  }
}
function kind(l) {
  if (l instanceof CameraLayer) return 'CAMERA';
  if (l instanceof LightLayer) return 'LIGHT';
  if (l instanceof TextLayer) return 'TEXT';
  if (l instanceof ShapeLayer) return 'SHAPE';
  if (l.nullLayer) return 'NULL';
  if (l.adjustmentLayer) return 'ADJ';
  try { if (l.source instanceof CompItem) return 'PRECOMP'; if (l.source.mainSource instanceof SolidSource) return 'SOLID'; if (l.source.mainSource instanceof FileSource) return 'FILE'; } catch (e) {}
  return 'AV';
}
try {
  if (AEP) {
    if (app.project && app.project.dirty) { w('NOTE: the open project had unsaved changes; it was left open in its own window state'); }
    app.open(new File(AEP));
  }
  var P = app.project;
  w('AE ' + app.version + '  project: ' + (P.file ? P.file.fsName : '(untitled)') + '  items=' + P.numItems + '  bpc=' + P.bitsPerChannel);
  var n, it, usage = {};
  // footage
  for (n = 1; n <= P.numItems; n++) {
    it = P.item(n);
    var pf = it.parentFolder ? it.parentFolder.name : '';
    if (it instanceof FootageItem) {
      var f = '';
      try { if (it.file) f = it.file.fsName; else if (it.mainSource instanceof SolidSource) f = 'solid ' + val(it.mainSource.color); } catch (e) {}
      w('FOOTAGE "' + it.name + '" [' + pf + '] ' + it.width + 'x' + it.height + ' dur=' + r2(it.duration) + (it.footageMissing ? ' MISSING' : '') + ' used=' + it.usedIn.length + ' ' + f);
    } else if (it instanceof FolderItem) {
      w('FOLDER "' + it.name + '" [' + pf + '] items=' + it.numItems);
    }
  }
  // comps
  for (n = 1; n <= P.numItems; n++) {
    it = P.item(n);
    if (!(it instanceof CompItem)) continue;
    var c = it;
    var u = []; for (var q = 0; q < c.usedIn.length; q++) u.push(c.usedIn[q].name);
    w('');
    w('COMP "' + c.name + '" [' + (c.parentFolder ? c.parentFolder.name : '') + '] ' + c.width + 'x' + c.height + ' dur=' + r2(c.duration) + ' fps=' + r2(c.frameRate) + ' layers=' + c.numLayers + ' renderer=' + c.renderer + ' mblur=' + c.motionBlur + ' shutter=' + c.shutterAngle + ' bg=' + val(c.bgColor) + ' usedIn=' + u.join('|'));
    try { var mk = c.markerProperty; for (var m = 1; m <= mk.numKeys; m++) w('   MARKER ' + r2(mk.keyTime(m)) + ' ' + clean(mk.keyValue(m).comment, 80)); } catch (em) {}
    for (var k = 1; k <= c.numLayers; k++) {
      var l = c.layer(k), s = '   L' + k + ' ' + kind(l) + ' "' + clean(l.name, 60) + '"';
      try { if (l.source) s += ' src="' + clean(l.source.name, 60) + '"'; } catch (e1) {}
      s += (l.threeDLayer ? ' 3D' : '') + (l.enabled ? '' : ' OFF') + (l.shy ? ' shy' : '') + (l.solo ? ' SOLO' : '') + (l.guideLayer ? ' GUIDE' : '');
      try { if (l.parent) s += ' parent=L' + l.parent.index; } catch (e2) {}
      s += ' in=' + r2(l.inPoint) + ' out=' + r2(l.outPoint) + ' st=' + r2(l.startTime);
      try { if (l.stretch !== 100) s += ' stretch=' + r2(l.stretch); } catch (e3) {}
      try { if (l.blendingMode !== BlendingMode.NORMAL) s += ' blend=' + l.blendingMode; } catch (e4) {}
      try { if (l.trackMatteType && l.trackMatteType !== TrackMatteType.NO_TRACK_MATTE) s += ' matte=' + l.trackMatteType; } catch (e5) {}
      try { if (l.motionBlur) s += ' mb'; if (l.collapseTransformation) s += ' collapse'; if (l.timeRemapEnabled) s += ' tremap'; } catch (e6) {}
      try { var tg = l.property('ADBE Transform Group'); s += ' pos=' + val(tg.property('ADBE Position').value) + ' sc=' + val(tg.property('ADBE Scale').value) + ' op=' + val(tg.property('ADBE Opacity').value); } catch (e7) {}
      try { var ms = l.property('ADBE Mask Parade'); if (ms && ms.numProperties) s += ' masks=' + ms.numProperties; } catch (e8) {}
      try { var ep = l.property('ADBE Effect Parade'), es = []; for (var z = 1; z <= ep.numProperties; z++) es.push(ep.property(z).name + '(' + ep.property(z).matchName + ')'); if (es.length) s += ' fx=' + es.join('+'); } catch (e9) {}
      if (l instanceof CameraLayer) { try { s += ' zoom=' + r2(l.property('ADBE Camera Options Group').property('ADBE Camera Zoom').value); } catch (e10) {} }
      w(s);
      if (l instanceof TextLayer) {
        try {
          var td = l.property('ADBE Text Properties').property('ADBE Text Document').value;
          var t = '      TEXT "' + clean(td.text, 140) + '" font=' + td.font + ' size=' + r2(td.fontSize) + ' track=' + td.tracking + ' lead=' + r2(td.leading);
          try { t += ' fill=' + val(td.fillColor); } catch (e11) {}
          try { t += ' just=' + td.justification; } catch (e12) {}
          try { t += ' caps=' + td.allCaps; } catch (e13) {}
          w(t);
          var an = l.property('ADBE Text Properties').property('ADBE Text Animators'), names = [];
          for (var a = 1; a <= an.numProperties; a++) names.push(an.property(a).name);
          if (names.length) w('      ANIMATORS ' + names.join(' | '));
        } catch (e14) {}
      }
      if (l instanceof ShapeLayer) {
        try { var ct = l.property('ADBE Root Vectors Group'), g = []; for (var y = 1; y <= ct.numProperties; y++) g.push(ct.property(y).name); w('      SHAPES ' + clean(g.join(' | '), 160)); } catch (e15) {}
      }
      try { walk(l, l, 0); } catch (e16) { w('      walk err ' + e16.toString()); }
    }
  }
} catch (x) { w('FATAL ' + x.toString() + ' line ' + x.line); }
var lf = new File(OUT + '/study.txt'); lf.encoding = 'UTF-8'; lf.open('w'); lf.write(L.join('\n')); lf.close();
var df = new File(OUT + '/study_done.txt'); df.open('w'); df.write('ok'); df.close();
})();
