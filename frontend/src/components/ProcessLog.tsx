import { CheckCircle2, ChevronDown, CircleAlert, Info, LoaderCircle, Trash2, X } from 'lucide-react'

export type ProcessLogEntry = {
  id: number
  level: 'info' | 'ok' | 'warning' | 'error'
  message: string
  elapsed: number
}

type Props = {
  open: boolean
  running: boolean
  progress: number
  entries: ProcessLogEntry[]
  onClose: () => void
  onClear: () => void
}

const iconFor = (level: ProcessLogEntry['level'], running: boolean) => {
  if (level === 'ok') return <CheckCircle2 size={13} />
  if (level === 'warning' || level === 'error') return <CircleAlert size={13} />
  if (running) return <LoaderCircle size={13} className="log-spin" />
  return <Info size={13} />
}

export default function ProcessLog({ open, running, progress, entries, onClose, onClear }: Props) {
  if (!open) return null

  return (
    <section className="process-console" aria-live="polite" aria-label="Registro del procesamiento">
      <header className="process-console-header">
        <div className="process-console-title">
          <span className={`console-status-dot ${running ? 'running' : ''}`} />
          <strong>Registro del procesamiento</strong>
          <span>{running ? 'Ejecutando' : entries.length ? 'Finalizado' : 'En espera'}</span>
        </div>
        <div className="process-console-actions">
          <span className="console-progress-label">{Math.round(progress)}%</span>
          <button type="button" className="console-icon-button" onClick={onClear} title="Limpiar registro"><Trash2 size={13} /></button>
          <button type="button" className="console-icon-button" onClick={onClose} title="Cerrar registro"><ChevronDown size={14} /></button>
        </div>
      </header>

      <div className="console-progress-track"><span style={{ width: `${Math.max(0, Math.min(100, progress))}%` }} /></div>

      <div className="process-console-body">
        {entries.length === 0 ? (
          <div className="console-empty"><Info size={13} /> Ejecuta un análisis para ver el progreso del motor.</div>
        ) : entries.map((entry, index) => {
          const isLastInfo = running && index === entries.length - 1 && entry.level === 'info'
          return (
            <div className={`console-line level-${entry.level}`} key={entry.id}>
              <span className="console-time">+{entry.elapsed.toFixed(1)}s</span>
              <span className="console-level">{entry.level.toUpperCase()}</span>
              <span className="console-line-icon">{iconFor(entry.level, isLastInfo)}</span>
              <span className="console-message">{entry.message}</span>
            </div>
          )
        })}
      </div>
    </section>
  )
}
