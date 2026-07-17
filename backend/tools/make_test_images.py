"""Gera imagens de teste numeradas (para provar a esteira de render).
Cria N imagens 'aleatorias' com cores/tamanhos variados, simulando o banco
de imagens real do usuario.
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Cores base para variar cada imagem (sem depender de random do sistema)
PALETTE = [
    (231, 76, 60), (52, 152, 219), (46, 204, 113), (155, 89, 182),
    (241, 196, 15), (26, 188, 156), (230, 126, 34), (52, 73, 94),
    (236, 64, 122), (0, 150, 136), (121, 85, 72), (63, 81, 181),
]
# Tamanhos variados para testar o "cover" (imagens com aspect ratios diferentes)
SIZES = [(1920, 1080), (1080, 1920), (1200, 1200), (1600, 900), (900, 1600)]


def make_images(out_dir: Path, count: int = 12) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(count):
        color = PALETTE[i % len(PALETTE)]
        w, h = SIZES[i % len(SIZES)]
        img = Image.new("RGB", (w, h), color)
        draw = ImageDraw.Draw(img)
        # gradiente simples para dar textura
        for y in range(0, h, 4):
            shade = int(40 * (y / h))
            draw.line([(0, y), (w, y)], fill=tuple(max(0, c - shade) for c in color))
        # numero grande no centro
        try:
            font = ImageFont.truetype("arialbd.ttf", size=int(min(w, h) * 0.4))
        except OSError:
            font = ImageFont.load_default()
        text = f"{i:02d}"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((w - tw) / 2 - bbox[0], (h - th) / 2 - bbox[1]), text,
                  fill=(255, 255, 255), font=font)
        p = out_dir / f"img_{i:03d}.jpg"
        img.save(p, quality=90)
        paths.append(p)
    return paths


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("assets/test_images")
    made = make_images(out, count)
    print(f"OK: {len(made)} imagens em {out.resolve()}")
