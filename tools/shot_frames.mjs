// Screenshot selected storyboard frames: node tools/shot_frames.mjs <page.html> <outdir> [indices...]
import { chromium } from 'playwright';
import { pathToFileURL } from 'node:url';
import fs from 'node:fs';
const [page, outdir, ...idx] = process.argv.slice(2);
fs.mkdirSync(outdir, { recursive: true });
const b = await chromium.launch();
const pg = await b.newPage({ viewport: { width: 1240, height: 900 } });
pg.on('pageerror', e => console.log('ERR', e.message));
await pg.goto(pathToFileURL(page).href);
await pg.waitForTimeout(3000);
const frames = await pg.$$('.frame');
const list = idx.length ? idx.map(Number) : frames.map((_, i) => i);
let n = 0;
for (const i of list) if (frames[i]) await frames[i].screenshot({ path: `${outdir}/f${String(++n).padStart(2, '0')}.png` });
console.log('frames', frames.length, 'shot', n);
await b.close();
