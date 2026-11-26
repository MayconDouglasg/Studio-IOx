// Frame-exact renderer. film.html is a pure function of time, so frames can be
// rendered out of order by several pages in parallel and streamed to ffmpeg in order.
//
//   node render.mjs                       full film  -> out/showreel.mp4
//   node render.mjs --contact [--offset 0.25] [--name sheet]   one frame per beat -> out/<name>.png
//   node render.mjs --at 3.2,7.9 [--name x]   single frames -> out/still_<t>.png (+ out/<name>.png tiled when several)
//   node render.mjs --alpha               ProRes 4444 with alpha -> out/<name>_alpha.mov (the page gets ?alpha=1 and must
//                                         paint no background; no audio unless --audio). Stills / contact keep the alpha too.
//   node render.mjs --timeline            write out/timeline.json = {film, events} from window.TIMELINE (the sound reads it)
//   options: --project <folder>  --workers 4  --subs 6  --fps 60  --out <file>  --audio
//   A project folder (anywhere on disk) holds film.html, optional beats.json, audio/score.wav; output goes to <project>/out/.
//   Files are served from the project first, then from motion-studio (so /fonts/... and /node_modules/... still work).
//   film.html may declare window.FILM = {w, h, dur, fps} (default 1080x1920, 15 s, 60 fps), also after loading its
//   files, before window.__ready. Without beats.json the contact sheet takes one frame every 0.5 s.
import { chromium } from 'playwright';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const arg = (k, d) => { const i = process.argv.indexOf('--' + k); return i < 0 ? d : (process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : true); };
const PROJ = path.resolve(ROOT, arg('project', '.'));
const ALPHA = !!arg('alpha');
const PAGE = 'film.html';
let W = 1080, H = 1920, DUR = 15, FPS = +arg('fps', 0);
const SUBS = +arg('subs', arg('contact') || arg('at') ? 6 : 16), WORKERS = +arg('workers', 4);
const OUTDIR = path.join(PROJ, 'out');
const BASE_NAME = PROJ === ROOT ? 'showreel' : path.basename(PROJ);
const OUT = arg('out') ? path.resolve(ROOT, arg('out')) : path.join(OUTDIR, BASE_NAME + (ALPHA ? '_alpha.mov' : '.mp4'));
fs.mkdirSync(OUTDIR, { recursive: true });

const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.woff2': 'font/woff2', '.wav': 'audio/wav', '.png': 'image/png', '.jpg': 'image/jpeg', '.ttf': 'font/ttf', '.otf': 'font/otf', '.svg': 'image/svg+xml' };
const okFile = p => fs.existsSync(p) && !fs.statSync(p).isDirectory();
const server = http.createServer((req, res) => {
  const u = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  const p = [PROJ, ROOT].map(b => [b, path.join(b, u)]).filter(([b, q]) => q.startsWith(b) && okFile(q)).map(x => x[1])[0];
  if (!p) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'Content-Type': MIME[path.extname(p)] || 'application/octet-stream' }); fs.createReadStream(p).pipe(res);
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const BASE = `http://127.0.0.1:${server.address().port}`;

const browser = await chromium.launch({ args: ['--force-color-profile=srgb', '--disable-lcd-text', '--font-render-hinting=none'] });
const QS = `render=1${ALPHA ? '&alpha=1' : ''}${FPS ? '&fps=' + FPS : ''}`;
{ const pg = await browser.newPage(); pg.on('console', m => { if (m.type() === 'error') console.error('console:', m.text()); });
  await pg.goto(`${BASE}/${PAGE}?${QS}&subs=1`); await pg.waitForFunction(() => window.__ready === true, null, { timeout: 60000 });
  const F = await pg.evaluate(() => window.FILM || null); if (F) { W = F.w; H = F.h; DUR = F.dur; if (!FPS && F.fps) FPS = F.fps; }
  if (arg('timeline')) {
    const tl = await pg.evaluate(() => window.TIMELINE || []);
    fs.writeFileSync(path.join(OUTDIR, 'timeline.json'), JSON.stringify({ film: { w: W, h: H, dur: DUR, fps: FPS || 60 }, events: tl }, null, 1));
    console.log(`timeline ${path.join(OUTDIR, 'timeline.json')} (${tl.length} events, ${DUR} s)`); await browser.close(); server.close(); process.exit(0);
  }
  await pg.close(); }
FPS = FPS || 60;
async function worker() {
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  page.on('pageerror', e => { console.error('PAGE ERROR', e.message); process.exitCode = 1; });
  page.on('console', m => { if (m.type() === 'error') console.error('console:', m.text()); });
  await page.goto(`${BASE}/${PAGE}?${QS}&subs=${SUBS}`);
  await page.waitForFunction(() => window.__ready === true, null, { timeout: 60000 });
  const cdp = await page.context().newCDPSession(page);
  if (ALPHA) await cdp.send('Emulation.setDefaultBackgroundColorOverride', { color: { r: 0, g: 0, b: 0, a: 0 } });
  return {
    async grab(t) {
      await page.evaluate(t => window.seek(t), t);
      const { data } = await cdp.send('Page.captureScreenshot', { format: 'png', clip: { x: 0, y: 0, width: W, height: H, scale: 1 }, optimizeForSpeed: !ALPHA });
      return Buffer.from(data, 'base64');
    },
  };
}
async function pool(times, onFrame) {
  const ws = await Promise.all(Array.from({ length: Math.min(WORKERS, times.length) }, worker));
  let next = 0;
  await Promise.all(ws.map(async w => { while (next < times.length) { const i = next++; onFrame(i, await w.grab(times[i])); } }));
}

const BJ = path.join(PROJ, 'beats.json');
const beats = fs.existsSync(BJ) ? JSON.parse(fs.readFileSync(BJ, 'utf8'))
  : { offset: 0.25, period: 0.5, grid: Array.from({ length: Math.ceil(DUR / 0.5) }, (_, i) => 0.25 + i * 0.5) };
const t0 = Date.now();

if (arg('contact')) {
  const off = +arg('offset', 0), name = arg('name', off ? `contact_${off}` : 'contact');
  const list = arg('beats') ? String(arg('beats')).split(',').map(Number) : beats.grid.map((_, i) => i + off).filter(x => beats.offset + x * beats.period < DUR);
  const times = list.map(x => Math.min(DUR - 1 / FPS, Math.max(0, beats.offset + x * beats.period)));
  const dir = path.join(OUTDIR, name); fs.mkdirSync(dir, { recursive: true });
  await pool(times, (i, png) => fs.writeFileSync(path.join(dir, `b${String(i).padStart(2, '0')}.png`), png));
  const sheet = path.join(OUTDIR, `${name}.png`);
  await run('ffmpeg', ['-y', '-loglevel', 'error', '-framerate', '1', '-i', path.join(dir, 'b%02d.png'), '-vf', (W > H ? 'scale=400:-1' : 'scale=240:-1') + ':flags=lanczos,pad=iw+8:ih+8:4:4:color=0x444444,tile=' + (W > H ? 4 : 6) + 'x' + Math.ceil(times.length / (W > H ? 4 : 6)), '-frames:v', '1', sheet]);
  console.log(`contact sheet ${sheet} (${times.length} beats) in ${((Date.now() - t0) / 1000).toFixed(1)}s`);
} else if (arg('at')) {
  const times = String(arg('at')).split(',').map(Number);
  await pool(times, (i, png) => fs.writeFileSync(path.join(OUTDIR, `still_${times[i]}.png`), png));
  console.log('stills', times.join(', '));
  if (times.length > 1) {                          // tile them too (ffmpeg on Windows has no -pattern_type glob: numbered copies)
    const name = arg('name', 'stills'), dir = path.join(OUTDIR, name); fs.mkdirSync(dir, { recursive: true });
    times.forEach((t, i) => fs.copyFileSync(path.join(OUTDIR, `still_${t}.png`), path.join(dir, `b${String(i).padStart(2, '0')}.png`)));
    const cols = W > H ? 4 : 6, sheet = path.join(OUTDIR, `${name}.png`);
    await run('ffmpeg', ['-y', '-loglevel', 'error', '-framerate', '1', '-i', path.join(dir, 'b%02d.png'), '-vf', (W > H ? 'scale=400:-1' : 'scale=240:-1') + ':flags=lanczos,pad=iw+8:ih+8:4:4:color=0x444444,tile=' + cols + 'x' + Math.ceil(times.length / cols), '-frames:v', '1', sheet]);
    console.log('sheet', sheet);
  }
} else {
  const N = Math.round(DUR * FPS), times = Array.from({ length: N }, (_, i) => i / FPS);
  const wav = path.join(PROJ, 'audio', 'score.wav'), withAudio = fs.existsSync(wav) && (!ALPHA || !!arg('audio'));
  if (!fs.existsSync(wav)) console.warn('no audio/score.wav: rendering without sound');
  const aIn = withAudio ? ['-i', wav, '-map', '0:v', '-map', '1:a'] : [];
  const enc = ALPHA
    ? ['-c:v', 'prores_ks', '-profile:v', '4', '-pix_fmt', 'yuva444p10le', '-alpha_bits', '16', '-vendor', 'apl0',       // ProRes 4444 + alpha
       ...(withAudio ? ['-c:a', 'pcm_s24le', '-ar', '48000'] : [])]
    : ['-vf', 'scale=out_color_matrix=bt709:out_range=tv:flags=lanczos+accurate_rnd+full_chroma_int,format=yuv420p',
       '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p',
       '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv',
       ...(withAudio ? ['-c:a', 'aac', '-b:a', '320k', '-ar', '48000'] : []), '-movflags', '+faststart'];
  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'png', '-i', '-',
    ...aIn, ...enc, '-t', String(DUR), OUT], { stdio: ['pipe', 'inherit', 'inherit'] });
  const buf = new Map(); let wrote = 0;
  const flush = async () => { while (buf.has(wrote)) { const b = buf.get(wrote); buf.delete(wrote); wrote++; if (!ff.stdin.write(b)) await new Promise(r => ff.stdin.once('drain', r)); if (wrote % 60 === 0) process.stdout.write(`\r${wrote}/${N} frames`); } };
  let chain = Promise.resolve();
  await pool(times, (i, png) => { buf.set(i, png); chain = chain.then(flush); });
  await chain; ff.stdin.end();
  await new Promise(r => ff.on('close', r));
  console.log(`\n${OUT} — ${N} frames in ${((Date.now() - t0) / 1000).toFixed(1)}s`);
}
await browser.close(); server.close();

function run(cmd, a) { return new Promise((res, rej) => { const p = spawn(cmd, a, { stdio: 'inherit' }); p.on('close', c => c ? rej(new Error(cmd + ' ' + c)) : res()); }); }
