export type GeocodedLocation = {
  lat: number
  lng: number
  municipality?: string
  department?: string
  country: string
  isColombia: boolean
  formattedDisplay: string
  rawAddress?: Record<string, string>
}

const geocodeCache = new Map<string, GeocodedLocation>()

function isWithinColombiaBounds(lat: number, lng: number): boolean {
  return lat >= -4.3 && lat <= 13.5 && lng >= -79.2 && lng <= -66.8
}

export async function reverseGeocode(lat: number, lng: number): Promise<GeocodedLocation> {
  const cacheKey = `${lat.toFixed(3)},${lng.toFixed(3)}`
  if (geocodeCache.has(cacheKey)) {
    return geocodeCache.get(cacheKey)!
  }

  const fallbackColombia = isWithinColombiaBounds(lat, lng)

  try {
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => controller.abort(), 3500)

    const url = `https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}&zoom=11&addressdetails=1`
    const response = await fetch(url, {
      signal: controller.signal,
      headers: {
        'Accept-Language': 'es',
      },
    })
    window.clearTimeout(timeoutId)

    if (response.ok) {
      const data = await response.json()
      const address = (data.address || {}) as Record<string, string>

      const country = address.country || (fallbackColombia ? 'Colombia' : 'Internacional')
      const countryCode = (address.country_code || '').toLowerCase()
      const isColombia = countryCode === 'co' || country.toLowerCase().includes('colombia') || fallbackColombia

      if (isColombia) {
        const municipality =
          address.city ||
          address.town ||
          address.municipality ||
          address.village ||
          address.hamlet ||
          address.county ||
          'Municipio no identificado'

        const department =
          address.state ||
          address.province ||
          address.region ||
          'Colombia'

        const formattedDisplay = department && department !== municipality
          ? `${municipality}, ${department}`
          : municipality

        const result: GeocodedLocation = {
          lat,
          lng,
          municipality,
          department,
          country: 'Colombia',
          isColombia: true,
          formattedDisplay,
          rawAddress: address,
        }
        geocodeCache.set(cacheKey, result)
        return result
      } else {
        const result: GeocodedLocation = {
          lat,
          lng,
          country,
          isColombia: false,
          formattedDisplay: country,
          rawAddress: address,
        }
        geocodeCache.set(cacheKey, result)
        return result
      }
    }
  } catch {
    // Network or timeout fallback
  }

  // Fallback si falla la llamada
  if (fallbackColombia) {
    const result: GeocodedLocation = {
      lat,
      lng,
      country: 'Colombia',
      isColombia: true,
      formattedDisplay: 'Colombia (Punto seleccionado)',
    }
    geocodeCache.set(cacheKey, result)
    return result
  }

  const result: GeocodedLocation = {
    lat,
    lng,
    country: 'Punto internacional',
    isColombia: false,
    formattedDisplay: 'Punto internacional',
  }
  geocodeCache.set(cacheKey, result)
  return result
}
