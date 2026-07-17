"""Benchmark de velocidade: 1080p, com grao, zoom-heavy (pior caso)."""
import sys, time, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.render import Recipe, Clip, render, probe_duration, FFMPEG  # noqa
from tools.make_test_images import make_images  # noqa

PROJ = ROOT.parent
imgs = make_images(PROJ / "assets" / "test_images", 8)
audio = PROJ / "assets" / "bench_audio.m4a"
subprocess.run([FFMPEG, "-y", "-hide_banner", "-f", "lavfi",
                "-i", "sine=frequency=220:duration=120", "-c:a", "aac", str(audio)],
               check=True, capture_output=True)

# ~90s de video: mistura de zoom (pior caso) e slides, com GRAO ligado
effs = ["zoom_in", "zoom_out", "slide_left", "zoom_in", "zoom_out", "slide_up"]
clips, total = [], 0
i = 0
while total < 90:
    d = 5.0
    clips.append(Clip(image=str(imgs[i % len(imgs)]), duration=d, effect=effs[i % len(effs)]))
    total += d; i += 1

rec = Recipe(clips=clips, audio=str(audio), grain=True, grain_amount=18,
             width=1920, height=1080, fps=30,
             output=str(PROJ / "output" / "bench.mp4"))
t0 = time.time()
out = render(rec, verbose=False)
dt = time.time() - t0
vdur = probe_duration(str(out))
print(f"Video: {vdur:.0f}s (1080p, grao ligado, {len(clips)} imagens)")
print(f"Render: {dt:.1f}s  ->  {vdur/dt:.1f}x tempo real")
print(f"Estimativa p/ video de 33min: {33*60/(vdur/dt)/60:.1f} min")
