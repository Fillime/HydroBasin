import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from 'react'
import L from 'leaflet'
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
  RotateCcw,
  Settings,
  SlidersHorizontal,
  Waves,
} from 'lucide-react'
import {
  CircleMarker,
  GeoJSON,
  ImageOverlay,
  MapContainer,
  Popup,
  ScaleControl,
  TileLayer,
  useMap,
  useMapEvents,
} from 'react-leaflet'

type Summary = {
  area_km2?: number
  perimetro_km?: number
  coeficiente_compacidad?: number
  relacion_circularidad?: number
  drainage_threshold?: number
  crs_dem?: string
  crs_calculo?: string
  dem_width?: number
  dem_height?: number
  dem_resolution?: [number, number]
  outlet_snapped?: { x: number; y: number; crs: string }
}

type Bounds = { west: number; south: number; east: number; north: number }
type DemPreview = {
  filename: string
  crs: string
  width: number
  height: number
  resolution: [number, number]
  bounds_native: Bounds
  bounds_wgs84: Bounds
  elevation_min: number
  elevation_max: number
  preview_data_url: string
}

type Outlet = { lat: number; lng: number }
type ViewId = 'home' | 'analysis' | 'projects' | 'results' | 'data' | 'settings'
type GeoJsonData = Record<string, unknown> | null

function MapClickHandler({ onPick }: { onPick: (outlet: Outlet) => void }) {
  useMapEvents({ click: (event) => onPick({ lat: event.latlng.lat, lng: event.latlng.lng }) })
  return null
}

function FitToGeoJson({ data }: { data: GeoJsonData }) {
  const map = useMap()
  useEffect(() => {
    if (!data) return
    const bounds = L.geoJSON(data as any).getBounds()
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 14 })
  }, [data, map])
  return null
}

function FitToDem({ preview }: { preview: DemPreview | null }) {
  const map = useMap()
  useEffect(() => {
    if (!preview) return
    const b = preview.bounds_wgs84
    map.fitBounds([[b.south, b.west], [b.north, b.east]], { padding: [24, 24] })
  }, [preview, map])
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

const viewLabels: Record<ViewId, string> = {
  home: 'Inicio', analysis: 'Análisis', projects: 'Proyectos', results: 'Resultados', data: 'Datos', settings: 'Configuración',
}

export default function App() {
  const [file, setFile] = useState<File | null>(null)
  const [demPreview, setDemPreview] = useState<DemPreview | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [outlet, setOutlet] = useState<Outlet>({ lat: 7.06, lng: -73.85 })
  const [minimumAreaKm2, setMinimumAreaKm2] = useState('1')
  const [resolutionM, setResolutionM] = useState('30')
  const [loading, setLoading] = useState(false)
  const [summary, setSummary] = useState<Summary | null>(null)
  const [watershedGeoJson, setWatershedGeoJson] = useState<GeoJsonData>(null)
  const [drainageGeoJson, setDrainageGeoJson] = useState<GeoJsonData>(null)
  const [jobId, setJobId] = useState('')
  const [error, setError] = useState('')
  const [activeStep, setActiveStep] = useState(0)
  const [activeView, setActiveView] = useState<ViewId>('analysis')
  const [showInspector, setShowInspector] = useState(true)
  const [layers, setLayers] = useState<Record<string, boolean>>({
    'Mapa base': true, DEM: true, Hillshade: false, 'DEM corregido': false,
    'Dirección de flujo': false, Acumulación: false, Cuenca: true,
    'Red de drenaje': true, Exutorio: true,
  })

  const fileSize = useMemo(() => file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : '', [file])
  const thresholdCells = useMemo(() => {
    const area = Number(minimumAreaKm2)
    const resolution = Number(resolutionM)
    if (!Number.isFinite(area) || !Number.isFinite(resolution) || area <= 0 || resolution <= 0) return 1000
    return Math.max(1, Math.round((area * 1_000_000) / (resolution * resolution)))
  }, [minimumAreaKm2, resolutionM])

  const clearResults = () => {
    setSummary(null); setWatershedGeoJson(null); setDrainageGeoJson(null); setJobId('')
  }

  const newProject = () => {
    setFile(null); setDemPreview(null); setOutlet({ lat: 7.06, lng: -73.85 })
    setMinimumAreaKm2('1'); setResolutionM('30'); setError(''); setActiveStep(0)
    setActiveView('analysis'); clearResults()
  }

  const onFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const selected = event.target.files?.[0] ?? null
    setFile(selected); setDemPreview(null); setError(''); clearResults(); setActiveStep(selected ? 1 : 0); setActiveView('analysis')
    if (!selected) return

    setPreviewLoading(true)
    try {
      const body = new FormData()
      body.append('dem', selected)
      const response = await fetch('/api/analysis/dem-preview', { method: 'POST', body })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'No fue posible leer la extensión del DEM.')
      setDemPreview(data)
      setLayers((current) => ({ ...current, DEM: true }))
      const b = data.bounds_wgs84 as Bounds
      setOutlet({ lat: (b.south + b.north) / 2, lng: (b.west + b.east) / 2 })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No fue posible inspeccionar el GeoTIFF.')
    } finally {
      setPreviewLoading(false)
    }
  }

  const pickOutlet = (point: Outlet) => {
    setOutlet(point); setActiveStep(5); setError(''); clearResults()
  }

  const runAnalysis = async (event: FormEvent) => {
    event.preventDefault()
    if (!file) { setError('Carga primero un DEM GeoTIFF.'); return }

    const body = new FormData()
    body.append('dem', file)
    body.append('x', outlet.lng.toString())
    body.append('y', outlet.lat.toString())
    body.append('point_crs', 'EPSG:4326')
    body.append('threshold', thresholdCells.toString())

    setLoading(true); setError('')
    try {
      const response = await fetch('/api/analysis/watershed', { method: 'POST', body })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'No fue posible ejecutar el análisis.')
      setSummary(data.summary)
      setWatershedGeoJson(data.watershed_geojson ?? null)
      setDrainageGeoJson(data.drainage_geojson ?? null)
      setJobId(data.job_id ?? '')
      setActiveStep(8); setActiveView('results')
      setLayers((current) => ({ ...current, Cuenca: true, 'Red de drenaje': true }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error inesperado.')
    } finally { setLoading(false) }
  }

  const resultMetrics = summary ? (
    <div className="metrics-list">
      <div><span>Área</span><strong>{summary.area_km2?.toFixed(2)} km²</strong></div>
      <div><span>Perímetro</span><strong>{summary.perimetro_km?.toFixed(2)} km</strong></div>
      <div><span>Compacidad</span><strong>{summary.coeficiente_compacidad?.toFixed(3)}</strong></div>
      <div><span>Circularidad</span><strong>{summary.relacion_circularidad?.toFixed(3)}</strong></div>
      <div><span>CRS del DEM</span><strong>{summary.crs_dem || '—'}</strong></div>
      <div><span>CRS de cálculo</span><strong>{summary.crs_calculo || '—'}</strong></div>
      <div><span>Umbral D8</span><strong>{summary.drainage_threshold?.toLocaleString()} celdas</strong></div>
    </div>
  ) : <div className="empty-state"><Droplets size={18} /><span>Ejecuta un análisis para generar resultados.</span></div>

  const demInfo = demPreview ? (
    <div className="metrics-list">
      <div><span>CRS</span><strong>{demPreview.crs}</strong></div>
      <div><span>Dimensiones</span><strong>{demPreview.width} × {demPreview.height}</strong></div>
      <div><span>Resolución</span><strong>{demPreview.resolution[0].toFixed(5)} × {demPreview.resolution[1].toFixed(5)}</strong></div>
      <div><span>Elevación</span><strong>{demPreview.elevation_min.toFixed(1)} – {demPreview.elevation_max.toFixed(1)} m</strong></div>
      <div><span>Oeste / Este</span><strong>{demPreview.bounds_wgs84.west.toFixed(5)} / {demPreview.bounds_wgs84.east.toFixed(5)}</strong></div>
      <div><span>Sur / Norte</span><strong>{demPreview.bounds_wgs84.south.toFixed(5)} / {demPreview.bounds_wgs84.north.toFixed(5)}</strong></div>
    </div>
  ) : null

  const renderInspector = () => {
    if (activeView === 'home') return (
      <div className="inspector-content">
        <div className="inspector-header"><span className="section-label">HYDROBASIN</span><h1>Inicio</h1><p>Workspace de delimitación y análisis de cuencas.</p></div>
        <section className="form-section"><div className="instruction-list"><span>1. Carga un DEM GeoTIFF.</span><span>2. Verifica su extensión en el mapa.</span><span>3. Marca el exutorio y ejecuta el análisis.</span></div></section>
        <div className="run-area"><button className="primary-button" onClick={() => setActiveView('analysis')}><Play size={14} /> Abrir análisis</button></div>
      </div>
    )

    if (activeView === 'projects') return (
      <div className="inspector-content">
        <div className="inspector-header"><span className="section-label">PROYECTOS</span><h1>Proyecto actual</h1><p>Por ahora HydroBasin trabaja con un proyecto local en memoria.</p></div>
        <section className="form-section project-card"><strong>Cuenca sin título</strong><span>{file ? file.name : 'Sin DEM cargado'}</span><span>{summary ? 'Análisis completado' : 'Sin procesar'}</span></section>
        <div className="run-area"><button className="secondary-button wide" onClick={newProject}><Plus size={14} /> Nuevo proyecto</button></div>
      </div>
    )

    if (activeView === 'results') return (
      <div className="inspector-content">
        <div className="inspector-header"><span className="section-label">RESULTADOS</span><h1>Cuenca delimitada</h1><p>{jobId ? `Proceso ${jobId.slice(0, 8)}` : 'Todavía no hay un proceso calculado.'}</p></div>
        <section className="results-section">{resultMetrics}</section>
        <div className="run-area"><button className="secondary-button wide" onClick={() => setActiveView('analysis')}><SlidersHorizontal size={14} /> Ajustar análisis</button></div>
      </div>
    )

    if (activeView === 'data') return (
      <div className="inspector-content">
        <div className="inspector-header"><span className="section-label">DATOS</span><h1>Entradas y capas</h1><p>Información disponible para el proyecto actual.</p></div>
        <section className="form-section">{demInfo || <div className="empty-state"><Mountain size={18} /><span>Carga un DEM para ver sus metadatos.</span></div>}</section>
      </div>
    )

    if (activeView === 'settings') return (
      <div className="inspector-content">
        <div className="inspector-header"><span className="section-label">CONFIGURACIÓN</span><h1>Parámetros</h1><p>Valores por defecto del análisis hidrológico.</p></div>
        <section className="form-section">
          <label className="field">Área mínima de aporte (km²)<input value={minimumAreaKm2} onChange={(e) => setMinimumAreaKm2(e.target.value)} type="number" min="0.001" step="0.1" /></label>
          <label className="field">Resolución del DEM (m)<input value={resolutionM} onChange={(e) => setResolutionM(e.target.value)} type="number" min="0.1" step="0.1" /></label>
          <div className="calculation-row"><span>Umbral equivalente</span><strong>{thresholdCells.toLocaleString()} celdas</strong></div>
        </section>
        <div className="run-area"><button className="secondary-button wide" onClick={newProject}><RotateCcw size={14} /> Restablecer proyecto</button></div>
      </div>
    )

    return (
      <>
        <form onSubmit={runAnalysis}>
          <div className="inspector-header"><span className="section-label">ENTRADA</span><h1>Delimitación de cuenca</h1><p>Carga el DEM, comprueba dónde está y selecciona el punto de salida.</p></div>
          <section className="form-section">
            <label className={`upload-row ${file ? 'ready' : ''}`}>
              <input type="file" accept=".tif,.tiff" onChange={onFile} />
              <FileUp size={16} />
              <div><strong>{file?.name || 'Seleccionar GeoTIFF'}</strong><span>{previewLoading ? 'Leyendo extensión…' : file ? fileSize : '.tif o .tiff'}</span></div>
            </label>
          </section>
          {demPreview && <section className="form-section"><div className="form-section-heading"><strong>Extensión del DEM</strong><span>{demPreview.crs}</span></div>{demInfo}<p className="helper">El mapa ya hizo zoom a esta extensión. La imagen gris corresponde a las elevaciones del DEM.</p></section>}
          <section className="form-section">
            <div className="form-section-heading"><strong>Exutorio</strong><span>EPSG:4326</span></div>
            <div className="field-grid">
              <label>Longitud<input value={outlet.lng} onChange={(e) => setOutlet((p) => ({ ...p, lng: Number(e.target.value) }))} type="number" step="any" /></label>
              <label>Latitud<input value={outlet.lat} onChange={(e) => setOutlet((p) => ({ ...p, lat: Number(e.target.value) }))} type="number" step="any" /></label>
            </div>
            <p className="helper">Haz clic dentro del DEM, idealmente sobre el cauce en el punto hasta donde quieres delimitar la cuenca.</p>
          </section>
          <section className="form-section">
            <div className="form-section-heading"><strong>Red de drenaje</strong><span>D8</span></div>
            <label className="field">Área mínima de aporte (km²)<input value={minimumAreaKm2} onChange={(e) => setMinimumAreaKm2(e.target.value)} type="number" min="0.001" step="0.1" /></label>
            <label className="field">Resolución para umbral (m)<input value={resolutionM} onChange={(e) => setResolutionM(e.target.value)} type="number" min="0.1" step="0.1" /></label>
            <div className="calculation-row"><span>Umbral equivalente</span><strong>{thresholdCells.toLocaleString()} celdas</strong></div>
          </section>
          {error && <div className="error-box">{error}</div>}
          <div className="run-area"><button className="primary-button" disabled={loading || previewLoading}><Play size={14} fill="currentColor" /> {loading ? 'Procesando…' : 'Ejecutar análisis'}</button></div>
        </form>
        <section className="results-section"><div className="form-section-heading"><strong>Resultados</strong><span>{summary ? 'Calculados' : 'Pendientes'}</span></div>{resultMetrics}</section>
      </>
    )
  }

  const layerRows = [
    { name: 'Mapa base', available: true },
    { name: 'DEM', available: Boolean(demPreview) },
    { name: 'Hillshade', available: false },
    { name: 'DEM corregido', available: false },
    { name: 'Dirección de flujo', available: false },
    { name: 'Acumulación', available: false },
    { name: 'Cuenca', available: Boolean(watershedGeoJson) },
    { name: 'Red de drenaje', available: Boolean(drainageGeoJson) },
    { name: 'Exutorio', available: true },
  ]

  const demBounds = demPreview ? [[demPreview.bounds_wgs84.south, demPreview.bounds_wgs84.west], [demPreview.bounds_wgs84.north, demPreview.bounds_wgs84.east]] as L.LatLngBoundsExpression : null

  return (
    <div className={`hydro-shell ${showInspector ? '' : 'inspector-hidden'}`}>
      <aside className="global-rail" aria-label="Navegación global">
        <div className="rail-brand"><Droplets size={18} /></div>
        <nav className="rail-nav">
          <button className={`rail-button ${activeView === 'home' ? 'active' : ''}`} title="Inicio" onClick={() => setActiveView('home')}><Home size={17} /></button>
          <button className={`rail-button ${activeView === 'analysis' ? 'active' : ''}`} title="Análisis" onClick={() => setActiveView('analysis')}><MapIcon size={17} /></button>
          <button className={`rail-button ${activeView === 'projects' ? 'active' : ''}`} title="Proyectos" onClick={() => setActiveView('projects')}><FolderOpen size={17} /></button>
          <button className={`rail-button ${activeView === 'results' ? 'active' : ''}`} title="Resultados" onClick={() => setActiveView('results')}><BarChart3 size={17} /></button>
          <button className={`rail-button ${activeView === 'data' ? 'active' : ''}`} title="Datos" onClick={() => setActiveView('data')}><Database size={17} /></button>
        </nav>
        <button className={`rail-button rail-footer ${activeView === 'settings' ? 'active' : ''}`} title="Configuración" onClick={() => setActiveView('settings')}><Settings size={17} /></button>
      </aside>

      <aside className="module-sidebar">
        <div className="module-title"><div><strong>HydroBasin</strong><span>Watershed Studio</span></div><button className="icon-button" title="Nuevo proyecto" onClick={newProject}><Plus size={14} /></button></div>
        <div className="sidebar-section"><div className="section-label">PROYECTO</div><button className="nav-row active" onClick={() => setActiveView('analysis')}><MapIcon size={15} /><span>Cuenca sin título</span></button></div>
        <div className="sidebar-section workflow-list">
          <div className="section-label">FLUJO DE TRABAJO</div>
          {workflow.map(({ label, icon: Icon }, index) => {
            const done = summary ? index <= 8 : file ? index <= activeStep : index === 0
            return <button key={label} className={`workflow-row ${index === activeStep ? 'active' : ''}`} onClick={() => { setActiveStep(index); setActiveView('analysis') }}><span className={`step-dot ${done ? 'done' : ''}`}>{index + 1}</span><Icon size={14} /><span>{label}</span></button>
          })}
        </div>
        <div className="sidebar-section layer-list">
          <div className="section-label">CAPAS</div>
          {layerRows.map(({ name, available }) => <label className={`layer-row ${available ? '' : 'disabled'}`} key={name}><input type="checkbox" checked={layers[name]} disabled={!available} onChange={(e) => setLayers((current) => ({ ...current, [name]: e.target.checked }))} /><span>{name}</span>{!available && <small>Pend.</small>}</label>)}
        </div>
      </aside>

      <main className="workspace-shell">
        <header className="topbar"><div className="breadcrumbs"><span>HydroBasin</span><ChevronRight size={12} /><strong>{viewLabels[activeView]}</strong></div><div className="topbar-actions"><span className="engine-status"><i /> Motor listo</span><button className="secondary-button" onClick={() => setShowInspector((value) => !value)}><SlidersHorizontal size={14} /> {showInspector ? 'Ocultar panel' : 'Mostrar panel'}</button></div></header>
        <div className="workspace-grid">
          <section className="map-workspace">
            <div className="map-toolbar"><div><MapIcon size={14} /><strong>Vista geográfica</strong></div><span>{demPreview ? `DEM: ${demPreview.filename}` : 'Carga un GeoTIFF para ver su extensión'}</span></div>
            <MapContainer center={[outlet.lat, outlet.lng]} zoom={11} className="map-canvas" zoomControl>
              {layers['Mapa base'] && <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />}
              <MapClickHandler onPick={pickOutlet} />
              {demPreview && layers.DEM && demBounds && <ImageOverlay url={demPreview.preview_data_url} bounds={demBounds} opacity={0.62} />}
              {demPreview && <FitToDem preview={demPreview} />}
              {layers.Exutorio && <CircleMarker center={[outlet.lat, outlet.lng]} radius={7} pathOptions={{ color: '#1f9d8f', weight: 2, fillColor: '#1f9d8f', fillOpacity: 0.35 }}><Popup><strong>Exutorio seleccionado</strong><br />{outlet.lat.toFixed(6)}, {outlet.lng.toFixed(6)}</Popup></CircleMarker>}
              {layers.Cuenca && watershedGeoJson && <GeoJSON key={`watershed-${jobId}`} data={watershedGeoJson as any} style={{ color: '#f59e0b', weight: 2, fillColor: '#f59e0b', fillOpacity: 0.12 }} />}
              {layers['Red de drenaje'] && drainageGeoJson && <GeoJSON key={`drainage-${jobId}`} data={drainageGeoJson as any} style={{ color: '#3b82f6', weight: 2, opacity: 0.9 }} />}
              {watershedGeoJson && <FitToGeoJson data={watershedGeoJson} />}
              <ScaleControl position="bottomleft" imperial={false} />
            </MapContainer>
            <div className="map-readout"><span>{demPreview ? 'Exutorio · dentro del DEM' : 'Exutorio'}</span><strong>{outlet.lat.toFixed(5)}, {outlet.lng.toFixed(5)}</strong></div>
          </section>
          {showInspector && <aside className="inspector">{renderInspector()}</aside>}
        </div>
      </main>
    </div>
  )
}
