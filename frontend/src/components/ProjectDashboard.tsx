import { BarChart3, Copy, Droplets, FolderOpen, Map, Plus, Trash2 } from 'lucide-react'
import type { StoredProject } from '../services/projectStore'

type Payload = {
  summary?: { area_km2?: number } | null
  serverDemId?: string
  localDemFileName?: string
  demSourceLabel?: string
  outlet?: { lat: number; lng: number }
}

type Props = {
  projects: StoredProject<Payload>[]
  activeProjectId: string
  onOpen: (id: string) => void
  onDuplicate: (project: StoredProject<Payload>) => void
  onDelete: (id: string) => void
  onNew: () => void
}

function projectStatus(project: StoredProject<Payload>) {
  if (project.payload.summary) return 'Analizado'
  if (project.payload.serverDemId) return 'DEM listo'
  if (project.payload.localDemFileName) return 'DEM local'
  return 'Borrador'
}

export default function ProjectDashboard({ projects, activeProjectId, onOpen, onDuplicate, onDelete, onNew }: Props) {
  const analyzed = projects.filter((project) => project.payload.summary).length
  const ready = projects.filter((project) => !project.payload.summary && (project.payload.serverDemId || project.payload.localDemFileName)).length
  const totalArea = projects.reduce((sum, project) => sum + (project.payload.summary?.area_km2 || 0), 0)

  return (
    <div className="project-dashboard">
      <header className="project-dashboard-hero">
        <div>
          <span className="dashboard-eyebrow">PORTAFOLIO HIDROLÓGICO</span>
          <h1>Proyectos</h1>
          <p>Administra cuencas, DEM, análisis y entregables desde un solo espacio.</p>
        </div>
        <button className="primary-button dashboard-new" onClick={onNew}><Plus size={15} /> Nuevo proyecto</button>
      </header>

      <section className="dashboard-kpis">
        <article><span><FolderOpen size={15} /> Proyectos</span><strong>{projects.length}</strong><small>Guardados localmente</small></article>
        <article><span><BarChart3 size={15} /> Analizados</span><strong>{analyzed}</strong><small>Con resultados disponibles</small></article>
        <article><span><Map size={15} /> Preparados</span><strong>{ready}</strong><small>DEM listo para procesar</small></article>
        <article><span><Droplets size={15} /> Área acumulada</span><strong>{totalArea.toLocaleString(undefined, { maximumFractionDigits: 1 })}</strong><small>km² delimitados</small></article>
      </section>

      <section className="dashboard-section">
        <div className="dashboard-section-heading">
          <div><strong>Proyectos recientes</strong><span>{projects.length ? 'Ordenados por última modificación' : 'Todavía no hay proyectos guardados'}</span></div>
        </div>
        <div className="dashboard-project-grid">
          {projects.length === 0 && <button className="dashboard-empty-project" onClick={onNew}><Plus size={22} /><strong>Crear primer proyecto</strong><span>Define un aforo, descarga un DEM y comienza el análisis.</span></button>}
          {projects.map((project) => {
            const status = projectStatus(project)
            const isActive = project.id === activeProjectId
            return (
              <article className={`dashboard-project-card ${isActive ? 'active' : ''}`} key={project.id}>
                <button className="dashboard-project-open" onClick={() => onOpen(project.id)}>
                  <div className="dashboard-project-top"><span className={`dashboard-status status-${status.toLowerCase().replace(' ', '-')}`}>{status}</span>{isActive && <small>ACTIVO</small>}</div>
                  <div className="dashboard-project-icon"><Droplets size={18} /></div>
                  <strong>{project.name}</strong>
                  <p>{project.payload.demSourceLabel || project.payload.localDemFileName || 'Sin fuente DEM definida'}</p>
                  <div className="dashboard-project-meta">
                    <span>{project.payload.summary?.area_km2 ? `${project.payload.summary.area_km2.toFixed(2)} km²` : 'Área pendiente'}</span>
                    <span>{new Date(project.updatedAt).toLocaleDateString()}</span>
                  </div>
                </button>
                <div className="dashboard-project-actions">
                  <button title="Duplicar" onClick={() => onDuplicate(project)}><Copy size={14} /> Duplicar</button>
                  <button title="Eliminar" onClick={() => onDelete(project.id)}><Trash2 size={14} /></button>
                </div>
              </article>
            )
          })}
        </div>
      </section>
    </div>
  )
}
