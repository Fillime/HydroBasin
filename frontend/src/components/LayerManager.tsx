import { useState } from 'react'
import {
  ChevronDown,
  ChevronRight,
  Droplets,
  Eye,
  EyeOff,
  Layers,
  Map as MapIcon,
  Mountain,
  Sliders,
  Waves,
} from 'lucide-react'

export type LayerStyleConfig = {
  // Cuenca principal
  watershedVisible: boolean
  watershedColor: string
  watershedOpacity: number
  watershedWidth: number
  // Subcuencas
  subbasinsVisible: boolean
  subbasinsColor: string
  subbasinsOpacity: number
  // Red de drenaje
  drainageVisible: boolean
  drainageColor: string
  drainageOpacity: number
  drainageWidth: number
  // Exutorio
  outletVisible: boolean
  outletColor: string
  outletSize: number
  // DEM
  demVisible: boolean
  demOpacity: number
  // Hillshade
  hillshadeVisible: boolean
  hillshadeOpacity: number
  // Basemap
  basemap: 'streets' | 'satellite' | 'terrain'
}

export const DEFAULT_LAYER_STYLES: LayerStyleConfig = {
  watershedVisible: true,
  watershedColor: '#f59e0b',
  watershedOpacity: 0.15,
  watershedWidth: 2.5,

  subbasinsVisible: true,
  subbasinsColor: '#1f9d8f',
  subbasinsOpacity: 0.16,

  drainageVisible: true,
  drainageColor: '#3b82f6',
  drainageOpacity: 0.95,
  drainageWidth: 1.8,

  outletVisible: true,
  outletColor: '#1f9d8f',
  outletSize: 6,

  demVisible: true,
  demOpacity: 0.65,

  hillshadeVisible: true,
  hillshadeOpacity: 0.35,

  basemap: 'terrain',
}

const PRESET_COLORS = [
  '#1f9d8f', // Hydro Teal
  '#3b82f6', // Blue
  '#f59e0b', // Amber
  '#ef4444', // Red
  '#22c55e', // Green
  '#8b5cf6', // Violet
  '#ec4899', // Pink
  '#06b6d4', // Cyan
  '#f97316', // Orange
  '#e2e8f0', // White / Silver
]

type Props = {
  styles: LayerStyleConfig
  onChange: (updater: (prev: LayerStyleConfig) => LayerStyleConfig) => void
  hasDem: boolean
  hasResults: boolean
}

export default function LayerManager({ styles, onChange, hasDem, hasResults }: Props) {
  const [expandedSection, setExpandedSection] = useState<string | null>('vector')

  const toggleSection = (section: string) => {
    setExpandedSection((prev) => (prev === section ? null : section))
  }

  const update = <K extends keyof LayerStyleConfig>(key: K, value: LayerStyleConfig[K]) => {
    onChange((prev) => ({ ...prev, [key]: value }))
  }

  return (
    <div className="layer-manager-container">
      <div className="layer-manager-header">
        <div className="layer-manager-title">
          <Layers size={15} />
          <strong>Capas y Simbología</strong>
        </div>
        <span className="layer-count-badge">
          {[styles.watershedVisible, styles.subbasinsVisible, styles.drainageVisible, styles.demVisible].filter(Boolean).length} activas
        </span>
      </div>

      <div className="layer-manager-scroll">
        {/* SECCIÓN 1: CAPAS VECTORIALES DE CUENCA */}
        <div className="layer-group">
          <button
            type="button"
            className="layer-group-header"
            onClick={() => toggleSection('vector')}
          >
            {expandedSection === 'vector' ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            <span>Capas Hidrológicas</span>
            <span className="layer-group-status">
              {hasResults ? 'Disponibles' : 'Pendiente cálculo'}
            </span>
          </button>

          {expandedSection === 'vector' && (
            <div className="layer-items-list">
              {/* Cuenca delimitada */}
              <div className={`layer-card ${!hasResults ? 'layer-disabled' : ''}`}>
                <div className="layer-card-top">
                  <button
                    type="button"
                    className="layer-visibility-btn"
                    onClick={() => update('watershedVisible', !styles.watershedVisible)}
                    title={styles.watershedVisible ? 'Ocultar cuenca' : 'Mostrar cuenca'}
                  >
                    {styles.watershedVisible ? <Eye size={14} /> : <EyeOff size={14} className="text-muted" />}
                  </button>
                  <span className="layer-name">Cuenca Principal</span>
                  <div className="layer-swatch-wrapper">
                    <input
                      type="color"
                      value={styles.watershedColor}
                      onChange={(e) => update('watershedColor', e.target.value)}
                      className="layer-color-input"
                      title="Cambiar color de cuenca"
                    />
                    <span className="layer-swatch-preview" style={{ backgroundColor: styles.watershedColor }} />
                  </div>
                </div>

                {styles.watershedVisible && hasResults && (
                  <div className="layer-controls-drawer">
                    <div className="control-row">
                      <span>Opacidad relleno: {Math.round(styles.watershedOpacity * 100)}%</span>
                      <input
                        type="range"
                        min="0"
                        max="1"
                        step="0.05"
                        value={styles.watershedOpacity}
                        onChange={(e) => update('watershedOpacity', parseFloat(e.target.value))}
                        className="sgi-slider"
                      />
                    </div>
                    <div className="control-row">
                      <span>Grosor borde: {styles.watershedWidth}px</span>
                      <input
                        type="range"
                        min="1"
                        max="5"
                        step="0.5"
                        value={styles.watershedWidth}
                        onChange={(e) => update('watershedWidth', parseFloat(e.target.value))}
                        className="sgi-slider"
                      />
                    </div>
                    <div className="color-palette-row">
                      {PRESET_COLORS.map((c) => (
                        <button
                          key={c}
                          type="button"
                          className={`palette-dot ${styles.watershedColor === c ? 'active' : ''}`}
                          style={{ backgroundColor: c }}
                          onClick={() => update('watershedColor', c)}
                        />
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Subcuencas */}
              <div className={`layer-card ${!hasResults ? 'layer-disabled' : ''}`}>
                <div className="layer-card-top">
                  <button
                    type="button"
                    className="layer-visibility-btn"
                    onClick={() => update('subbasinsVisible', !styles.subbasinsVisible)}
                  >
                    {styles.subbasinsVisible ? <Eye size={14} /> : <EyeOff size={14} className="text-muted" />}
                  </button>
                  <span className="layer-name">Subcuencas</span>
                  <div className="layer-swatch-wrapper">
                    <input
                      type="color"
                      value={styles.subbasinsColor}
                      onChange={(e) => update('subbasinsColor', e.target.value)}
                      className="layer-color-input"
                    />
                    <span className="layer-swatch-preview" style={{ backgroundColor: styles.subbasinsColor }} />
                  </div>
                </div>

                {styles.subbasinsVisible && hasResults && (
                  <div className="layer-controls-drawer">
                    <div className="control-row">
                      <span>Opacidad: {Math.round(styles.subbasinsOpacity * 100)}%</span>
                      <input
                        type="range"
                        min="0"
                        max="1"
                        step="0.05"
                        value={styles.subbasinsOpacity}
                        onChange={(e) => update('subbasinsOpacity', parseFloat(e.target.value))}
                        className="sgi-slider"
                      />
                    </div>
                    <div className="color-palette-row">
                      {PRESET_COLORS.map((c) => (
                        <button
                          key={c}
                          type="button"
                          className={`palette-dot ${styles.subbasinsColor === c ? 'active' : ''}`}
                          style={{ backgroundColor: c }}
                          onClick={() => update('subbasinsColor', c)}
                        />
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Red de Drenaje */}
              <div className={`layer-card ${!hasResults ? 'layer-disabled' : ''}`}>
                <div className="layer-card-top">
                  <button
                    type="button"
                    className="layer-visibility-btn"
                    onClick={() => update('drainageVisible', !styles.drainageVisible)}
                  >
                    {styles.drainageVisible ? <Eye size={14} /> : <EyeOff size={14} className="text-muted" />}
                  </button>
                  <span className="layer-name">Red de Drenaje</span>
                  <div className="layer-swatch-wrapper">
                    <input
                      type="color"
                      value={styles.drainageColor}
                      onChange={(e) => update('drainageColor', e.target.value)}
                      className="layer-color-input"
                    />
                    <span className="layer-swatch-preview" style={{ backgroundColor: styles.drainageColor }} />
                  </div>
                </div>

                {styles.drainageVisible && hasResults && (
                  <div className="layer-controls-drawer">
                    <div className="control-row">
                      <span>Opacidad: {Math.round(styles.drainageOpacity * 100)}%</span>
                      <input
                        type="range"
                        min="0"
                        max="1"
                        step="0.05"
                        value={styles.drainageOpacity}
                        onChange={(e) => update('drainageOpacity', parseFloat(e.target.value))}
                        className="sgi-slider"
                      />
                    </div>
                    <div className="control-row">
                      <span>Grosor del río: {styles.drainageWidth}px</span>
                      <input
                        type="range"
                        min="1"
                        max="4"
                        step="0.2"
                        value={styles.drainageWidth}
                        onChange={(e) => update('drainageWidth', parseFloat(e.target.value))}
                        className="sgi-slider"
                      />
                    </div>
                    <div className="color-palette-row">
                      {PRESET_COLORS.map((c) => (
                        <button
                          key={c}
                          type="button"
                          className={`palette-dot ${styles.drainageColor === c ? 'active' : ''}`}
                          style={{ backgroundColor: c }}
                          onClick={() => update('drainageColor', c)}
                        />
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Punto de Exutorio / Aforo */}
              <div className="layer-card">
                <div className="layer-card-top">
                  <button
                    type="button"
                    className="layer-visibility-btn"
                    onClick={() => update('outletVisible', !styles.outletVisible)}
                  >
                    {styles.outletVisible ? <Eye size={14} /> : <EyeOff size={14} className="text-muted" />}
                  </button>
                  <span className="layer-name">Punto de Aforo (Exutorio)</span>
                  <div className="layer-swatch-wrapper">
                    <input
                      type="color"
                      value={styles.outletColor}
                      onChange={(e) => update('outletColor', e.target.value)}
                      className="layer-color-input"
                    />
                    <span className="layer-swatch-preview" style={{ backgroundColor: styles.outletColor }} />
                  </div>
                </div>

                {styles.outletVisible && (
                  <div className="layer-controls-drawer">
                    <div className="control-row">
                      <span>Tamaño punto: {styles.outletSize}px</span>
                      <input
                        type="range"
                        min="4"
                        max="12"
                        step="1"
                        value={styles.outletSize}
                        onChange={(e) => update('outletSize', parseInt(e.target.value, 10))}
                        className="sgi-slider"
                      />
                    </div>
                    <div className="color-palette-row">
                      {PRESET_COLORS.map((c) => (
                        <button
                          key={c}
                          type="button"
                          className={`palette-dot ${styles.outletColor === c ? 'active' : ''}`}
                          style={{ backgroundColor: c }}
                          onClick={() => update('outletColor', c)}
                        />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* SECCIÓN 2: RASTER Y RELIEVE */}
        <div className="layer-group">
          <button
            type="button"
            className="layer-group-header"
            onClick={() => toggleSection('raster')}
          >
            {expandedSection === 'raster' ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            <span>Raster y Relieve</span>
            <span className="layer-group-status">{hasDem ? 'DEM cargado' : 'Sin DEM'}</span>
          </button>

          {expandedSection === 'raster' && (
            <div className="layer-items-list">
              {/* Modelo DEM */}
              <div className={`layer-card ${!hasDem ? 'layer-disabled' : ''}`}>
                <div className="layer-card-top">
                  <button
                    type="button"
                    className="layer-visibility-btn"
                    onClick={() => update('demVisible', !styles.demVisible)}
                  >
                    {styles.demVisible ? <Eye size={14} /> : <EyeOff size={14} className="text-muted" />}
                  </button>
                  <span className="layer-name">Modelo de Elevación (DEM)</span>
                  <span className="layer-badge-tag">Raster</span>
                </div>

                {styles.demVisible && hasDem && (
                  <div className="layer-controls-drawer">
                    <div className="control-row">
                      <span>Opacidad DEM: {Math.round(styles.demOpacity * 100)}%</span>
                      <input
                        type="range"
                        min="0"
                        max="1"
                        step="0.05"
                        value={styles.demOpacity}
                        onChange={(e) => update('demOpacity', parseFloat(e.target.value))}
                        className="sgi-slider"
                      />
                    </div>
                  </div>
                )}
              </div>

              {/* Relieve 3D / Hillshade */}
              <div className="layer-card">
                <div className="layer-card-top">
                  <button
                    type="button"
                    className="layer-visibility-btn"
                    onClick={() => update('hillshadeVisible', !styles.hillshadeVisible)}
                  >
                    {styles.hillshadeVisible ? <Eye size={14} /> : <EyeOff size={14} className="text-muted" />}
                  </button>
                  <span className="layer-name">Relieve Sombreado 3D</span>
                  <span className="layer-badge-tag">Terreno</span>
                </div>

                {styles.hillshadeVisible && (
                  <div className="layer-controls-drawer">
                    <div className="control-row">
                      <span>Exageración / Opacidad: {Math.round(styles.hillshadeOpacity * 100)}%</span>
                      <input
                        type="range"
                        min="0"
                        max="1"
                        step="0.05"
                        value={styles.hillshadeOpacity}
                        onChange={(e) => update('hillshadeOpacity', parseFloat(e.target.value))}
                        className="sgi-slider"
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* SECCIÓN 3: MAPA BASE */}
        <div className="layer-group">
          <button
            type="button"
            className="layer-group-header"
            onClick={() => toggleSection('basemap')}
          >
            {expandedSection === 'basemap' ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            <span>Mapa Base</span>
          </button>

          {expandedSection === 'basemap' && (
            <div className="layer-items-list">
              <div className="basemap-selector-grid">
                <button
                  type="button"
                  className={`basemap-card-btn ${styles.basemap === 'terrain' ? 'active' : ''}`}
                  onClick={() => update('basemap', 'terrain')}
                >
                  <Mountain size={15} />
                  <span>Relieve 3D</span>
                </button>
                <button
                  type="button"
                  className={`basemap-card-btn ${styles.basemap === 'satellite' ? 'active' : ''}`}
                  onClick={() => update('basemap', 'satellite')}
                >
                  <MapIcon size={15} />
                  <span>Satélite</span>
                </button>
                <button
                  type="button"
                  className={`basemap-card-btn ${styles.basemap === 'streets' ? 'active' : ''}`}
                  onClick={() => update('basemap', 'streets')}
                >
                  <Droplets size={15} />
                  <span>Calles</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
