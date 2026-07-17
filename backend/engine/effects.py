"""Efeitos por imagem, construidos como cadeias de filtro do FFmpeg.

Cada funcao recebe:
  idx   -> indice do input no comando ffmpeg (ex: [3:v])
  dur   -> duracao do clipe em segundos
  w, h  -> resolucao final do video
  fps   -> frames por segundo
E devolve uma string de filtro que produz um stream rotulado [v{idx}],
com exatamente `dur` segundos, no tamanho w x h.

Efeitos disponiveis: zoom_in, zoom_out, slide_left, slide_right,
slide_up, slide_down, grain.
"""

# Efeitos de MOVIMENTO, sorteados aleatoriamente POR IMAGEM.
# (o grao NAO entra aqui: ele e um filtro GLOBAL, aplicado ao video inteiro)
MOVEMENT_EFFECTS = [
    "zoom_in", "zoom_out",
    "slide_left", "slide_right", "slide_up", "slide_down",
]
# mantido por compatibilidade: o pool sorteado por imagem
ALL_EFFECTS = MOVEMENT_EFFECTS


def _cover(w: int, h: int, scale_w=None, scale_h=None) -> str:
    """Escala a imagem para COBRIR o quadro (sem barras), depois corta no centro.
    Se scale_w/scale_h forem passados, escala para um tamanho maior (para dar
    espaco de movimento em slides)."""
    tw = scale_w if scale_w else w
    th = scale_h if scale_h else h
    return (f"scale={tw}:{th}:force_original_aspect_ratio=increase,"
            f"crop={tw}:{th}")


# Fator de super-amostragem do zoom: 1.5x da resolucao de saida.
# (o zoom vai ate 1.30x, entao 1.5x mantem nitidez sem escalar a imagem toda
#  para 4x/8K, o que deixava o render MUITO lento.)
def _zoom_scale(w, h):
    return (w * 3) // 2, (h * 3) // 2


def zoom_in(idx, dur, w, h, fps):
    sw, sh = _zoom_scale(w, h)
    return (
        f"[{idx}:v]{_cover(w, h, sw, sh)},"
        f"zoompan=z='min(1.0+0.0008*on,1.30)':d=1:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"s={w}x{h}:fps={fps},"
        f"trim=duration={dur},setpts=PTS-STARTPTS,setsar=1[v{idx}]"
    )


def zoom_out(idx, dur, w, h, fps):
    sw, sh = _zoom_scale(w, h)
    return (
        f"[{idx}:v]{_cover(w, h, sw, sh)},"
        f"zoompan=z='max(1.30-0.0008*on,1.0)':d=1:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"s={w}x{h}:fps={fps},"
        f"trim=duration={dur},setpts=PTS-STARTPTS,setsar=1[v{idx}]"
    )


def _slide(idx, dur, w, h, fps, axis, direction):
    # Escala maior no eixo do movimento para ter o que "deslizar"
    margin = 0.18  # 18% de folga
    if axis == "x":
        sw, sh = round(w * (1 + margin)), h
        travel = f"(iw-{w})"
        xexpr = f"{travel}*(t/{dur})" if direction > 0 else f"{travel}*(1-t/{dur})"
        yexpr = "0"
    else:
        sw, sh = w, round(h * (1 + margin))
        travel = f"(ih-{h})"
        xexpr = "0"
        yexpr = f"{travel}*(t/{dur})" if direction > 0 else f"{travel}*(1-t/{dur})"
    return (
        f"[{idx}:v]{_cover(w, h, sw, sh)},"
        f"crop={w}:{h}:x='{xexpr}':y='{yexpr}',"
        f"fps={fps},trim=duration={dur},setsar=1[v{idx}]"
    )


def slide_left(idx, dur, w, h, fps):
    return _slide(idx, dur, w, h, fps, "x", +1)


def slide_right(idx, dur, w, h, fps):
    return _slide(idx, dur, w, h, fps, "x", -1)


def slide_up(idx, dur, w, h, fps):
    return _slide(idx, dur, w, h, fps, "y", +1)


def slide_down(idx, dur, w, h, fps):
    return _slide(idx, dur, w, h, fps, "y", -1)


def grain(idx, dur, w, h, fps):
    # (legado) imagem parada + ruido por imagem. O grao agora e GLOBAL;
    # mantido apenas para nao quebrar timelines antigas.
    return (
        f"[{idx}:v]{_cover(w, h)},"
        f"fps={fps},noise=alls=18:allf=t+u,"
        f"trim=duration={dur},setpts=PTS-STARTPTS,setsar=1[v{idx}]"
    )


def global_grain(amount: int) -> str:
    """Filtro de grao/ruido aplicado ao VIDEO INTEIRO (nao por imagem).
    `amount` = intensidade (~5 leve, ~40 forte). Use no stream ja concatenado.
    """
    return f"noise=alls={int(amount)}:allf=t+u"


_BUILDERS = {
    "zoom_in": zoom_in, "zoom_out": zoom_out,
    "slide_left": slide_left, "slide_right": slide_right,
    "slide_up": slide_up, "slide_down": slide_down,
    "grain": grain,
}


def build_effect(name, idx, dur, w, h, fps) -> str:
    """Devolve a cadeia de filtro para o efeito `name`."""
    builder = _BUILDERS.get(name)
    if builder is None:
        raise ValueError(f"Efeito desconhecido: {name}")
    return builder(idx, dur, w, h, fps)
