import { Check, Database, Mountain, Sparkles } from 'lucide-react'

export type DemSourceOption = {
  id: string
  name: string
  resolution_m: number
  coverage: string
  kind: string
  note: string
  recommended: boolean
  estimated_cells: number
}

type Props = {
  sources: DemSourceOption[]
  value: string
  onChange: (value: string) => void
  compact?: boolean
}

export default function DemSourcePicker({ sources, value, onChange, compact = false }: Props) {
  if (!sources.length) return null

  return (
    <div className={`dem-source-picker ${compact ? 'compact' : ''}`}>
      {sources.map((source) => {
        const selected = source.id === value
        return (
          <button
            type="button"
            key={source.id}
            className={`dem-source-card ${selected ? 'selected' : ''}`}
            onClick={() => onChange(source.id)}
            aria-pressed={selected}
          >
            <span className="dem-source-radio">{selected ? <Check size={11} /> : null}</span>
            <span className="dem-source-main">
              <span className="dem-source-name">
                {source.name}
                {source.recommended && <span className="dem-source-badge"><Sparkles size={10} /> Recomendado</span>}
              </span>
              <span className="dem-source-note">{source.note}</span>
              <span className="dem-source-meta">
                <span><Mountain size={11} /> {source.resolution_m} m</span>
                <span><Database size={11} /> {source.kind}</span>
                <span>{source.estimated_cells.toLocaleString()} celdas est.</span>
              </span>
            </span>
          </button>
        )
      })}
    </div>
  )
}
