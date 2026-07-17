"""PROVA DE CONCEITO da esteira de render.

Gera imagens + audio de teste, monta timelines UNICAS para um lote de videos,
sorteia um efeito por imagem e renderiza tudo na RTX 5070 (NVENC), medindo
o tempo. Serve para provar que o pipeline inteiro funciona e e rapido.

Uso:
    python backend/tools/poc_render.py [n_videos] [audio_seg]
"""
import sys
import time
import random
import subprocess
from pathlib import Path

# permite importar o pacote engine estando em qualquer cwd
ROOT = Path(__file__).resolve().parents[1]   # .../backend
sys.path.insert(0, str(ROOT))

from engine.render import Recipe, Clip, render, probe_duration, FFMPEG  # noqa: E402
from engine.effects import ALL_EFFECTS                                  # noqa: E402
from engine.shuffle import build_batch_timelines                        # noqa: E402
from tools.make_test_images import make_images                          # noqa: E402

PROJ = ROOT.parent                       # .../video-factory
ASSETS = PROJ / "assets"
OUT = PROJ / "output"


def make_test_audio(path: Path, seconds: float):
    """Cria um audio de teste (tom senoidal) com duracao conhecida."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [FFMPEG, "-y", "-hide_banner", "-f", "lavfi",
         "-i", f"sine=frequency=220:duration={seconds}",
         "-c:a", "aac", "-b:a", "192k", str(path)],
        check=True, capture_output=True,
    )


def main():
    n_videos = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    audio_sec = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0

    print(f"== POC: {n_videos} videos, ~{audio_sec}s cada ==\n")

    # 1) banco de imagens de teste
    print("Gerando imagens de teste...")
    pool = make_images(ASSETS / "test_images", count=12)

    # 2) audio de narracao de teste (mesma duracao para simplificar)
    print("Gerando audio de teste...")
    audio_path = ASSETS / "test_audio.m4a"
    make_test_audio(audio_path, audio_sec)
    audio_dur = probe_duration(str(audio_path))
    print(f"Audio: {audio_dur:.2f}s\n")

    # 3) timelines UNICAS para o lote (imagens ate o audio acabar, 3-8s cada)
    dur_min, dur_max = 3.0, 8.0
    timelines = build_batch_timelines(
        [str(p) for p in pool],
        audio_durations=[audio_dur] * n_videos,
        dur_min=dur_min, dur_max=dur_max, seed=42,
    )

    # confere unicidade
    sigs = {tuple(img for img, _ in tl) for tl in timelines}
    print(f"Sequencias unicas no lote: {len(sigs)}/{n_videos} "
          f"({'OK' if len(sigs) == n_videos else 'REPETIU!'})\n")

    # 4) renderiza cada video, sorteando um efeito por imagem
    rng = random.Random(7)
    total_render = 0.0
    for vi, tl in enumerate(timelines):
        clips = [Clip(image=img, duration=dur,
                      effect=rng.choice(ALL_EFFECTS)) for img, dur in tl]
        recipe = Recipe(
            clips=clips, audio=str(audio_path),
            width=1920, height=1080, fps=30,
            output=str(OUT / f"poc_video_{vi + 1}.mp4"),
        )
        print(f"Video {vi + 1}: {len(clips)} imagens | "
              f"efeitos: {', '.join(c.effect for c in clips[:4])}...")
        t0 = time.time()
        out = render(recipe, verbose=False)
        dt = time.time() - t0
        total_render += dt
        size_mb = out.stat().st_size / 1e6
        vdur = probe_duration(str(out))
        print(f"  -> {out.name} | {vdur:.1f}s de video | {size_mb:.1f} MB | "
              f"render em {dt:.1f}s ({vdur / dt:.1f}x tempo real)\n")

    print(f"== FIM: {n_videos} videos em {total_render:.1f}s "
          f"({total_render / n_videos:.1f}s por video) ==")


if __name__ == "__main__":
    main()
