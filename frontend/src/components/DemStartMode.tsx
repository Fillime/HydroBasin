import { FileUp, Map, MapPinned, Sparkles } from 'lucide-react'

export type DemStartModeValue = 'outlet' | 'area' | 'file'

type Props = {
  value: DemStartModeValue
  onChange: (value: DemStartModeValue) => void
}

const options = [
  {
    id: 'outlet' as const,
    icon: MapPinned,
    title: 'Punto de aforo',
    description: 'Marca el exutorio y HydroBasin determina automáticamente cuánto DEM necesita.',
    recommended: true,
  },
  {
    id: 'area' as const,
    icon: Map,
    title: 'Área manual',
    description: 'Dibuja la extensión que quieres descargar y ajusta sus esquinas en el mapa.',
    recommended: false,
  },
  {
    id: 'file' as const,
    icon: FileUp,
    title: 'DEM propio',
    description: 'Carga un GeoTIFF que ya tengas en tu equipo.',
    recommended: false,
  },
]

export default function DemStartMode({ value, onChange }: Props) {
  return (
    <div className="dem-start-modes">
      {options.map(({ id, icon: Icon, title, description, recommended }) => (
        <button
          type="button"
          key={id}
          className={`dem-start-card ${value === id ? 'selected' : ''}`}
          onClick={() => onChange(id)}
          aria-pressed={value === id}
        >
          <span className="dem-start-icon"><Icon size={16} /></span>
          <span className="dem-start-copy">
            <span className="dem-start-title">{title}{recommended && <span className="mode-badge"><Sparkles size={9} /> Recomendado</span>}</span>
            <span className="dem-start-description">{description}</span>
          </span>
        </button>
      ))}
    </div>
  )
}
