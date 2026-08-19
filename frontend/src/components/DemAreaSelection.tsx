import { useEffect, useMemo, useState } from 'react'
import L from 'leaflet'
import { Marker, Rectangle, useMapEvents } from 'react-leaflet'

export type DemBounds = { west: number; south: number; east: number; north: number }

type Props = {
  active: boolean
  bounds: DemBounds | null
  onBoundsChange: (bounds: DemBounds) => void
  onFirstPoint?: () => void
}

type Corner = 'nw' | 'ne' | 'sw' | 'se'

const handleIcon = L.divIcon({
  className: 'dem-area-resize-handle',
  html: '<span></span>',
  iconSize: [14, 14],
  iconAnchor: [7, 7],
})

function normalizeBounds(a: L.LatLng, b: L.LatLng): DemBounds {
  return {
    west: Math.min(a.lng, b.lng),
    east: Math.max(a.lng, b.lng),
    south: Math.min(a.lat, b.lat),
    north: Math.max(a.lat, b.lat),
  }
}

function cornerPosition(bounds: DemBounds, corner: Corner): L.LatLngExpression {
  if (corner === 'nw') return [bounds.north, bounds.west]
  if (corner === 'ne') return [bounds.north, bounds.east]
  if (corner === 'sw') return [bounds.south, bounds.west]
  return [bounds.south, bounds.east]
}

function resizedBounds(bounds: DemBounds, corner: Corner, point: L.LatLng): DemBounds {
  const opposite = corner === 'nw'
    ? L.latLng(bounds.south, bounds.east)
    : corner === 'ne'
      ? L.latLng(bounds.south, bounds.west)
      : corner === 'sw'
        ? L.latLng(bounds.north, bounds.east)
        : L.latLng(bounds.north, bounds.west)

  return normalizeBounds(opposite, point)
}

export default function DemAreaSelection({ active, bounds, onBoundsChange, onFirstPoint }: Props) {
  const [first, setFirst] = useState<L.LatLng | null>(null)
  const [cursor, setCursor] = useState<L.LatLng | null>(null)
  const [editingBounds, setEditingBounds] = useState<DemBounds | null>(null)

  useEffect(() => {
    if (!active) {
      setFirst(null)
      setCursor(null)
    }
  }, [active])

  useEffect(() => {
    setEditingBounds(bounds)
  }, [bounds])

  useMapEvents({
    click(event) {
      if (!active) return
      if (!first) {
        setFirst(event.latlng)
        setCursor(event.latlng)
        onFirstPoint?.()
        return
      }

      const next = normalizeBounds(first, event.latlng)
      setFirst(null)
      setCursor(null)
      setEditingBounds(next)
      onBoundsChange(next)
    },
    mousemove(event) {
      if (!active || !first) return
      setCursor(event.latlng)
    },
  })

  const previewBounds = useMemo(() => {
    if (active && first && cursor) return normalizeBounds(first, cursor)
    return editingBounds
  }, [active, first, cursor, editingBounds])

  const resize = (corner: Corner, point: L.LatLng, commit: boolean) => {
    const current = editingBounds ?? bounds
    if (!current) return
    const next = resizedBounds(current, corner, point)
    setEditingBounds(next)
    if (commit) onBoundsChange(next)
  }

  if (!previewBounds) return null

  return (
    <>
      <Rectangle
        bounds={[[previewBounds.south, previewBounds.west], [previewBounds.north, previewBounds.east]]}
        pathOptions={{
          color: '#22c3b6',
          weight: 2,
          fillColor: '#22c3b6',
          fillOpacity: active && first ? 0.12 : 0.08,
          dashArray: active && first ? '4 4' : undefined,
        }}
      />

      {!active && editingBounds && (['nw', 'ne', 'sw', 'se'] as Corner[]).map((corner) => (
        <Marker
          key={corner}
          position={cornerPosition(editingBounds, corner)}
          icon={handleIcon}
          draggable
          eventHandlers={{
            drag(event) {
              resize(corner, event.target.getLatLng(), false)
            },
            dragend(event) {
              resize(corner, event.target.getLatLng(), true)
            },
          }}
        />
      ))}
    </>
  )
}
