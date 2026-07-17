"""Gera um overlay de PARTICULAS (o 'Barulho 2' do CapCut): pontinhos de luz
pequenos flutuando devagar, em fundo preto, em loop perfeito.

O video sai em fundo preto -> na hora do render e sobreposto com blend 'screen'
(so soma as luzinhas, sem escurecer a imagem).

O movimento e senoidal (periodico), entao o video faz LOOP sem salto.
"""
import math
import subprocess
import shutil
from pathlib import Path
from PIL import Image

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"


def _glow_sprite(size: int) -> Image.Image:
    """Sprite de brilho radial (branco) com alfa suave."""
    img = Image.new("L", (size, size), 0)
    cx = cy = (size - 1) / 2
    r = size / 2
    px = img.load()
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - cx, y - cy) / r
            v = max(0.0, 1.0 - d)
            px[x, y] = int(255 * (v ** 2.2))   # nucleo forte, borda suave
    return img


def _particles(count, w, h, seed=7):
    """Parametros de cada particula (posicao base, orbita, brilho, tamanho)."""
    rng = __import__("random").Random(seed)
    ps = []
    for _ in range(count):
        ps.append({
            "x": rng.uniform(0, w), "y": rng.uniform(0, h),
            # orbita pequena (movimento flutuante), frequencias inteiras => loop
            "ax": rng.uniform(8, 40), "ay": rng.uniform(8, 40),
            "fx": rng.randint(1, 2), "fy": rng.randint(1, 2),
            "phx": rng.uniform(0, 2 * math.pi), "phy": rng.uniform(0, 2 * math.pi),
            "size": rng.choice([10, 14, 18, 24, 30]),
            "base": rng.uniform(0.35, 1.0),           # brilho maximo
            "ft": rng.randint(1, 3), "pht": rng.uniform(0, 2 * math.pi),  # cintilar
        })
    return ps


def generate(out_path: Path, w=1920, h=1080, fps=30, seconds=12, count=70):
    frames_dir = out_path.parent / "_pframes"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    sprite = _glow_sprite(64)
    ps = _particles(count, w, h)
    total = fps * seconds
    T = seconds

    for f in range(total):
        t = f / fps
        frame = Image.new("RGB", (w, h), (0, 0, 0))
        for p in ps:
            x = p["x"] + p["ax"] * math.sin(2 * math.pi * p["fx"] * t / T + p["phx"])
            y = p["y"] + p["ay"] * math.sin(2 * math.pi * p["fy"] * t / T + p["phy"])
            twinkle = 0.55 + 0.45 * math.sin(2 * math.pi * p["ft"] * t / T + p["pht"])
            alpha = max(0.0, min(1.0, p["base"] * twinkle))
            s = p["size"]
            spr = sprite.resize((s, s)).point(lambda v: int(v * alpha))
            white = Image.new("RGB", (s, s), (255, 255, 255))
            frame.paste(white, (int(x - s / 2), int(y - s / 2)), spr)
        frame.save(frames_dir / f"f_{f:04d}.png")

    # encode em fundo preto (qualidade alta pra os pontos sobreviverem)
    subprocess.run(
        [FFMPEG, "-y", "-hide_banner", "-framerate", str(fps),
         "-i", str(frames_dir / "f_%04d.png"),
         "-c:v", "libx264", "-preset", "slow", "-crf", "16",
         "-pix_fmt", "yuv420p", str(out_path)],
        check=True, capture_output=True)
    shutil.rmtree(frames_dir, ignore_errors=True)
    return out_path


if __name__ == "__main__":
    import sys
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("assets/overlays/particles.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    generate(out)
    print("OK:", out.resolve())
