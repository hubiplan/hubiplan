import { describe, expect, it } from 'vitest'
import { pointFromLink } from '../components/mapLink.ts'

describe('Punkt aus Kartenlink', () => {
  it('liest OpenStreetMap, Google Maps, geo: und Zahlen', () => {
    const p = { latitude: 51.17123, longitude: 6.75456 }
    expect(
      pointFromLink('https://www.openstreetmap.org/?mlat=51.17123&mlon=6.75456#map=17/51.1/6.7'),
    ).toEqual(p)
    expect(pointFromLink('https://www.openstreetmap.org/#map=18/51.17123/6.75456')).toEqual(p)
    expect(
      pointFromLink('https://www.google.com/maps/place/X/@51.1,6.7,17z/data=!3d51.17123!4d6.75456'),
    ).toEqual(p)
    expect(pointFromLink('https://www.google.com/maps/@51.17123,6.75456,15z')).toEqual(p)
    expect(pointFromLink('https://maps.google.com/?q=51.17123,6.75456')).toEqual(p)
    expect(pointFromLink('geo:51.17123,6.75456?z=17')).toEqual(p)
    expect(pointFromLink('51.17123, 6.75456')).toEqual(p)
  })

  it('lehnt Unsinn ab', () => {
    expect(pointFromLink('https://example.org/')).toBeNull()
    expect(pointFromLink('99.1, 6.7')).toBeNull()
  })
})
