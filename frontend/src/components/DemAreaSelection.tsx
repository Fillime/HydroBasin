import { useEffect, useState } from 'react'
import L from 'leaflet'
import { Rectangle, useMapEvents } from 'react-leaflet'

export type DemBounds = { west: number; south: number; east: number; north: number }

type Props = {
  active: boolean
  bounds: DemBounds | null
  onBoundsChange: (bounds: DemBounds) => void
  onFirstPoint?: () => void
}

export default function DemAreaSelection({ active, bounds, onBoundsChange, onFirstPoint }: Props) {
  const [first, setFirst] = useState<L.LatLng | null>(null)

  useEffect(() => {
    if (!active) setFirst(null)
  }, [active])

  useMapEvents({
    click(event) {
      if (!active) return
      if (!first) {
        setFirst(event.latlng)
        onFirstPoint?.()
        return
      }

      const west = Math.min(first.lng, event.latlng.lng)
      const east = Math.max(first.lng, event.latlng.lng)
      const south = Math.min(first.lat, event.latlng.lat)
      const north = Math.max(first.lat, event.latlng.lat)
      setFirst(null)
      onBoundsChange({ west, south, east, north })
    },
  })

  if (!bounds) return null
  return (
    <Rectangle
      bounds={[[bounds.south, bounds.west], [bounds.north, bounds.east]]}
      pathOptions={{ color: '#22c3b6', weight: 2, fillColor: '#22c3b6', fillOpacity: 0.08, dashArray: '6 5' }}
    />
  )
}
