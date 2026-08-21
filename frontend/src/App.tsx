import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from 'react'
import {
  Activity,
  BarChart3,
  Check,
  ChevronDown,
  ChevronRight,
  CircleDot,
  Copy,
  Database,
  Download,
  Droplets,
  Edit2,
  FileText,
  FileUp,
  FolderOpen,
  FolderPlus,
  Globe,
  Home,
  Layers,
  Map as MapIcon,
  MapPin,
  Mountain,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  Play,
  Plus,
  RotateCcw,
  Settings,
  SlidersHorizontal,
  Terminal,
  Waves,
} from 'lucide-react'
import DemSourcePicker from './components/DemSourcePicker'
import DemStartMode, { type DemStartModeValue } from './components/DemStartMode'
import LayerManager, { DEFAULT_LAYER_STYLES, type LayerStyleConfig } from './components/LayerManager'
import MapLibreWorkspace, { type MapBounds } from './components/MapLibreWorkspace'
import ProcessLog, { type ProcessLogEntry } from './components/ProcessLog'
import ProjectDashboard from './components/ProjectDashboard'
import ProjectModal, { type ProjectFormData } from './components/ProjectModal'
import {
  createProjectId,
  deleteProject,
  getActiveProjectId,
  getProject,
  listProjects,
  putProject,
  setActiveProjectId,
  type StoredProject,
} from './services/projectStore'

type Summary = {
  area_km2?: number
  perimetro_km?: number
  coeficiente_compacidad?: number
  relacion_circularidad?: number
  factor_forma?: number
  longitud_axial_km?: number
  densidad_drenaje_km_km2?: number
  drainage_threshold?: number
  minimum_area_km2?: number
  strahler_max?: number
  subbasin_count?: number
  metric_resolution_m?: [number, number] | null
  dem_source?: string
  crs_dem?: string
  crs_calculo?: string
  dem_width?: number
  dem_height?: number
  dem_resolution?: [number, number]
  outlet_snapped?: { x: number; y: number; crs: string }
  outlet_original?: { x: number; y: number; crs: string }
  project_name?: string
  client?: string
  calculated_by?: string
  reviewed_by?: string
  tc_kirpich_h?: number
  tc_temez_h?: number
  tc_promedio_h?: number
  cn_weighted?: number
  curve_number?: { cn_weighted?: number; s_retention_mm?: number; ia_abstraction_mm?: number; units?: any[] }
  peak_discharges?: Array<{
    tr_anos: number
    intensidad_mm_h: number
    precipitacion_total_mm: number
    precipitacion_efectiva_mm: number
    caudal_racional_m3_s: number
    caudal_scs_m3_s: number
    caudal_diseno_m3_s: number
  }>
  ideam_stations?: Array<{
    codigo: string
    nombre: string
    categoria: string
    altitud?: number
    latitud: number
    longitud: number
    municipio: string
    distancia_km: number
  }>
  thiessen_weights?: Array<{
    codigo: string
    nombre: string
    area_km2: number
    porcentaje: number
  }>
  [key: string]: any
}

type ReportInfo = {
  tex?: string | null
  pdf?: string | null
  plan_tex?: string | null
  plan_pdf?: string | null
  compiled?: boolean
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

type DemSource = {
  id: string
  name: string
  resolution_m: number
  coverage: string
  kind: string
  note: string
  recommended: boolean
  estimated_cells: number
}

type DemCatalog = {
  area_km2: number
  recommended_source: string
  sources: DemSource[]
  api_configured: boolean
}

type DemDownloadJob = {
  status: 'queued' | 'downloading' | 'processing' | 'ready' | 'error'
  message?: string
  dem_id?: string
  source?: string
  size_bytes?: number
  preview?: DemPreview
  detail?: string
  iteration?: number
  max_iterations?: number
  adaptive?: { contained?: boolean; rounds?: number }
}

type Outlet = { lat: number; lng: number }
type ViewId = 'analysis' | 'projects'
type RightSidebarTab = 'workflow' | 'advanced'
type GeoJsonData = Record<string, unknown> | null

type StreamEvent = {
  type: 'log' | 'result' | 'error' | 'done'
  level?: ProcessLogEntry['level']
  message?: string
  percent?: number
  job_id?: string
  summary?: Summary
  watershed_geojson?: GeoJsonData
  drainage_geojson?: GeoJsonData
  subbasins_geojson?: GeoJsonData
  report?: ReportInfo
}

type ProjectPayload = {
  serverDemId: string
  localDemFileName: string
  demPreview: DemPreview | null
  outlet: Outlet
  startMode: DemStartModeValue
  minimumAreaKm2: string
  summary: Summary | null
  reportInfo: ReportInfo | null
  watershedGeoJson: GeoJsonData
  drainageGeoJson: GeoJsonData
  subbasinsGeoJson: GeoJsonData
  jobId: string
  activeStep: number
  aoiBounds: MapBounds | null
  selectedDemSource: string
  demAreaKm2: number | null
  demSourceLabel: string
  layerStyles?: LayerStyleConfig
}

const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))
const DEFAULT_OUTLET = { lat: 7.06, lng: -73.85 }

export default function App() {
  const [file, setFile] = useState<File | null>(null)
  const [localDemFileName, setLocalDemFileName] = useState('')
  const [serverDemId, setServerDemId] = useState('')
  const [demPreview, setDemPreview] = useState<DemPreview | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [outlet, setOutlet] = useState<Outlet>(DEFAULT_OUTLET)
  const [showPointCard, setShowPointCard] = useState(false)
  const [startMode, setStartMode] = useState<DemStartModeValue>('outlet')
  const [minimumAreaKm2, setMinimumAreaKm2] = useState('5')
  const [loading, setLoading] = useState(false)
  const [summary, setSummary] = useState<Summary | null>(null)
  const [reportInfo, setReportInfo] = useState<ReportInfo | null>(null)
  const [watershedGeoJson, setWatershedGeoJson] = useState<GeoJsonData>(null)
  const [drainageGeoJson, setDrainageGeoJson] = useState<GeoJsonData>(null)
  const [subbasinsGeoJson, setSubbasinsGeoJson] = useState<GeoJsonData>(null)
  const [jobId, setJobId] = useState('')
  const [error, setError] = useState('')
  const [activeStep, setActiveStep] = useState(0)
  const [lastCalculatedOutlet, setLastCalculatedOutlet] = useState<Outlet | null>(null)
  const [reprocessMenuOpen, setReprocessMenuOpen] = useState(false)

  const isOutletChanged = useMemo(() => {
    if (!lastCalculatedOutlet) return false
    return (
      Math.abs(outlet.lat - lastCalculatedOutlet.lat) > 0.00005 ||
      Math.abs(outlet.lng - lastCalculatedOutlet.lng) > 0.00005
    )
  }, [outlet, lastCalculatedOutlet])

  // Pantalla inicial por defecto: Lista de Proyectos
  const [activeView, setActiveView] = useState<ViewId>('projects')
  const [rightTab, setRightTab] = useState<RightSidebarTab>('workflow')

  const [leftSidebarCollapsed, setLeftSidebarCollapsed] = useState(false)
  const [rightSidebarCollapsed, setRightSidebarCollapsed] = useState(false)
  const [logOpen, setLogOpen] = useState(false)
  const [processProgress, setProcessProgress] = useState(0)
  const [processLogs, setProcessLogs] = useState<ProcessLogEntry[]>([])
  const [aoiBounds, setAoiBounds] = useState<MapBounds | null>(null)
  const [selectingDemArea, setSelectingDemArea] = useState(false)
  const [demSources, setDemSources] = useState<DemSource[]>([])
  const [selectedDemSource, setSelectedDemSource] = useState('COP30')
  const [demAreaKm2, setDemAreaKm2] = useState<number | null>(null)
  const [demApiConfigured, setDemApiConfigured] = useState<boolean | null>(null)
  const [demDownloading, setDemDownloading] = useState(false)
  const [demDownloadMessage, setDemDownloadMessage] = useState('')
  const [demSourceLabel, setDemSourceLabel] = useState('GeoTIFF satelital automático')
  const [layerStyles, setLayerStyles] = useState<LayerStyleConfig>(DEFAULT_LAYER_STYLES)

  // Project Management States
  const [projectId, setProjectId] = useState('')
  const [projectName, setProjectName] = useState('Cuenca Hidrográfica 1')
  const [projectClient, setProjectClient] = useState('')
  const [projectCalculatedBy, setProjectCalculatedBy] = useState('')
  const [projectReviewedBy, setProjectReviewedBy] = useState('')
  const [projectDescription, setProjectDescription] = useState('')
  const [projectCreatedAt, setProjectCreatedAt] = useState('')
  const [projects, setProjects] = useState<StoredProject<ProjectPayload>[]>([])
  const [projectsReady, setProjectsReady] = useState(false)
  const [saveStatus, setSaveStatus] = useState('Listo')
  const [projectDropdownOpen, setProjectDropdownOpen] = useState(false)
  const [projectModalOpen, setProjectModalOpen] = useState(false)
  const [isEditingProject, setIsEditingProject] = useState(false)
  const [reportDownloadOpen, setReportDownloadOpen] = useState(false)

  const hasDem = Boolean(file || serverDemId)
  const fileSize = useMemo(() => (file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : ''), [file])
  const selectedSource = useMemo(
    () => demSources.find((source) => source.id === selectedDemSource) ?? null,
    [demSources, selectedDemSource]
  )

  const clearResults = () => {
    setSummary(null)
    setReportInfo(null)
    setWatershedGeoJson(null)
    setDrainageGeoJson(null)
    setSubbasinsGeoJson(null)
    setJobId('')
  }

  const resetWorkspace = () => {
    setFile(null)
    setLocalDemFileName('')
    setServerDemId('')
    setDemPreview(null)
    setOutlet(DEFAULT_OUTLET)
    setShowPointCard(false)
    setStartMode('outlet')
    setMinimumAreaKm2('5')
    setError('')
    setActiveStep(0)
    setProcessLogs([])
    setProcessProgress(0)
    setLogOpen(false)
    setAoiBounds(null)
    setSelectingDemArea(false)
    setDemSources([])
    setDemAreaKm2(null)
    setDemApiConfigured(null)
    setSelectedDemSource('COP30')
    setDemDownloadMessage('')
    setDemSourceLabel('GeoTIFF satelital automático')
    setLayerStyles(DEFAULT_LAYER_STYLES)
    clearResults()
  }

  const currentPayload = (): ProjectPayload => ({
    serverDemId,
    localDemFileName: file?.name || localDemFileName,
    demPreview,
    outlet,
    startMode,
    minimumAreaKm2,
    summary,
    reportInfo,
    watershedGeoJson,
    drainageGeoJson,
    subbasinsGeoJson,
    jobId,
    activeStep,
    aoiBounds,
    selectedDemSource,
    demAreaKm2,
    demSourceLabel,
    layerStyles,
  })

  const persistCurrentProject = async () => {
    if (!projectsReady || !projectId) return
    const now = new Date().toISOString()
    const project: StoredProject<ProjectPayload> = {
      id: projectId,
      name: projectName.trim() || 'Cuenca sin título',
      client: projectClient.trim(),
      calculatedBy: projectCalculatedBy.trim(),
      reviewedBy: projectReviewedBy.trim(),
      description: projectDescription.trim(),
      createdAt: projectCreatedAt || now,
      updatedAt: now,
      payload: currentPayload(),
    }
    setSaveStatus('Guardando…')
    await putProject(project)
    setProjects((current) => [project, ...current.filter((item) => item.id !== project.id)].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)))
    setSaveStatus('Guardado localmente')
  }

  const restoreProject = (project: StoredProject<ProjectPayload>, navigateToWorkspace = false) => {
    const p = project.payload
    setProjectId(project.id)
    setProjectName(project.name)
    setProjectClient(project.client || '')
    setProjectCalculatedBy(project.calculatedBy || '')
    setProjectReviewedBy(project.reviewedBy || '')
    setProjectDescription(project.description || '')
    setProjectCreatedAt(project.createdAt)
    setActiveProjectId(project.id)
    setFile(null)
    setLocalDemFileName(p.localDemFileName || '')
    setServerDemId(p.serverDemId || '')
    setDemPreview(p.demPreview || null)
    setOutlet(p.outlet || DEFAULT_OUTLET)
    setShowPointCard(Boolean(p.outlet))
    setStartMode(p.startMode || 'outlet')
    setMinimumAreaKm2(p.minimumAreaKm2 || '5')
    setSummary(p.summary || null)
    setReportInfo(p.reportInfo || null)
    setWatershedGeoJson(p.watershedGeoJson || null)
    setDrainageGeoJson(p.drainageGeoJson || null)
    setSubbasinsGeoJson(p.subbasinsGeoJson || null)
    setJobId(p.jobId || '')
    setActiveStep(p.activeStep ?? 0)
    setAoiBounds(p.aoiBounds || null)
    setSelectedDemSource(p.selectedDemSource || 'COP30')
    setDemAreaKm2(p.demAreaKm2 ?? null)
    setDemSourceLabel(p.demSourceLabel || 'GeoTIFF satelital automático')
    if (p.layerStyles) setLayerStyles(p.layerStyles)
    setDemSources([])
    setDemApiConfigured(null)
    setDemDownloadMessage('')
    setProcessLogs([])
    setProcessProgress(p.summary ? 100 : 0)
    setError('')
    setSelectingDemArea(false)
    setLogOpen(false)
    if (navigateToWorkspace) {
      setActiveView('analysis')
    }
    setSaveStatus('Guardado localmente')
  }

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const stored = await listProjects<ProjectPayload>()
        if (cancelled) return
        if (stored.length > 0) {
          setProjects(stored)
          const activeId = getActiveProjectId()
          const active = activeId ? await getProject<ProjectPayload>(activeId) : null
          const project = active || stored[0]
          restoreProject(project, false)
        } else {
          const id = createProjectId()
          const now = new Date().toISOString()
          const initialProject: StoredProject<ProjectPayload> = {
            id,
            name: 'Cuenca Hidrográfica 1',
            client: '',
            calculatedBy: '',
            reviewedBy: '',
            description: 'Proyecto inicial para delimitación y caracterización morfométrica.',
            createdAt: now,
            updatedAt: now,
            payload: {
              serverDemId: '',
              localDemFileName: '',
              demPreview: null,
              outlet: DEFAULT_OUTLET,
              startMode: 'outlet',
              minimumAreaKm2: '5',
              summary: null,
              reportInfo: null,
              watershedGeoJson: null,
              drainageGeoJson: null,
              subbasinsGeoJson: null,
              jobId: '',
              activeStep: 0,
              aoiBounds: null,
              selectedDemSource: 'COP30',
              demAreaKm2: null,
              demSourceLabel: 'GeoTIFF satelital automático',
              layerStyles: DEFAULT_LAYER_STYLES,
            },
          }
          await putProject(initialProject)
          setProjects([initialProject])
          restoreProject(initialProject, false)
        }
        setProjectsReady(true)
        // La lista de proyectos aparece de primero al iniciar la app
        setActiveView('projects')
        setSaveStatus('Listo')
      } catch (err) {
        if (!cancelled) {
          const id = createProjectId()
          setProjectId(id)
          setProjectCreatedAt(new Date().toISOString())
          setProjectsReady(true)
          setActiveView('projects')
          setSaveStatus('Almacenamiento local no disponible')
          setError(err instanceof Error ? err.message : 'No fue posible abrir los proyectos locales.')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    const handleGlobalClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      if (!target.closest('.split-action-container')) {
        setReprocessMenuOpen(false)
      }
      if (!target.closest('.project-topbar-selector')) {
        setProjectDropdownOpen(false)
      }
    }
    window.addEventListener('click', handleGlobalClick)
    return () => window.removeEventListener('click', handleGlobalClick)
  }, [])

  useEffect(() => {
    if (!projectsReady || !projectId || loading || demDownloading || previewLoading) return
    const timer = window.setTimeout(() => {
      void persistCurrentProject().catch(() => setSaveStatus('No se pudo guardar'))
    }, 450)
    return () => window.clearTimeout(timer)
  }, [
    projectsReady,
    projectId,
    projectName,
    projectClient,
    projectCalculatedBy,
    projectReviewedBy,
    projectDescription,
    serverDemId,
    localDemFileName,
    demPreview,
    outlet,
    startMode,
    minimumAreaKm2,
    summary,
    reportInfo,
    watershedGeoJson,
    drainageGeoJson,
    subbasinsGeoJson,
    jobId,
    activeStep,
    aoiBounds,
    selectedDemSource,
    demAreaKm2,
    demSourceLabel,
    layerStyles,
  ])

  const openNewProjectModal = () => {
    setIsEditingProject(false)
    setProjectModalOpen(true)
    setProjectDropdownOpen(false)
  }

  const openEditProjectModal = () => {
    setIsEditingProject(true)
    setProjectModalOpen(true)
    setProjectDropdownOpen(false)
  }

  const handleEditProjectFromDashboard = (project: StoredProject<ProjectPayload>) => {
    setProjectId(project.id)
    setProjectName(project.name)
    setProjectClient(project.client || '')
    setProjectCalculatedBy(project.calculatedBy || '')
    setProjectReviewedBy(project.reviewedBy || '')
    setProjectDescription(project.description || '')
    setProjectCreatedAt(project.createdAt)
    setIsEditingProject(true)
    setProjectModalOpen(true)
  }

  const handleSaveProjectModal = async (data: ProjectFormData) => {
    setProjectModalOpen(false)
    if (isEditingProject) {
      setProjectName(data.name)
      setProjectClient(data.client)
      setProjectCalculatedBy(data.calculatedBy)
      setProjectReviewedBy(data.reviewedBy)
      setProjectDescription(data.description)
    } else {
      try {
        await persistCurrentProject()
      } catch {
        /* ignore */
      }
      resetWorkspace()
      const id = createProjectId()
      const now = new Date().toISOString()
      setProjectId(id)
      setProjectName(data.name)
      setProjectClient(data.client)
      setProjectCalculatedBy(data.calculatedBy)
      setProjectReviewedBy(data.reviewedBy)
      setProjectDescription(data.description)
      setProjectCreatedAt(now)
      setActiveProjectId(id)
      setActiveView('analysis')
      setSaveStatus('Proyecto nuevo iniciado')
    }
  }

  const openStoredProject = async (id: string) => {
    setProjectDropdownOpen(false)
    try {
      await persistCurrentProject()
      const project = await getProject<ProjectPayload>(id)
      if (!project) throw new Error('El proyecto ya no existe en el almacenamiento local.')
      restoreProject(project, true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No fue posible abrir el proyecto.')
    }
  }

  const duplicateStoredProject = async (project: StoredProject<ProjectPayload>) => {
    const now = new Date().toISOString()
    const copy: StoredProject<ProjectPayload> = {
      ...project,
      id: createProjectId(),
      name: `${project.name} · copia`,
      createdAt: now,
      updatedAt: now,
    }
    await putProject(copy)
    setProjects((current) => [copy, ...current])
  }

  const removeStoredProject = async (id: string) => {
    await deleteProject(id)
    const remaining = projects.filter((item) => item.id !== id)
    setProjects(remaining)
    if (id !== projectId) return
    if (remaining.length > 0) restoreProject(remaining[0], false)
    else {
      resetWorkspace()
      const nextId = createProjectId()
      const now = new Date().toISOString()
      setProjectId(nextId)
      setProjectName('Cuenca Hidrográfica 1')
      setProjectClient('')
      setProjectCalculatedBy('')
      setProjectReviewedBy('')
      setProjectDescription('')
      setProjectCreatedAt(now)
      setActiveProjectId(nextId)
      setActiveView('projects')
    }
  }

  const inspectDemFile = async (selected: File, sourceLabel: string) => {
    setFile(selected)
    setLocalDemFileName(selected.name)
    setServerDemId('')
    setDemPreview(null)
    setError('')
    clearResults()
    setActiveStep(1)
    setActiveView('analysis')
    setDemSourceLabel(sourceLabel)
    setPreviewLoading(true)
    try {
      const body = new FormData()
      body.append('dem', selected)
      const response = await fetch('/api/analysis/dem-preview', { method: 'POST', body })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'No fue posible leer la extensión del DEM.')
      setDemPreview(data)
      const b = data.bounds_wgs84 as Bounds
      const newOut = { lat: (b.south + b.north) / 2, lng: (b.west + b.east) / 2 }
      setOutlet(newOut)
      setShowPointCard(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No fue posible inspeccionar el GeoTIFF.')
    } finally {
      setPreviewLoading(false)
    }
  }

  const onFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const selected = event.target.files?.[0] ?? null
    if (selected) await inspectDemFile(selected, 'GeoTIFF cargado por el usuario')
  }

  const loadDemCatalog = async (bounds: MapBounds) => {
    setError('')
    try {
      const params = new URLSearchParams({
        south: String(bounds.south),
        north: String(bounds.north),
        west: String(bounds.west),
        east: String(bounds.east),
      })
      const response = await fetch(`/api/analysis/dem-sources?${params.toString()}`)
      const data = (await response.json()) as DemCatalog & { detail?: string }
      if (!response.ok) throw new Error(data.detail || 'No fue posible consultar las fuentes DEM.')
      setDemSources(data.sources)
      setSelectedDemSource(data.recommended_source)
      setDemAreaKm2(data.area_km2)
      setDemApiConfigured(data.api_configured)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No fue posible consultar las fuentes DEM.')
    }
  }

  const loadDemCatalogForOutlet = async (point: Outlet) => {
    const radiusKm = 25
    const dLat = radiusKm / 111.32
    const dLng = radiusKm / Math.max(1, 111.32 * Math.cos((point.lat * Math.PI) / 180))
    await loadDemCatalog({
      west: point.lng - dLng,
      east: point.lng + dLng,
      south: point.lat - dLat,
      north: point.lat + dLat,
    })
  }

  const onDemAreaSelected = (bounds: MapBounds) => {
    setAoiBounds(bounds)
    setSelectingDemArea(false)
    void loadDemCatalog(bounds)
  }

  const pollDemJob = async (jobIdValue: string): Promise<DemDownloadJob> => {
    for (let attempt = 0; attempt < 1200; attempt += 1) {
      await sleep(1000)
      const statusResponse = await fetch(`/api/analysis/dem-download-jobs/${jobIdValue}`)
      const status = (await statusResponse.json()) as DemDownloadJob
      if (!statusResponse.ok) throw new Error(status.detail || 'No fue posible consultar el estado de la descarga.')
      setDemDownloadMessage(status.message || 'Procesando DEM en el servidor…')
      if (status.status === 'error') throw new Error(status.message || 'No fue posible generar el DEM.')
      if (status.status === 'ready') return status
    }
    throw new Error('El proceso de obtención del DEM superó el tiempo máximo de espera.')
  }

  const activateServerDem = (ready: DemDownloadJob, sourceLabel: string, preserveOutlet = false) => {
    if (!ready.preview || !ready.dem_id) throw new Error('El servidor no devolvió un DEM válido.')
    setFile(null)
    setLocalDemFileName('')
    setServerDemId(ready.dem_id)
    setDemPreview(ready.preview)
    setDemSourceLabel(sourceLabel)
    setActiveStep(1)
    setActiveView('analysis')
    setAoiBounds(ready.preview.bounds_wgs84)
    clearResults()
    if (!preserveOutlet) {
      const b = ready.preview.bounds_wgs84
      setOutlet({ lat: (b.south + b.north) / 2, lng: (b.west + b.east) / 2 })
    }
    const size = ready.size_bytes ? ` · ${(ready.size_bytes / 1024 / 1024).toFixed(1)} MB` : ''
    setDemDownloadMessage(`${ready.message || 'DEM listo'}${size}.`)
  }

  const downloadAutomaticDem = async (): Promise<DemDownloadJob | null> => {
    if (!selectedDemSource) return null
    setDemDownloading(true)
    setDemDownloadMessage('Iniciando búsqueda automática de la extensión necesaria…')
    setError('')
    try {
      const params = new URLSearchParams({
        source: selectedDemSource,
        lat: String(outlet.lat),
        lng: String(outlet.lng),
      })
      const startResponse = await fetch(`/api/analysis/dem-auto-jobs?${params.toString()}`, { method: 'POST' })
      const started = (await startResponse.json()) as { job_id?: string; detail?: string }
      if (!startResponse.ok || !started.job_id) throw new Error(started.detail || 'No fue posible iniciar la obtención automática del DEM.')
      const ready = await pollDemJob(started.job_id)
      const source = demSources.find((item) => item.id === selectedDemSource)
      activateServerDem(ready, `${source?.name || selectedDemSource} · OpenTopography`, true)
      return ready
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No fue posible obtener automáticamente el DEM.')
      return null
    } finally {
      setDemDownloading(false)
    }
  }

  const pickOutlet = (point: Outlet) => {
    setOutlet(point)
    setShowPointCard(true)
    setActiveStep(5)
    setError('')
    clearResults()
    if (!hasDem) {
      setDemDownloadMessage('Punto de aforo definido. Consultando fuentes satelitales…')
      void loadDemCatalogForOutlet(point)
    }
  }

  const runAnalysisWithDemId = async (targetDemId: string | null, targetFile: File | null) => {
    const area = Number(minimumAreaKm2)
    if (!Number.isFinite(area) || area <= 0) {
      setError('El área mínima de aporte debe ser mayor que cero.')
      return
    }

    const body = new FormData()
    if (targetDemId) body.append('dem_id', targetDemId)
    else if (targetFile) body.append('dem', targetFile)
    else {
      setError('Carga o descarga primero un DEM GeoTIFF.')
      return
    }

    body.append('x', outlet.lng.toString())
    body.append('y', outlet.lat.toString())
    body.append('point_crs', 'EPSG:4326')
    body.append('minimum_area_km2', area.toString())
    body.append('dem_source', demSourceLabel)
    body.append('project_name', projectName.trim() || 'Cuenca sin título')
    if (projectClient) body.append('client', projectClient.trim())
    if (projectCalculatedBy) body.append('calculated_by', projectCalculatedBy.trim())
    if (projectReviewedBy) body.append('reviewed_by', projectReviewedBy.trim())

    const startedAt = performance.now()
    const addLog = (level: ProcessLogEntry['level'], message: string) => {
      setProcessLogs((current) => [
        ...current,
        { id: Date.now() + current.length, level, message, elapsed: (performance.now() - startedAt) / 1000 },
      ])
    }

    setLoading(true)
    setError('')
    setLogOpen(true)
    setProcessLogs([])
    setProcessProgress(0)
    clearResults()
    addLog('info', `Iniciando delimitación de cuenca para ${projectName}…`)

    try {
      const response = await fetch('/api/analysis/watershed-stream', { method: 'POST', body })
      if (!response.ok) {
        const data = await response.json().catch(() => null)
        throw new Error(data?.detail || 'No fue posible iniciar el análisis.')
      }
      if (!response.body) throw new Error('El servidor no devolvió un flujo de progreso.')
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let streamError = ''
      let resultReceived = false

      while (true) {
        const { value, done } = await reader.read()
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (!line.trim()) continue
          const item = JSON.parse(line) as StreamEvent
          if (item.type === 'log' && item.message) {
            addLog(item.level || 'info', item.message)
            if (typeof item.percent === 'number') setProcessProgress(item.percent)
          }
          if (item.type === 'error') {
            streamError = item.message || 'Error durante el procesamiento.'
            addLog('error', streamError)
            setProcessProgress(item.percent ?? 100)
          }
          if (item.type === 'result') {
            resultReceived = true
            setSummary(item.summary ?? null)
            setReportInfo(item.report ?? null)
            setWatershedGeoJson(item.watershed_geojson ?? null)
            setDrainageGeoJson(item.drainage_geojson ?? null)
            setSubbasinsGeoJson(item.subbasins_geojson ?? null)
            setJobId(item.job_id ?? '')
          }
        }
        if (done) break
      }
      if (streamError) throw new Error(streamError)
      if (!resultReceived) throw new Error('El procesamiento terminó sin devolver resultados.')
      setLastCalculatedOutlet({ lat: outlet.lat, lng: outlet.lng })
      setProcessProgress(100)
      setActiveStep(8)
      setShowPointCard(false)
      setRightTab('workflow')
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error inesperado.'
      setError(message)
      setProcessLogs((current) => [
        ...current,
        { id: Date.now(), level: 'error', message, elapsed: (performance.now() - startedAt) / 1000 },
      ])
    } finally {
      setLoading(false)
    }
  }

  const handleTriggerAnalysis = async (e?: FormEvent) => {
    if (e) e.preventDefault()

    if (!hasDem) {
      const ready = await downloadAutomaticDem()
      if (ready && ready.dem_id) {
        await runAnalysisWithDemId(ready.dem_id, null)
      }
      return
    }

    await runAnalysisWithDemId(serverDemId || null, file || null)
  }

  const runReprocess = async (mode: 'full' | 'delineation' | 'streams' | 'hydrology' | 'report') => {
    setReprocessMenuOpen(false)
    if (mode === 'full' || !jobId) {
      await handleTriggerAnalysis()
      return
    }

    const area = Number(minimumAreaKm2)
    if (!Number.isFinite(area) || area <= 0) {
      setError('El área mínima de aporte debe ser mayor que cero.')
      return
    }

    const body = new FormData()
    body.append('job_id', jobId)
    body.append('mode', mode)
    body.append('x', outlet.lng.toString())
    body.append('y', outlet.lat.toString())
    body.append('point_crs', 'EPSG:4326')
    body.append('minimum_area_km2', area.toString())
    body.append('project_name', projectName.trim() || 'Cuenca sin título')
    if (projectClient) body.append('client', projectClient.trim())
    if (projectCalculatedBy) body.append('calculated_by', projectCalculatedBy.trim())
    if (projectReviewedBy) body.append('reviewed_by', projectReviewedBy.trim())

    const startedAt = performance.now()
    const addLog = (level: ProcessLogEntry['level'], message: string) => {
      setProcessLogs((current) => [
        ...current,
        { id: Date.now() + current.length, level, message, elapsed: (performance.now() - startedAt) / 1000 },
      ])
    }

    setLoading(true)
    setError('')
    setLogOpen(true)
    setProcessLogs([])
    setProcessProgress(0)
    addLog('info', `Iniciando re-procesamiento (${mode}) para ${projectName}…`)

    try {
      const response = await fetch('/api/analysis/reprocess-stream', { method: 'POST', body })
      if (!response.ok) {
        const data = await response.json().catch(() => null)
        throw new Error(data?.detail || 'No fue posible re-procesar la etapa seleccionada.')
      }
      if (!response.body) throw new Error('El servidor no devolvió un flujo de progreso.')
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let streamError = ''
      let resultReceived = false

      while (true) {
        const { value, done } = await reader.read()
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (!line.trim()) continue
          const item = JSON.parse(line) as StreamEvent
          if (item.type === 'log' && item.message) {
            addLog(item.level || 'info', item.message)
            if (typeof item.percent === 'number') setProcessProgress(item.percent)
          }
          if (item.type === 'error') {
            streamError = item.message || 'Error durante el re-procesamiento.'
            addLog('error', streamError)
            setProcessProgress(item.percent ?? 100)
          }
          if (item.type === 'result') {
            resultReceived = true
            setSummary(item.summary ?? null)
            setReportInfo(item.report ?? null)
            if (item.watershed_geojson) setWatershedGeoJson(item.watershed_geojson)
            if (item.drainage_geojson) setDrainageGeoJson(item.drainage_geojson)
            if (item.subbasins_geojson) setSubbasinsGeoJson(item.subbasins_geojson)
          }
        }
        if (done) break
      }
      if (streamError) throw new Error(streamError)
      if (!resultReceived) throw new Error('El re-procesamiento terminó sin devolver resultados.')
      setLastCalculatedOutlet({ lat: outlet.lat, lng: outlet.lng })
      setProcessProgress(100)
      setShowPointCard(false)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error inesperado.'
      setError(message)
      setProcessLogs((current) => [
        ...current,
        { id: Date.now(), level: 'error', message, elapsed: (performance.now() - startedAt) / 1000 },
      ])
    } finally {
      setLoading(false)
    }
  }

  const downloadArtifact = (path: string) => {
    if (jobId) window.open(`/api/analysis/jobs/${jobId}/artifact/${path}`, '_blank')
  }

  const renderWorkflowTab = () => (
    <div className="sidebar-tab-content">
      {/* Paso 1: Proyecto y Aforo */}
      <div className="workflow-step-card">
        <div className="step-card-header">
          <div className="step-card-number completed">1</div>
          <strong className="step-card-title">Punto de Aforo / Exutorio</strong>
          <span className="step-card-badge">EPSG:4326</span>
        </div>
        <div className="point-coords-row">
          <div className="coords-text">
            <span>Lat: {outlet.lat.toFixed(5)}°</span>
            <span>Lng: {outlet.lng.toFixed(5)}°</span>
          </div>
          <button
            type="button"
            className="coords-copy-btn"
            onClick={() => setShowPointCard(true)}
            title="Ver tarjeta de aforo"
          >
            <MapPin size={12} />
            <span>Ver</span>
          </button>
        </div>
        <p className="helper">Haz clic en cualquier parte del mapa para mover o reubicar el exutorio.</p>
      </div>

      {/* Paso 2: Modelo de Elevación (DEM) */}
      <div className="workflow-step-card">
        <div className="step-card-header">
          <div className={`step-card-number ${hasDem ? 'completed' : ''}`}>2</div>
          <strong className="step-card-title">Modelo de Elevación (DEM)</strong>
          <span className="step-card-badge">{hasDem ? 'Listo' : 'Pendiente'}</span>
        </div>

        {hasDem ? (
          <div className="dem-loaded-box">
            <div className="dem-loaded-header">
              <div className="dem-loaded-badge">
                <Check size={12} />
                <span>DEM Activo</span>
              </div>
              <button
                type="button"
                className="dem-change-btn"
                onClick={() => {
                  setFile(null)
                  setServerDemId('')
                  setDemPreview(null)
                }}
                title="Cambiar o reemplazar el DEM"
              >
                Cambiar
              </button>
            </div>
            <div className="dem-loaded-name">{demSourceLabel}</div>
            <div className="dem-loaded-meta">
              {demPreview
                ? `${demPreview.width} × ${demPreview.height} px · Cotas ${demPreview.elevation_min.toFixed(0)}m a ${demPreview.elevation_max.toFixed(0)}m`
                : 'DEM procesado y listo en memoria'}
            </div>
          </div>
        ) : (
          <div className="dem-options-flow">
            {/* Opción 1: Botón Satelital Automático */}
            <button
              type="button"
              className="dem-auto-btn"
              disabled={demDownloading || demApiConfigured === false}
              onClick={() => void downloadAutomaticDem()}
            >
              <div className="dem-auto-icon">
                <Globe size={15} />
              </div>
              <div className="dem-auto-text">
                <div className="dem-auto-title">
                  {demDownloading ? 'Descargando satélite…' : 'Descargar DEM Satelital'}
                </div>
                <div className="dem-auto-sub">Copernicus GLO-30 (30m) automático</div>
              </div>
            </button>

            {/* Separador */}
            <div className="dem-divider">
              <span>o carga tu archivo</span>
            </div>

            {/* Opción 2: Zona de Carga para GeoTIFF */}
            <label className="dem-upload-zone">
              <input
                type="file"
                accept=".tif,.tiff"
                onChange={onFile}
                style={{ display: 'none' }}
              />
              <FileUp size={18} className="dem-upload-icon" />
              <div className="dem-upload-title">
                {file ? file.name : 'Subir GeoTIFF (.tif / .tiff)'}
              </div>
              <div className="dem-upload-hint">
                {file ? fileSize : 'Haz clic para seleccionar tu ráster local'}
              </div>
            </label>
          </div>
        )}
        {demDownloadMessage && <p className="download-status">{demDownloadMessage}</p>}
      </div>

      {/* Paso 3: Ejecución / Re-procesamiento de Análisis */}
      <div className="workflow-step-card">
        <div className="step-card-header">
          <div className={`step-card-number ${summary ? 'completed' : ''}`}>3</div>
          <strong className="step-card-title">Análisis y Re-procesamiento</strong>
          <span className="step-card-badge">{summary ? 'Ejecutado' : 'Pendiente'}</span>
        </div>

        {/* Split Action Button */}
        <div className="split-action-container">
          <button
            type="button"
            className="split-primary-btn"
            disabled={loading || demDownloading || previewLoading}
            onClick={() => void runReprocess(isOutletChanged || !summary ? 'full' : 'full')}
          >
            <Play size={14} fill="currentColor" />
            <span>
              {loading
                ? `Procesando (${Math.round(processProgress)}%)…`
                : summary
                  ? isOutletChanged
                    ? 'Re-delimitar con Nuevo Exutorio'
                    : 'Re-analizar Cuenca'
                  : 'Ejecutar Análisis de Cuenca'}
            </span>
          </button>

          <button
            type="button"
            className="split-dropdown-trigger"
            disabled={loading || demDownloading || previewLoading}
            onClick={() => setReprocessMenuOpen((v) => !v)}
            title="Opciones de re-procesamiento por etapas"
          >
            <ChevronDown size={14} />
          </button>

          {reprocessMenuOpen && (
            <div className="split-dropdown-menu">
              <div className="split-menu-header">Re-procesar desde etapa</div>

              {/* 1. Análisis Completo */}
              <button
                type="button"
                className="split-menu-item"
                onClick={() => void runReprocess('full')}
              >
                <div className="split-item-icon"><RotateCcw size={14} /></div>
                <div className="split-item-body">
                  <div className="split-item-title">
                    <span>Análisis Completo</span>
                    <span className="split-item-badge">Desde cero</span>
                  </div>
                  <span className="split-item-desc">Vuelve a descargar o preparar el DEM y recalcula todo el flujo D8.</span>
                </div>
              </button>

              {/* 2. Desde Delimitación */}
              <button
                type="button"
                className="split-menu-item"
                disabled={!hasDem && !jobId}
                onClick={() => void runReprocess('delineation')}
              >
                <div className="split-item-icon"><MapPin size={14} /></div>
                <div className="split-item-body">
                  <div className="split-item-title">
                    <span>Desde Delimitación de Cuenca</span>
                    <span className="split-item-badge">Exutorio</span>
                  </div>
                  <span className="split-item-desc">Usa el DEM cargado para trazar la cuenca con el punto actual.</span>
                  {!hasDem && !jobId && <span className="split-item-disabled-reason">Requiere DEM cargado</span>}
                </div>
              </button>

              {/* 3. Desde Red de Drenaje / Subcuencas */}
              <button
                type="button"
                className="split-menu-item"
                disabled={!summary || isOutletChanged}
                onClick={() => void runReprocess('streams')}
              >
                <div className="split-item-icon"><Layers size={14} /></div>
                <div className="split-item-body">
                  <div className="split-item-title">
                    <span>Desde Red de Drenaje y Subcuencas</span>
                    <span className="split-item-badge">{minimumAreaKm2} km²</span>
                  </div>
                  <span className="split-item-desc">Recalcula afluentes y subcuencas manteniendo la cuenca actual.</span>
                  {isOutletChanged && <span className="split-item-disabled-reason">El exutorio cambió; re-delimita primero</span>}
                </div>
              </button>

              {/* 4. Desde Hidrología */}
              <button
                type="button"
                className="split-menu-item"
                disabled={!summary || isOutletChanged}
                onClick={() => void runReprocess('hydrology')}
              >
                <div className="split-item-icon"><Droplets size={14} /></div>
                <div className="split-item-body">
                  <div className="split-item-title">
                    <span>Desde Hidrología y Caudales</span>
                    <span className="split-item-badge">IDEAM · IDF · CN</span>
                  </div>
                  <span className="split-item-desc">Actualiza estaciones, Thiessen, IDF, CN y Caudales Tr.</span>
                  {isOutletChanged && <span className="split-item-disabled-reason">El exutorio cambió; re-delimita primero</span>}
                </div>
              </button>

              {/* 5. Desde Informe y Planos */}
              <button
                type="button"
                className="split-menu-item"
                disabled={!summary || isOutletChanged}
                onClick={() => void runReprocess('report')}
              >
                <div className="split-item-icon"><FileText size={14} /></div>
                <div className="split-item-body">
                  <div className="split-item-title">
                    <span>Desde Generación de Informe y Planos</span>
                    <span className="split-item-badge">PDFs</span>
                  </div>
                  <span className="split-item-desc">Recompila el informe y los planos con nuevos nombres/metadatos al instante.</span>
                  {isOutletChanged && <span className="split-item-disabled-reason">El exutorio cambió; re-delimita primero</span>}
                </div>
              </button>
            </div>
          )}
        </div>
        {error && <div className="error-box">{error}</div>}
      </div>

      {/* Paso 4: Resultados Morfométricos */}
      {summary && (
        <div className="workflow-step-card">
          <div className="step-card-header">
            <div className="step-card-number completed">4</div>
            <strong className="step-card-title">Métricas de la Cuenca</strong>
            <span className="step-card-badge">{summary.dem_source || 'DEM'}</span>
          </div>

          <div className="metrics-grid-dense">
            <div className="metric-dense-card">
              <span>Área Total</span>
              <strong>{summary.area_km2?.toFixed(2)} km²</strong>
            </div>
            <div className="metric-dense-card">
              <span>Perímetro</span>
              <strong>{summary.perimetro_km?.toFixed(2)} km</strong>
            </div>
            <div className="metric-dense-card">
              <span>Orden Strahler</span>
              <strong>{summary.strahler_max ?? '—'}</strong>
            </div>
            <div className="metric-dense-card">
              <span>Compacidad Gravelius</span>
              <strong>{summary.coeficiente_compacidad?.toFixed(3)}</strong>
            </div>
            <div className="metric-dense-card">
              <span>Circularidad Miller</span>
              <strong>{summary.relacion_circularidad?.toFixed(3)}</strong>
            </div>
            <div className="metric-dense-card">
              <span>Subcuencas</span>
              <strong>{summary.subbasin_count ?? '—'}</strong>
            </div>
            <div className="metric-dense-card">
              <span>Tc Promedio</span>
              <strong>{summary.tc_promedio_h ? `${(summary.tc_promedio_h * 60).toFixed(1)} min` : '—'}</strong>
            </div>
            <div className="metric-dense-card">
              <span>Número Curva (CN)</span>
              <strong>{summary.cn_weighted ? summary.cn_weighted.toFixed(1) : (summary.curve_number?.cn_weighted?.toFixed(1) ?? '—')}</strong>
            </div>
            <div className="metric-dense-card">
              <span>Qp (Tr = 100 años)</span>
              <strong style={{ color: '#dc2626' }}>
                {summary.peak_discharges && summary.peak_discharges.length > 5
                  ? `${summary.peak_discharges[5].caudal_diseno_m3_s} m³/s`
                  : '—'}
              </strong>
            </div>
          </div>

          {/* Tabla de Caudales de Diseño por Periodo de Retorno */}
          {summary.peak_discharges && summary.peak_discharges.length > 0 && (
            <div className="peak-flows-container">
              <div className="peak-flows-title">
                Caudales Máximos de Diseño (m³/s)
              </div>
              <div className="peak-flows-grid">
                {summary.peak_discharges.slice(1).map((q: any) => (
                  <div key={q.tr_anos} className="peak-flow-pill">
                    <span className="peak-flow-label">Tr {q.tr_anos} a</span>
                    <strong className="peak-flow-value">{q.caudal_diseno_m3_s} m³/s</strong>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Paso 5: Entregables y Descargas */}
      {jobId && reportInfo && (
        <div className="workflow-step-card">
          <div className="step-card-header">
            <div className="step-card-number completed">5</div>
            <strong className="step-card-title">Entregables y Reportes</strong>
            <span className="step-card-badge">PDF · DOCX · GIS</span>
          </div>
          <div className="download-list">
            {/* Split Download Button for Technical Report (PDF / Word) */}
            <div className="split-action-container" style={{ marginBottom: 6 }}>
              <button
                type="button"
                className="split-primary-btn"
                style={{ height: 34, fontSize: 12 }}
                onClick={() => downloadArtifact(reportInfo.pdf || 'informe_hydrobasin.pdf')}
                title="Descargar Informe Técnico en PDF"
              >
                <FileText size={14} /> Informe Técnico (PDF)
              </button>
              <button
                type="button"
                className="split-dropdown-trigger"
                style={{ height: 34, width: 32 }}
                onClick={() => setReportDownloadOpen(!reportDownloadOpen)}
                title="Opciones de formato (PDF / Word)"
              >
                <ChevronDown size={14} />
              </button>

              {reportDownloadOpen && (
                <div className="split-dropdown-menu">
                  <div className="split-menu-header">FORMATO DE INFORME TÉCNICO</div>
                  <button
                    type="button"
                    className="split-menu-item"
                    onClick={() => {
                      setReportDownloadOpen(false)
                      downloadArtifact(reportInfo.pdf || 'informe_hydrobasin.pdf')
                    }}
                  >
                    <div className="split-item-icon">📄</div>
                    <div className="split-item-text">
                      <div className="split-item-label">Informe Técnico (PDF)</div>
                      <div className="split-item-desc">Documento oficial vectorial de alta calidad</div>
                    </div>
                  </button>
                  <button
                    type="button"
                    className="split-menu-item"
                    onClick={() => {
                      setReportDownloadOpen(false)
                      downloadArtifact('informe_hydrobasin.docx')
                    }}
                  >
                    <div className="split-item-icon">📝</div>
                    <div className="split-item-text">
                      <div className="split-item-label">Informe Técnico (Word .docx)</div>
                      <div className="split-item-desc">Documento editable con tablas y gráficos</div>
                    </div>
                  </button>
                </div>
              )}
            </div>

            {reportInfo.plan_pdf && (
              <button
                type="button"
                className="secondary-button wide"
                onClick={() => downloadArtifact(reportInfo.plan_pdf!)}
              >
                <MapIcon size={14} /> Plano Hidrográfico PDF (2 hojas)
              </button>
            )}
            <button
              type="button"
              className="secondary-button wide"
              onClick={() => downloadArtifact('cuenca_shp.zip')}
            >
              <Download size={14} /> Cuenca Shapefile (.zip)
            </button>
            <button
              type="button"
              className="secondary-button wide"
              onClick={() => downloadArtifact('red_drenaje_shp.zip')}
            >
              <Download size={14} /> Red de Drenaje (.zip)
            </button>
            {summary?.subbasin_count ? (
              <button
                type="button"
                className="secondary-button wide"
                onClick={() => downloadArtifact('subcuencas_shp.zip')}
              >
                <Download size={14} /> Subcuencas Shapefile (.zip)
              </button>
            ) : null}
            {reportInfo.tex && (
              <button
                type="button"
                className="secondary-button wide"
                onClick={() => downloadArtifact(reportInfo.tex!)}
              >
                <FileText size={14} /> Código Fuente LaTeX
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )

  const renderAdvancedTab = () => (
    <div className="sidebar-tab-content">
      {/* Configuración de Área Mínima de Flujo */}
      <div className="workflow-step-card">
        <div className="step-card-header">
          <strong className="step-card-title">Área Mínima de Aporte (km²)</strong>
        </div>
        <input
          value={minimumAreaKm2}
          onChange={(e) => setMinimumAreaKm2(e.target.value)}
          type="number"
          min="0.001"
          step="any"
          className="sgi-modal-input"
          placeholder="5"
        />
        <div className="preset-row">
          {[1, 5, 10, 25].map((val) => (
            <button
              type="button"
              key={val}
              className={Number(minimumAreaKm2) === val ? 'active' : ''}
              onClick={() => setMinimumAreaKm2(String(val))}
            >
              {val} km²
            </button>
          ))}
        </div>
        <p className="helper">
          Controla la densidad y el detalle de la red de drenaje calculada por el algoritmo D8.
        </p>
      </div>

      {/* Selector de Satélite / DEM Source */}
      <div className="workflow-step-card">
        <div className="step-card-header">
          <strong className="step-card-title">Fuente Satelital DEM</strong>
          <span className="step-card-badge">{selectedSource ? `${selectedSource.resolution_m}m` : 'Global'}</span>
        </div>
        {demSources.length > 0 ? (
          <DemSourcePicker sources={demSources} value={selectedDemSource} onChange={setSelectedDemSource} />
        ) : (
          <div className="dem-source-picker">
            {[
              { id: 'COP30', name: 'Copernicus GLO-30', res: '30 m', desc: 'Recomendado global · Alta consistencia' },
              { id: 'SRTMGL1', name: 'SRTM GL1 30m', res: '30 m', desc: 'NASA · Cobertura 60°N - 56°S' },
              { id: 'AW3D30', name: 'ALOS World 3D', res: '30 m', desc: 'JAXA PRISM · Precisión óptica' },
              { id: 'NASADEM', name: 'NASADEM 30m', res: '30 m', desc: 'NASA Reprocesado' },
            ].map((src) => (
              <button
                type="button"
                key={src.id}
                className={`dem-source-card ${selectedDemSource === src.id ? 'selected' : ''}`}
                onClick={() => setSelectedDemSource(src.id)}
              >
                <div className="dem-source-radio">
                  {selectedDemSource === src.id && <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#fff' }} />}
                </div>
                <div className="dem-source-main">
                  <div className="dem-source-name">
                    <strong>{src.name}</strong>
                    <span className="dem-source-badge">{src.res}</span>
                  </div>
                  <span className="dem-source-note">{src.desc}</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Modo de Inicio Manual / Dibujo */}
      <div className="workflow-step-card">
        <div className="step-card-header">
          <strong className="step-card-title">Modo de Extensión DEM</strong>
        </div>
        <DemStartMode value={startMode} onChange={setStartMode} />
        {startMode === 'area' && (
          <button
            type="button"
            className={`secondary-button wide ${selectingDemArea ? 'active' : ''}`}
            onClick={() => {
              setSelectingDemArea(true)
              setAoiBounds(null)
              setError('')
            }}
            style={{ marginTop: 8 }}
          >
            <MapIcon size={14} />
            {selectingDemArea ? 'Marca dos esquinas en el mapa…' : 'Dibujar área en el mapa'}
          </button>
        )}
      </div>
    </div>
  )

  return (
    <div
      className={`hydro-shell ${
        activeView === 'projects' ? 'fullscreen-view' : ''
      } ${leftSidebarCollapsed ? 'left-sidebar-collapsed' : ''} ${
        rightSidebarCollapsed ? 'right-sidebar-collapsed' : ''
      }`}
    >
      {/* 1. GLOBAL RAIL (52px) */}
      <aside className="global-rail" aria-label="Navegación global">
        <div className="rail-brand" title="HydroBasin Studio">
          <Droplets size={18} />
        </div>
        <nav className="rail-nav">
          <button
            type="button"
            className={`rail-button ${activeView === 'projects' ? 'active' : ''}`}
            title="Proyectos Guardados"
            onClick={() => setActiveView('projects')}
          >
            <FolderOpen size={17} />
          </button>
          <button
            type="button"
            className={`rail-button ${activeView === 'analysis' ? 'active' : ''}`}
            title="Estudio y Mapa"
            onClick={() => setActiveView('analysis')}
          >
            <MapIcon size={17} />
          </button>
        </nav>
        <button
          type="button"
          className="rail-button rail-footer"
          title="Nuevo Proyecto"
          onClick={openNewProjectModal}
        >
          <Plus size={17} />
        </button>
      </aside>

      {/* 2. LEFT SIDEBAR (EXCLUSIVAMENTE CAPAS Y SIMBOLOGÍA) */}
      {activeView !== 'projects' && (
        <aside className="left-layer-sidebar">
          <LayerManager
            styles={layerStyles}
            onChange={setLayerStyles}
            hasDem={hasDem}
            hasResults={Boolean(watershedGeoJson)}
          />
        </aside>
      )}

      {/* 3. CENTER WORKSPACE SHELL */}
      <main className="workspace-shell">
        <header className="topbar">
          <div className="topbar-left">
            {activeView === 'analysis' && (
              <button
                type="button"
                className="icon-button"
                title={leftSidebarCollapsed ? 'Mostrar panel de capas' : 'Ocultar panel de capas'}
                onClick={() => setLeftSidebarCollapsed((v) => !v)}
              >
                {leftSidebarCollapsed ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />}
              </button>
            )}

            {/* Project Selector & Metadata Dropdown */}
            <div className="project-topbar-selector">
              <button
                type="button"
                className="project-selector-btn"
                onClick={() => setProjectDropdownOpen((v) => !v)}
              >
                <Droplets size={14} className="text-accent" />
                <span className="project-name-display">{projectName || 'Cuenca sin título'}</span>
                <span className="project-badge-tag">{summary ? 'Analizado' : hasDem ? 'DEM Listo' : 'Activo'}</span>
                <ChevronDown size={12} className="text-muted" />
              </button>

              {projectDropdownOpen && (
                <div className="project-selector-dropdown">
                  <div className="dropdown-header-row">
                    <span>PROYECTOS RECIENTES</span>
                    <button
                      type="button"
                      className="coords-copy-btn"
                      onClick={openEditProjectModal}
                      title="Editar metadatos del proyecto"
                    >
                      <Edit2 size={11} /> Editar
                    </button>
                  </div>
                  <div className="dropdown-project-list">
                    {projects.map((p) => (
                      <button
                        type="button"
                        key={p.id}
                        className={`dropdown-project-item ${p.id === projectId ? 'active' : ''}`}
                        onClick={() => void openStoredProject(p.id)}
                      >
                        <span className="truncate">{p.name}</span>
                        {p.id === projectId && <Check size={12} className="text-accent" />}
                      </button>
                    ))}
                  </div>
                  <div className="dropdown-actions-footer">
                    <button
                      type="button"
                      className="primary-button wide"
                      onClick={openNewProjectModal}
                    >
                      <FolderPlus size={13} /> Nuevo Proyecto
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="topbar-actions">
            {activeView === 'analysis' && (
              <>
                <span className={`engine-status ${loading ? 'running' : ''}`}>
                  <i />
                  {loading
                    ? `Procesando · ${Math.round(processProgress)}%`
                    : demDownloading
                    ? 'Obteniendo DEM satelital…'
                    : saveStatus}
                </span>

                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => setLogOpen((v) => !v)}
                >
                  <Terminal size={14} /> Registro
                </button>

                <button
                  type="button"
                  className="icon-button"
                  title={rightSidebarCollapsed ? 'Mostrar panel derecho' : 'Ocultar panel derecho'}
                  onClick={() => setRightSidebarCollapsed((v) => !v)}
                >
                  {rightSidebarCollapsed ? <PanelRightOpen size={15} /> : <PanelRightClose size={15} />}
                </button>
              </>
            )}

            {activeView === 'projects' && (
              <button
                type="button"
                className="secondary-button"
                onClick={() => setActiveView('analysis')}
              >
                <MapIcon size={14} /> Abrir Mapa
              </button>
            )}
          </div>
        </header>

        <div
          className="dashboard-workspace-grid"
          style={{ display: activeView === 'projects' ? 'block' : 'none' }}
        >
          <ProjectDashboard
            projects={projects}
            activeProjectId={projectId}
            onOpen={(id) => {
              void openStoredProject(id)
            }}
            onDuplicate={(p) => void duplicateStoredProject(p)}
            onDelete={(id) => void removeStoredProject(id)}
            onEdit={(p) => handleEditProjectFromDashboard(p)}
            onNew={openNewProjectModal}
          />
        </div>

        <section
          className="map-workspace-wrapper"
          style={{ display: activeView === 'projects' ? 'none' : 'flex' }}
        >
          <MapLibreWorkspace
            outlet={outlet}
            onPickOutlet={pickOutlet}
            demPreview={demPreview}
            watershedGeoJson={watershedGeoJson}
            drainageGeoJson={drainageGeoJson}
            subbasinsGeoJson={subbasinsGeoJson}
            layerStyles={layerStyles}
            onBasemapChange={(basemap) => setLayerStyles((prev) => ({ ...prev, basemap }))}
            selectingArea={startMode === 'area' && selectingDemArea}
            areaBounds={startMode === 'area' ? aoiBounds : null}
            onAreaSelected={onDemAreaSelected}
            onAreaFirstPoint={() => setError('Selecciona la esquina opuesta del área de interés.')}
            showPointCard={showPointCard}
            onClosePointCard={() => setShowPointCard(false)}
            onAnalyzePoint={() => void handleTriggerAnalysis()}
            analyzing={loading || demDownloading}
            activeView={activeView}
          />

          <ProcessLog
            open={logOpen}
            running={loading}
            progress={processProgress}
            entries={processLogs}
            onClose={() => setLogOpen(false)}
            onClear={() => {
              if (!loading) {
                setProcessLogs([])
                setProcessProgress(0)
              }
            }}
          />
        </section>
      </main>

      {/* 4. RIGHT SIDEBAR (TABS: FLUJO DE TRABAJO | OPCIONES AVANZADAS) */}
      {activeView !== 'projects' && (
        <aside className="right-workflow-sidebar">
          <div className="right-sidebar-tabs">
            <button
              type="button"
              className={`sidebar-tab-btn ${rightTab === 'workflow' ? 'active' : ''}`}
              onClick={() => setRightTab('workflow')}
            >
              <Activity size={14} />
              <span>Flujo de Trabajo</span>
            </button>
            <button
              type="button"
              className={`sidebar-tab-btn ${rightTab === 'advanced' ? 'active' : ''}`}
              onClick={() => setRightTab('advanced')}
            >
              <SlidersHorizontal size={14} />
              <span>Opciones Avanzadas</span>
            </button>
          </div>

          {rightTab === 'workflow' ? renderWorkflowTab() : renderAdvancedTab()}
        </aside>
      )}

      {/* 5. MODAL NUEVO / EDITAR PROYECTO */}
      <ProjectModal
        open={projectModalOpen}
        initialData={{
          name: projectName,
          client: projectClient,
          calculatedBy: projectCalculatedBy,
          reviewedBy: projectReviewedBy,
          description: projectDescription,
        }}
        isEdit={isEditingProject}
        onClose={() => setProjectModalOpen(false)}
        onSave={handleSaveProjectModal}
      />
    </div>
  )
}
