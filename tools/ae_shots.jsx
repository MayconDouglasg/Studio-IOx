// Saves check frames of the OPEN project: every scene comp (S##_...) and, for overlay scenes, the main comp.
// Placeholders: __OUT__ (folder), __MOTION__ (true/false), __ONLY__ (regex source or empty), __TIMES__ (array or null)
(function () {
var OUT = '__OUT__', MOTION = __MOTION__, ONLY = '__ONLY__', TIMES = __TIMES__, L = [], n, q;
try {
  var sd = new Folder(OUT); if (!sd.exists) sd.create();
  var main = null;
  for (n = 1; n <= app.project.numItems; n++) { var it = app.project.item(n); if (it instanceof CompItem && it.name.indexOf('MAIN') === 0) main = it; }
  for (n = 1; n <= app.project.numItems; n++) {
    var c = app.project.item(n);
    if (!(c instanceof CompItem) || !/^S[0-9][0-9]_/.test(c.name)) continue;
    if (ONLY && !(new RegExp(ONLY)).test(c.name)) continue;
    var id = c.name.substr(1, 2), du = c.duration;
    var times = TIMES ? TIMES : (MOTION ? [0.14, 0.4, 0.7, 1.0, 1.4, du * 0.6, du - 0.36, du - 0.14] : [du * 0.6]);
    for (q = 0; q < times.length; q++) {
      var tt = times[q] < 0 ? du + times[q] : times[q];
      c.saveFrameToPng(Math.max(0, Math.min(du - 0.04, tt)), new File(OUT + '/S' + id + '_' + (q < 10 ? '0' : '') + q + '.png'));
    }
    if (main) {                                  // every scene also seen in the edit (overlays need the face under them)
      for (q = 1; q <= main.numLayers; q++) if (main.layer(q).name === c.name) main.saveFrameToPng(main.layer(q).startTime + du * 0.6, new File(OUT + '/M' + id + '.png'));
    }
    L.push('ok ' + c.name);
  }
} catch (x) { L.push('FATAL ' + x.toString() + ' line ' + x.line); }
var lf = new File(OUT + '/shots_done.txt'); lf.encoding = 'UTF-8'; lf.open('w'); lf.write(L.join(String.fromCharCode(10))); lf.close();
})();
