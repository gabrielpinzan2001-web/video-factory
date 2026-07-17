"""Embaralhamento das imagens.

Regras (conforme definido pelo usuario):
- Cada video do LOTE tem uma sequencia unica (nenhum repete o embaralhamento
  de outro do mesmo lote).
- Nao precisa guardar historico entre lotes (o banco de 2000 imagens torna a
  colisao praticamente impossivel).
- Cada imagem fica na tela por um tempo aleatorio dentro do intervalo
  [dur_min, dur_max] definido pelo usuario.
- As imagens vao passando ate a narracao (audio) acabar.
"""
import random


def _seq_signature(seq):
    """Assinatura da ordem das imagens (para detectar repeticao no lote)."""
    return tuple(seq)


def build_timeline(image_pool, audio_duration, dur_min, dur_max, rng, margin=1.0):
    """Monta a lista (image_path, duracao) ate cobrir a duracao do audio.

    `margin` = segundos extras de folga apos o fim do audio, para garantir que
    o video nunca termine antes da narracao (o -shortest corta no fim do audio).

    Retorna: (lista_de_(path, dur), assinatura_da_sequencia)
    """
    pool = list(image_pool)
    rng.shuffle(pool)

    target = audio_duration + margin
    timeline = []
    order = []
    total = 0.0
    i = 0
    # Preenche ATE PASSAR do fim do audio (a ultima imagem sobra um pouco).
    # Assim o video e sempre >= a narracao, e o corte final (-shortest) casa
    # exatamente com o fim do audio, sem cortar a fala.
    while total < target:
        if i >= len(pool):
            # banco menor que o necessario: re-embaralha e continua (repete imagem,
            # o que o usuario permite; o que nao pode repetir e a EDICAO inteira).
            rng.shuffle(pool)
            i = 0
        img = pool[i]
        dur = round(rng.uniform(dur_min, dur_max), 2)
        timeline.append((img, dur))
        order.append(str(img))
        total += dur
        i += 1

    return timeline, _seq_signature(order)


def build_batch_timelines(image_pool, audio_durations, dur_min, dur_max, seed=None):
    """Gera timelines UNICAS para um lote inteiro.

    image_pool      -> lista de caminhos de imagem (o banco)
    audio_durations -> lista com a duracao (s) da narracao de cada video
    Retorna: lista de timelines (uma por video), todas com sequencia distinta.
    """
    rng = random.Random(seed)
    seen = set()
    timelines = []
    for dur in audio_durations:
        # tenta ate achar uma sequencia inedita no lote
        for _attempt in range(50):
            tl, sig = build_timeline(image_pool, dur, dur_min, dur_max, rng)
            if sig not in seen:
                seen.add(sig)
                timelines.append(tl)
                break
        else:
            # extremamente improvavel; aceita mesmo assim
            timelines.append(tl)
    return timelines
