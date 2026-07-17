"""Motor de render: transforma uma 'receita' de video em um .mp4,
usando FFmpeg + NVENC (aceleracao por hardware da RTX 5070).

Render em SEGMENTOS: as imagens sao divididas em blocos (~40), cada bloco vira
um pedaco de video, e os pedacos sao juntados (copia direta, instantaneo).
Isso mantem cada comando do FFmpeg pequeno -> funciona com qualquer quantidade
de imagens (o Windows limita o tamanho da linha de comando a ~32k chars).
"""
import json
import subprocess
import shutil
import tempfile
import threading
from dataclasses import dataclass, asdict, field
from pathlib import Path

from .effects import build_effect, global_grain
from .captions import build_ass

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

# ---- controle de cancelamento (permite PARAR o render em andamento) ----
_control = {"cancel": False, "proc": None, "lock": threading.Lock()}


class RenderCancelled(Exception):
    """Levantada quando o usuario para o render."""


def reset_stop():
    """Zera o pedido de cancelamento (chamar ao INICIAR um lote)."""
    _control["cancel"] = False


def request_stop():
    """Pede para parar: marca cancelamento e mata o FFmpeg atual."""
    _control["cancel"] = True
    with _control["lock"]:
        p = _control["proc"]
    if p and p.poll() is None:
        p.terminate()

SEGMENT_SIZE = 40   # imagens por segmento (mantem a linha de comando curta)

# overlay de particulas (o 'Barulho 2' do CapCut) - fundo preto, em loop
PARTICLES_OVERLAY = Path(__file__).resolve().parents[2] / "assets" / "overlays" / "particles.mp4"
PARTICLES_LOOP = 12.0   # duracao do loop do overlay (segundos)

# parametros de encode NVENC reaproveitados (segmentos e mux precisam casar)
_NVENC = ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "23",
          "-b:v", "0", "-pix_fmt", "yuv420p"]


@dataclass
class Clip:
    image: str
    duration: float
    effect: str


@dataclass
class Recipe:
    clips: list[Clip]
    audio: str                      # narracao (obrigatorio)
    music: str | None = None        # trilha opcional
    music_volume: float = 0.20      # volume da musica (0-1)
    grain: bool = False             # grao/ruido no video INTEIRO
    grain_amount: int = 28          # intensidade do grao
    particles: bool = False         # overlay de particulas ('Barulho 2')
    captions: bool = False          # legenda queimada no video
    caption_blocks: list = field(default_factory=list)  # [{start,end,text}]
    caption_position: str = "bottom"                    # top|middle|bottom
    caption_upper: bool = False     # legenda em MAIUSCULAS
    caption_animate: bool = True    # efeito de entrada na legenda
    caption_font: str = "Arial"
    caption_font_size: int | None = None
    width: int = 1920
    height: int = 1080
    fps: int = 30
    output: str = "output/video.mp4"

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def probe_duration(path: str) -> float:
    """Duracao (segundos) de um arquivo de midia."""
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def _run(cmd: list[str], cwd: str | None = None):
    if _control["cancel"]:
        raise RenderCancelled()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, cwd=cwd)
    with _control["lock"]:
        _control["proc"] = proc
    _out, err = proc.communicate()
    with _control["lock"]:
        _control["proc"] = None
    if _control["cancel"]:
        raise RenderCancelled()
    if proc.returncode != 0:
        raise RuntimeError("FFmpeg falhou:\n" + (err or "")[-3000:])


def _render_segment(chunk: list[Clip], recipe: Recipe, seg_out: Path, tmp: Path,
                    idx: int, ass_name: str | None = None,
                    particle_offset: float | None = None):
    """Renderiza um bloco de imagens em um pedaco de video (SEM audio).
    Aplica: efeito por imagem -> concatena -> grao -> legenda -> particulas.
    `particle_offset` (segundos) desloca o overlay para manter continuidade
    entre segmentos."""
    w, h, fps = recipe.width, recipe.height, recipe.fps
    args = [FFMPEG, "-y", "-hide_banner"]
    for clip in chunk:
        # -framerate {fps}: a imagem em loop alimenta frames na taxa correta.
        # Sem isso o loop assume 25fps e o zoompan (d=1) encolhe o clipe.
        args += ["-framerate", str(fps), "-loop", "1",
                 "-t", f"{clip.duration}", "-i", str(clip.image)]

    # input do overlay de particulas (loopado, deslocado p/ continuidade,
    # limitado a duracao do segmento p/ o blend nao rodar pra sempre)
    use_particles = particle_offset is not None
    if use_particles:
        seg_dur = sum(c.duration for c in chunk)
        args += ["-stream_loop", "-1", "-ss", f"{particle_offset}",
                 "-t", f"{seg_dur}", "-i", str(PARTICLES_OVERLAY)]
        pidx = len(chunk)

    # grafo: efeito por imagem -> concatena -> (grao) -> (legenda) -> (particulas)
    parts, labels = [], []
    for i, clip in enumerate(chunk):
        parts.append(build_effect(clip.effect, i, clip.duration, w, h, fps))
        labels.append(f"[v{i}]")
    graph = ";".join(parts) + ";" + "".join(labels) + f"concat=n={len(chunk)}:v=1:a=0[vc]"
    cur = "vc"
    if recipe.grain:
        graph += f";[{cur}]{global_grain(recipe.grain_amount)}[vg]"
        cur = "vg"
    if ass_name:
        graph += f";[{cur}]ass={ass_name}[vca]"
        cur = "vca"
    if use_particles:
        # IMPORTANTE: blend em RGB (gbrp). Em YUV o 'screen' mexe na crominancia
        # (U/V) e tinge a imagem inteira de magenta.
        graph += (f";[{pidx}:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
                  f"crop={w}:{h},fps={fps},format=gbrp[pp];"
                  f"[{cur}]format=gbrp[cg];"
                  f"[cg][pp]blend=all_mode=screen:shortest=1[vpar]")
        cur = "vpar"
    graph += f";[{cur}]null[vout]"

    script = tmp / f"filters_{idx}.txt"
    script.write_text(graph, encoding="utf-8")

    args += ["-filter_complex_script", str(script), "-map", "[vout]"]
    args += _NVENC + ["-an", str(seg_out)]   # -an = sem audio no segmento
    _run(args, cwd=str(tmp))   # cwd=tmp: o ass_name relativo funciona sem escape


def _concat_segments(segments: list[Path], tmp: Path, out: Path):
    """Junta os pedacos de video em copia direta (instantaneo)."""
    listfile = tmp / "concat.txt"
    listfile.write_text(
        "".join(f"file '{s.as_posix()}'\n" for s in segments), encoding="utf-8")
    _run([FFMPEG, "-y", "-hide_banner", "-f", "concat", "-safe", "0",
          "-i", str(listfile), "-c", "copy", str(out)])


def _mux_audio(video: Path, recipe: Recipe, out: Path):
    """Junta o video (copia, sem re-encode) com a narracao + musica opcional,
    cortando no fim da narracao (-shortest)."""
    args = [FFMPEG, "-y", "-hide_banner", "-i", str(video), "-i", str(recipe.audio)]
    if recipe.music:
        args += ["-stream_loop", "-1", "-i", str(recipe.music)]
        args += ["-filter_complex",
                 f"[2:a]volume={recipe.music_volume}[mus];"
                 f"[1:a][mus]amix=inputs=2:duration=first:dropout_transition=0[aout]"]
        amap = "[aout]"
    else:
        amap = "1:a"
    args += ["-map", "0:v", "-map", amap,
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
             "-shortest", "-movflags", "+faststart", str(out)]
    _run(args)


def render(recipe: Recipe, verbose: bool = True, progress=None) -> Path:
    """Renderiza a receita (em segmentos) e devolve o caminho do arquivo final.
    `progress` (opcional) e chamado com uma fracao 0..1 conforme avanca."""
    out = Path(recipe.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    clips = recipe.clips
    if not clips:
        raise RuntimeError("Receita sem imagens.")

    def _report(done, total):
        if progress:
            progress(max(0.0, min(1.0, done / total)))

    # tempo de inicio (global) de cada clipe -> para posicionar a legenda
    starts, t = [], 0.0
    for c in clips:
        starts.append(t)
        t += c.duration

    tmp = Path(tempfile.mkdtemp(prefix="vf_", dir=str(out.parent)))
    try:
        # 1) renderiza cada bloco de imagens em um pedaco de video
        segments = []
        chunks = [clips[i:i + SEGMENT_SIZE] for i in range(0, len(clips), SEGMENT_SIZE)]
        total_stages = len(chunks) + 2   # segmentos + concat + mux
        _report(0, total_stages)
        for idx, chunk in enumerate(chunks):
            seg = tmp / f"seg_{idx:03d}.mp4"
            if verbose:
                print(f"  segmento {idx + 1}/{len(chunks)} ({len(chunk)} imagens)...")

            ass_name = None
            if recipe.captions and recipe.caption_blocks:
                i0 = idx * SEGMENT_SIZE
                seg_start = starts[i0]
                seg_dur = sum(c.duration for c in chunk)
                # legendas que caem neste segmento, com tempo deslocado para 0
                sub = []
                for b in recipe.caption_blocks:
                    s = b["start"] - seg_start
                    e = b["end"] - seg_start
                    if e <= 0 or s >= seg_dur:
                        continue
                    sub.append({"start": max(0.0, s), "end": min(seg_dur, e),
                                "text": b["text"]})
                if sub:
                    ass_name = f"cap_{idx:03d}.ass"
                    build_ass(sub, str(tmp / ass_name), recipe.width, recipe.height,
                              position=recipe.caption_position, font=recipe.caption_font,
                              font_size=recipe.caption_font_size,
                              animate=recipe.caption_animate, upper=recipe.caption_upper)

            # particulas: desloca o overlay pelo tempo do segmento (continuidade)
            p_off = None
            if recipe.particles and PARTICLES_OVERLAY.exists():
                p_off = round(starts[idx * SEGMENT_SIZE] % PARTICLES_LOOP, 3)

            _render_segment(chunk, recipe, seg, tmp, idx, ass_name, p_off)
            segments.append(seg)
            _report(idx + 1, total_stages)

        # 2) junta os pedacos (copia direta)
        full = tmp / "full.mp4"
        _concat_segments(segments, tmp, full)
        _report(len(chunks) + 1, total_stages)

        # 3) junta com o audio (narracao + musica), cortando no fim da narracao
        _mux_audio(full, recipe, out)
        _report(total_stages, total_stages)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return out
