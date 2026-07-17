import React, { useEffect, useState, useCallback, useRef } from 'react'
import { api, mediaUrl } from './api.js'
import Timeline from './Timeline.jsx'
import Ai33Panel from './Ai33Panel.jsx'

export default function App() {
  const [items, setItems] = useState([])
  const [selId, setSelId] = useState(null)
  const [images, setImages] = useState(0)
  const [imageList, setImageList] = useState([])
  const [sources, setSources] = useState([])
  const [folderPath, setFolderPath] = useState('')
  const [showBank, setShowBank] = useState(true)
  const [audios, setAudios] = useState([])
  const [musics, setMusics] = useState([])
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState('')
  const [capPreview, setCapPreview] = useState('')
  const [capLoading, setCapLoading] = useState(false)
  const [view, setView] = useState('editor')            // 'editor' | 'ai33'
  const [selectedVoice, setSelectedVoice] = useState(null)
  const downloadedRef = useRef(null)                    // controla download automático

  const sel = items.find((i) => i.id === selId) || null

  const refresh = useCallback(async () => {
    const [q, im, au, mu, sr] = await Promise.all([
      api.queue(), api.images(), api.listAudio(), api.listMusic(), api.sources(),
    ])
    setItems(q.items)
    setImages(im.count)
    setImageList(im.images)
    setSources(sr.folders)
    setAudios(au.audio)
    setMusics(mu.music)
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const [polling, setPolling] = useState(false)

  // Consulta o status do render SÓ enquanto há um render em andamento.
  // Quando idle, a interface fica quieta (não fica pingando o servidor).
  useEffect(() => {
    if (!polling) return
    const t = setInterval(async () => {
      const s = await api.renderStatus()
      setStatus(s)
      refresh()
      if (!s.running) setPolling(false)   // acabou: para de pingar
    }, 1500)
    return () => clearInterval(t)
  }, [polling, refresh])

  // download automático assim que um vídeo termina de renderizar
  useEffect(() => {
    if (!status?.items) return
    const done = status.items.filter((i) => i.status === 'done' && i.output)
    if (downloadedRef.current === null) {
      // primeira leitura: marca os já prontos como "vistos" (não baixa antigos)
      downloadedRef.current = new Set(done.map((i) => i.output))
      return
    }
    for (const it of done) {
      if (downloadedRef.current.has(it.output)) continue
      downloadedRef.current.add(it.output)
      const name = (it.title || it.id).replace(/[^\w\- ]+/g, '').trim().slice(0, 60) || it.id
      const a = document.createElement('a')
      a.href = `/output/${it.output}`
      a.download = name + '.mp4'
      document.body.appendChild(a); a.click(); a.remove()
    }
  }, [status])

  const patchSel = async (patch) => {
    const updated = { ...sel, ...patch }
    setItems(items.map((i) => (i.id === sel.id ? updated : i)))
    await api.updateItem(sel.id, updated)
  }

  const addItem = async () => {
    const it = await api.addItem({ title: `Vídeo ${items.length + 1}` })
    await refresh()
    setSelId(it.id)
  }

  const genTestImages = async () => {
    setBusy('Gerando imagens de teste...')
    await api.generateTestImages(); await refresh(); setBusy('')
  }
  const uploadImages = async (files) => {
    if (!files?.length) return
    setBusy(`Enviando ${files.length} imagens...`)
    const r = await api.uploadImages(files)
    await refresh(); setBusy('')
    alert(`${r.saved} imagens enviadas. Banco agora tem ${r.count}.`)
  }
  const clearImages = async () => {
    if (!confirm('Esvaziar o banco? (isso desvincula as pastas e apaga só os envios avulsos — suas imagens originais NÃO são apagadas)')) return
    setBusy('Limpando banco...')
    await api.clearImages(); await refresh(); setBusy('')
  }
  const importFolder = async () => {
    if (!folderPath.trim()) return
    setBusy('Lendo pasta...')
    try {
      const r = await api.importFolder(folderPath)
      await refresh(); setBusy('')
      alert(`Pasta vinculada! ${r.found} imagens encontradas. Banco agora: ${r.count}.`)
      setFolderPath('')
    } catch (e) {
      setBusy(''); alert('Erro: ' + e.message)
    }
  }
  const genTestAudio = async () => {
    setBusy('Gerando áudio de teste...')
    const a = await api.makeTestAudio(20, 'narracao')
    await refresh()
    if (sel) await patchSel({ audio: a.filename })
    setBusy('')
  }

  const applyDurationAll = async () => {
    setBusy('Aplicando duração a todos os vídeos...')
    try {
      const r = await api.applySettingsAll({
        dur_min: sel.settings.dur_min, dur_max: sel.settings.dur_max,
      })
      await refresh(); setBusy('')
      alert(`Duração ${sel.settings.dur_min}–${sel.settings.dur_max}s aplicada em ${r.applied} vídeo(s).`)
    } catch (e) { setBusy(''); alert('Erro: ' + e.message) }
  }

  const build = async () => {
    setBusy('Montando timeline...')
    try { const it = await api.build(sel.id); setItems(items.map((i) => i.id === it.id ? it : i)) }
    catch (e) { alert('Erro: ' + e.message) }
    setBusy('')
  }
  const reshuffle = async () => {
    setBusy('Re-embaralhando...')
    const it = await api.reshuffle(sel.id)
    setItems(items.map((i) => (i.id === it.id ? it : i)))
    setBusy('')
  }
  const clearTimeline = async () => {
    if (!confirm('Limpar a timeline deste vídeo? (os clipes são apagados; o banco de imagens não é afetado)')) return
    await patchSel({ clips: [], status: 'draft' })
  }

  const setCaptionPos = (pos) =>
    patchSel({ settings: { ...sel.settings, caption_position: pos } })
  const previewCaption = () => {
    setCapLoading(true)
    setCapPreview(api.captionPreviewUrl(sel.id, sel.settings.caption_position || 'middle',
      sel.settings.caption_upper))
  }
  const applyCaptionsAll = async () => {
    setBusy('Aplicando legendas no lote (transcrevendo o áudio)…')
    try {
      const r = await api.applyCaptions(
        sel.settings.caption_position || 'middle', true,
        sel.settings.caption_upper !== false, sel.settings.caption_animate !== false)
      await refresh(); setBusy('')
      alert(`Legendas ativadas em ${r.applied} vídeo(s).`)
    } catch (e) { setBusy(''); alert('Erro: ' + e.message) }
  }
  const disableCaptionsAll = async () => {
    setBusy('Removendo legendas…')
    try { await api.applyCaptions('bottom', false); await refresh() } catch (e) { alert('Erro: ' + e.message) }
    setCapPreview(''); setBusy('')
  }

  const renderAll = async () => {
    try { await api.render(null); setPolling(true) } catch (e) { alert('Erro: ' + e.message) }
  }
  const renderOne = async () => {
    try { await api.render([sel.id]); setPolling(true) } catch (e) { alert('Erro: ' + e.message) }
  }
  const stopRender = async () => {
    setBusy('Parando render...')
    try { await api.stopRender() } catch (e) { alert('Erro: ' + e.message) }
    setBusy('')
  }

  const del = async (id) => {
    await api.deleteItem(id); if (selId === id) setSelId(null); refresh()
  }

  const statusOf = (id) => status?.items?.find((s) => s.id === id)?.status
  const outputOf = (id) => status?.items?.find((s) => s.id === id)?.output
  const progressOf = (id) => status?.items?.find((s) => s.id === id)?.progress

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">🎬 Video Factory</div>
        <nav className="tabs">
          <button className={'tab' + (view === 'editor' ? ' active' : '')} onClick={() => setView('editor')}>Editor</button>
          <button className={'tab' + (view === 'ai33' ? ' active' : '')} onClick={() => setView('ai33')}>🎙️ Narração</button>
        </nav>
        <div className="stats">
          <button className="bank-toggle" onClick={() => setShowBank(!showBank)}>
            🖼️ Banco: {images} imagens {showBank ? '▲' : '▼'}
          </button>
          <span>{items.length} na fila</span>
          {status?.running && <span className="running">● renderizando…</span>}
        </div>
        <div className="top-actions">
          <button className="primary" onClick={renderAll} disabled={status?.running}>
            ▶ Renderizar lote
          </button>
          {status?.running && (
            <button className="danger" onClick={stopRender}>⏹ Parar</button>
          )}
        </div>
      </header>

      {/* -------- banco de imagens global -------- */}
      {showBank && (
        <section className="bank">
          <div className="bank-head">
            <div className="bank-title">
              Banco de imagens <b>({images})</b>
              <span className="bank-hint">
                Suba todas as suas imagens aqui uma vez. Cada vídeo embaralha a partir delas.
              </span>
            </div>
            <div className="bank-actions">
              <button onClick={genTestImages}>Gerar imagens teste</button>
              <button className="danger" onClick={clearImages} disabled={!images && !sources.length}>
                🗑 Limpar
              </button>
            </div>
          </div>

          {/* forma PRINCIPAL: apontar a pasta no disco (instantâneo p/ 2000+ imgs) */}
          <div className="bank-import">
            <input
              type="text" className="folder-input"
              placeholder="Cole aqui o caminho da pasta com suas imagens. Ex: E:\\Imagens\\MeuBanco"
              value={folderPath}
              onChange={(e) => setFolderPath(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && importFolder()}
            />
            <button className="primary" onClick={importFolder}>📁 Importar pasta</button>
            <label className="upl small-upl" title="Só para poucas imagens">
              ⬆ Enviar avulsas
              <input type="file" accept="image/*" multiple hidden
                onChange={(e) => uploadImages(e.target.files)} />
            </label>
          </div>

          {sources.length > 0 && (
            <div className="bank-sources">
              Pastas vinculadas: {sources.map((s, i) => <code key={i}>{s}</code>)}
            </div>
          )}

          {images === 0 && (
            <div className="bank-empty">
              Banco vazio. Cole o caminho da sua pasta de imagens acima e clique <b>Importar pasta</b>.
            </div>
          )}
          {images > 0 && (
            <div className="bank-grid">
              {imageList.map((img) => (
                <img key={img} src={mediaUrl(img)} alt="" />
              ))}
              {images > imageList.length && (
                <div className="bank-more">+{images - imageList.length}<br />mais</div>
              )}
            </div>
          )}
        </section>
      )}

      <div className="body">
        {/* -------- fila -------- */}
        <aside className="queue">
          <div className="queue-head">
            <span>Fila</span>
            <button onClick={addItem}>+ Adicionar</button>
          </div>
          {items.map((it) => {
            const st = statusOf(it.id) || it.status
            const pct = progressOf(it.id)
            return (
              <div
                key={it.id}
                className={'q-item' + (it.id === selId ? ' active' : '')}
                onClick={() => setSelId(it.id)}
              >
                <div className="q-row">
                  <div className="q-title">{it.title || '(sem título)'}</div>
                  <div className={'q-status s-' + st}>{st}</div>
                  <button className="q-del" onClick={(e) => { e.stopPropagation(); del(it.id) }}>✕</button>
                </div>
                {st === 'rendering' && (
                  <div className="q-prog">
                    <div className="q-prog-bar" style={{ width: (pct || 0) + '%' }} />
                    <span className="q-prog-pct">{pct != null ? pct + '%' : '…'}</span>
                  </div>
                )}
              </div>
            )
          })}
          {!items.length && <div className="empty">Adicione um vídeo à fila.</div>}
        </aside>

        {/* -------- editor -------- */}
        <main className="editor">
          {view === 'ai33' && (
            <Ai33Panel items={items} onGenerated={refresh}
              selectedVoice={selectedVoice} setSelectedVoice={setSelectedVoice} />
          )}
          {view === 'editor' && !sel && <div className="placeholder">Selecione ou adicione um vídeo na fila.</div>}
          {view === 'editor' && sel && (
            <>
              <div className="field">
                <label>Título</label>
                <input value={sel.title} onChange={(e) => patchSel({ title: e.target.value })} />
              </div>
              <div className="field">
                <label>Roteiro</label>
                <textarea rows={4} value={sel.script}
                  onChange={(e) => patchSel({ script: e.target.value })}
                  placeholder="Cole aqui o roteiro do vídeo…" />
              </div>

              <div className="row">
                <div className="field">
                  <label>Narração (áudio)</label>
                  <div className="inline">
                    {sel.audio
                      ? <span className="audio-current">🔊 {sel.audio}
                          <button className="linkbtn" onClick={() => patchSel({ audio: null })}>remover</button>
                        </span>
                      : <span className="audio-none">Sem áudio — gere na aba 🎙️ Narração, ou:</span>}
                    <label className="upl">
                      Enviar
                      <input type="file" accept="audio/*" hidden
                        onChange={async (e) => {
                          const f = e.target.files[0]; if (!f) return
                          setBusy('Enviando áudio...')
                          const a = await api.uploadAudio(f); await refresh()
                          await patchSel({ audio: a.filename }); setBusy('')
                        }} />
                    </label>
                    <button onClick={genTestAudio}>Áudio teste</button>
                  </div>
                </div>

                <div className="field">
                  <label>Música (opcional)</label>
                  <div className="inline">
                    <select value={sel.music || ''} onChange={(e) => patchSel({ music: e.target.value || null })}>
                      <option value="">— nenhuma —</option>
                      {musics.map((m) => <option key={m} value={m}>{m}</option>)}
                    </select>
                    <label className="upl">
                      Enviar
                      <input type="file" accept="audio/*" hidden
                        onChange={async (e) => {
                          const f = e.target.files[0]; if (!f) return
                          setBusy('Enviando música...')
                          const m = await api.uploadMusic(f); await refresh()
                          await patchSel({ music: m.filename }); setBusy('')
                        }} />
                    </label>
                  </div>
                </div>
              </div>

              <div className="row settings">
                <div className="field small">
                  <label>Duração mín. (s)</label>
                  <input type="number" min="0.5" step="0.5" value={sel.settings.dur_min}
                    onChange={(e) => patchSel({ settings: { ...sel.settings, dur_min: Number(e.target.value) } })} />
                </div>
                <div className="field small">
                  <label>Duração máx. (s)</label>
                  <input type="number" min="1" step="0.5" value={sel.settings.dur_max}
                    onChange={(e) => patchSel({ settings: { ...sel.settings, dur_max: Number(e.target.value) } })} />
                </div>
                <div className="field small">
                  <label>&nbsp;</label>
                  <button onClick={applyDurationAll}
                    title="Aplicar esta duração (mín/máx) em TODOS os vídeos da fila">
                    ↔ Aplicar duração a todos
                  </button>
                </div>
                <div className="field small">
                  <label>Resolução</label>
                  <select value={sel.settings.width + 'x' + sel.settings.height}
                    onChange={(e) => {
                      const [w, h] = e.target.value.split('x').map(Number)
                      patchSel({ settings: { ...sel.settings, width: w, height: h } })
                    }}>
                    <option value="1920x1080">1080p (16:9)</option>
                    <option value="1080x1920">Vertical (9:16)</option>
                    <option value="1280x720">720p (16:9)</option>
                  </select>
                </div>
                <div className="field small">
                  <label>Partículas (Barulho 2)</label>
                  <label className="chk">
                    <input type="checkbox" checked={!!sel.settings.particles}
                      onChange={(e) => patchSel({ settings: { ...sel.settings, particles: e.target.checked } })} />
                    Ativar
                  </label>
                </div>
                <div className="field small">
                  <label>Grão (ruído)</label>
                  <div className="inline grain-ctl">
                    <label className="chk">
                      <input type="checkbox" checked={!!sel.settings.grain}
                        onChange={(e) => patchSel({ settings: { ...sel.settings, grain: e.target.checked } })} />
                      Ativar
                    </label>
                    {sel.settings.grain && (
                      <input type="range" min="10" max="60" step="1"
                        value={sel.settings.grain_amount ?? 28}
                        title={'Intensidade: ' + (sel.settings.grain_amount ?? 28)}
                        onChange={(e) => patchSel({ settings: { ...sel.settings, grain_amount: Number(e.target.value) } })} />
                    )}
                  </div>
                </div>
              </div>

              <div className="cap-panel">
                <div className="cap-head">
                  <span className="cap-title">📝 Legendas (estilo CapCut)</span>
                  {sel.settings.captions
                    ? <span className="cap-on">● ativadas ({sel.settings.caption_position})</span>
                    : <span className="cap-off">desativadas</span>}
                </div>
                <div className="cap-ctl">
                  <label>Posição:</label>
                  <select value={sel.settings.caption_position || 'middle'}
                    onChange={(e) => setCaptionPos(e.target.value)}>
                    <option value="top">Cima</option>
                    <option value="middle">Meio</option>
                    <option value="bottom">Baixo</option>
                  </select>
                  <label className="chk">
                    <input type="checkbox" checked={!!sel.settings.caption_upper}
                      onChange={(e) => patchSel({ settings: { ...sel.settings, caption_upper: e.target.checked } })} />
                    MAIÚSCULAS
                  </label>
                  <label className="chk">
                    <input type="checkbox" checked={sel.settings.caption_animate !== false}
                      onChange={(e) => patchSel({ settings: { ...sel.settings, caption_animate: e.target.checked } })} />
                    Animação
                  </label>
                  <button onClick={previewCaption}>👁 Prévia</button>
                  <button className="primary" onClick={applyCaptionsAll}>
                    Aplicar legenda em TODO o lote
                  </button>
                  {sel.settings.captions &&
                    <button className="danger" onClick={disableCaptionsAll}>Tirar legendas</button>}
                </div>
                {(capLoading || capPreview) && (
                  <div className="cap-preview">
                    {capLoading && <div className="cap-loading">Gerando prévia (transcrevendo o áudio na primeira vez)…</div>}
                    {capPreview && (
                      <img src={capPreview} alt="prévia da legenda"
                        onLoad={() => setCapLoading(false)}
                        onError={() => { setCapLoading(false); setCapPreview('') }} />
                    )}
                  </div>
                )}
              </div>

              <div className="tl-actions">
                <button className="primary" onClick={build}>Montar timeline</button>
                {sel.clips?.length > 0 && <button onClick={reshuffle}>🔀 Re-embaralhar</button>}
                {sel.clips?.length > 0 && (
                  <button className="danger" onClick={clearTimeline}>🗑 Limpar timeline</button>
                )}
                {sel.clips?.length > 0 && (
                  <button className="ok" onClick={renderOne} disabled={status?.running}>▶ Renderizar este</button>
                )}
              </div>

              <Timeline clips={sel.clips || []} onChange={(clips) => patchSel({ clips })} />

              {outputOf(sel.id) && (
                <div className="preview">
                  <label>Prévia do vídeo renderizado</label>
                  <video src={`/output/${outputOf(sel.id)}`} controls width="480" />
                </div>
              )}
              {sel.error && <div className="err">Erro: {sel.error}</div>}
            </>
          )}
        </main>
      </div>

      {busy && <div className="busy">{busy}</div>}
      {status?.log?.length > 0 && (
        <div className="log">{status.log.slice(-4).map((l, i) => <div key={i}>{l}</div>)}</div>
      )}
    </div>
  )
}
