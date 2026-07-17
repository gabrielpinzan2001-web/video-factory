"""Teste rapido: confirma que a duracao do video renderizado bate com a soma
das duracoes dos clipes (foco no efeito de zoom, que estava encolhendo)."""
import sys, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.render import Recipe, Clip, render, probe_duration, FFMPEG  # noqa
from tools.make_test_images import make_images  # noqa

PROJ = ROOT.parent
imgs = make_images(PROJ / "assets" / "test_images", 8)
audio = PROJ / "assets" / "test_dur_audio.m4a"
subprocess.run([FFMPEG, "-y", "-hide_banner", "-f", "lavfi",
                "-i", "sine=frequency=220:duration=60", "-c:a", "aac", str(audio)],
               check=True, capture_output=True)

# 10 clipes de zoom com duracoes variadas (mistura zoom_in/out + 1 slide + 1 grao-via-mov)
plan = [("zoom_in", 5.0), ("zoom_out", 4.0), ("zoom_in", 6.5), ("zoom_out", 3.0),
        ("slide_left", 5.5), ("zoom_in", 4.5), ("zoom_out", 7.0), ("slide_up", 3.5),
        ("zoom_in", 5.0), ("zoom_out", 6.0)]
clips = [Clip(image=str(imgs[i % len(imgs)]), duration=d, effect=e)
         for i, (e, d) in enumerate(plan)]
expected = sum(d for _, d in plan)

rec = Recipe(clips=clips, audio=str(audio), width=1280, height=720, fps=30,
             output=str(PROJ / "output" / "test_duration.mp4"))
out = render(rec, verbose=True)
got = probe_duration(str(out))
print(f"\nEsperado (soma dos clipes): {expected:.2f}s")
print(f"Video renderizado:          {got:.2f}s")
print(f"Diferenca:                  {abs(got-expected):.2f}s  ->  "
      f"{'OK' if abs(got-expected) < 0.5 else 'AINDA ERRADO'}")
