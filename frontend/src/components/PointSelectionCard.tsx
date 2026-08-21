import { useEffect, useState } from 'react'
import {
  Check,
  Copy,
  Globe2,
  Loader2,
  MapPin,
  Play,
  X,
} from 'lucide-react'
import { reverseGeocode, type GeocodedLocation } from '../services/geocodingService'

type Props = {
  lat: number
  lng: number
  onAnalyze: () => void
  onClose: () => void
  analyzing?: boolean
  disabled?: boolean
  style?: React.CSSProperties
}

export default function PointSelectionCard({
  lat,
  lng,
  onAnalyze,
  onClose,
  analyzing = false,
  disabled = false,
  style,
}: Props) {
  const [location, setLocation] = useState<GeocodedLocation | null>(null)
  const [loadingGeo, setLoadingGeo] = useState(true)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoadingGeo(true)

    reverseGeocode(lat, lng)
      .then((res) => {
        if (!cancelled) {
          setLocation(res)
          setLoadingGeo(false)
        }
      })
      .catch(() => {
        if (!cancelled) setLoadingGeo(false)
      })

    return () => {
      cancelled = true
    }
  }, [lat, lng])

  const copyCoords = () => {
    const text = `${lat.toFixed(6)}, ${lng.toFixed(6)}`
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div className="point-selection-card" style={style}>
      <div className="point-card-header">
        <div className="point-card-title">
          <MapPin size={14} className="point-pin-icon" />
          <span>Punto de Aforo Seleccionado</span>
        </div>
        <div className="point-card-actions">
          <button
            type="button"
            className="point-close-btn"
            onClick={onClose}
            title="Cerrar"
          >
            <X size={13} />
          </button>
        </div>
      </div>

      <div className="point-card-body">
        {/* Geocoding display */}
        <div className="point-location-box">
          {loadingGeo ? (
            <div className="point-location-loading">
              <Loader2 size={13} className="animate-spin" />
              <span>Consultando ubicación geográfica…</span>
            </div>
          ) : location ? (
            <div className="point-location-info">
              {location.isColombia ? (
                <>
                  <div className="location-place-name">
                    <strong>{location.municipality || 'Municipio no identificado'}</strong>
                    {location.department && (
                      <span className="location-department">{location.department}</span>
                    )}
                  </div>
                  <div className="location-country-badge">
                    <span className="co-flag-dot" />
                    <span>Colombia</span>
                  </div>
                </>
              ) : (
                <div className="location-place-name">
                  <div className="location-international">
                    <Globe2 size={13} className="text-muted" />
                    <strong>{location.country}</strong>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="point-location-info">
              <strong>Ubicación seleccionada</strong>
            </div>
          )}
        </div>

        {/* Coordinates readout with copy */}
        <div className="point-coords-row">
          <div className="coords-text">
            <span>Lat: {lat.toFixed(5)}°</span>
            <span>Lng: {lng.toFixed(5)}°</span>
          </div>
          <button
            type="button"
            className="coords-copy-btn"
            onClick={copyCoords}
            title="Copiar coordenadas"
          >
            {copied ? <Check size={12} className="text-success" /> : <Copy size={12} />}
            <span>{copied ? 'Copiado' : 'Copiar'}</span>
          </button>
        </div>
      </div>

      <div className="point-card-footer">
        <button
          type="button"
          className="analyze-point-button"
          disabled={analyzing || disabled}
          onClick={onAnalyze}
        >
          {analyzing ? (
            <>
              <Loader2 size={14} className="animate-spin" />
              <span>Procesando cuenca…</span>
            </>
          ) : (
            <>
              <Play size={14} fill="currentColor" />
              <span>Analizar Cuenca</span>
            </>
          )}
        </button>
      </div>
    </div>
  )
}
