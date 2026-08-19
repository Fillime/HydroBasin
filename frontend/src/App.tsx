import { ChangeEvent, FormEvent, useMemo, useState } from 'react'
import {
  Activity,
  BarChart3,
  ChevronRight,
  CircleDot,
  Database,
  Droplets,
  FileUp,
  FolderOpen,
  Home,
  Layers3,
  Map as MapIcon,
  Mountain,
  Play,
  Plus,
  Settings,
  SlidersHorizontal,
  Waves,
} from 'lucide-react'
import {
  CircleMarker,
  LayersControl,
  MapContainer,
  Popup,
  ScaleControl,
  TileLayer,
  useMapEvents,
} from 'react-leaflet'

type Summary = {
  area_km2?: number
  perimetro_km?: number
  coeficiente_compacidad?: number
  relacion_circularidad?: number
  drainage_threshold?: number
  crs_dem?: string
  outlet_snapped?: { x: number; y: number; crs: string }
}

type Outlet = { lat: number; lng: number }

type MapClickProps = {
  onPick: (outlet: Outlet) => void
}

function MapClickHandler({ onPick }: MapClickProps) {
  useMapEvents({
    click(event) {
      onPick({ lat: event.latlng.lat, lng: event.latlng.lng })
    },
  })
  return null
}

const workflow = [
  { label: 'Área de estudio', icon: MapIcon },
  { label: 'Modelo de elevación', icon: Mountain },
  { label: 'Corrección del DEM', icon: Layers3 },
  { label: 'Dirección de flujo', icon: Waves },
  { label: 'Acumulación', icon: Activity },
  { label: 'Exutorio', icon: CircleDot },
  { label: 'Delimitación', icon: Droplets },
  { label: 'Red de drenaje', icon: Waves },
  { label: 'Morfometría', icon: BarChart3 },
]

const layerItems = [
  ['Mapa base', true],
  ['DEM', false],
  ['Hillshade', false],
  ['DEM corregido', false],
  ['Dirección de flujo', false],
  ['Acumulación', false],
  ['Cuenca', false],
  ['Red de drenaje', false],
  ['Exutorio', true],
] as const

export default function App() {
  const [file, setFile] = useState<File | null>(null)
  const [outlet, setOutlet] = useState<Outlet>({ lat: 7.06, lng: -73.85 })
  const [minimumAreaKm2, setMinimumAreaKm2] = useState('1')
  const [resolutionM, setResolutionM] = useState('30')
  const [loading, setLoading] = useState(false)
  const [summary, setSummary] = useState<Summary | null>(null)
  const [error, setError] = useState('')
  const [activeStep, setActiveStep] = useState(0)
  const [layers, setLayers] = useState<Record<string, boolean>>(
    Object.fromEntries(layerItems.map(([name, enabled]) => [name, enabled])),
  )

  const fileSize = useMemo(() => {
    if (!file) return ''
    return `${(file.size / 1024 / 1024).toFixed(2)} MB`
  }, [file])

  const thresholdCells = useMemo(() => {
    const area = Number(minimumAreaKm2)
    const resolution = Number(resolutionM)
    if (!Number.isFinite(area) || !Number.isFinite(resolution) || area <= 0 || resolution <= 0) return 1000
    return Math.max(1, Math.round((area * 1_000_000) / (resolution * resolution)))
  }, [minimumAreaKm2, resolutionM])

  const onFile = (event: ChangeEvent<HTMLInputElement>) => {
    setFile(event.target.files?.[0] ?? null)
    setSummary(null)
    setError('')
    setActiveStep(1)
  }

  const pickOutlet = (point: Outlet) => {
    setOutlet(point)
    setActiveStep(5)
    setSummary(null)
  }

  const runAnalysis = async (event: FormEvent) => {
    event.preventDefault()
    if (!file) {
      setError('Carga primero un DEM GeoTIFF.')
      return
    }

    const body = new FormData()
    body.append('dem', file)
    body.append('x', outlet.lng.toString())
    body.append('y', outlet.lat.toString())
    body.append('point_crs', 'EPSG:4326')
    body.append('threshold', thresholdCells.toString())

    setLoading(true)
    setError('')
    try {
      const response = await fetch('/api/analysis/watershed', { method: 'POST', body })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'No fue posible ejecutar el análisis.')
      setSummary(data.summary)
      setActiveStep(8)
      setLayers((current) => ({ ...current, Cuenca: true, 'Red de drenaje': true }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error inesperado.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="hydro-shell">
      <aside className="global-rail" aria-label="Navegación global">
        <div className="rail-brand"><Droplets size={18} /></div>
        <nav className="rail-nav">
          <button className="rail-button" title="Inicio"><Home size={17} /></button>
          <button className="rail-button active" title="Mapa"><MapIcon size={17} /></button>
          <button className="rail-button" title="Proyectos"><FolderOpen size={17} /></button>
          <button className="rail-button" title="Resultados"><BarChart3 size={17} /></button>
          <button className="rail-button" title="Datos"><Database size={17} /></button>
        </nav>
        <button className="rail-button rail-footer" title="Configuración"><Settings size={17} /></button>
      </aside>

      <aside className="module-sidebar">
        <div className="module-title">
          <div><strong>HydroBasin</strong><span>Watershed Studio</span></div>
          <button className="icon-button" title="Nuevo proyecto"><Plus size={14} /></button>
        </div>

        <div className="sidebar-section">
          <div className="section-label">PROYECTO</div>
          <button className="nav-row active"><MapIcon size={15} /><span>Cuenca sin título</span></button>
        </div>

        <div className="sidebar-section workflow-list">
          <div className="section-label">FLUJO DE TRABAJO</div>
          {workflow.map(({ label, icon: Icon }, index) => {
            const done = summary ? index <= 8 : file ? index <= activeStep : index === 0
            return (
              <button
                key={label}
                className={`workflow-row ${index === activeStep ? 'active' : ''}`}
                onClick={() => setActiveStep(index)}
              >
                <span className={`step-dot ${done ? 'done' : ''}`}>{index + 1}</span>
                <Icon size={14} />
                <span>{label}</span>
              </button>
            )
          })}
        </div>

        <div className="sidebar-section layer-list">
          <div className="section-label">CAPAS</div>
          {layerItems.map(([name]) => (
            <label className="layer-row" key={name}>
              <input
                type="checkbox"
                checked={layers[name]}
                onChange={(event) => setLayers((current) => ({ ...current, [name]: event.target.checked }))}
              />
              <span>{name}</span>
            </label>
          ))}
        </div>
      </aside>

      <main className="workspace-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            <span>Proyectos</span><ChevronRight size={12} /><strong>Cuenca sin título</strong>
          </div>
          <div className="topbar-actions">
            <span className="engine-status"><i /> Motor listo</span>
            <button className="secondary-button"><SlidersHorizontal size={14} /> Vista</button>
          </div>
        </header>

        <div className="workspace-grid">
          <section className="map-workspace">
            <div className="map-toolbar">
              <div><MapIcon size={14} /><strong>Vista geográfica</strong></div>
              <span>Haz clic para definir el exutorio · WGS 84</span>
            </div>
            <MapContainer center={[outlet.lat, outlet.lng]} zoom={11} className="map-canvas" zoomControl>
              <LayersControl position="topright">
                <LayersControl.BaseLayer checked name="OpenStreetMap">
                  <TileLayer
                    attribution="&copy; OpenStreetMap contributors"
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                  />
                </LayersControl.BaseLayer>
                <LayersControl.BaseLayer name="Relieve">
                  <TileLayer
                    attribution="Tiles &copy; Esri"
                    url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}"
                  />
                </LayersControl.BaseLayer>
              </LayersControl>
              <MapClickHandler onPick={pickOutlet} />
              {layers.Exutorio && (
                <CircleMarker
                  center={[outlet.lat, outlet.lng]}
                  radius={7}
                  pathOptions={{ color: '#46c2b5', weight: 2, fillColor: '#46c2b5', fillOpacity: 0.3 }}
                >
                  <Popup>
                    <strong>Exutorio seleccionado</strong><br />
                    {outlet.lat.toFixed(6)}, {outlet.lng.toFixed(6)}
                  </Popup>
                </CircleMarker>
              )}
              <ScaleControl position="bottomleft" imperial={false} />
            </MapContainer>
            <div className="map-readout">
              <span>Exutorio</span>
              <strong>{outlet.lat.toFixed(5)}, {outlet.lng.toFixed(5)}</strong>
            </div>
          </section>

          <aside className="inspector">
            <form onSubmit={runAnalysis}>
              <div className="inspector-header">
                <span className="section-label">ENTRADA</span>
                <h1>Delimitación de cuenca</h1>
                <p>Carga el DEM, selecciona el punto de salida en el mapa y ejecuta el análisis.</p>
              </div>

              <section className="form-section">
                <label className={`upload-row ${file ? 'ready' : ''}`}>
                  <input type="file" accept=".tif,.tiff" onChange={onFile} />
                  <FileUp size={16} />
                  <div><strong>{file?.name || 'Seleccionar GeoTIFF'}</strong><span>{file ? fileSize : '.tif o .tiff'}</span></div>
                </label>
              </section>

              <section className="form-section">
                <div className="form-section-heading"><strong>Exutorio</strong><span>EPSG:4326</span></div>
                <div className="field-grid">
                  <label>Longitud<input value={outlet.lng} onChange={(e) => setOutlet((p) => ({ ...p, lng: Number(e.target.value) }))} type="number" step="any" /></label>
                  <label>Latitud<input value={outlet.lat} onChange={(e) => setOutlet((p) => ({ ...p, lat: Number(e.target.value) }))} type="number" step="any" /></label>
                </div>
                <p className="helper">También puedes definirlo haciendo clic directamente sobre el mapa.</p>
              </section>

              <section className="form-section">
                <div className="form-section-heading"><strong>Red de drenaje</strong><span>D8</span></div>
                <label className="field">Área mínima de aporte (km²)<input value={minimumAreaKm2} onChange={(e) => setMinimumAreaKm2(e.target.value)} type="number" min="0.001" step="0.1" /></label>
                <label className="field">Resolución del DEM (m)<input value={resolutionM} onChange={(e) => setResolutionM(e.target.value)} type="number" min="0.1" step="0.1" /></label>
                <div className="calculation-row"><span>Umbral equivalente</span><strong>{thresholdCells.toLocaleString()} celdas</strong></div>
              </section>

              {error && <div className="error-box">{error}</div>}

              <div className="run-area">
                <button className="primary-button" disabled={loading}>
                  <Play size={14} fill="currentColor" /> {loading ? 'Procesando…' : 'Ejecutar análisis'}
                </button>
              </div>
            </form>

            <section className="results-section">
              <div className="form-section-heading"><strong>Resultados</strong><span>{summary ? 'Calculados' : 'Pendientes'}</span></div>
              {summary ? (
                <div className="metrics-list">
                  <div><span>Área</span><strong>{summary.area_km2?.toFixed(2)} km²</strong></div>
                  <div><span>Perímetro</span><strong>{summary.perimetro_km?.toFixed(2)} km</strong></div>
                  <div><span>Compacidad</span><strong>{summary.coeficiente_compacidad?.toFixed(3)}</strong></div>
                  <div><span>Circularidad</span><strong>{summary.relacion_circularidad?.toFixed(3)}</strong></div>
                  <div><span>CRS del DEM</span><strong>{summary.crs_dem || '—'}</strong></div>
                </div>
              ) : (
                <div className="empty-state"><Droplets size={18} /><span>Los parámetros aparecerán después del procesamiento.</span></div>
              )}
            </section>
          </aside>
        </div>
      </main>
    </div>
  )
}
