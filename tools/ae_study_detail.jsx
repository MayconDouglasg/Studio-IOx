// Read-only detail pass on the OPEN project (after ae_study.jsx): what text animators change, range selector
// settings, effect parameters (drop shadow, transform, fill), masks (feather / expansion). __OUT__ = folder.
(function () {
var OUT = '__OUT__';
var L = [];
function w(s) { L.push(s); }
function r2(v) { return Math.round(v * 100) / 100; }
function val(v) { if (v instanceof Array) { var o = []; for (var i = 0; i < v.length && i < 4; i++) o.push(r2(v[i])); return '[' + o.join(',') + ']'; } if (typeof v === 'number') return String(r2(v)); return String(v); }
function props(g, pre, depth, out) {
  for (var i = 1; i <= g.numProperties; i++) {
    var p = g.property(i);
    if (!p) continue;
    if (p.propertyType === PropertyType.PROPERTY) {
      var v; try { v = p.value; } catch (e) { continue; }
      if (typeof v === 'object' && !(v instanceof Array)) continue;
      out.push(pre + p.name + '=' + val(v) + (p.numKeys ? '(k' + p.numKeys + ')' : ''));
    } else if (depth < 6) props(p, pre + p.name + '>', depth + 1, out);
  }
}
try {
  var P = app.project, seen = {};
  for (var n = 1; n <= P.numItems; n++) {
    var c = P.item(n);
    if (!(c instanceof CompItem)) continue;
    if (!/^S\d\d_|^Pre-comp 2|^Null 7|Linked Comp 18|^Pre-comp 1/.test(c.name)) continue;
    w('COMP ' + c.name);
    for (var k = 1; k <= c.numLayers; k++) {
      var l = c.layer(k);
      // text animators: only the properties they change + selector settings
      if (l instanceof TextLayer) {
        var an = l.property('ADBE Text Properties').property('ADBE Text Animators');
        for (var a = 1; a <= an.numProperties; a++) {
          var A = an.property(a), o = [];
          props(A.property('ADBE Text Animator Properties'), '', 0, o);
          var sel = [];
          try { var rs = A.property('ADBE Text Selectors').property(1); props(rs.property('ADBE Text Range Advanced'), '', 0, sel); } catch (e1) {}
          var sig = A.name + ' | ' + o.join(', ') + ' | ' + sel.join(', ');
          if (!seen[sig]) { seen[sig] = 1; w('  ANIM L' + k + ' ' + l.name + ' :: ' + sig); }
        }
      }
      // effects with their parameters (first time each signature)
      try {
        var ep = l.property('ADBE Effect Parade');
        for (var z = 1; z <= ep.numProperties; z++) {
          var fx = ep.property(z), q = [];
          if (/Animation Composer|Pseudo/.test(fx.matchName)) continue;
          props(fx, '', 0, q);
          var s2 = fx.name + ' :: ' + q.slice(0, 14).join(', ');
          if (!seen[s2]) { seen[s2] = 1; w('  FX L' + k + ' ' + l.name + ' :: ' + s2); }
        }
      } catch (e2) {}
      // masks (reading shadow, rounded tiles)
      try {
        var ms = l.property('ADBE Mask Parade');
        for (var m = 1; m <= ms.numProperties; m++) {
          var M = ms.property(m), sh = M.property('ADBE Mask Shape').value;
          var xs = [], ys = [];
          for (var v = 0; v < sh.vertices.length; v++) { xs.push(sh.vertices[v][0]); ys.push(sh.vertices[v][1]); }
          var s3 = 'MASK ' + l.name + ' pts=' + sh.vertices.length + ' x=' + r2(Math.min.apply(null, xs)) + '..' + r2(Math.max.apply(null, xs)) + ' y=' + r2(Math.min.apply(null, ys)) + '..' + r2(Math.max.apply(null, ys)) + ' feather=' + val(M.property('ADBE Mask Feather').value) + ' exp=' + r2(M.property('ADBE Mask Offset').value) + ' mode=' + M.maskMode + ' inv=' + M.inverted;
          if (/sombra|Black Solid/.test(l.name) || !seen[s3]) { seen[s3] = 1; w('  ' + s3); }
        }
      } catch (e3) {}
    }
  }
} catch (x) { w('FATAL ' + x.toString() + ' line ' + x.line); }
var lf = new File(OUT + '/study_detail.txt'); lf.encoding = 'UTF-8'; lf.open('w'); lf.write(L.join('\n')); lf.close();
var df = new File(OUT + '/detail_done.txt'); df.open('w'); df.write('ok'); df.close();
})();
