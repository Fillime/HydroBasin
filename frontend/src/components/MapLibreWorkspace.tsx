import { useEffect, useRef, useState } from 'react'
import maplibregl, { type GeoJSONSource, type ImageSource, type Map as MapLibreMap, type StyleSpecification } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

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
  layers: Record<string, boolean>
  selectingArea: boolean
  areaBounds: MapBounds | null
  onAreaSelected: (bounds: MapBounds) => void
  onAreaFirstPoint?: () => void
}

type BasemapId = 'streets' | 'satellite' | 'terrain'

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
    features: [{
      type: 'Feature',
      properties: {},
      geometry: {
        type: 'Polygon',
        coordinates: [[
          [bounds.west, bounds.south], [bounds.east, bounds.south],
          [bounds.east, bounds.north], [bounds.west, bounds.north],
          [bounds.west, bounds.south],
        ]],
      },
    }],
  }
}

function pointGeoJson(point: MapOutlet) {
  return {
    type: 'FeatureCollection',
    features: [{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: [point.lng, point.lat] } }],
  }
}

function geoJsonBounds(data: GeoJsonData): [[number, number], [number, number]] | null {
  if (!data) return null
  let west = Infinity; let south = Infinity; let east = -Infinity; let north = -Infinity
  const visit = (value: unknown) => {
    if (!Array.isArray(value)) return
    if (value.length >= 2 && typeof value[0] === 'number' && typeof value[1] === 'number') {
      west = Math.min(west, value[0]); east = Math.max(east, value[0])
      south = Math.min(south, value[1]); north = Math.max(north, value[1])
      return
    }
    value.forEach(visit)
  }
  const features = (data as { features?: Array<{ geometry?: { coordinates?: unknown } }> }).features || []
  features.forEach((feature) => visit(feature.geometry?.coordinates))
  return Number.isFinite(west) ? [[west, south], [east, north]] : null
}

export default function MapLibreWorkspace({
  outlet, onPickOutlet, demPreview, watershedGeoJson, drainageGeoJson, subbasinsGeoJson,
  layers, selectingArea, areaBounds, onAreaSelected, onAreaFirstPoint,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const firstAreaPointRef = useRef<MapOutlet | null>(null)
  const selectingAreaRef = useRef(selectingArea)
  const onPickOutletRef = useRef(onPickOutlet)
  const onAreaSelectedRef = useRef(onAreaSelected)
  const onAreaFirstPointRef = useRef(onAreaFirstPoint)
  const [basemap, setBasemap] = useState<BasemapId>('terrain')
  const [ready, setReady] = useState(false)

  selectingAreaRef.current = selectingArea
  onPickOutletRef.current = onPickOutlet
  onAreaSelectedRef.current = onAreaSelected
  onAreaFirstPointRef.current = onAreaFirstPoint

  const styleFor = (id: BasemapId): string | StyleSpecification => (
    id === 'satellite' ? SATELLITE_STYLE : OPENFREE_STYLE
  )

  const ensureSource = (map: MapLibreMap, id: string, data: unknown) => {
    const source = map.getSource(id) as GeoJSONSource | undefined
    if (source) source.setData(data as GeoJSON.GeoJSON)
    else map.addSource(id, { type: 'geojson', data: data as GeoJSON.GeoJSON })
  }

  const syncOperationalLayers = (map: MapLibreMap) => {
    if (!map.isStyleLoaded()) return

    if (demPreview) {
      const b = demPreview.bounds_wgs84
      const coordinates: [[number, number], [number, number], [number, number], [number, number]] = [
        [b.west, b.north], [b.east, b.north], [b.east, b.south], [b.west, b.south],
      ]
      if (!map.getSource('hb-dem')) map.addSource('hb-dem', { type: 'image', url: demPreview.preview_data_url, coordinates })
      else (map.getSource('hb-dem') as ImageSource).updateImage({ url: demPreview.preview_data_url, coordinates })
      if (!map.getLayer('hb-dem-layer')) map.addLayer({ id: 'hb-dem-layer', type: 'raster', source: 'hb-dem', paint: { 'raster-opacity': 0.62 } })
      map.setLayoutProperty('hb-dem-layer', 'visibility', layers.DEM ? 'visible' : 'none')
    }

    ensureSource(map, 'hb-subbasins', subbasinsGeoJson || EMPTY_FC)
    if (!map.getLayer('hb-subbasins-fill')) map.addLayer({ id: 'hb-subbasins-fill', type: 'fill', source: 'hb-subbasins', paint: { 'fill-color': '#1f9d8f', 'fill-opacity': 0.14 } })
    if (!map.getLayer('hb-subbasins-line')) map.addLayer({ id: 'hb-subbasins-line', type: 'line', source: 'hb-subbasins', paint: { 'line-color': '#d8e4e4', 'line-width': 1 } })

    ensureSource(map, 'hb-watershed', watershedGeoJson || EMPTY_FC)
    if (!map.getLayer('hb-watershed-fill')) map.addLayer({ id: 'hb-watershed-fill', type: 'fill', source: 'hb-watershed', paint: { 'fill-color': '#f59e0b', 'fill-opacity': 0.07 } })
    if (!map.getLayer('hb-watershed-line')) map.addLayer({ id: 'hb-watershed-line', type: 'line', source: 'hb-watershed', paint: { 'line-color': '#f59e0b', 'line-width': 2.4 } })

    ensureSource(map, 'hb-drainage', drainageGeoJson || EMPTY_FC)
    if (!map.getLayer('hb-drainage-line')) map.addLayer({ id: 'hb-drainage-line', type: 'line', source: 'hb-drainage', paint: { 'line-color': '#3b82f6', 'line-width': 1.65, 'line-opacity': 0.95 } })

    ensureSource(map, 'hb-outlet', pointGeoJson(outlet))
    if (!map.getLayer('hb-outlet-glow')) map.addLayer({ id: 'hb-outlet-glow', type: 'circle', source: 'hb-outlet', paint: { 'circle-radius': 10, 'circle-color': '#1f9d8f', 'circle-opacity': 0.18 } })
    if (!map.getLayer('hb-outlet-dot')) map.addLayer({ id: 'hb-outlet-dot', type: 'circle', source: 'hb-outlet', paint: { 'circle-radius': 5.5, 'circle-color': '#1f9d8f', 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2 } })

    ensureSource(map, 'hb-aoi', polygonFromBounds(areaBounds))
    if (!map.getLayer('hb-aoi-fill')) map.addLayer({ id: 'hb-aoi-fill', type: 'fill', source: 'hb-aoi', paint: { 'fill-color': '#22c3b6', 'fill-opacity': 0.08 } })
    if (!map.getLayer('hb-aoi-line')) map.addLayer({ id: 'hb-aoi-line', type: 'line', source: 'hb-aoi', paint: { 'line-color': '#22c3b6', 'line-width': 2, 'line-dasharray': [2, 1.5] } })

    const visibility = (names: string[], visible: boolean) => names.forEach((name) => map.getLayer(name) && map.setLayoutProperty(name, 'visibility', visible ? 'visible' : 'none'))
    visibility(['hb-subbasins-fill', 'hb-subbasins-line'], Boolean(layers.Subcuencas && subbasinsGeoJson))
    visibility(['hb-watershed-fill', 'hb-watershed-line'], Boolean(layers.Cuenca && watershedGeoJson))
    visibility(['hb-drainage-line'], Boolean(layers['Red de drenaje'] && drainageGeoJson))
    visibility(['hb-outlet-glow', 'hb-outlet-dot'], Boolean(layers.Exutorio))

    if (basemap === 'terrain') {
      if (!map.getSource('hb-terrain-dem')) {
        map.addSource('hb-terrain-dem', {
          type: 'raster-dem',
          tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],
          encoding: 'terrarium',
          tileSize: 256,
          maxzoom: 15,
          attribution: 'Elevation tiles © AWS Terrain Tiles',
        })
      }
      map.setTerrain({ source: 'hb-terrain-dem', exaggeration: 1.25 })
      if (!map.getLayer('hb-hillshade')) map.addLayer({ id: 'hb-hillshade', type: 'hillshade', source: 'hb-terrain-dem', paint: { 'hillshade-exaggeration': 0.32 } })
      visibility(['hb-hillshade'], Boolean(layers.Hillshade))
    } else if (map.getTerrain()) {
      map.setTerrain(null)
    }
  }

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: styleFor(basemap),
      center: [outlet.lng, outlet.lat],
      zoom: 10.5,
      pitch: 28,
      bearing: 0,
      antialias: true,
      attributionControl: true,
    })
    mapRef.current = map
    map.addControl(new maplibregl.NavigationControl({ showCompass: true, showZoom: true, visualizePitch: true }), 'top-right')
    map.addControl(new maplibregl.FullscreenControl(), 'top-right')
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric', maxWidth: 120 }), 'bottom-left')

    map.on('load', () => setReady(true))
    map.on('style.load', () => setReady(true))
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
            west: Math.min(first.lng, point.lng), east: Math.max(first.lng, point.lng),
            south: Math.min(first.lat, point.lat), north: Math.max(first.lat, point.lat),
          })
        }
      } else {
        onPickOutletRef.current(point)
      }
    })

    return () => { map.remove(); mapRef.current = null }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    firstAreaPointRef.current = null
    const map = mapRef.current
    if (map) map.getCanvas().style.cursor = 'crosshair'
  }, [selectingArea])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    syncOperationalLayers(map)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, outlet, demPreview, watershedGeoJson, drainageGeoJson, subbasinsGeoJson, areaBounds, layers, basemap])

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

  const changeBasemap = (next: BasemapId) => {
    setBasemap(next)
    const map = mapRef.current
    if (!map) return
    setReady(false)
    map.setStyle(styleFor(next))
  }

  return (
    <div className="mapbox-workspace-shell">
      <div ref={containerRef} className="mapbox-workspace" />
      <div className="map-style-switcher" aria-label="Mapa base">
        <button className={basemap === 'streets' ? 'active' : ''} onClick={() => changeBasemap('streets')}>Calles</button>
        <button className={basemap === 'satellite' ? 'active' : ''} onClick={() => changeBasemap('satellite')}>Satélite</button>
        <button className={basemap === 'terrain' ? 'active' : ''} onClick={() => changeBasemap('terrain')}>Relieve 3D</button>
      </div>
      <div className="map-token-note">MapLibre · sin token · OpenFreeMap + datos abiertos</div>
    </div>
  )
}
