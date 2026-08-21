import { FormEvent, useState } from 'react'
import { Droplets, Info, User, X } from 'lucide-react'

export type ProjectFormData = {
  name: string
  client: string
  calculatedBy: string
  reviewedBy: string
  description: string
}

type Props = {
  open: boolean
  initialData?: Partial<ProjectFormData>
  isEdit?: boolean
  onClose: () => void
  onSave: (data: ProjectFormData) => void
}

export default function ProjectModal({
  open,
  initialData,
  isEdit = false,
  onClose,
  onSave,
}: Props) {
  const [name, setName] = useState(initialData?.name || '')
  const [client, setClient] = useState(initialData?.client || '')
  const [calculatedBy, setCalculatedBy] = useState(initialData?.calculatedBy || '')
  const [reviewedBy, setReviewedBy] = useState(initialData?.reviewedBy || '')
  const [description, setDescription] = useState(initialData?.description || '')
  const [error, setError] = useState('')

  if (!open) return null

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    const trimmedName = name.trim()
    if (!trimmedName) {
      setError('El nombre del proyecto es obligatorio.')
      return
    }
    setError('')
    onSave({
      name: trimmedName,
      client: client.trim(),
      calculatedBy: calculatedBy.trim(),
      reviewedBy: reviewedBy.trim(),
      description: description.trim(),
    })
  }

  return (
    <div className="sgi-modal-backdrop">
      <div className="sgi-modal-dialog" role="dialog" aria-modal="true" style={{ maxWidth: 480 }}>
        <div className="sgi-modal-header">
          <div className="sgi-modal-title">
            <div className="modal-icon-badge">
              <Droplets size={17} />
            </div>
            <div>
              <h3>{isEdit ? 'Editar Proyecto' : 'Nuevo Proyecto Hidrológico'}</h3>
              <p>Define la identificación del estudio y los responsables para el rótulo e informe.</p>
            </div>
          </div>
          <button
            type="button"
            className="sgi-modal-close"
            onClick={onClose}
            title="Cerrar"
          >
            <X size={15} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="sgi-modal-body">
          {error && <div className="modal-error-alert">{error}</div>}

          <div className="sgi-form-field">
            <label htmlFor="project-name-input">
              Nombre del proyecto <span className="text-accent">*</span>
            </label>
            <input
              id="project-name-input"
              type="text"
              className="sgi-modal-input"
              placeholder="Ej: Cuenca Quebrada La Honda"
              value={name}
              onChange={(e) => {
                setName(e.target.value)
                if (error) setError('')
              }}
              autoFocus
              required
            />
          </div>

          <div className="sgi-form-field">
            <label htmlFor="project-client-input">
              Cliente / Entidad <small>(Opcional)</small>
            </label>
            <input
              id="project-client-input"
              type="text"
              className="sgi-modal-input"
              placeholder="Ej: Consorcio Vial / Alcaldía Municipal"
              value={client}
              onChange={(e) => setClient(e.target.value)}
            />
          </div>

          <div className="field-grid">
            <div className="sgi-form-field">
              <label htmlFor="project-calc-input">
                Calculó / Elaboró <small>(Opcional)</small>
              </label>
              <input
                id="project-calc-input"
                type="text"
                className="sgi-modal-input"
                placeholder="Ej: Ing. Juan Pérez"
                value={calculatedBy}
                onChange={(e) => setCalculatedBy(e.target.value)}
              />
            </div>
            <div className="sgi-form-field">
              <label htmlFor="project-rev-input">
                Revisó <small>(Opcional)</small>
              </label>
              <input
                id="project-rev-input"
                type="text"
                className="sgi-modal-input"
                placeholder="Ej: Ing. Carlos Gómez"
                value={reviewedBy}
                onChange={(e) => setReviewedBy(e.target.value)}
              />
            </div>
          </div>

          <div className="sgi-form-field">
            <label htmlFor="project-desc-input">
              Descripción / Notas del estudio <small>(Opcional)</small>
            </label>
            <textarea
              id="project-desc-input"
              className="sgi-modal-textarea"
              rows={2}
              placeholder="Ej: Análisis morfométrico y delimitación para diseño de pontón y obras de drenaje."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          <div className="project-modal-tip">
            <Info size={14} className="tip-icon" />
            <span>
              Estos datos se incorporarán automáticamente en la portada del informe técnico y en el rótulo de los planos.
            </span>
          </div>

          <div className="sgi-modal-footer">
            <button
              type="button"
              className="secondary-button"
              onClick={onClose}
            >
              Cancelar
            </button>
            <button
              type="submit"
              className="primary-button"
            >
              {isEdit ? 'Guardar Cambios' : 'Crear e Iniciar'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
