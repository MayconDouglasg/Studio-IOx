"""Measure the beat grid of the master and write beats.json.
Usage: python -I tools/analyze.py audio/score.wav beats.json
"""
import json
import sys
import numpy as np
import librosa

src, dst = sys.argv[1], sys.argv[2]
y, sr = librosa.load(src, sr=48000, mono=True)
hop = 256
env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
tempo, frames = librosa.beat.beat_track(onset_envelope=env, sr=sr, hop_length=hop,
                                        start_bpm=120, tightness=300, trim=False)
beats = librosa.frames_to_time(frames, sr=sr, hop_length=hop)
onsets = librosa.onset.onset_detect(onset_envelope=env, sr=sr, hop_length=hop, units="time", backtrack=True)

# Fit a straight grid t = offset + k * period through the measured beats.
p0 = 60.0 / float(np.atleast_1d(tempo)[0])
k = np.round((beats - beats[0]) / p0)
A = np.vstack([np.ones_like(k), k]).T
(c0, period), *_ = np.linalg.lstsq(A, beats, rcond=None)
# Re-anchor so beat index 0 is the first grid line at or after t=0.
k0 = np.ceil(-c0 / period - 1e-6)
offset = c0 + k0 * period
# Snap phase to the nearest strong onset (librosa beats lag a few ms).
near = onsets[np.argmin(np.abs(onsets - offset))] if len(onsets) else offset
if abs(near - offset) < 0.03:
    offset = float(near)
# Sample-accurate phase: find each beat's transient attack in the waveform
# (first sample above 40% of the local peak within -45..+15 ms) and take the median shift.
shifts = []
w = int(0.001 * sr)
envw = np.convolve(np.abs(y), np.ones(w) / w, mode="same")
for i in range(int((15.0 - offset) / period) + 1):
    g = offset + i * period
    a, b = max(0, int((g - 0.03) * sr)), int((g + 0.015) * sr)
    seg = envw[a:b]
    if len(seg) < 10:
        continue
    d = np.diff(seg)
    shifts.append((a + int(np.argmax(d))) / sr - g)
if shifts:
    offset = float(offset + np.median(shifts))
grid = [round(offset + i * period, 5) for i in range(int((15.0 - offset) / period) + 1)]
resid = beats - (offset + np.round((beats - offset) / period) * period)  # vs onset-envelope beats (lag ~20ms expected)
out = {
    "bpm": round(60.0 / period, 4),
    "period": round(float(period), 6),
    "offset": round(float(offset), 5),
    "measured": [round(float(b), 5) for b in beats],
    "grid": grid,
    "residual_ms": round(float(np.sqrt(np.mean(resid ** 2)) * 1000), 2),
}
json.dump(out, open(dst, "w"), indent=1)
print(f"bpm {out['bpm']}  offset {out['offset']}s  beats measured {len(beats)}  rms residual {out['residual_ms']} ms")
