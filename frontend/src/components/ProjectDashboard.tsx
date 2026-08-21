import { useMemo, useState } from 'react'
import {
  Building2,
  Calendar,
  Check,
  ChevronRight,
  Copy,
  Droplets,
  Edit2,
  ExternalLink,
  Eye,
  FileSpreadsheet,
  Filter,
  FolderOpen,
  MapPin,
  Plus,
  Search,
  Trash2,
  User,
} from 'lucide-react'
import type { StoredProject } from '../services/projectStore'

type Payload = {
  summary?: { area_km2?: number } | null
  serverDemId?: string
  localDemFileName?: string
  demSourceLabel?: string
  outlet?: { lat: number; lng: number }
  [key: string]: unknown
}

type Props<T = Payload> = {
  projects: StoredProject<T>[]
  activeProjectId: string
  onOpen: (id: string) => void
  onDuplicate: (project: StoredProject<T>) => void
  onDelete: (id: string) => void
  onEdit: (project: StoredProject<T>) => void
  onNew: () => void
}

function getProjectStatus(project: StoredProject<Payload>) {
  if (project.payload.summary) {
    return { label: 'Analizado', class: 'status-analizado' }
  }
  if (project.payload.serverDemId || project.payload.localDemFileName) {
    return { label: 'DEM listo', class: 'status-dem-listo' }
  }
  return { label: 'Borrador', class: 'status-borrador' }
}

export default function ProjectDashboard<T extends Payload = Payload>({
  projects,
  activeProjectId,
  onOpen,
  onDuplicate,
  onDelete,
  onEdit,
  onNew,
}: Props<T>) {
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'analizado' | 'dem' | 'draft'>('all')

  const totalProjects = projects.length
  const analyzedCount = projects.filter((p) => p.payload.summary).length
  const totalArea = projects.reduce((sum, p) => sum + (p.payload.summary?.area_km2 || 0), 0)

  const filteredProjects = useMemo(() => {
    return projects.filter((p) => {
      const matchesSearch =
        !search.trim() ||
        p.name.toLowerCase().includes(search.toLowerCase()) ||
        (p.client && p.client.toLowerCase().includes(search.toLowerCase())) ||
        (p.calculatedBy && p.calculatedBy.toLowerCase().includes(search.toLowerCase())) ||
        (p.description && p.description.toLowerCase().includes(search.toLowerCase()))

      if (!matchesSearch) return false

      if (statusFilter === 'analizado') return Boolean(p.payload.summary)
      if (statusFilter === 'dem') return !p.payload.summary && (p.payload.serverDemId || p.payload.localDemFileName)
      if (statusFilter === 'draft') return !p.payload.summary && !p.payload.serverDemId && !p.payload.localDemFileName

      return true
    })
  }, [projects, search, statusFilter])

  return (
    <div className="sgi-table-workspace">
      {/* SgiPageHeader Estándar */}
      <header className="sgi-page-header">
        <div className="sgi-header-meta">
          <span className="sgi-eyebrow">PORTAFOLIO DE PROYECTOS</span>
          <h1 className="sgi-title">Estudios y Cuencas Hidrográficas</h1>
          <p className="sgi-desc">
            Gestiona tus proyectos de delimitación hidrológica, accede a sus mapas y genera entregables técnicos.
          </p>
        </div>
        <div className="sgi-header-actions">
          <button type="button" className="primary-button" onClick={onNew} style={{ height: 32 }}>
            <Plus size={14} /> Nuevo Proyecto
          </button>
        </div>
      </header>

      {/* Barra de Filtros y Búsqueda */}
      <div className="sgi-filter-bar">
        <div className="sgi-search-box">
          <Search size={14} className="sgi-search-icon" />
          <input
            type="text"
            className="sgi-search-input"
            placeholder="Buscar por nombre, cliente, responsable…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {search && (
            <button type="button" className="sgi-search-clear" onClick={() => setSearch('')}>
              ×
            </button>
          )}
        </div>

        <div className="sgi-tab-group">
          <button
            type="button"
            className={`sgi-filter-tab ${statusFilter === 'all' ? 'active' : ''}`}
            onClick={() => setStatusFilter('all')}
          >
            Todos <span className="tab-badge">{totalProjects}</span>
          </button>
          <button
            type="button"
            className={`sgi-filter-tab ${statusFilter === 'analizado' ? 'active' : ''}`}
            onClick={() => setStatusFilter('analizado')}
          >
            Analizados <span className="tab-badge">{analyzedCount}</span>
          </button>
          <button
            type="button"
            className={`sgi-filter-tab ${statusFilter === 'dem' ? 'active' : ''}`}
            onClick={() => setStatusFilter('dem')}
          >
            Con DEM
          </button>
          <button
            type="button"
            className={`sgi-filter-tab ${statusFilter === 'draft' ? 'active' : ''}`}
            onClick={() => setStatusFilter('draft')}
          >
            Borradores
          </button>
        </div>
      </div>

      {/* Contenedor de Tabla Compacta */}
      <div className="sgi-table-container">
        <table className="sgi-compact-table">
          <thead>
            <tr>
              <th style={{ width: '28%' }}>PROYECTO</th>
              <th style={{ width: '18%' }}>CLIENTE / ENTIDAD</th>
              <th style={{ width: '11%' }}>ESTADO</th>
              <th style={{ width: '12%', textAlign: 'right' }}>ÁREA CUENCA</th>
              <th style={{ width: '15%' }}>RESPONSABLE</th>
              <th style={{ width: '16%', textAlign: 'center' }}>ACCIONES</th>
            </tr>
          </thead>
          <tbody>
            {filteredProjects.length === 0 ? (
              <tr>
                <td colSpan={6} className="sgi-table-empty">
                  <FolderOpen size={28} className="empty-icon" />
                  <p>
                    {search || statusFilter !== 'all'
                      ? 'No se encontraron proyectos con los filtros actuales.'
                      : 'No hay proyectos registrados.'}
                  </p>
                  <button type="button" className="secondary-button" onClick={onNew} style={{ marginTop: 8 }}>
                    <Plus size={13} /> Crear Proyecto
                  </button>
                </td>
              </tr>
            ) : (
              filteredProjects.map((project) => {
                const status = getProjectStatus(project)
                const isActive = project.id === activeProjectId
                const area = project.payload.summary?.area_km2

                return (
                  <tr
                    key={project.id}
                    className={`sgi-table-row ${isActive ? 'row-active' : ''}`}
                    onDoubleClick={() => onOpen(project.id)}
                  >
                    {/* Columna 1: Proyecto */}
                    <td className="col-project">
                      <div className="project-cell-main">
                        <div className="project-icon-indicator" title="Doble clic para abrir">
                          <Droplets size={14} />
                        </div>
                        <div className="project-cell-text">
                          <div className="project-title-row">
                            <span className="project-name-text" onClick={() => onOpen(project.id)}>
                              {project.name}
                            </span>
                            {isActive && <span className="active-pill">ACTIVO</span>}
                          </div>
                          {project.description && (
                            <span className="project-sub-desc">{project.description}</span>
                          )}
                        </div>
                      </div>
                    </td>

                    {/* Columna 2: Cliente */}
                    <td className="col-client">
                      {project.client ? (
                        <div className="cell-client">
                          <Building2 size={12} className="cell-sub-icon" />
                          <span className="truncate">{project.client}</span>
                        </div>
                      ) : (
                        <span className="text-dim">—</span>
                      )}
                    </td>

                    {/* Columna 3: Estado */}
                    <td className="col-status">
                      <span className={`sgi-badge ${status.class}`}>{status.label}</span>
                    </td>

                    {/* Columna 4: Área */}
                    <td className="col-area" style={{ textAlign: 'right' }}>
                      {area != null ? (
                        <strong className="area-value">{area.toFixed(2)} km²</strong>
                      ) : (
                        <span className="text-dim">—</span>
                      )}
                    </td>

                    {/* Columna 5: Responsable */}
                    <td className="col-author">
                      {project.calculatedBy || project.reviewedBy ? (
                        <div className="cell-author">
                          <User size={12} className="cell-sub-icon" />
                          <span className="truncate">
                            {project.calculatedBy || project.reviewedBy}
                          </span>
                        </div>
                      ) : (
                        <span className="text-dim">—</span>
                      )}
                    </td>

                    {/* Columna 6: Acciones */}
                    <td className="col-actions" style={{ textAlign: 'center' }}>
                      <div className="action-button-group">
                        <button
                          type="button"
                          className="sgi-action-btn btn-view"
                          title="Abrir espacio de trabajo y mapa"
                          onClick={() => onOpen(project.id)}
                        >
                          <Eye size={13} />
                          <span>Ver</span>
                        </button>

                        <button
                          type="button"
                          className="sgi-action-btn"
                          title="Editar información del proyecto"
                          onClick={() => onEdit(project)}
                        >
                          <Edit2 size={13} />
                          <span>Editar</span>
                        </button>

                        <button
                          type="button"
                          className="sgi-action-btn icon-only"
                          title="Duplicar proyecto"
                          onClick={() => onDuplicate(project)}
                        >
                          <Copy size={13} />
                        </button>

                        <button
                          type="button"
                          className="sgi-action-btn icon-only btn-delete"
                          title="Eliminar proyecto"
                          onClick={() => onDelete(project.id)}
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Barra de Estadísticas y Resumen Inferior */}
      <footer className="sgi-table-footer">
        <div className="footer-stat">
          <span>Total Proyectos:</span>
          <strong>{totalProjects}</strong>
        </div>
        <div className="footer-stat-divider" />
        <div className="footer-stat">
          <span>Analizados:</span>
          <strong className="text-success">{analyzedCount}</strong>
        </div>
        <div className="footer-stat-divider" />
        <div className="footer-stat">
          <span>Área Acumulada:</span>
          <strong>{totalArea.toFixed(1)} km²</strong>
        </div>
        <div className="footer-tip">
          <span>Doble clic en una fila para abrir directamente en el mapa.</span>
        </div>
      </footer>
    </div>
  )
}
