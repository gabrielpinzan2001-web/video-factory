import React, { useEffect, useRef, useState } from 'react'
import { api } from './api.js'

const PROVIDERS = ['elevenlabs', 'minimax', 'fishaudio', 'edge', 'kokoro', 'clone', 'vbee']

export default function Ai33Panel({ items, onGenerated, selectedVoice, setSelectedVoice }) {
  const [configured, setConfigured] = useState(false)
  const [keyInput, setKeyInput] = useState('')
  const [credits, setCredits] = useState(null)
  const [provider, setProvider] = useState('elevenlabs')
  const [query, setQuery] = useState('')
  const [voices, setVoices] = useState([])
  const [loading, setLoading] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [gen, setGen] = useState(null)
  const [msg, setMsg] = useState('')
  const audioRef = useRef(null)

  useEffect(() => {
    api.ai33KeyStatus().then((r) => setConfigured(r.configured)).catch(() => {})
  }, [])

  useEffect(() => {
    if (configured) refreshCredits()
  }, [configured])

  const refreshCredits = () =>
    api.ai33Credits().then((r) => setCredits(r.credits)).catch(() => setCredits(null))

  const saveKey = async () => {
    if (!keyInput.trim()) return
    setMsg('Salvando chave...')
    try {
      await api.ai33SetKey(keyInput.trim())
      setConfigured(true); setKeyInput(''); setMsg('Chave salva!')
      refreshCredits()
    } catch (e) { setMsg('Erro: ' + e.message) }
  }

  const loadVoices = async () => {
    setLoading(true); setMsg('')
    try {
      const r = await api.ai33Voices(provider, query)
      setVoices(r.data || [])
      if (!r.data?.length) setMsg('Nenhuma voz encontrada.')
    } catch (e) { setMsg('Erro: ' + e.message) }
    setLoading(false)
  }

  const playPreview = (url) => {
    if (!url) return
    if (audioRef.current) { audioRef.current.pause() }
    audioRef.current = new Audio(url)
    audioRef.current.play().catch(() => setMsg('Não consegui tocar a prévia.'))
  }

  // polling do progresso da geração
  useEffect(() => {
    if (!gen?.running) return
    const t = setInterval(async () => {
      const s = await api.ai33GenStatus()
      setGen(s)
      if (!s.running) { clearInterval(t); onGenerated?.(); refreshCredits() }
    }, 2000)
    return () => clearInterval(t)
  }, [gen?.running])

  const withScript = items.filter((i) => (i.script || '').trim())

  const generateAll = async () => {
    if (!selectedVoice) { setMsg('Selecione uma voz primeiro.'); return }
    if (!withScript.length) { setMsg('Nenhum vídeo com roteiro.'); return }
    setMsg('')
    try {
      await api.ai33Generate(selectedVoice.voice_id, speed)
      setGen({ running: true, progress: {}, log: [] })
    } catch (e) { setMsg('Erro: ' + e.message) }
  }

  return (
    <div className="ai33">
      <h2>🎙️ Narração (ai33)</h2>

      {/* API key */}
      <div className="ai33-card">
        <div className="ai33-row">
          <b>API key</b>
          {configured
            ? <span className="ok-tag">● configurada</span>
            : <span className="off-tag">não configurada</span>}
          {credits != null && <span className="credits">créditos: {credits}</span>}
        </div>
        <div className="inline">
          <input type="password" placeholder="Cole sua API key da ai33 aqui"
            value={keyInput} onChange={(e) => setKeyInput(e.target.value)} style={{ flex: 1 }} />
          <button className="primary" onClick={saveKey}>Salvar chave</button>
        </div>
        <div className="hint">A chave fica salva só no seu PC (não vai pra lugar nenhum).</div>
      </div>

      {/* Vozes */}
      <div className="ai33-card">
        <b>Escolher voz</b>
        <div className="inline" style={{ marginTop: 8 }}>
          <select value={provider} onChange={(e) => setProvider(e.target.value)}>
            {PROVIDERS.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          <input placeholder="buscar (idioma, nome, gênero...)" value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && loadVoices()} style={{ flex: 1 }} />
          <button onClick={loadVoices} disabled={!configured}>Buscar vozes</button>
        </div>

        {selectedVoice && (
          <div className="selected-voice">Voz selecionada: <b>{selectedVoice.name}</b> ({selectedVoice.voice_id})</div>
        )}

        {loading && <div className="hint">Carregando vozes...</div>}
        <div className="voice-list">
          {voices.map((v) => (
            <div key={v.voice_id}
              className={'voice-item' + (selectedVoice?.voice_id === v.voice_id ? ' sel' : '')}>
              <div className="voice-info">
                <div className="voice-name">{v.name}</div>
                <div className="voice-meta">{v.language} · {v.gender} {v.tags?.length ? '· ' + v.tags.slice(0, 3).join(', ') : ''}</div>
              </div>
              {v.preview_url && <button onClick={() => playPreview(v.preview_url)}>▶ Ouvir</button>}
              <button className="primary" onClick={() => setSelectedVoice(v)}>Selecionar</button>
            </div>
          ))}
        </div>
      </div>

      {/* Gerar */}
      <div className="ai33-card">
        <b>Gerar áudios do lote</b>
        <div className="hint">
          {withScript.length} vídeo(s) com roteiro. Cada áudio gerado vai automaticamente pro vídeo correspondente.
        </div>
        <div className="inline" style={{ marginTop: 8 }}>
          <label>Velocidade: {speed.toFixed(2)}x</label>
          <input type="range" min="0.5" max="1.5" step="0.05" value={speed}
            onChange={(e) => setSpeed(Number(e.target.value))} />
          <button className="ok" onClick={generateAll}
            disabled={gen?.running || !configured || !selectedVoice}>
            🎧 Gerar áudios ({withScript.length})
          </button>
        </div>

        {gen && (
          <div className="gen-progress">
            {withScript.map((it) => {
              const p = gen.progress?.[it.id]
              return (
                <div key={it.id} className="gen-item">
                  <span className="gen-title">{it.title || it.id}</span>
                  <span className="gen-pct">
                    {p === -1 ? '❌ erro' : p === 100 ? '✅ pronto' : p != null ? p + '%' : (gen.running ? '…' : '—')}
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {msg && <div className="ai33-msg">{msg}</div>}
    </div>
  )
}
