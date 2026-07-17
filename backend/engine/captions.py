"""Legendas: transcreve o audio (Whisper) e gera legenda ANIMADA (ASS)
estilo CapCut - centralizada, minimalista, com efeito de entrada (pop + fade).

- Transcricao com faster-whisper (roda local; CPU int8 por padrao).
- Resultado fica em cache por audio (nao re-transcreve a cada render).
- Agrupa as palavras em blocos curtos (~4-5 palavras) para o visual CapCut.
- Posicao configuravel: topo / meio / base.
"""
import json
import os
import re
from pathlib import Path


def _clean(text: str) -> str:
    """Limpa espacos estranhos (ex: 'eight -year -old' -> 'eight-year-old')."""
    text = re.sub(r"\s+([-,.!?;:])", r"\1", text)   # tira espaco antes de pontuacao/hifen
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()

_models = {}       # (size, device) -> WhisperModel
_cuda_ready = False


def _setup_cuda():
    """Poe as DLLs do CUDA (cuBLAS/cuDNN, instaladas via pip) no PATH.
    Sem isso o faster-whisper nao acha cublas64_12.dll na GPU."""
    global _cuda_ready
    if _cuda_ready:
        return
    try:
        import nvidia
        for base in list(nvidia.__path__):
            for sub in ("cublas", "cudnn"):
                d = os.path.join(base, sub, "bin")
                if os.path.isdir(d):
                    os.environ["PATH"] = d + os.pathsep + os.environ["PATH"]
    except Exception:  # noqa: BLE001
        pass
    _cuda_ready = True


def _get_model(size: str, device: str):
    from faster_whisper import WhisperModel
    key = (size, device)
    if key not in _models:
        ctype = "float16" if device == "cuda" else "int8"
        _models[key] = WhisperModel(size, device=device, compute_type=ctype)
    return _models[key]


def _run_whisper(audio, size, lang):
    """Tenta na GPU (RTX 5070, ~28x tempo real); se falhar, cai pra CPU."""
    _setup_cuda()
    for device in ("cuda", "cpu"):
        try:
            model = _get_model(size, device)
            segments, _info = model.transcribe(
                str(audio), language=lang, word_timestamps=True, vad_filter=True)
            return list(segments)
        except Exception as e:  # noqa: BLE001
            if device == "cpu":
                raise
            print(f"[captions] GPU indisponivel ({e}); usando CPU.")
    return []


def transcribe(audio_path: str, model_size: str = "small", lang: str | None = None):
    """Transcreve o audio e devolve blocos de legenda: [{start, end, text}].
    Usa cache em <audio>.captions.json."""
    audio = Path(audio_path)
    cache = audio.with_suffix(audio.suffix + ".captions.json")
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))["blocks"]
        except Exception:  # noqa: BLE001
            pass

    segments = _run_whisper(audio, model_size, lang)

    # agrupa palavras em blocos curtos (estilo CapCut)
    blocks = []
    cur, cur_start = [], None
    MAX_WORDS, MAX_CHARS = 5, 30
    for seg in segments:
        for w in (seg.words or []):
            word = w.word.strip()
            if not word:
                continue
            if cur_start is None:
                cur_start = w.start
            cur.append((word, w.end))
            text = " ".join(x[0] for x in cur)
            if len(cur) >= MAX_WORDS or len(text) >= MAX_CHARS:
                blocks.append({"start": round(cur_start, 2),
                               "end": round(cur[-1][1], 2), "text": _clean(text)})
                cur, cur_start = [], None
    if cur:
        blocks.append({"start": round(cur_start, 2), "end": round(cur[-1][1], 2),
                       "text": _clean(" ".join(x[0] for x in cur))})

    cache.write_text(json.dumps({"blocks": blocks}, ensure_ascii=False),
                     encoding="utf-8")
    return blocks


# ---- geracao do arquivo ASS (legenda animada) ----
_ALIGN = {"top": 8, "middle": 5, "bottom": 2}   # numpad ASS (centralizado)


def _ts(t: float) -> str:
    """segundos -> H:MM:SS.cs (formato ASS)."""
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def build_ass(blocks, out_path: str, width: int, height: int,
              position: str = "bottom", font: str = "Arial",
              font_size: int | None = None, animate: bool = True,
              upper: bool = False):
    """Gera o arquivo .ass com as legendas. `animate` liga o efeito de entrada
    (fade+pop); `upper` deixa o texto em MAIUSCULAS."""
    align = _ALIGN.get(position, 2)
    fs = font_size or max(36, height // 18)   # tamanho proporcional
    margin_v = max(40, height // 12)          # distancia da borda
    outline = max(2, fs // 16)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},{fs},&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,{outline},2,{align},60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    # efeito de entrada CapCut: fade rapido + "pop" (escala 82% -> 100%)
    intro = r"{\fad(120,60)\fscx82\fscy82\t(0,140,\fscx100\fscy100)}" if animate else ""
    lines = []
    for b in blocks:
        txt = _esc(b["text"].upper() if upper else b["text"])
        lines.append(
            f"Dialogue: 0,{_ts(b['start'])},{_ts(b['end'])},Cap,,0,0,0,,{intro}{txt}")

    Path(out_path).write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return out_path
