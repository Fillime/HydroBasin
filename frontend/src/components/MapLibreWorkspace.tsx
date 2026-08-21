import { useEffect, useRef, useState } from 'react'
import maplibregl, {
  type GeoJSONSource,
  type ImageSource,
  type Map as MapLibreMap,
  type StyleSpecification,
} from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { Globe, Map as MapIcon, Mountain } from 'lucide-react'
import PointSelectionCard from './PointSelectionCard'
import type { LayerStyleConfig } from './LayerManager'

export type MapBounds = { west: number; south: number; east: number; north: number }
export type MapOutlet = { lat: number; lng: number }
type GeoJsonData = Record<string, unknown> | null

type DemPreview = {
  filename: string
  bounds_wgs84: MapBounds
  preview_data_url: string
}

type Props = {
  outlet: MapOutlet
  onPickOutlet: (point: MapOutlet) => void
  demPreview: DemPreview | null
  watershedGeoJson: GeoJsonData
  drainageGeoJson: GeoJsonData
  subbasinsGeoJson: GeoJsonData
  layerStyles: LayerStyleConfig
  onBasemapChange?: (basemap: 'streets' | 'satellite' | 'terrain') => void
  selectingArea: boolean
  areaBounds: MapBounds | null
  onAreaSelected: (bounds: MapBounds) => void
  onAreaFirstPoint?: () => void
  showPointCard?: boolean
  onClosePointCard?: () => void
  onAnalyzePoint?: () => void
  analyzing?: boolean
  activeView?: string
}

const EMPTY_FC = { type: 'FeatureCollection', features: [] } as const
const OPENFREE_STYLE = 'https://tiles.openfreemap.org/styles/liberty'

const SATELLITE_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    satellite: {
      type: 'raster',
      tiles: [
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      ],
      tileSize: 256,
      attribution: 'Tiles © Esri',
      maxzoom: 19,
    },
  },
  layers: [{ id: 'satellite', type: 'raster', source: 'satellite' }],
}

function polygonFromBounds(bounds: MapBounds | null) {
  if (!bounds) return EMPTY_FC
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        properties: {},
        geometry: {
          type: 'Polygon',
          coordinates: [
            [
              [bounds.west, bounds.south],
              [bounds.east, bounds.south],
              [bounds.east, bounds.north],
              [bounds.west, bounds.north],
              [bounds.west, bounds.south],
            ],
          ],
        },
      },
    ],
  }
}

function pointGeoJson(point: MapOutlet) {
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        properties: {},
        geometry: { type: 'Point', coordinates: [point.lng, point.lat] },
      },
    ],
  }
}

function geoJsonBounds(data: GeoJsonData): [[number, number], [number, number]] | null {
  if (!data) return null
  let west = Infinity
  let south = Infinity
  let east = -Infinity
  let north = -Infinity
  const visit = (value: unknown) => {
    if (!Array.isArray(value)) return
    if (value.length >= 2 && typeof value[0] === 'number' && typeof value[1] === 'number') {
      west = Math.min(west, value[0])
      east = Math.max(east, value[0])
      south = Math.min(south, value[1])
      north = Math.max(north, value[1])
      return
    }
    value.forEach(visit)
  }
  const features = (data as { features?: Array<{ geometry?: { coordinates?: unknown } }> }).features || []
  features.forEach((feature) => visit(feature.geometry?.coordinates))
  return Number.isFinite(west) ? [[west, south], [east, north]] : null
}

export default function MapLibreWorkspace({
  outlet,
  onPickOutlet,
  demPreview,
  watershedGeoJson,
  drainageGeoJson,
  subbasinsGeoJson,
  layerStyles,
  onBasemapChange,
  selectingArea,
  areaBounds,
  onAreaSelected,
  onAreaFirstPoint,
  showPointCard = false,
  onClosePointCard,
  onAnalyzePoint,
  analyzing = false,
  activeView = 'analysis',
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const firstAreaPointRef = useRef<MapOutlet | null>(null)
  const selectingAreaRef = useRef(selectingArea)
  const onPickOutletRef = useRef(onPickOutlet)
  const onAreaSelectedRef = useRef(onAreaSelected)
  const onAreaFirstPointRef = useRef(onAreaFirstPoint)
  const [ready, setReady] = useState(false)
  const [cardPos, setCardPos] = useState<{ left: number; top: number } | null>(null)

  selectingAreaRef.current = selectingArea
  onPickOutletRef.current = onPickOutlet
  onAreaSelectedRef.current = onAreaSelected
  onAreaFirstPointRef.current = onAreaFirstPoint

  const styleFor = (id: 'streets' | 'satellite' | 'terrain'): string | StyleSpecification =>
    id === 'satellite' ? SATELLITE_STYLE : OPENFREE_STYLE

  const ensureSource = (map: MapLibreMap, id: string, data: unknown) => {
    const source = map.getSource(id) as GeoJSONSource | undefined
    if (source) source.setData(data as GeoJSON.GeoJSON)
    else map.addSource(id, { type: 'geojson', data: data as GeoJSON.GeoJSON })
  }

  const syncOperationalLayers = (map: MapLibreMap) => {
    if (!map.isStyleLoaded()) return

    const visibility = (ids: string[], visible: boolean) => {
      ids.forEach((id) => {
        if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none')
      })
    }

    // DEM Layer
    if (demPreview) {
      const b = demPreview.bounds_wgs84
      const coordinates: [[number, number], [number, number], [number, number], [number, number]] = [
        [b.west, b.north],
        [b.east, b.north],
        [b.east, b.south],
        [b.west, b.south],
      ]
      if (!map.getSource('hb-dem')) {
        map.addSource('hb-dem', { type: 'image', url: demPreview.preview_data_url, coordinates })
      } else {
        ;(map.getSource('hb-dem') as ImageSource).updateImage({ url: demPreview.preview_data_url, coordinates })
      }

      if (!map.getLayer('hb-dem-layer')) {
        map.addLayer({
          id: 'hb-dem-layer',
          type: 'raster',
          source: 'hb-dem',
          paint: { 'raster-opacity': layerStyles.demOpacity },
        })
      } else {
        map.setPaintProperty('hb-dem-layer', 'raster-opacity', layerStyles.demOpacity)
      }
      visibility(['hb-dem-layer'], Boolean(layerStyles.demVisible))
    }

    // Operational Vector Sources
    ensureSource(map, 'hb-watershed', watershedGeoJson || EMPTY_FC)
    ensureSource(map, 'hb-subbasins', subbasinsGeoJson || EMPTY_FC)
    ensureSource(map, 'hb-drainage', drainageGeoJson || EMPTY_FC)
    ensureSource(map, 'hb-outlet', pointGeoJson(outlet))
    ensureSource(map, 'hb-area-box', polygonFromBounds(areaBounds))

    // Operational Vector Layers: 1. Watershed
    if (!map.getLayer('hb-watershed-fill')) {
      map.addLayer({
        id: 'hb-watershed-fill',
        type: 'fill',
        source: 'hb-watershed',
        paint: { 'fill-color': layerStyles.watershedColor, 'fill-opacity': layerStyles.watershedOpacity },
      })
    } else {
      map.setPaintProperty('hb-watershed-fill', 'fill-color', layerStyles.watershedColor)
      map.setPaintProperty('hb-watershed-fill', 'fill-opacity', layerStyles.watershedOpacity)
    }

    if (!map.getLayer('hb-watershed-line')) {
      map.addLayer({
        id: 'hb-watershed-line',
        type: 'line',
        source: 'hb-watershed',
        paint: { 'line-color': layerStyles.watershedColor, 'line-width': layerStyles.watershedWidth },
      })
    } else {
      map.setPaintProperty('hb-watershed-line', 'line-color', layerStyles.watershedColor)
      map.setPaintProperty('hb-watershed-line', 'line-width', layerStyles.watershedWidth)
    }

    // 2. Subbasins (Crash-proof expressions for null safety)
    if (!map.getLayer('hb-subbasins-fill')) {
      map.addLayer({
        id: 'hb-subbasins-fill',
        type: 'fill',
        source: 'hb-subbasins',
        paint: {
          'fill-color': [
            'case',
            ['has', 'color'],
            ['get', 'color'],
            ['has', 'subbasin_id'],
            [
              'match',
              ['%', ['to-number', ['get', 'subbasin_id'], 0], 6],
              0,
              '#38bdf8',
              1,
              '#34d399',
              2,
              '#fbbf24',
              3,
              '#f472b6',
              4,
              '#a78bfa',
              '#fb923c',
            ],
            layerStyles.subbasinsColor || '#1f9d8f',
          ],
          'fill-opacity': layerStyles.subbasinsOpacity,
        },
      })
    } else {
      map.setPaintProperty('hb-subbasins-fill', 'fill-opacity', layerStyles.subbasinsOpacity)
    }

    if (!map.getLayer('hb-subbasins-line')) {
      map.addLayer({
        id: 'hb-subbasins-line',
        type: 'line',
        source: 'hb-subbasins',
        paint: { 'line-color': '#0f172a', 'line-width': 1.2, 'line-opacity': 0.75, 'line-dasharray': [2, 2] },
      })
    }

    // 3. Drainage (Crash-proof expressions for null safety)
    if (!map.getLayer('hb-drainage-line')) {
      map.addLayer({
        id: 'hb-drainage-line',
        type: 'line',
        source: 'hb-drainage',
        paint: {
          'line-color': layerStyles.drainageColor,
          'line-width': [
            'case',
            ['has', 'strahler'],
            [
              'interpolate',
              ['linear'],
              ['to-number', ['get', 'strahler'], 1],
              1,
              layerStyles.drainageWidth * 0.7,
              3,
              layerStyles.drainageWidth * 1.3,
              5,
              layerStyles.drainageWidth * 2.2,
            ],
            layerStyles.drainageWidth,
          ],
          'line-opacity': layerStyles.drainageOpacity,
        },
      })
    } else {
      map.setPaintProperty('hb-drainage-line', 'line-color', layerStyles.drainageColor)
      map.setPaintProperty('hb-drainage-line', 'line-opacity', layerStyles.drainageOpacity)
    }

    // 4. Outlet Marker
    if (!map.getLayer('hb-outlet-circle')) {
      map.addLayer({
        id: 'hb-outlet-circle',
        type: 'circle',
        source: 'hb-outlet',
        paint: {
          'circle-radius': layerStyles.outletSize + 2,
          'circle-color': '#ffffff',
          'circle-stroke-width': 2.5,
          'circle-stroke-color': '#ef4444',
        },
      })
      map.addLayer({
        id: 'hb-outlet-inner',
        type: 'circle',
        source: 'hb-outlet',
        paint: {
          'circle-radius': layerStyles.outletSize - 1,
          'circle-color': '#ef4444',
        },
      })
    }

    // 5. Area Box (AOI)
    if (!map.getLayer('hb-area-fill')) {
      map.addLayer({
        id: 'hb-area-fill',
        type: 'fill',
        source: 'hb-area-box',
        paint: { 'fill-color': '#38bdf8', 'fill-opacity': 0.15 },
      })
      map.addLayer({
        id: 'hb-area-line',
        type: 'line',
        source: 'hb-area-box',
        paint: { 'line-color': '#0284c7', 'line-width': 2, 'line-dasharray': [3, 2] },
      })
    }

    visibility(['hb-watershed-fill', 'hb-watershed-line'], Boolean(layerStyles.watershedVisible))
    visibility(['hb-subbasins-fill', 'hb-subbasins-line'], Boolean(layerStyles.subbasinsVisible))
    visibility(['hb-drainage-line'], Boolean(layerStyles.drainageVisible))
    visibility(['hb-outlet-circle', 'hb-outlet-inner'], Boolean(layerStyles.outletVisible))
    visibility(['hb-area-fill', 'hb-area-line'], Boolean(areaBounds))

    // 6. Terrain & Hillshade
    if (layerStyles.basemap === 'terrain') {
      if (!map.getSource('hb-terrain-dem')) {
        map.addSource('hb-terrain-dem', {
          type: 'raster-dem',
          tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],
          tileSize: 256,
          encoding: 'terrarium',
          maxzoom: 15,
        })
      }
      try {
        map.setTerrain({ source: 'hb-terrain-dem', exaggeration: 1.25 })
      } catch {
        // ignore
      }

      if (!map.getLayer('hb-hillshade')) {
        map.addLayer({
          id: 'hb-hillshade',
          type: 'hillshade',
          source: 'hb-terrain-dem',
          paint: { 'hillshade-exaggeration': layerStyles.hillshadeOpacity },
        })
      } else {
        map.setPaintProperty('hb-hillshade', 'hillshade-exaggeration', layerStyles.hillshadeOpacity)
      }
      visibility(['hb-hillshade'], Boolean(layerStyles.hillshadeVisible))
    } else if (map.getTerrain()) {
      map.setTerrain(null)
    }
  }

  const updateCardPosition = () => {
    const map = mapRef.current
    const container = containerRef.current
    if (!map || !container) return
    try {
      const p = map.project([outlet.lng, outlet.lat])
      const cardWidth = 300
      const cardHeight = 220
      const rect = container.getBoundingClientRect()

      let left = p.x + 18
      if (left + cardWidth > rect.width - 12) {
        left = p.x - cardWidth - 18
      }
      left = Math.max(12, Math.min(rect.width - cardWidth - 12, left))

      let top = p.y - cardHeight / 2
      top = Math.max(12, Math.min(rect.height - cardHeight - 12, top))

      setCardPos({ left, top })
    } catch {
      // ignore
    }
  }

  // Initialize Map
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: styleFor(layerStyles.basemap),
      center: [outlet.lng, outlet.lat],
      zoom: 10.5,
      pitch: 28,
      bearing: 0,
      attributionControl: { compact: true },
    })
    mapRef.current = map
    map.addControl(new maplibregl.NavigationControl({ showCompass: true, showZoom: true, visualizePitch: true }), 'top-right')
    map.addControl(new maplibregl.FullscreenControl(), 'top-right')
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric', maxWidth: 120 }), 'bottom-left')

    // Handle missing sprite images cleanly to suppress console warnings
    map.on('styleimagemissing', (e) => {
      if (!map.hasImage(e.id)) {
        const dummy = new Uint8Array([0, 0, 0, 0])
        map.addImage(e.id, { width: 1, height: 1, data: dummy })
      }
    })

    const onReady = () => {
      setReady(true)
      syncOperationalLayers(map)
      updateCardPosition()
    }

    map.on('load', onReady)
    map.on('style.load', onReady)

    map.on('click', (event) => {
      const point = { lat: event.lngLat.lat, lng: event.lngLat.lng }
      if (selectingAreaRef.current) {
        const first = firstAreaPointRef.current
        if (!first) {
          firstAreaPointRef.current = point
          onAreaFirstPointRef.current?.()
        } else {
          firstAreaPointRef.current = null
          onAreaSelectedRef.current({
            west: Math.min(first.lng, point.lng),
            east: Math.max(first.lng, point.lng),
            south: Math.min(first.lat, point.lat),
            north: Math.max(first.lat, point.lat),
          })
        }
      } else {
        onPickOutletRef.current(point)
      }
    })

    return () => {
      map.remove()
      mapRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // View switch: ensure map is resized and layers are synced immediately
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (activeView === 'analysis') {
      window.requestAnimationFrame(() => {
        map.resize()
        syncOperationalLayers(map)
        updateCardPosition()
      })
    }
  }, [activeView])

  // Track position on movement
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    updateCardPosition()
    map.on('move', updateCardPosition)
    map.on('zoom', updateCardPosition)
    map.on('resize', updateCardPosition)
    return () => {
      map.off('move', updateCardPosition)
      map.off('zoom', updateCardPosition)
      map.off('resize', updateCardPosition)
    }
  }, [ready, outlet])

  useEffect(() => {
    firstAreaPointRef.current = null
    const map = mapRef.current
    if (map) map.getCanvas().style.cursor = 'crosshair'
  }, [selectingArea])

  // Sync operational layers whenever inputs change
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    syncOperationalLayers(map)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, outlet, demPreview, watershedGeoJson, drainageGeoJson, subbasinsGeoJson, areaBounds, layerStyles])

  // Fit bounds when results or DEM load
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    if (watershedGeoJson) {
      const bounds = geoJsonBounds(watershedGeoJson)
      if (bounds) map.fitBounds(bounds, { padding: 54, maxZoom: 13, duration: 900 })
    } else if (demPreview) {
      const b = demPreview.bounds_wgs84
      map.fitBounds([[b.west, b.south], [b.east, b.north]], { padding: 44, duration: 800 })
    }
  }, [demPreview, watershedGeoJson, ready])

  // Basemap switcher effect
  const currentBasemapRef = useRef(layerStyles.basemap)
  useEffect(() => {
    if (currentBasemapRef.current !== layerStyles.basemap) {
      currentBasemapRef.current = layerStyles.basemap
      const map = mapRef.current
      if (map) {
        setReady(false)
        map.setStyle(styleFor(layerStyles.basemap))
      }
    }
  }, [layerStyles.basemap])

  return (
    <div className="mapbox-workspace-shell">
      <div ref={containerRef} className="mapbox-workspace" />

      {/* Floating Basemap Selector on the Map */}
      <div className="map-basemap-floating-bar">
        <button
          type="button"
          className={`map-basemap-pill ${layerStyles.basemap === 'streets' ? 'active' : ''}`}
          onClick={() => onBasemapChange?.('streets')}
          title="Capa Calles (OpenFreeMap)"
        >
          <MapIcon size={12} />
          <span>Calles</span>
        </button>
        <button
          type="button"
          className={`map-basemap-pill ${layerStyles.basemap === 'satellite' ? 'active' : ''}`}
          onClick={() => onBasemapChange?.('satellite')}
          title="Capa Satelital (Esri World Imagery)"
        >
          <Globe size={12} />
          <span>Satélite</span>
        </button>
        <button
          type="button"
          className={`map-basemap-pill ${layerStyles.basemap === 'terrain' ? 'active' : ''}`}
          onClick={() => onBasemapChange?.('terrain')}
          title="Capa Relieve 3D con Sombreado"
        >
          <Mountain size={12} />
          <span>Relieve</span>
        </button>
      </div>

      {/* Floating Point Information Card Positioned Next to Outlet */}
      {showPointCard && (
        <PointSelectionCard
          lat={outlet.lat}
          lng={outlet.lng}
          onAnalyze={onAnalyzePoint || (() => {})}
          onClose={onClosePointCard || (() => {})}
          analyzing={analyzing}
          style={
            cardPos
              ? {
                  position: 'absolute',
                  left: cardPos.left,
                  top: cardPos.top,
                  bottom: 'auto',
                  zIndex: 120,
                }
              : undefined
          }
        />
      )}
    </div>
  )
}
