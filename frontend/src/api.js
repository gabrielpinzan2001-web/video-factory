// Comunicacao com o backend (FastAPI)
const j = async (r) => {
  if (!r.ok) throw new Error((await r.text()) || r.statusText)
  return r.json()
}

export const api = {
  health: () => fetch('/api/health').then(j),
  images: () => fetch('/api/images').then(j),
  generateTestImages: () =>
    fetch('/api/images/generate-test', { method: 'POST' }).then(j),
  uploadImages: (files) => {
    const fd = new FormData()
    for (const f of files) fd.append('files', f)
    return fetch('/api/images/upload', { method: 'POST', body: fd }).then(j)
  },
  clearImages: () => fetch('/api/images/clear', { method: 'POST' }).then(j),
  importFolder: (path) =>
    fetch('/api/images/import-folder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    }).then(j),
  sources: () => fetch('/api/images/sources').then(j),

  listAudio: () => fetch('/api/audio').then(j),
  listMusic: () => fetch('/api/music').then(j),
  makeTestAudio: (seconds, name) =>
    fetch('/api/audio/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ seconds, name }),
    }).then(j),
  uploadAudio: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return fetch('/api/upload/audio', { method: 'POST', body: fd }).then(j)
  },
  uploadMusic: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return fetch('/api/upload/music', { method: 'POST', body: fd }).then(j)
  },

  queue: () => fetch('/api/queue').then(j),
  addItem: (payload) =>
    fetch('/api/queue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(j),
  updateItem: (id, item) =>
    fetch(`/api/queue/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(item),
    }).then(j),
  deleteItem: (id) => fetch(`/api/queue/${id}`, { method: 'DELETE' }).then(j),
  applySettingsAll: (patch) =>
    fetch('/api/queue/apply-settings', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ patch }),
    }).then(j),
  build: (id) => fetch(`/api/queue/${id}/build`, { method: 'POST' }).then(j),
  reshuffle: (id) => fetch(`/api/queue/${id}/reshuffle`, { method: 'POST' }).then(j),

  render: (ids) =>
    fetch('/api/render', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_ids: ids || null }),
    }).then(j),
  applyCaptions: (position, enable = true, upper = true, animate = true) =>
    fetch('/api/captions/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ position, upper, animate, enable }),
    }).then(j),
  captionPreviewUrl: (id, position, upper) =>
    `/api/captions/preview?item_id=${id}&position=${position}&upper=${upper ? 'true' : 'false'}&_=${Date.now()}`,

  stopRender: () => fetch('/api/render/stop', { method: 'POST' }).then(j),
  renderStatus: () => fetch('/api/render/status').then(j),

  // ---- ai33 (narração) ----
  ai33KeyStatus: () => fetch('/api/ai33/key').then(j),
  ai33SetKey: (api_key) =>
    fetch('/api/ai33/key', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key }),
    }).then(j),
  ai33Credits: () => fetch('/api/ai33/credits').then(j),
  ai33Voices: (provider, q = '', page = 1) =>
    fetch(`/api/ai33/voices?provider=${provider}&q=${encodeURIComponent(q)}&page=${page}`).then(j),
  ai33Generate: (voice_id, speed, item_ids) =>
    fetch('/api/ai33/generate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ voice_id, speed, item_ids: item_ids || null }),
    }).then(j),
  ai33GenStatus: () => fetch('/api/ai33/generate/status').then(j),
}

// caminho de midia (imagem no disco) -> URL servida pelo backend
export const mediaUrl = (path) => `/media?path=${encodeURIComponent(path)}`
// Efeitos de MOVIMENTO (por imagem). O grão é global, fora daqui.
export const EFFECTS = [
  'zoom_in', 'zoom_out', 'slide_left', 'slide_right',
  'slide_up', 'slide_down',
]
export const EFFECT_LABEL = {
  zoom_in: 'Zoom in', zoom_out: 'Zoom out',
  slide_left: 'Desliza ←', slide_right: 'Desliza →',
  slide_up: 'Desliza ↑', slide_down: 'Desliza ↓',
}
