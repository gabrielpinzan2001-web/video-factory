import React, { useState } from 'react'
import { mediaUrl, EFFECTS, EFFECT_LABEL } from './api.js'

// Timeline editavel: cada clipe = 1 imagem. Da pra reordenar (arrastar),
// trocar o efeito, mudar a duracao e remover.
export default function Timeline({ clips, onChange }) {
  const [dragIdx, setDragIdx] = useState(null)

  const update = (i, patch) => {
    const next = clips.map((c, idx) => (idx === i ? { ...c, ...patch } : c))
    onChange(next)
  }
  const remove = (i) => onChange(clips.filter((_, idx) => idx !== i))

  const onDrop = (i) => {
    if (dragIdx === null || dragIdx === i) return
    const next = [...clips]
    const [moved] = next.splice(dragIdx, 1)
    next.splice(i, 0, moved)
    setDragIdx(null)
    onChange(next)
  }

  const total = clips.reduce((s, c) => s + Number(c.duration || 0), 0)

  if (!clips.length)
    return <div className="tl-empty">Monte a timeline para ver os clipes aqui.</div>

  return (
    <div>
      <div className="tl-info">
        {clips.length} imagens · duração total {total.toFixed(1)}s
      </div>
      <div className="tl-strip">
        {clips.map((c, i) => (
          <div
            key={i}
            className={'tl-clip' + (dragIdx === i ? ' dragging' : '')}
            draggable
            onDragStart={() => setDragIdx(i)}
            onDragOver={(e) => e.preventDefault()}
            onDrop={() => onDrop(i)}
          >
            <div className="tl-num">{i + 1}</div>
            <img className="tl-thumb" src={mediaUrl(c.image)} alt="" loading="lazy" />
            <select
              className="tl-effect"
              value={c.effect}
              onChange={(e) => update(i, { effect: e.target.value })}
            >
              {EFFECTS.map((ef) => (
                <option key={ef} value={ef}>{EFFECT_LABEL[ef]}</option>
              ))}
            </select>
            <div className="tl-dur">
              <input
                type="number" min="0.5" max="30" step="0.5"
                value={c.duration}
                onChange={(e) => update(i, { duration: Number(e.target.value) })}
              />
              <span>s</span>
            </div>
            <button className="tl-del" title="Remover" onClick={() => remove(i)}>✕</button>
          </div>
        ))}
      </div>
    </div>
  )
}
