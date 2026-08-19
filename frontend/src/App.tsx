import { ChangeEvent, FormEvent, useMemo, useState } from 'react'
import {
  Activity,
  BarChart3,
  ChevronRight,
  Droplets,
  FileUp,
  Layers3,
  Map,
  Mountain,
  Play,
  Plus,
  Settings,
  Waves,
} from 'lucide-react'

type Summary = {
  area_km2?: number
  perimetro_km?: number
  coeficiente_compacidad?: number
  relacion_circularidad?: number
  drainage_threshold?: number
}

const steps = [
  ['Modelo de elevación', Mountain],
  ['Corrección del DEM', Layers3],
  ['Dirección de flujo', Waves],
  ['Acumulación', Activity],
  ['Delimitación', Droplets],
  ['Morfometría', BarChart3],
]

export default function App() {
  const [file, setFile] = useState<File | null>(null)
  const [x, setX] = useState('-73.85')
  const [y, setY] = useState('7.06')
  const [threshold, setThreshold] = useState('1000')
  const [loading, setLoading] = useState(false)
  const [summary, setSummary] = useState<Summary | null>(null)
  const [error, setError] = useState('')

  const fileSize = useMemo(() => {
    if (!file) return ''
    return `${(file.size / 1024 / 1024).toFixed(2)} MB`
  }, [file])

  const onFile = (event: ChangeEvent<HTMLInputElement>) => {
    setFile(event.target.files?.[0] ?? null)
    setSummary(null)
    setError('')
  }

  const runAnalysis = async (event: FormEvent) => {
    event.preventDefault()
    if (!file) {
      setError('Selecciona primero un DEM GeoTIFF.')
      return
    }

    const body = new FormData()
    body.append('dem', file)
    body.append('x', x)
    body.append('y', y)
    body.append('point_crs', 'EPSG:4326')
    body.append('threshold', threshold)

    setLoading(true)
    setError('')
    try {
      const response = await fetch('/api/analysis/watershed', { method: 'POST', body })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'No fue posible ejecutar el análisis.')
      setSummary(data.summary)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error inesperado.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Droplets size={22} /></div>
          <div><strong>HydroBasin</strong><span>Watershed Studio</span></div>
        </div>

        <button className="new-project"><Plus size={17} /> Nuevo proyecto</button>

        <nav>
          <button className="nav-item active"><Map size={18} /> Análisis</button>
          <button className="nav-item"><Layers3 size={18} /> Capas</button>
          <button className="nav-item"><BarChart3 size={18} /> Resultados</button>
        </nav>

        <div className="process">
          <span className="eyebrow">FLUJO DE TRABAJO</span>
          {steps.map(([label, Icon], index) => (
            <div className="process-step" key={label as string}>
              <span className="step-number">{index + 1}</span>
              <Icon size={16} />
              <span>{label as string}</span>
            </div>
          ))}
        </div>

        <button className="nav-item settings"><Settings size={18} /> Configuración</button>
      </aside>

      <main>
        <header className="topbar">
          <div>
            <span className="breadcrumb">Proyectos <ChevronRight size={14} /> Nuevo análisis</span>
            <h1>Delimitación de cuenca</h1>
          </div>
          <span className="status"><i /> Motor listo</span>
        </header>

        <section className="workspace">
          <div className="map-panel">
            <div className="map-toolbar">
              <span><Map size={16} /> Vista geográfica</span>
              <span className="crs">WGS 84 · EPSG:4326</span>
            </div>
            <div className="terrain">
              <div className="contour contour-a" />
              <div className="contour contour-b" />
              <div className="contour contour-c" />
              <div className="river river-a" />
              <div className="river river-b" />
              <div className="outlet"><span /></div>
              <div className="map-message">
                <div className="map-icon"><Map size={24} /></div>
                <strong>Mapa interactivo</strong>
                <p>La siguiente etapa permitirá ubicar el exutorio directamente sobre el mapa.</p>
              </div>
            </div>
          </div>

          <aside className="analysis-panel">
            <form onSubmit={runAnalysis}>
              <div className="panel-heading">
                <span className="eyebrow">ENTRADA</span>
                <h2>Modelo de elevación</h2>
                <p>Carga un DEM GeoTIFF y define el punto de salida de la cuenca.</p>
              </div>

              <label className={`upload ${file ? 'has-file' : ''}`}>
                <input type="file" accept=".tif,.tiff" onChange={onFile} />
                <FileUp size={24} />
                {file ? (
                  <><strong>{file.name}</strong><span>{fileSize}</span></>
                ) : (
                  <><strong>Seleccionar GeoTIFF</strong><span>.tif o .tiff</span></>
                )}
              </label>

              <div className="field-group">
                <label>Longitud / X<input value={x} onChange={(e) => setX(e.target.value)} type="number" step="any" /></label>
                <label>Latitud / Y<input value={y} onChange={(e) => setY(e.target.value)} type="number" step="any" /></label>
              </div>

              <label className="field">Umbral de drenaje<input value={threshold} onChange={(e) => setThreshold(e.target.value)} type="number" min="1" /></label>

              {error && <div className="error">{error}</div>}

              <button className="run-button" disabled={loading}>
                <Play size={17} fill="currentColor" /> {loading ? 'Procesando…' : 'Ejecutar análisis'}
              </button>
            </form>

            <div className="results-preview">
              <span className="eyebrow">RESULTADOS</span>
              {summary ? (
                <div className="metric-grid">
                  <div><span>Área</span><strong>{summary.area_km2?.toFixed(2)} km²</strong></div>
                  <div><span>Perímetro</span><strong>{summary.perimetro_km?.toFixed(2)} km</strong></div>
                  <div><span>Compacidad</span><strong>{summary.coeficiente_compacidad?.toFixed(3)}</strong></div>
                  <div><span>Circularidad</span><strong>{summary.relacion_circularidad?.toFixed(3)}</strong></div>
                </div>
              ) : (
                <div className="empty-results"><Droplets size={22} /><p>Los parámetros de la cuenca aparecerán aquí después del procesamiento.</p></div>
              )}
            </div>
          </aside>
        </section>
      </main>
    </div>
  )
}
