// Gespeicherte Orte der aktiven Einheit laden (für PlaceField und Einstellungen › Orte).
import { useEffect, useState } from 'react'
import { placeApi } from '../api/places.ts'
import type { Place } from '../api/places.ts'
import { useOptionalOrg } from '../org/OrgContext.tsx'

/** Adresse der Orte für die aktive Einheit (null: keine Orte, z. B. Mitgliederbereich). */
export function usePlacesBase(): string | null {
  const org = useOptionalOrg()
  if (org?.active && (org.active.type === 'club' || org.active.type === 'federation'))
    return `/api/orgs/${org.active.id}/places/`
  if (org?.activeDept) return `/api/depts/${org.activeDept.id}/places/`
  return null
}

interface Loaded {
  places: Place[]
  canEdit: boolean
}

// Mehrere Ortsfelder auf einer Seite laden die Liste nur einmal
const cache = new Map<string, Promise<Loaded>>()

function loadPlaces(base: string): Promise<Loaded> {
  let hit = cache.get(base)
  if (!hit) {
    hit = placeApi.list(base).then((d) => ({ places: d.places, canEdit: d.can_edit }))
    hit.catch(() => cache.delete(base))
    cache.set(base, hit)
  }
  return hit
}

/** Nach Änderungen unter Einstellungen › Orte neu laden. */
export function forgetPlaces() {
  cache.clear()
}

export function usePlaces(): Loaded & { base: string | null; add: (p: Place) => void } {
  const base = usePlacesBase()
  const [data, setData] = useState<Loaded>({ places: [], canEdit: false })
  useEffect(() => {
    if (!base) return
    let live = true
    loadPlaces(base).then(
      (d) => live && setData(d),
      () => undefined,
    )
    return () => {
      live = false
    }
  }, [base])
  const add = (p: Place) => {
    const next = { ...data, places: [...data.places, p] }
    setData(next)
    if (base) cache.set(base, Promise.resolve(next))
  }
  return { ...data, base, add }
}

export function findPlace(places: Place[], name: string): Place | undefined {
  const key = name.trim().toLowerCase()
  return key ? places.find((p) => p.name.toLowerCase() === key) : undefined
}
