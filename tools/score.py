"""Synthesized score for the 15 s showreel. 120 BPM, A minor.
Everything here is generated from code; seeded RNG only.
Event positions are in beats and mirror the visual timeline in film.html.
Usage: python -I tools/score.py audio/score_raw.wav
"""
import sys
import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt, fftconvolve

SR = 48000
BPM = 120.0
BEAT = 60.0 / BPM
DUR = 15.0
N = int(SR * DUR)
rng = np.random.default_rng(1207)

buses = {k: np.zeros((2, N)) for k in ("drums", "bass", "music", "sfx", "send")}
kick_times = []


def T(b):
    return b * BEAT


def place(bus, sig, t, gain=1.0, pan=0.0, send=0.0):
    i = int(round(t * SR))
    if i >= N or i < 0:
        return
    s = (sig[: N - i] if sig.ndim == 1 else sig[:, : N - i]) * gain
    a = (pan + 1) * np.pi / 4
    l, r = np.cos(a) * np.sqrt(2), np.sin(a) * np.sqrt(2)
    if s.ndim == 1:
        buses[bus][0, i:i + len(s)] += s * l
        buses[bus][1, i:i + len(s)] += s * r
        if send:
            buses["send"][0, i:i + len(s)] += s * l * send
            buses["send"][1, i:i + len(s)] += s * r * send
    else:
        buses[bus][:, i:i + s.shape[1]] += s
        if send:
            buses["send"][:, i:i + s.shape[1]] += s * send


def tt(d):
    return np.arange(int(d * SR)) / SR


def filt(x, kind, f, order=2):
    if kind == "bp":
        sos = butter(order, [f[0] / (SR / 2), f[1] / (SR / 2)], "band", output="sos")
    else:
        sos = butter(order, f / (SR / 2), kind, output="sos")
    return sosfilt(sos, x)


def noise(d):
    return rng.standard_normal(int(d * SR))


# ---------------------------------------------------------------- instruments
def kick(punch=1.0):
    t = tt(0.5)
    f = 46 + 120 * np.exp(-t / 0.028) * punch
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-t / 0.17)
    click = filt(noise(0.5), "hp", 2500) * np.exp(-t / 0.0025) * 0.35
    return np.tanh(1.8 * (body + click)) * 0.9


def clap():
    t = tt(0.4)
    env = np.zeros_like(t)
    for o in (0.0, 0.009, 0.018):
        m = t >= o
        env[m] += np.exp(-(t[m] - o) / 0.004)
    env += 0.6 * np.exp(-t / 0.09)
    n = filt(noise(0.4), "bp", (900, 4200)) * env
    tone = np.sin(2 * np.pi * 185 * t) * np.exp(-t / 0.045) * 0.5
    return np.tanh(1.4 * (n * 0.8 + tone))


def hat(open_=False):
    d = 0.35 if open_ else 0.06
    t = tt(d)
    n = filt(noise(d), "hp", 7000)
    return n * np.exp(-t / (0.09 if open_ else 0.016)) * 0.5


def saw(freq, t, detune=0.0):
    ph = (freq * (1 + detune)) * t + rng.random()
    return 2 * (ph % 1.0) - 1


def stab(freqs, dur=0.32, cutoff=2600, decay=0.12):
    t = tt(dur)
    s = np.zeros_like(t)
    for f in freqs:
        for dt in (-0.011, -0.004, 0.0, 0.005, 0.012):
            s += saw(f, t, dt)
    s /= len(freqs) * 5
    s = filt(s, "lp", cutoff, 2)
    env = np.minimum(t / 0.003, 1) * np.exp(-t / decay)
    st = np.vstack([s * env, np.roll(s, 37) * env])
    return st * 0.9


def bass(freq, dur=0.22):
    t = tt(dur)
    s = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(4 * np.pi * freq * t)
    s += 0.25 * filt(saw(freq, t), "lp", 600)
    env = np.minimum(t / 0.004, 1) * np.clip((dur - t) / 0.03, 0, 1)
    return np.tanh(1.6 * s * env) * 0.8


def blip(freq, d=0.09, drop=0.12):
    t = tt(d)
    f = freq * (1 + drop * np.exp(-t / 0.01))
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t / (d / 4)) * np.minimum(t / 0.0015, 1)


def tick():
    t = tt(0.03)
    return filt(noise(0.03), "bp", (2500, 9000)) * np.exp(-t / 0.004)


def sweep(d, f0, f1, bands=10, q=0.35):
    """Noise swept through a moving band (whoosh / riser)."""
    n = noise(d)
    t = np.linspace(0, 1, len(n))
    centers = np.geomspace(150, 12000, bands)
    fc = np.exp(np.log(f0) + (np.log(f1) - np.log(f0)) * t)
    out = np.zeros_like(n)
    for c in centers:
        b = filt(n, "bp", (c * (1 - q), min(c * (1 + q), SR / 2 - 100)))
        w = np.exp(-(np.log(fc / c) ** 2) / (2 * 0.35 ** 2))
        out += b * w
    return out


def whoosh(d=0.45, up=True):
    s = sweep(d, 300 if up else 6000, 6000 if up else 300)
    t = np.linspace(0, 1, len(s))
    env = (t ** 2.2) if up else (np.sin(np.pi * t) ** 1.5)
    s = s * env
    return np.vstack([s, np.roll(s, 120)]) * 0.7


def impact(big=1.0):
    t = tt(2.6)
    sub = np.sin(2 * np.pi * np.cumsum(38 + 50 * np.exp(-t / 0.08)) / SR) * np.exp(-t / 0.9)
    crash = filt(noise(2.6), "hp", 3500) * np.exp(-t / 0.55) * 0.35
    k = np.zeros_like(t)
    kk = kick(1.3)
    k[: len(kk)] = kk
    s = np.tanh(1.3 * (sub * 0.9 + k * 0.9)) + crash
    return np.vstack([s, s * 0.98 + np.roll(crash, 300) * 0.1]) * big


def zap():
    t = tt(0.25)
    f = 180 * np.exp(t * 14)
    f = np.minimum(f, 9000)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t / 0.07) * 0.5


# ---------------------------------------------------------------- harmony
A2, F2, C3, G2, E2, D3 = 110.0, 87.31, 130.81, 98.0, 82.41, 146.83
CH = {
    "Am": [220.0, 261.63, 329.63, 440.0],
    "F": [174.61, 220.0, 261.63, 349.23],
    "C": [261.63, 329.63, 392.0, 523.25],
    "G": [196.0, 246.94, 293.66, 392.0],
    "E": [164.81, 207.65, 246.94, 329.63],
    "Dm": [146.83, 220.0, 293.66, 349.23],
}
ROOT = {"Am": A2 / 2, "F": F2 / 2, "C": C3 / 2, "G": G2 / 2, "E": E2 / 2, "Dm": D3 / 4}


def chord_at(b):
    bar = int(b // 4)
    return ["Am", "F", "C", "G", "Am", "F", "Am", "Am"][min(bar, 7)] if b < 22 or b >= 24 else ("E" if b >= 22 else "F")


# ---------------------------------------------------------------- arrangement
# Scene 1 (B0-4): NOTHING / STAYS / STILL.
place("music", impact(0.9), T(0), send=0.25)
kick_times.append(T(0))
for b, ch in ((0, "Am"), (1, "Am"), (2, "Am")):
    place("music", stab(CH[ch], 0.5, 3200, 0.16), T(b), 0.55, send=0.3)
for b in (1, 2):
    place("drums", kick(), T(b), 0.9)
    kick_times.append(T(b))
place("sfx", whoosh(0.30, True), T(1) - 0.30, 0.45, pan=0.6)            # STAYS slides in from the right
for i in range(5):                                                        # S T I L L drop (32nds)
    place("sfx", blip(900 + i * 160, 0.07), T(2 + i * 0.125), 0.28, pan=-0.6 + i * 0.3)
    place("sfx", tick(), T(2 + i * 0.125), 0.35)
place("sfx", blip(1320, 0.18, 0.4), T(3), 0.4, send=0.4)                 # the dot lands
place("drums", kick(0.8), T(3), 0.7)
kick_times.append(T(3))
place("sfx", whoosh(0.5, True), T(4) - 0.5, 0.6)                          # circle wipe

# groove B4-B20, final groove B24-B28
for b in range(4, 20):
    place("drums", kick(), T(b), 1.0)
    kick_times.append(T(b))
    place("drums", hat(True), T(b + 0.5), 0.32, pan=0.25)
    if b >= 8:
        for s in (0.25, 0.75):
            place("drums", hat(), T(b + s), 0.22 + 0.06 * rng.random(), pan=-0.3)
    if b % 2 == 1:
        place("drums", clap(), T(b), 0.55, send=0.18)
    root = ROOT[chord_at(b)]
    for s in (0.5, 0.75) if b % 2 else (0.5,):
        place("bass", bass(root * 2, 0.2), T(b + s), 0.75)
for bar in range(1, 5):
    b0 = bar * 4
    ch = CH[chord_at(b0)]
    for s, d in ((0, 0.28), (1.5, 0.22), (3.0, 0.3)):
        place("music", stab(ch, d + 0.1, 2200 + 500 * (bar % 2), 0.1), T(b0 + s), 0.42, send=0.25)

# Scene 2 (B4-8): easing lanes. Arrivals at B6 and B7.5, converge B8
for i, b in enumerate((6.0, 7.5)):
    for k in range(5):
        place("sfx", blip(660 * (1.12 ** k) * (1 + i * 0.5), 0.07), T(b) + k * 0.012, 0.12, pan=-0.8 + k * 0.4)
place("sfx", zap(), T(7.75), 0.25)

# Scene 3 (B8-12): radial tile wave B8 -> 1.5 beats, flip at B10, fall at B12
for i in range(48):
    tw = T(8) + (i / 48) ** 1.2 * 1.5 * BEAT
    place("sfx", tick(), tw, 0.08 + 0.1 * rng.random(), pan=rng.uniform(-0.9, 0.9))
place("sfx", whoosh(0.45, False), T(10) - 0.05, 0.45)
for k in range(8):
    place("sfx", blip(1046.5 * (2 ** (k / 12 * 2)), 0.06), T(10 + k * 0.0625), 0.1, pan=-0.7 + k * 0.2)
place("sfx", whoosh(0.5, False), T(12), 0.5)

# Scene 4 (B12-16): point cloud morphs on B13, B14, B15, collapse B16
for b in (13, 14, 15):
    place("sfx", whoosh(0.28, True), T(b) - 0.28, 0.4, pan=(b - 14) * 0.6)
    place("bass", bass(ROOT[chord_at(b)] * 4, 0.12), T(b), 0.5)
place("sfx", whoosh(0.4, True), T(16) - 0.4, 0.5)

# Scene 5 (B16-20): line field, dot hops, ripple per kick
place("sfx", zap(), T(16), 0.4)
for b in (17, 18, 19):
    place("sfx", blip(784 * (1.0595 ** ((b - 17) * 3)), 0.14, 0.3), T(b), 0.25, send=0.35)

# Scene 6 (B20-24): countdown build
cuts = [20, 21, 22, 22.5, 23, 23.25, 23.5, 23.75]
for i, c in enumerate(cuts):
    place("sfx", blip(440 * 2 ** (i / 12 * 2), 0.08), T(c), 0.32, send=0.2)
    place("drums", kick(0.9), T(c), 0.55 + 0.05 * i)
    kick_times.append(T(c))
roll = [20 + k * 0.5 for k in range(4)] + [22 + k * 0.25 for k in range(4)] + [23 + k * 0.125 for k in range(8)]
for i, b in enumerate(roll):
    place("drums", clap(), T(b), 0.18 + 0.45 * i / len(roll), pan=(-1) ** i * 0.15)
for b in np.arange(20, 24, 0.5):
    place("music", stab(CH[chord_at(b)], 0.24, 900 + (b - 20) * 900, 0.08), T(b), 0.35)
    place("bass", bass(ROOT[chord_at(b)] * 2, 0.2), T(b + 0.25), 0.55)
riser = sweep(2.0, 200, 11000)
rt = np.linspace(0, 1, len(riser))
riser = riser * rt ** 2.5
place("sfx", np.vstack([riser, np.roll(riser, 200)]) * 0.55, T(20))
place("sfx", whoosh(0.35, True), T(24) - 0.35, 0.5)

# Scene 7 (B24-30): DROP and signature
place("music", impact(1.0), T(24), send=0.3)
kick_times.append(T(24))
place("music", stab(CH["Am"], 1.0, 3800, 0.4), T(24), 0.6, send=0.45)
for b in (25, 26, 27):
    place("drums", kick(), T(b), 1.0)
    kick_times.append(T(b))
    place("drums", hat(True), T(b + 0.5), 0.3)
    place("music", stab(CH[["F", "G", "E"][b - 25]], 0.35, 3000, 0.12), T(b), 0.5, send=0.3)
    place("bass", bass(ROOT[["F", "G", "E"][b - 25]] * 2, 0.2), T(b + 0.5), 0.7)
for b in (25, 27):
    place("drums", clap(), T(b), 0.6, send=0.2)
place("sfx", whoosh(0.25, True), T(28) - 0.25, 0.4)
place("music", impact(0.85), T(28), send=0.45)
kick_times.append(T(28))
place("music", stab(CH["Am"] + [659.25], 1.0, 2400, 0.5), T(28), 0.55, send=0.6)
place("sfx", blip(1760, 0.3, 0.2), T(28), 0.3, send=0.6)                  # the period lands
for i in range(14):                                                        # mono line types out
    place("sfx", tick(), T(28.5) + i * 0.035, 0.12)

# ---------------------------------------------------------------- mix
side = np.ones(N)
for kt in kick_times:
    i = int(kt * SR)
    t = tt(0.25)
    seg = 1 - 0.7 * np.exp(-t / 0.07)
    j = min(N, i + len(seg))
    side[i:j] = np.minimum(side[i:j], seg[: j - i])
for k in ("bass", "music"):
    buses[k] *= side

ir_t = tt(2.2)
ir = np.vstack([
    filt(noise(2.2), "lp", 6000) * np.exp(-ir_t / 0.45),
    filt(noise(2.2), "lp", 6000) * np.exp(-ir_t / 0.45),
])
ir /= np.abs(ir).sum(axis=1, keepdims=True) ** 0.5 * 9
wet = np.vstack([fftconvolve(buses["send"][c], ir[c])[:N] for c in range(2)])

mix = buses["drums"] * 0.9 + buses["bass"] * 0.8 + buses["music"] * 0.8 + buses["sfx"] * 0.9 + wet * 0.6
mix = np.vstack([filt(mix[c], "hp", 28) for c in range(2)])
mix = np.tanh(mix * 1.1) / np.tanh(1.1)
fade = np.ones(N)
fl = int(0.25 * SR)
fade[-fl:] = np.linspace(1, 0, fl) ** 2
mix *= fade
mix /= np.max(np.abs(mix)) / 0.89

sf.write(sys.argv[1] if len(sys.argv) > 1 else "audio/score_raw.wav", mix.T, SR, subtype="PCM_24")
print("wrote score", mix.shape, "peak", float(np.max(np.abs(mix))))
