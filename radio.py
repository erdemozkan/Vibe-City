"""
Vibe City radio - five stations of original synth music, generated from scratch.

Every sound is synthesized by this file the first time you run the game: drums
from noise and sine sweeps, bass/pads/leads from simple oscillators, and the
melodies are seeded random walks over common chord progressions. Nothing is
sampled from, or modelled on, any real song.

Needs numpy. Plays through macOS `afplay`. Loops are cached in ./radio/.
"""
import os
import random
import shutil
import subprocess
import threading
import time
import wave

try:
    import numpy as np
except ImportError:  # the game still runs, just silently
    np = None

SR = 22050
VERSION = 2
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "radio")
MINOR = [0, 2, 3, 5, 7, 8, 10]
MAJOR = [0, 2, 4, 5, 7, 9, 11]

def _song(title, seed, prog, bpm=0, key=0):
    return dict(title=title, seed=seed, prog=prog, bpm_shift=bpm, key_shift=key)


# Every song is a different seed (new melody, drum fills, voicing) over its own
# chord progression, tempo and key. Titles are made up for Vibe City.
STATIONS = [
    dict(name="NEON WAVE 88.6", style="synthwave", bpm=100, root=45, scale=MINOR, songs=[
        _song("Midnight Palms", 11, [0, 5, 2, 6]),
        _song("Chrome Horizon", 12, [0, 3, 5, 4], bpm=4, key=2),
        _song("Afterglow Drive", 13, [5, 6, 0, 0], bpm=-6, key=-2)]),
    dict(name="FLAMINGO FM", style="disco", bpm=118, root=41, scale=MINOR, songs=[
        _song("Pastel Suits", 22, [0, 3, 6, 4]),
        _song("Velvet Rollerdisco", 23, [0, 6, 5, 6], bpm=4, key=3),
        _song("Mirrorball Heart", 24, [3, 4, 0, 0], bpm=-2, key=-1)]),
    dict(name="CHROME RADIO", style="dark", bpm=92, root=40, scale=MINOR, songs=[
        _song("Heat Mirage", 33, [0, 0, 5, 4]),
        _song("Steel Rain", 34, [0, 1, 0, 6], bpm=6, key=1),
        _song("Overpass", 35, [0, 5, 3, 4], bpm=-4, key=-2)]),
    dict(name="BAYSIDE SOUL", style="soul", bpm=78, root=43, scale=MAJOR, songs=[
        _song("Low Tide Love", 44, [0, 5, 1, 4]),
        _song("Porch Light", 45, [0, 3, 0, 4], bpm=4, key=2),
        _song("Salt & Honey", 46, [5, 3, 0, 4], bpm=-4, key=-3)]),
    dict(name="STATIC 103", style="chip", bpm=140, root=48, scale=MAJOR, songs=[
        _song("Six Lanes of Sunset", 55, [0, 4, 5, 3]),
        _song("Pixel Coast", 56, [0, 5, 3, 4], bpm=8, key=2),
        _song("Insert Coin Boulevard", 57, [5, 3, 0, 4], bpm=-6, key=-1)]),
]


def song_spec(si, ti):
    """Flatten station si / song ti into the dict render() expects."""
    st, so = STATIONS[si], STATIONS[si]["songs"][ti]
    return dict(name=st["name"], title=so["title"], style=st["style"], scale=st["scale"],
                bpm=st["bpm"] + so["bpm_shift"], root=st["root"] + so["key_shift"],
                prog=so["prog"], seed=so["seed"])

DRUMS = {  # 16 steps per bar
    "synthwave": dict(k=[0, 8], s=[4, 12], h=list(range(0, 16, 2)), oh=[]),
    "disco":     dict(k=[0, 4, 8, 12], s=[4, 12], h=[0, 4, 8, 12], oh=[2, 6, 10, 14]),
    "dark":      dict(k=[0, 3, 8, 10], s=[4, 12], h=list(range(16)), oh=[]),
    "soul":      dict(k=[0, 7, 10], s=[4, 12], h=list(range(0, 16, 2)), oh=[]),
    "chip":      dict(k=[0, 8, 11], s=[4, 12], h=[2, 6, 10, 14], oh=[]),
}
BASS = {  # (step, length in steps, semitones above chord root)
    "synthwave": [(s, 2, 0) for s in range(0, 16, 2)],
    "disco":     [(s, 2, 12 if (s // 2) % 2 else 0) for s in range(0, 16, 2)],
    "dark":      [(s, 1, 0) for s in range(16)],
    "soul":      [(0, 7, 0), (8, 3, 7), (11, 5, 5)],
    "chip":      [(s, 2, [0, 7, 12, 7][(s // 2) % 4]) for s in range(0, 16, 2)],
}
RHYTHMS = [[0, 4, 8, 12], [0, 3, 6, 8, 12], [0, 6, 8, 10, 12], [0, 2, 4, 8, 11], [0, 4, 6, 10]]


# --------------------------------------------------------------------------- synthesis

def midi_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def deg(scale, root, d):
    octave, i = divmod(d, 7)
    return root + 12 * octave + scale[i]


def osc(kind, hz, n, harmonics=8, vibrato=0.0):
    t = np.arange(n) / SR
    if vibrato:
        phase = 2 * np.pi * np.cumsum(hz * (1 + vibrato * np.sin(2 * np.pi * 5.0 * t))) / SR
    else:
        phase = 2 * np.pi * hz * t
    if kind == "sine":
        return np.sin(phase)
    if kind == "tri":
        return 2 / np.pi * np.arcsin(np.sin(phase))
    if kind == "pulse":  # raw, deliberately buzzy (chiptune)
        return np.where((phase / (2 * np.pi)) % 1 < 0.25, 0.5, -0.5)
    out = np.zeros(n)
    step = 1 if kind == "saw" else 2
    for k in range(1, 2 * harmonics if step == 2 else harmonics + 1, step):
        if hz * k > SR / 2.3:
            break
        out += np.sin(phase * k) / k
    return out * (0.6 if kind == "saw" else 0.8)


def env(n, a=0.005, d=0.1, s=0.6, r=0.05):
    e = np.full(n, float(s))
    a_n = min(int(a * SR), n)
    e[:a_n] = np.linspace(0, 1, a_n, endpoint=False)
    d_n = min(int(d * SR), n - a_n)
    if d_n > 0:
        e[a_n:a_n + d_n] = 1 - (1 - s) * np.linspace(0, 1, d_n)
    r_n = min(int(r * SR), n)
    if r_n > 0:
        e[n - r_n:] *= np.linspace(1, 0, r_n)
    return e


class Bus:
    """A stereo buffer that wraps note tails round to the start, so loops are seamless."""

    def __init__(self, n):
        self.n, self.L, self.R = n, np.zeros(n), np.zeros(n)

    def add(self, start, sig, gain=1.0, pan=0.0):
        gl, gr = gain * min(1.0, 1 - pan), gain * min(1.0, 1 + pan)
        start %= self.n
        sig = sig[: self.n]
        first = min(len(sig), self.n - start)
        self.L[start:start + first] += sig[:first] * gl
        self.R[start:start + first] += sig[:first] * gr
        rest = len(sig) - first
        if rest > 0:
            self.L[:rest] += sig[first:] * gl
            self.R[:rest] += sig[first:] * gr

    def echo(self, delay, fb=0.3):
        d = int(delay)
        self.L, self.R = (self.L + fb * np.roll(self.R, d) + fb * fb * np.roll(self.L, 2 * d),
                          self.R + fb * np.roll(self.L, d) + fb * fb * np.roll(self.R, 2 * d))


def kick():
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    return np.sin(2 * np.pi * np.cumsum(45 + 90 * np.exp(-t * 30)) / SR) * np.exp(-t * 9)


def snare(rng):
    n = int(0.22 * SR)
    t = np.arange(n) / SR
    return (rng.uniform(-1, 1, n) * 0.7 + 0.5 * np.sin(2 * np.pi * 190 * t)) * np.exp(-t * 18)


def hat(rng, open_=False):
    n = int((0.18 if open_ else 0.05) * SR)
    noise = np.diff(rng.uniform(-1, 1, n), prepend=0.0)
    return noise * np.exp(-np.arange(n) / SR * (12 if open_ else 70)) * 0.35


def render(st):
    """Synthesize one station's loop; returns float stereo arrays (L, R)."""
    style, scale, root = st["style"], st["scale"], st["root"]
    rng, prnd = np.random.default_rng(st["seed"]), random.Random(st["seed"])
    bars = 16 if st["bpm"] >= 118 else 8
    step = SR * 60.0 / st["bpm"] / 4
    n = int(round(bars * 16 * step))
    drums, bass, pad, lead = Bus(n), Bus(n), Bus(n), Bus(n)

    def at(bar, s):
        return int(round((bar * 16 + s) * step))

    def length(steps):
        return int(steps * step)

    k_sig = kick()
    pat = DRUMS[style]
    for bar in range(bars):
        chord = st["prog"][(bar // 2) % len(st["prog"])]
        croot = deg(scale, root, chord)
        tones = [deg(scale, root + 12, chord + i) for i in (0, 2, 4)]
        # drums
        for s in pat["k"]:
            drums.add(at(bar, s), k_sig, 0.9)
        for s in pat["s"]:
            drums.add(at(bar, s), snare(rng), 0.45 if style != "soul" else 0.3)
        for s in pat["h"]:
            drums.add(at(bar, s), hat(rng), 0.5 if s % 4 else 0.3, pan=0.3)
        for s in pat["oh"]:
            drums.add(at(bar, s), hat(rng, True), 0.45, pan=-0.3)
        # bass
        for s, ln, iv in BASS[style]:
            nn = length(ln)
            hz = midi_hz(croot + iv)
            if style == "soul":
                sig = 0.7 * osc("sine", hz, nn) + 0.3 * osc("tri", hz, nn)
            elif style == "chip":
                sig = osc("tri", hz, nn)
            else:
                sig = osc("saw", hz, nn, harmonics={"dark": 10, "disco": 8}.get(style, 6))
            accent = 1.0 if s % 4 == 0 else 0.8
            bass.add(at(bar, s), sig * env(nn, d=0.08, s=0.7, r=0.02), 0.32 * accent)
        # chords
        if bar % 2 == 0 and style in ("synthwave", "disco", "dark"):
            nn = length(32)
            for m in tones:
                for detune, pan in ((0.997, -0.6), (1.003, 0.6)):
                    sig = osc("saw", midi_hz(m) * detune, nn, harmonics=5)
                    pad.add(at(bar, 0), sig * env(nn, a=0.4, d=0.5, s=0.8, r=0.5), 0.07, pan)
        elif style == "soul":  # soft electric-piano stabs
            for s in (0, 6, 10):
                nn = length(8)
                for m in tones:
                    hz = midi_hz(m)
                    sig = osc("sine", hz, nn) + 0.25 * osc("sine", hz * 2, nn)
                    pad.add(at(bar, s), sig * env(nn, d=1.0, s=0.15, r=0.2), 0.09, prnd.uniform(-0.4, 0.4))
        # arpeggio
        if style in ("synthwave", "chip"):
            for s in range(16):
                m = tones[[0, 1, 2, 1][s % 4]] + (12 if (s // 4) % 2 else 0) + 12
                nn = length(1)
                kind = "pulse" if style == "chip" else "square"
                sig = osc(kind, midi_hz(m), nn, harmonics=4) * env(nn, d=0.05, s=0.3, r=0.02)
                lead.add(at(bar, s), sig, 0.045 if style == "synthwave" else 0.05, 0.4 if s % 2 else -0.4)
        # melody in the second half of every 8 bars
        if bar % 8 >= 4:
            onsets = prnd.choice(RHYTHMS)
            chord_degs = [chord, chord + 2, chord + 4, chord + 7]
            cur = getattr(render, "_cur", 9)
            for i, s in enumerate(onsets):
                cur = max(5, min(14, cur + prnd.choice([-2, -1, -1, 1, 1, 2, 0])))
                if i == 0:
                    cur = min(chord_degs + [c + 7 for c in chord_degs], key=lambda c: abs(c - cur))
                end = onsets[i + 1] if i + 1 < len(onsets) else 16
                nn = length(max(2, end - s))
                m = deg(scale, root + 24 if style != "dark" else root + 12, cur)
                hz = midi_hz(m)
                if style == "soul":
                    sig = osc("sine", hz, nn, vibrato=0.006)
                elif style == "chip":
                    sig = osc("pulse", hz, nn)
                elif style == "dark":
                    sig = osc("saw", hz, nn, harmonics=12)
                elif style == "disco":
                    sig = osc("saw", hz, nn, harmonics=10) + 0.5 * osc("saw", hz * 2, nn, harmonics=5)
                else:
                    sig = osc("square", hz, nn, harmonics=5)
                lead.add(at(bar, s), sig * env(nn, a=0.01, d=0.2, s=0.6, r=0.08), 0.11)
            render._cur = cur
    if style != "chip":
        lead.echo(step * 3, 0.32)
        pad.echo(step * 6, 0.2)
    L = drums.L + bass.L + pad.L + lead.L
    R = drums.R + bass.R + pad.R + lead.R
    L, R = np.tanh(L * 1.3), np.tanh(R * 1.3)
    peak = max(np.abs(L).max(), np.abs(R).max(), 1e-6)
    return L / peak * 0.85, R / peak * 0.85


def slug(text):
    return "".join(c.lower() if c.isalnum() else "-" for c in text).strip("-")


def _base(si, ti):
    sp = song_spec(si, ti)
    return os.path.join(CACHE, "%s--%s-v%d" % (slug(sp["name"]), slug(sp["title"]), VERSION))


def path_for(si, ti):
    """The cached file for a song: compressed .m4a if afconvert worked, else .wav."""
    base = _base(si, ti)
    for ext in (".m4a", ".wav"):
        if os.path.exists(base + ext):
            return base + ext
    return None


def build(si, ti, repeats=2):
    """Render one song (written atomically), compress it if possible, return its path."""
    found = path_for(si, ti)
    if found:
        return found
    os.makedirs(CACHE, exist_ok=True)
    render._cur = 9
    L, R = render(song_spec(si, ti))
    pcm = (np.stack([L, R], axis=1) * 32767).astype("<i2")
    pcm = np.tile(pcm, (repeats, 1))
    base = _base(si, ti)
    tmp = base + ".tmp.wav"
    with wave.open(tmp, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    if shutil.which("afconvert"):  # macOS built-in; AAC is ~10x smaller than WAV
        r = subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", "-b", "128000",
                            tmp, base + ".tmp.m4a"], capture_output=True)
        if r.returncode == 0:
            os.replace(base + ".tmp.m4a", base + ".m4a")
            os.remove(tmp)
            return base + ".m4a"
    os.replace(tmp, base + ".wav")
    return base + ".wav"


# --------------------------------------------------------------------------- playback

class Radio:
    """Plays the current station's songs back to back with afplay, in a background thread."""

    def __init__(self, volume=None):
        if volume is None:
            try:
                volume = float(os.environ.get("VIBE_VOLUME", "0.6"))
            except ValueError:
                volume = 0.6
        self.available = np is not None and shutil.which("afplay") is not None
        self.reason = "" if self.available else ("needs numpy" if np is None else "needs afplay")
        self.index, self.on, self.volume = 0, self.available, volume
        self.track = [0] * len(STATIONS)  # which song each station is on
        self.ready = set()                # (station, song) pairs already built
        self.gen = 0
        self.stopped = False
        self.proc = None
        self.cond = threading.Condition()
        if self.available:
            threading.Thread(target=self._build_all, daemon=True).start()
            threading.Thread(target=self._worker, daemon=True).start()

    @property
    def station(self):
        return STATIONS[self.index]

    @property
    def title(self):
        return self.station["songs"][self.track[self.index]]["title"]

    def status(self):
        if not self.available:
            return "no sound (%s)" % self.reason
        if not self.on:
            return "muted"
        return "" if (self.index, self.track[self.index]) in self.ready else "tuning in..."

    def _terminate_proc_locked(self, wait=False):
        proc = self.proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass
            if wait:
                try:
                    proc.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    try:
                        proc.kill()
                        proc.wait(timeout=0.5)
                    except OSError:
                        pass

    def next_station(self):
        with self.cond:
            self.index = (self.index + 1) % len(STATIONS)
            self.gen += 1
            self._terminate_proc_locked()
            self.cond.notify_all()

    def next_song(self):
        with self.cond:
            songs = len(STATIONS[self.index]["songs"])
            self.track[self.index] = (self.track[self.index] + 1) % songs
            self.gen += 1
            self._terminate_proc_locked()
            self.cond.notify_all()

    def toggle(self):
        if not self.available:
            return
        with self.cond:
            self.on = not self.on
            self.gen += 1
            self._terminate_proc_locked()
            self.cond.notify_all()

    def stop(self):
        with self.cond:
            self.stopped = True
            self.on = False
            self.gen += 1
            self._terminate_proc_locked(wait=True)
            self.proc = None
            self.cond.notify_all()

    def _build_all(self):
        # first songs of every station first (so R is instant), then the rest
        order = [(si, 0) for si in range(len(STATIONS))]
        order += [(si, ti) for ti in range(1, 3) for si in range(len(STATIONS))
                  if ti < len(STATIONS[si]["songs"])]
        for key in order:
            try:
                build(*key)
                with self.cond:
                    self.ready.add(key)
                    self.cond.notify_all()
            except Exception:
                pass

    def _worker(self):
        # Single playback thread ensures at most one afplay process ever runs at a time.
        while True:
            with self.cond:
                while not self.stopped:
                    if not self.on:
                        self.cond.wait()
                        continue
                    si = self.index
                    ti = self.track[si]
                    if (si, ti) not in self.ready:
                        self.cond.wait(timeout=0.1)
                        continue
                    gen = self.gen
                    path = path_for(si, ti)
                    if not path:
                        self.cond.wait(timeout=0.1)
                        continue
                    proc = subprocess.Popen(["afplay", "-v", str(self.volume), path],
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self.proc = proc
                    break
                else:
                    return
            proc.wait()
            with self.cond:
                if self.proc is proc:
                    self.proc = None
                if not self.stopped and self.on and self.gen == gen:
                    self.track[si] = (ti + 1) % len(STATIONS[si]["songs"])
