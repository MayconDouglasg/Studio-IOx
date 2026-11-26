// Read-only inspector: dumps fonts, comps and layer transforms of the OPEN project, saves a few frames.
(function () {
var OUT = '__OUT__';
var FONTRX = /__FONTS__/i;   // fill __FONTS__ with the client's families, e.g. Montserrat|Playfair
var L = [];
function w(s) { L.push(s); }
function arr(a) { if (!(a instanceof Array)) return String(Math.round(a * 100) / 100); var o = []; for (var i = 0; i < a.length; i++) o.push(Math.round(a[i] * 10) / 10); return '[' + o.join(',') + ']'; }
try {
  var OPEN = '__OPEN__';
  if (OPEN && app.project.file === null && app.project.numItems === 0) { app.open(new File(OPEN)); }
  w('AE ' + app.version + '  project: ' + (app.project.file ? app.project.file.fsName : '(untitled)') + '  dirty=' + app.project.dirty);
  // fonts
  try {
    var all = app.fonts.allFonts, i, j;
    for (i = 0; i < all.length; i++) for (j = 0; j < all[i].length; j++) {
      var f = all[i][j];
      if (FONTRX && FONTRX.test(f.familyName + f.postScriptName)) w('FONT  ps=' + f.postScriptName + '  fam=' + f.familyName + '  style=' + f.styleName + '  sub=' + f.isSubstitute + (f.designAxesData ? '  VARIABLE' : ''));
    }
    try { var ms = app.fonts.missingOrSubstitutedFonts; for (i = 0; i < ms.length; i++) w('MISSING ' + ms[i].postScriptName); } catch (e1) {}
  } catch (e) { w('fonts api: ' + e.toString()); }
  // items
  var n;
  for (n = 1; n <= app.project.numItems; n++) {
    var it = app.project.item(n);
    var pf = it.parentFolder ? it.parentFolder.name : '';
    if (it instanceof CompItem) {
      w('COMP "' + it.name + '" [' + pf + '] ' + it.width + 'x' + it.height + ' dur=' + Math.round(it.duration * 100) / 100 + ' fps=' + Math.round(it.frameRate * 100) / 100 + ' layers=' + it.numLayers + ' renderer=' + it.renderer);
      var detail = /MOCKUP/i.test(pf) || /^S\d\d_|Phone|Screen|SCENE|Text/i.test(it.name);
      if (!detail) continue;
      for (var k = 1; k <= it.numLayers; k++) {
        var l = it.layer(k), tr = l.property('ADBE Transform Group'), s = '  ' + k + ' "' + l.name + '"';
        try { s += ' src=' + (l.source ? l.source.name : '-'); } catch (e2) {}
        s += (l.threeDLayer ? ' 3D' : '') + (l.enabled ? '' : ' OFF') + (l.parent ? ' parent=' + l.parent.index : '') + (l.nullLayer ? ' NULL' : '');
        try { s += ' pos=' + arr(tr.property('ADBE Position').value) + (tr.property('ADBE Position').numKeys ? '(k' + tr.property('ADBE Position').numKeys + ')' : '') + ' anc=' + arr(tr.property('ADBE Anchor Point').value) + ' sc=' + arr(tr.property('ADBE Scale').value); } catch (e3) {}
        try { s += ' in=' + arr(l.inPoint) + ' out=' + arr(l.outPoint); } catch (e4) {}
        try { if (l.hasTrackMatte) s += ' MATTE'; if (l.collapseTransformation) s += ' COLLAPSE'; if (l.timeRemapEnabled) s += ' TREMAP'; } catch (e7) {}
        try { var td = l.property('ADBE Text Properties').property('ADBE Text Document').value; s += ' TEXT font=' + td.font + ' size=' + arr(td.fontSize) + ' rect=' + arr([l.sourceRectAtTime(0, false).left, l.sourceRectAtTime(0, false).top, l.sourceRectAtTime(0, false).width, l.sourceRectAtTime(0, false).height]); } catch (e5) {}
        try { var ep = l.property('ADBE Effect Parade'), es = []; for (var q = 1; q <= ep.numProperties; q++) es.push(ep.property(q).matchName); if (es.length) s += ' fx=' + es.join('+'); } catch (e6) {}
        try { if (tr.property('ADBE Position').expression) s += ' EXPR'; } catch (e8) {}
        w(s);
      }
    } else if (it instanceof FootageItem) {
      w('FOOTAGE "' + it.name + '" [' + pf + '] ' + it.width + 'x' + it.height + ' dur=' + Math.round(it.duration * 100) / 100 + (it.footageMissing ? ' MISSING' : '') + (it.file ? ' file=' + it.file.name : ''));
    }
  }
  // frames
  var shots = __SHOTS__;
  for (n = 1; n <= app.project.numItems; n++) {
    var c = app.project.item(n);
    if (!(c instanceof CompItem)) continue;
    for (var z = 0; z < shots.length; z++) if (c.name.indexOf(shots[z][0]) === 0) {
      try { c.saveFrameToPng(shots[z][1], new File(OUT + '/' + shots[z][0].replace(/[^A-Za-z0-9]+/g, '_') + '_' + shots[z][1] + '.png')); w('shot ' + c.name + ' @' + shots[z][1]); } catch (e9) { w('shot failed ' + c.name + ': ' + e9.toString()); }
    }
  }
} catch (x) { w('FATAL ' + x.toString() + ' line ' + x.line); }
var lf = new File(OUT + '/dump.txt'); lf.encoding = 'UTF-8'; lf.open('w'); lf.write(L.join('\n')); lf.close();
})();
