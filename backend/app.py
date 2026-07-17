"""Video Factory - Backend (FastAPI).

Gerencia a fila de videos, monta/edita as timelines (receitas) e comanda o
motor de render (FFmpeg + NVENC). Serve tambem os arquivos de saida e o
frontend.
"""
import json
import shutil
import threading
import time
import uuid
from pathlib import Path

import random
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from engine.render import (Recipe, Clip, render, probe_duration,
                           reset_stop, request_stop, RenderCancelled)
from engine.effects import ALL_EFFECTS
from engine.shuffle import build_timeline
from tools.make_test_images import make_images

# ---------------------------------------------------------------- caminhos
ROOT = Path(__file__).resolve().parents[1]        # video-factory/
ASSETS = ROOT / "assets"
IMAGES_DIR = ASSETS / "images"
UPLOAD_AUDIO = ASSETS / "uploads" / "audio"
UPLOAD_MUSIC = ASSETS / "uploads" / "music"
OUTPUT_DIR = ROOT / "output"
STATE_FILE = ROOT / "backend" / "queue_state.json"
BACKUP_FILE = ROOT / "backend" / "queue_state.bak.json"
FRONTEND_DIST = ROOT / "frontend" / "dist"

for d in (IMAGES_DIR, UPLOAD_AUDIO, UPLOAD_MUSIC, OUTPUT_DIR):
    d.mkdir(parents=True, exist_ok=True)

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

# ---------------------------------------------------------------- modelos
class Settings(BaseModel):
    dur_min: float = 3.0
    dur_max: float = 8.0
    width: int = 1920
    height: int = 1080
    fps: int = 30
    music_volume: float = 0.20
    grain: bool = False          # grao/ruido no video inteiro
    grain_amount: int = 28       # intensidade do grao
    particles: bool = False      # overlay de particulas ('Barulho 2')
    captions: bool = False       # legenda queimada no video
    caption_position: str = "middle"   # top|middle|bottom (padrao: meio)
    caption_upper: bool = True         # legenda em MAIUSCULAS (padrao: ligado)
    caption_animate: bool = True       # efeito de entrada na legenda


class ClipModel(BaseModel):
    image: str            # caminho absoluto da imagem
    duration: float
    effect: str


class QueueItem(BaseModel):
    id: str
    title: str = ""
    script: str = ""
    audio: str | None = None       # nome do arquivo em uploads/audio
    music: str | None = None       # nome do arquivo em uploads/music
    settings: Settings = Settings()
    clips: list[ClipModel] = []
    status: str = "draft"          # draft|ready|rendering|done|error
    output: str | None = None      # nome do arquivo em output/
    error: str | None = None
    seed: int | None = None        # semente do embaralhamento (p/ reproduzir)


# ---------------------------------------------------------------- store
class Store:
    def __init__(self):
        self.lock = threading.Lock()
        self.items: dict[str, QueueItem] = {}
        self.load()

    def _read_items(self, path: Path):
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("items", [])
        except Exception:  # noqa: BLE001
            return []

    def load(self):
        items = self._read_items(STATE_FILE) if STATE_FILE.exists() else []
        # se o arquivo principal veio vazio/corrompido, tenta o BACKUP
        # (o backup so e escrito quando ha itens, entao ele preserva o ultimo
        #  estado bom mesmo que algo sobrescreva o principal com vazio).
        if not items and BACKUP_FILE.exists():
            items = self._read_items(BACKUP_FILE)
        for raw in items:
            item = QueueItem(**raw)
            self.items[item.id] = item

    def save(self):
        text = json.dumps({"items": [i.model_dump() for i in self.items.values()]},
                          ensure_ascii=False, indent=2)
        # escrita atomica: grava em .tmp e renomeia (evita arquivo corrompido)
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(STATE_FILE)
        # backup so quando ha itens -> nunca perde tudo por uma escrita vazia
        if self.items:
            BACKUP_FILE.write_text(text, encoding="utf-8")

    def list(self) -> list[QueueItem]:
        return list(self.items.values())

    def get(self, item_id: str) -> QueueItem:
        it = self.items.get(item_id)
        if not it:
            raise HTTPException(404, "Item nao encontrado")
        return it

    def put(self, item: QueueItem):
        self.items[item.id] = item
        self.save()

    def delete(self, item_id: str):
        self.items.pop(item_id, None)
        self.save()


store = Store()

# ---------------------------------------------------------------- helpers
SOURCES_FILE = ROOT / "backend" / "image_sources.json"


def load_sources() -> list[str]:
    """Pastas externas registradas como fonte de imagens (referenciadas no disco)."""
    if SOURCES_FILE.exists():
        try:
            return json.loads(SOURCES_FILE.read_text(encoding="utf-8")).get("folders", [])
        except Exception:  # noqa: BLE001
            return []
    return []


def save_sources(folders: list[str]):
    SOURCES_FILE.write_text(json.dumps({"folders": folders}, ensure_ascii=False, indent=2),
                            encoding="utf-8")


def list_image_pool() -> list[str]:
    """Banco global de imagens = uploads (assets/images) + pastas referenciadas.
    As pastas externas sao lidas DIRETO do disco (sem copiar), o que torna
    'carregar' 2000+ imagens instantaneo."""
    imgs = [p for p in IMAGES_DIR.rglob("*") if p.suffix.lower() in IMG_EXT]
    for folder in load_sources():
        d = Path(folder)
        if d.exists():
            imgs += [p for p in d.rglob("*") if p.suffix.lower() in IMG_EXT]
    # remove duplicatas preservando ordem
    seen, out = set(), []
    for p in sorted(imgs):
        s = str(p)
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def build_timeline_for(item: QueueItem) -> QueueItem:
    """Monta a timeline (receita) do item a partir do audio + configuracoes."""
    if not item.audio:
        raise HTTPException(400, "Item sem audio (narracao). Faca upload do audio.")
    audio_path = UPLOAD_AUDIO / item.audio
    if not audio_path.exists():
        raise HTTPException(400, f"Audio nao encontrado: {item.audio}")

    pool = list_image_pool()
    if not pool:
        raise HTTPException(400, "Nenhuma imagem no banco (assets/images).")

    audio_dur = probe_duration(str(audio_path))
    seed = item.seed if item.seed is not None else uuid.uuid4().int % (2**31)
    rng = random.Random(seed)
    timeline, _sig = build_timeline(
        pool, audio_dur, item.settings.dur_min, item.settings.dur_max, rng)

    # sorteia um efeito por imagem
    clips = [ClipModel(image=img, duration=dur, effect=rng.choice(ALL_EFFECTS))
             for img, dur in timeline]
    item.clips = clips
    item.seed = seed
    item.status = "ready"
    return item


def render_item(item: QueueItem):
    """Renderiza um item (bloqueante). Atualiza status no store."""
    audio_path = UPLOAD_AUDIO / item.audio
    music_path = str(UPLOAD_MUSIC / item.music) if item.music else None
    out_name = f"{item.id}.mp4"
    caption_blocks = []
    if item.settings.captions:
        from engine.captions import transcribe
        caption_blocks = transcribe(str(audio_path))

    recipe = Recipe(
        clips=[Clip(image=c.image, duration=c.duration, effect=c.effect)
               for c in item.clips],
        audio=str(audio_path),
        music=music_path,
        music_volume=item.settings.music_volume,
        grain=item.settings.grain,
        grain_amount=item.settings.grain_amount,
        particles=item.settings.particles,
        captions=item.settings.captions,
        caption_blocks=caption_blocks,
        caption_position=item.settings.caption_position,
        caption_upper=item.settings.caption_upper,
        caption_animate=item.settings.caption_animate,
        width=item.settings.width, height=item.settings.height,
        fps=item.settings.fps,
        output=str(OUTPUT_DIR / out_name),
    )
    render(recipe, verbose=False,
           progress=lambda f: render_state["progress"].__setitem__(item.id, round(f * 100)))
    item.output = out_name
    item.status = "done"
    item.error = None


# ---------------------------------------------------------------- render em lote
render_state = {"running": False, "log": [], "progress": {}}


def run_batch(item_ids: list[str]):
    render_state["running"] = True
    render_state["log"] = []
    reset_stop()   # zera qualquer pedido de parada anterior
    for iid in item_ids:
        item = store.items.get(iid)
        if not item or not item.clips:
            continue
        item.status = "rendering"
        render_state["progress"][item.id] = 0
        store.put(item)
        render_state["log"].append(f"Renderizando: {item.title or item.id}")
        try:
            render_item(item)
            render_state["progress"][item.id] = 100
            render_state["log"].append(f"OK: {item.title or item.id}")
        except RenderCancelled:
            item.status = "ready"   # volta a 'pronto' para poder renderizar de novo
            item.error = None
            render_state["progress"].pop(item.id, None)
            render_state["log"].append(f"PARADO: {item.title or item.id}")
            store.put(item)
            break                    # interrompe o lote inteiro
        except Exception as e:  # noqa: BLE001
            item.status = "error"
            item.error = str(e)[-500:]
            render_state["log"].append(f"ERRO: {item.title or item.id}: {item.error}")
        store.put(item)
    render_state["running"] = False
    render_state["log"].append("Lote finalizado.")


# ---------------------------------------------------------------- app
app = FastAPI(title="Video Factory")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"ok": True, "images": len(list_image_pool())}


@app.get("/api/images")
def get_images(preview: int = 60):
    """Conta o banco global e devolve uma amostra (preview) de miniaturas.
    Nao devolve as 2000 de uma vez para nao pesar o navegador."""
    pool = list_image_pool()
    return {"count": len(pool), "images": pool[:preview]}


@app.post("/api/images/upload")
async def upload_images(files: list[UploadFile] = File(...)):
    """Sobe VARIAS imagens de uma vez para o banco global (assets/images)."""
    saved = 0
    for file in files:
        ext = Path(file.filename).suffix.lower()
        if ext not in IMG_EXT:
            continue
        dest = IMAGES_DIR / file.filename
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        saved += 1
    return {"saved": saved, "count": len(list_image_pool())}


class FolderReq(BaseModel):
    path: str


@app.post("/api/images/import-folder")
def import_folder(req: FolderReq):
    """Aponta uma PASTA do disco como fonte de imagens (lê direto, sem copiar).
    Ideal para bancos grandes (ex: 2000 imagens) — instantâneo."""
    raw = req.path.strip().strip('"').strip("'")
    d = Path(raw)
    if not d.exists() or not d.is_dir():
        raise HTTPException(400, f"Pasta não encontrada: {raw}")
    found = sum(1 for p in d.rglob("*") if p.suffix.lower() in IMG_EXT)
    if found == 0:
        raise HTTPException(400, "Nenhuma imagem encontrada nessa pasta.")
    sources = load_sources()
    key = str(d.resolve())
    if key not in sources:
        sources.append(key)
        save_sources(sources)
    return {"folder": key, "found": found, "count": len(list_image_pool())}


@app.get("/api/images/sources")
def get_sources():
    return {"folders": load_sources()}


@app.post("/api/images/clear")
def clear_images():
    """Esvazia o banco: desvincula as pastas referenciadas e apaga só os
    uploads em assets/images. NÃO apaga suas imagens originais nas pastas."""
    removed = 0
    for p in IMAGES_DIR.rglob("*"):
        if p.suffix.lower() in IMG_EXT and p.is_file():
            p.unlink()
            removed += 1
    save_sources([])   # desvincula pastas externas (originais permanecem no disco)
    return {"removed": removed, "count": len(list_image_pool())}


@app.post("/api/images/generate-test")
def generate_test():
    """Gera imagens de teste direto no banco (para experimentar sem upload)."""
    made = make_images(IMAGES_DIR, count=12)
    return {"generated": len(made), "count": len(list_image_pool())}


@app.post("/api/upload/audio")
async def upload_audio(file: UploadFile = File(...)):
    dest = UPLOAD_AUDIO / file.filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"filename": file.filename, "duration": probe_duration(str(dest))}


@app.post("/api/upload/music")
async def upload_music(file: UploadFile = File(...)):
    dest = UPLOAD_MUSIC / file.filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"filename": file.filename}


@app.get("/api/audio")
def list_audio():
    """Lista os audios de narracao ja disponiveis (uploads/audio)."""
    files = [p.name for p in UPLOAD_AUDIO.glob("*") if p.is_file()]
    out = []
    for name in sorted(files):
        try:
            dur = probe_duration(str(UPLOAD_AUDIO / name))
        except Exception:  # noqa: BLE001
            dur = 0.0
        out.append({"filename": name, "duration": round(dur, 1)})
    return {"audio": out}


@app.get("/api/music")
def list_music():
    files = [p.name for p in UPLOAD_MUSIC.glob("*") if p.is_file()]
    return {"music": sorted(files)}


class TestAudioReq(BaseModel):
    seconds: float = 20.0
    name: str = "narracao_teste"


@app.post("/api/audio/test")
def make_test_audio(req: TestAudioReq):
    """Gera um audio de teste (tom senoidal) para experimentar sem a i33."""
    import subprocess
    from engine.render import FFMPEG
    name = f"{req.name}_{int(req.seconds)}s.m4a"
    dest = UPLOAD_AUDIO / name
    subprocess.run(
        [FFMPEG, "-y", "-hide_banner", "-f", "lavfi",
         "-i", f"sine=frequency=220:duration={req.seconds}",
         "-c:a", "aac", "-b:a", "192k", str(dest)],
        check=True, capture_output=True,
    )
    return {"filename": name, "duration": req.seconds}


@app.get("/api/queue")
def get_queue():
    return {"items": [i.model_dump() for i in store.list()]}


class NewItem(BaseModel):
    title: str = ""
    script: str = ""
    audio: str | None = None
    music: str | None = None
    settings: Settings = Settings()


@app.post("/api/queue")
def add_item(payload: NewItem):
    item = QueueItem(id=uuid.uuid4().hex[:8], **payload.model_dump())
    store.put(item)
    return item.model_dump()


@app.put("/api/queue/{item_id}")
def update_item(item_id: str, payload: QueueItem):
    payload.id = item_id
    store.put(payload)
    return payload.model_dump()


@app.delete("/api/queue/{item_id}")
def delete_item(item_id: str):
    store.delete(item_id)
    return {"ok": True}


class ApplySettings(BaseModel):
    patch: dict   # campos de settings para aplicar em TODOS os itens


@app.post("/api/queue/apply-settings")
def apply_settings_all(req: ApplySettings):
    """Aplica os campos de `patch` nas settings de TODOS os vídeos da fila.
    Ex: {"patch": {"dur_min": 3, "dur_max": 8}} sincroniza a duração em todos."""
    applied = 0
    for item in store.list():
        s = item.settings.model_dump()
        for k, v in req.patch.items():
            if k in s:
                s[k] = v
        item.settings = Settings(**s)
        store.put(item)
        applied += 1
    return {"applied": applied}


@app.post("/api/queue/{item_id}/build")
def build_item(item_id: str):
    item = store.get(item_id)
    item = build_timeline_for(item)
    store.put(item)
    return item.model_dump()


@app.post("/api/queue/{item_id}/reshuffle")
def reshuffle_item(item_id: str):
    """Re-embaralha (nova semente) para gerar uma edicao diferente."""
    item = store.get(item_id)
    item.seed = None
    item = build_timeline_for(item)
    store.put(item)
    return item.model_dump()


class RenderRequest(BaseModel):
    item_ids: list[str] | None = None   # None = renderiza todos os 'ready'


@app.post("/api/render")
def start_render(req: RenderRequest):
    if render_state["running"]:
        raise HTTPException(409, "Ja existe um render em andamento.")
    ids = req.item_ids or [i.id for i in store.list()
                           if i.status in ("ready", "done", "error") and i.clips]
    if not ids:
        raise HTTPException(400, "Nenhum item pronto para renderizar.")
    threading.Thread(target=run_batch, args=(ids,), daemon=True).start()
    return {"started": ids}


class CaptionApply(BaseModel):
    position: str = "middle"        # top|middle|bottom
    upper: bool = True
    animate: bool = True
    enable: bool = True


@app.post("/api/captions/apply")
def captions_apply(req: CaptionApply):
    """Liga/desliga legenda em TODOS os videos do lote (transcreve o audio de
    CADA video individualmente). Como a transcricao fica em cache por audio,
    audios iguais so sao processados 1x."""
    from engine.captions import transcribe
    applied, transcribed = 0, 0
    for item in store.list():
        if not item.audio:
            continue
        if req.enable:
            audio_path = UPLOAD_AUDIO / item.audio
            if audio_path.exists():
                blocks = transcribe(str(audio_path))   # usa cache (por audio)
                transcribed += 1 if blocks else 0
        item.settings.captions = req.enable
        item.settings.caption_position = req.position
        item.settings.caption_upper = req.upper
        item.settings.caption_animate = req.animate
        store.put(item)
        applied += 1
    return {"applied": applied, "position": req.position, "enabled": req.enable}


@app.get("/api/captions/preview")
def captions_preview(item_id: str, position: str = "bottom", upper: bool = False):
    """Gera um frame de PREVIA com uma legenda de exemplo na posicao escolhida."""
    import subprocess
    from engine.captions import transcribe, build_ass
    from engine.render import FFMPEG
    item = store.get(item_id)
    if not item.audio:
        raise HTTPException(400, "Item sem audio.")
    blocks = transcribe(str(UPLOAD_AUDIO / item.audio))
    if not blocks:
        raise HTTPException(400, "Nao consegui transcrever o audio.")
    sample = blocks[min(3, len(blocks) - 1)]
    w, h = item.settings.width, item.settings.height

    tmp = OUTPUT_DIR / f".cap_preview_{item_id}"
    tmp.mkdir(exist_ok=True)
    build_ass([{"start": 0, "end": 5, "text": sample["text"]}],
              str(tmp / "prev.ass"), w, h, position=position, animate=False, upper=upper)

    pool = list_image_pool()
    out_png = tmp / "preview.png"
    args = [FFMPEG, "-y", "-hide_banner"]
    if pool:
        args += ["-i", pool[0],
                 "-filter_complex",
                 f"scale={w}:{h}:force_original_aspect_ratio=increase,"
                 f"crop={w}:{h},ass=prev.ass"]
    else:
        args += ["-f", "lavfi", "-i", f"color=c=gray:s={w}x{h}",
                 "-filter_complex", "ass=prev.ass"]
    args += ["-frames:v", "1", str(out_png)]
    subprocess.run(args, cwd=str(tmp), capture_output=True, text=True)
    if not out_png.exists():
        raise HTTPException(500, "Falha ao gerar previa.")
    return FileResponse(str(out_png), media_type="image/png")


# ---------------------------------------------------------------- ai33 (narracao)
from engine import ai33  # noqa: E402

ai33_state = {"running": False, "log": [], "progress": {}}


class Ai33Key(BaseModel):
    api_key: str


@app.post("/api/ai33/key")
def ai33_set_key(payload: Ai33Key):
    ai33.set_key(payload.api_key)
    return {"configured": True}


@app.get("/api/ai33/key")
def ai33_get_key():
    """Nao devolve a chave; so diz se esta configurada."""
    return {"configured": bool(ai33.get_key())}


@app.get("/api/ai33/credits")
def ai33_credits():
    try:
        return {"credits": ai33.get_credits()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Erro ao consultar creditos: {e}")


@app.get("/api/ai33/voices")
def ai33_voices(provider: str, q: str = "", page: int = 1):
    try:
        return ai33.list_voices(provider, q=q, page=page)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Erro ao listar vozes: {e}")


def run_tts_batch(item_ids: list[str], voice_id: str, speed: float):
    ai33_state["running"] = True
    ai33_state["log"] = []
    for iid in item_ids:
        item = store.items.get(iid)
        if not item or not (item.script or "").strip():
            continue
        ai33_state["progress"][iid] = 0
        ai33_state["log"].append(f"Gerando narração: {item.title or iid}")
        try:
            task_id = ai33.tts(item.script, voice_id, speed)
            url = ai33.wait_task(
                task_id,
                on_progress=lambda p, k=iid: ai33_state["progress"].__setitem__(k, p))
            name = f"tts_{iid}.mp3"
            ai33.download(url, UPLOAD_AUDIO / name)
            item.audio = name
            store.put(item)
            ai33_state["progress"][iid] = 100
            ai33_state["log"].append(f"OK: {item.title or iid}")
        except Exception as e:  # noqa: BLE001
            ai33_state["progress"][iid] = -1
            ai33_state["log"].append(f"ERRO: {item.title or iid}: {str(e)[:200]}")
    ai33_state["running"] = False
    ai33_state["log"].append("Geração de áudios finalizada.")


class TtsRequest(BaseModel):
    voice_id: str
    speed: float = 1.0
    item_ids: list[str] | None = None   # None = todos com roteiro


@app.post("/api/ai33/generate")
def ai33_generate(req: TtsRequest):
    if ai33_state["running"]:
        raise HTTPException(409, "Já existe uma geração de áudios em andamento.")
    if not ai33.get_key():
        raise HTTPException(400, "Configure a API key da ai33 primeiro.")
    ids = req.item_ids or [i.id for i in store.list() if (i.script or "").strip()]
    if not ids:
        raise HTTPException(400, "Nenhum vídeo com roteiro para gerar áudio.")
    threading.Thread(target=run_tts_batch, args=(ids, req.voice_id, req.speed),
                     daemon=True).start()
    return {"started": ids}


@app.get("/api/ai33/generate/status")
def ai33_generate_status():
    return {"running": ai33_state["running"], "log": ai33_state["log"][-30:],
            "progress": ai33_state["progress"]}


@app.post("/api/render/stop")
def stop_render():
    """Para o render em andamento (mata o FFmpeg atual)."""
    if not render_state["running"]:
        return {"stopped": False, "msg": "Nenhum render em andamento."}
    request_stop()
    render_state["log"].append("Parando render...")
    return {"stopped": True}


@app.get("/api/render/status")
def render_status():
    return {
        "running": render_state["running"],
        "log": render_state["log"][-30:],
        "items": [{"id": i.id, "title": i.title, "status": i.status,
                   "output": i.output, "error": i.error,
                   "progress": render_state["progress"].get(i.id)} for i in store.list()],
    }


# arquivos servidos: imagens, saidas
@app.get("/media")
def media(path: str):
    p = Path(path)
    if not p.exists():
        raise HTTPException(404, "Arquivo nao encontrado")
    return FileResponse(str(p))


app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")

# frontend compilado (quando existir)
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="app")
