# Video Factory 🎬

Ferramenta local de **geração de vídeos em lote** para YouTube, usando a GPU
(RTX 5070 + NVENC) para renderizar rápido e de graça.

Você adiciona vários vídeos numa fila (título + roteiro + narração + imagens),
e a ferramenta monta cada um com imagens embaralhadas, efeitos aleatórios,
legendas sincronizadas e música opcional — renderizando tudo em lote.

## Como funciona (visão geral)

```
Roteiro + Título ─┐
                  ├─> Narração (API i33 / ou áudio pronto)
Música (opcional)─┘        │
                          ├─> Legendas sincronizadas (i33 ou Whisper local)
Banco de imagens ─────────┤
                          └─> Motor de edição:
                                • embaralha imagens (único por vídeo no lote)
                                • duração aleatória por imagem (intervalo seu)
                                • efeito aleatório por imagem
                                • sincroniza com a narração
                                        │
                                        └─> FFmpeg + NVENC (RTX 5070) ─> .mp4
```

## Estrutura do projeto

```
video-factory/
├─ backend/
│  ├─ engine/            # motor de render (o coração)
│  │  ├─ render.py       # receita -> comando FFmpeg (NVENC)
│  │  ├─ effects.py      # zoom, slide, grão
│  │  └─ shuffle.py      # embaralhamento único no lote
│  └─ tools/
│     ├─ make_test_images.py   # imagens de teste
│     └─ poc_render.py         # PROVA DE CONCEITO (render em lote)
├─ frontend/             # (a construir) interface visual + timeline
├─ assets/               # suas imagens, músicas, áudios (não vai pro GitHub)
└─ output/               # vídeos renderizados (não vai pro GitHub)
```

## Requisitos (já instalados neste PC)

- Python 3.12, Node.js 24, FFmpeg 7.1 com NVENC, Git
- NVIDIA RTX 5070 (12 GB) com driver atualizado

## Testar a prova de conceito

```bash
python backend/tools/poc_render.py 3 20
# 3 vídeos de ~20s, renderizados na GPU. Saída em output/
```

## Status atual

- [x] Motor de render com NVENC (imagens + áudio -> mp4)
- [x] Embaralhamento único por vídeo no lote
- [x] Duração aleatória por imagem (intervalo configurável)
- [x] Efeitos: zoom in/out, slide (4 direções), grão
- [x] Sincronização com a narração (vídeo cobre todo o áudio)
- [x] Música opcional em volume reduzido
- [x] Sistema de fila (backend FastAPI)
- [x] Interface visual + timeline editável (frontend React/Vite)
- [x] Editor de receita: reordenar, trocar efeito/duração, remover, re-embaralhar
- [x] Render em lote pela interface + prévia do vídeo
- [ ] Legendas estilo CapCut (sincronizadas)
- [ ] Integração com a API i33 (narração)
- [ ] Geração de roteiro por IA (opcional)
- [ ] Render em paralelo (para o alvo de 10 vídeos em ~20 min)

## Como rodar

```powershell
# liga backend + frontend e abre no navegador
powershell -ExecutionPolicy Bypass -File start.ps1
# depois acesse http://localhost:5173
```
```
