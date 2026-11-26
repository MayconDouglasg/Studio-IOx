"""Reusable code-synthesized instruments, SFX and mix bus for project scores.
    from synth import Mix, kick, hat, clap, stab, pad, bass, blip, tick, whoosh, impact, pop, glitch, scribble
    m = Mix(duration=8.0, bpm=120); m.place('drums', kick(), m.T(0)); m.render('audio/score_raw.wav')
Seeded RNG only.
"""
import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt, fftconvolve

SR = 48000
rng = np.random.default_rng(1207)


def tt(d):
    return np.arange(int(d * SR)) / SR


def noise(d):
    return rng.standard_normal(int(d * SR))


def filt(x, kind, f, order=2):
    if kind == "bp":
        sos = butter(order, [f[0] / (SR / 2), min(f[1], SR / 2 - 100) / (SR / 2)], "band", output="sos")
    else:
        sos = butter(order, f / (SR / 2), kind, output="sos")
    return sosfilt(sos, x)


def st(x, d=37):
    return np.vstack([x, np.roll(x, d)])


# ------------------------------------------------------------ drums
def kick(punch=1.0, decay=0.17):
    t = tt(0.5)
    f = 46 + 120 * np.exp(-t / 0.028) * punch
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / decay)
    click = filt(noise(0.5), "hp", 2500) * np.exp(-t / 0.0025) * 0.3
    return np.tanh(1.8 * (body + click)) * 0.9


def clap():
    t = tt(0.4)
    env = sum(np.where(t >= o, np.exp(-(t - o) / 0.004), 0) for o in (0, .009, .018)) + 0.6 * np.exp(-t / 0.09)
    return np.tanh(1.4 * (filt(noise(0.4), "bp", (900, 4200)) * env * .8 + np.sin(2 * np.pi * 185 * t) * np.exp(-t / .045) * .5))


def hat(open_=False):
    d = 0.35 if open_ else 0.06
    return filt(noise(d), "hp", 7000) * np.exp(-tt(d) / (0.09 if open_ else 0.016)) * 0.5


def shaker():
    t = tt(0.09)
    return filt(noise(0.09), "bp", (4000, 11000)) * np.sin(np.pi * t / 0.09) ** 2 * 0.4


# ------------------------------------------------------------ tonal
def _saw(f, t, dt=0.0):
    ph = f * (1 + dt) * t + rng.random()
    return 2 * (ph % 1.0) - 1


def stab(freqs, dur=0.32, cutoff=2600, decay=0.12):
    t = tt(dur)
    s = sum(_saw(f, t, d) for f in freqs for d in (-.011, -.004, 0, .005, .012)) / (len(freqs) * 5)
    s = filt(s, "lp", cutoff) * np.minimum(t / .003, 1) * np.exp(-t / decay)
    return st(s) * .9


def pad(freqs, dur=2.0, cutoff=1400, attack=0.25):
    t = tt(dur)
    s = sum(_saw(f, t, d) for f in freqs for d in (-.006, 0, .007)) / (len(freqs) * 3)
    s = filt(s, "lp", cutoff) * np.minimum(t / attack, 1) * np.clip((dur - t) / 0.4, 0, 1)
    return st(s, 211) * .6


def bass(freq, dur=0.22):
    t = tt(dur)
    s = np.sin(2 * np.pi * freq * t) + .35 * np.sin(4 * np.pi * freq * t) + .25 * filt(_saw(freq, t), "lp", 600)
    return np.tanh(1.6 * s * np.minimum(t / .004, 1) * np.clip((dur - t) / .03, 0, 1)) * .8


def pluck(freq, dur=0.5):
    t = tt(dur)
    s = filt(_saw(freq, t) + _saw(freq * 2.005, t) * .4, "lp", 3200) * np.exp(-t / .12) * np.minimum(t / .002, 1)
    return st(s) * .6


# ------------------------------------------------------------ sfx
def blip(freq, d=0.09, drop=0.12):
    t = tt(d)
    f = freq * (1 + drop * np.exp(-t / 0.01))
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / (d / 4)) * np.minimum(t / .0015, 1)


def pop():
    """UI tile pop: short pitched bubble + click."""
    t = tt(0.12)
    f = 520 + 900 * np.exp(-t / 0.012)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.03) + filt(noise(0.12), "hp", 3000) * np.exp(-t / .003) * .3
    return s * .8


def tick():
    return filt(noise(0.03), "bp", (2500, 9000)) * np.exp(-tt(0.03) / 0.004)


def sweep(d, f0, f1, bands=10, q=0.35):
    n = noise(d)
    x = np.linspace(0, 1, len(n))
    fc = np.exp(np.log(f0) + (np.log(f1) - np.log(f0)) * x)
    out = np.zeros_like(n)
    for c in np.geomspace(150, 12000, bands):
        out += filt(n, "bp", (c * (1 - q), c * (1 + q))) * np.exp(-(np.log(fc / c) ** 2) / (2 * .35 ** 2))
    return out


def whoosh(d=0.45, up=True):
    s = sweep(d, 300 if up else 6000, 6000 if up else 300)
    x = np.linspace(0, 1, len(s))
    return st(s * ((x ** 2.2) if up else (np.sin(np.pi * x) ** 1.5)), 120) * .7


def scribble(d=0.35):
    """Marker on paper: band-passed noise with stroke-like amplitude wobble."""
    t = tt(d)
    env = (0.55 + 0.45 * np.abs(np.sin(2 * np.pi * 9 * t))) * np.sin(np.pi * t / d) ** .6
    return filt(noise(d), "bp", (1800, 7000)) * env * .45


def glitch(d=0.22):
    t = tt(d)
    sq = np.sign(np.sin(2 * np.pi * (180 + 900 * rng.random()) * t))
    gate = (np.floor(t * 60) % 2 == 0)
    s = (sq * .3 + filt(noise(d), "hp", 2000) * .5) * gate * np.exp(-t / .12)
    return st(s, 300) * .7


def impact(big=1.0, length=2.6):
    t = tt(length)
    sub = np.sin(2 * np.pi * np.cumsum(38 + 50 * np.exp(-t / .08)) / SR) * np.exp(-t / .9)
    crash = filt(noise(length), "hp", 3500) * np.exp(-t / .55) * .3
    k = np.zeros_like(t)
    kk = kick(1.3)
    k[:len(kk)] = kk
    s = np.tanh(1.3 * (sub * .9 + k * .9)) + crash
    return st(s, 300) * big


# ------------------------------------------------------------ mix
class Mix:
    def __init__(self, duration, bpm=120.0):
        self.N = int(SR * duration)
        self.beat = 60.0 / bpm
        self.b = {k: np.zeros((2, self.N)) for k in ("drums", "bass", "music", "sfx", "send")}
        self.kicks = []

    def T(self, b):
        return b * self.beat

    def place(self, bus, sig, t, gain=1.0, pan=0.0, send=0.0):
        i = int(round(t * SR))
        if i >= self.N or i < 0:
            return
        s = (sig[: self.N - i] if sig.ndim == 1 else sig[:, : self.N - i]) * gain
        if s.ndim == 1:
            a = (pan + 1) * np.pi / 4
            s = np.vstack([s * np.cos(a), s * np.sin(a)]) * np.sqrt(2)
        self.b[bus][:, i:i + s.shape[1]] += s
        if send:
            self.b["send"][:, i:i + s.shape[1]] += s * send
        if sig is not None and bus == "drums" and getattr(sig, "_kick", False):
            self.kicks.append(t)

    def duck(self, times, depth=0.6):
        side = np.ones(self.N)
        for kt in times:
            i = int(kt * SR)
            seg = 1 - depth * np.exp(-tt(.25) / .07)
            j = min(self.N, i + len(seg))
            side[i:j] = np.minimum(side[i:j], seg[: j - i])
        for k in ("bass", "music"):
            self.b[k] *= side

    def render(self, path, fade=0.3):
        ir_t = tt(2.2)
        ir = np.vstack([filt(noise(2.2), "lp", 6000) * np.exp(-ir_t / .45) for _ in range(2)])
        ir /= np.abs(ir).sum(axis=1, keepdims=True) ** .5 * 9
        wet = np.vstack([fftconvolve(self.b["send"][c], ir[c])[: self.N] for c in range(2)])
        mix = self.b["drums"] * .9 + self.b["bass"] * .8 + self.b["music"] * .8 + self.b["sfx"] * .9 + wet * .6
        mix = np.vstack([filt(mix[c], "hp", 28) for c in range(2)])
        mix = np.tanh(mix * 1.1) / np.tanh(1.1)
        f = np.ones(self.N)
        fl = int(fade * SR)
        f[-fl:] = np.linspace(1, 0, fl) ** 2
        mix *= f
        mix /= np.max(np.abs(mix)) / .89
        sf.write(path, mix.T, SR, subtype="PCM_24")
        return mix
