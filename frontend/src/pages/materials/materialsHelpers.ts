// Gemeinsame Helfer, Typen und Konstanten von MaterialsPage.
import type { Material, StockKind } from '../../api/materials.ts'
import { t } from '../../i18n/index.ts'
import './materials.css'

// Bestand: Material oder Infrastruktur (Schießstand, Schützenhaus, Vereinsheim)
export interface Stock {
  kind: StockKind
  // Oberfläche, z. B. /material
  root: string
  // Schnittstelle, z. B. /api/orgs/1/materials/
  base: string
  // Schnittstelle der Einheit, z. B. /api/orgs/1/
  prefix: string
  infrastructure: boolean
  materialView: boolean
}

export function stockRoot(kind: StockKind) {
  return kind === 'facility' ? '/infrastruktur' : '/material'
}

export function conditionLabel(value: string, kind: StockKind = 'material') {
  if (kind === 'facility')
    return (
      {
        ready: t('Nutzbar'),
        limited: t('Eingeschränkt nutzbar'),
        defective: t('Gesperrt'),
        retired: t('Aufgegeben'),
      }[value] ?? value
    )
  return (
    {
      ready: t('Einsatzbereit'),
      limited: t('Eingeschränkt nutzbar'),
      defective: t('Defekt'),
      retired: t('Ausgesondert'),
    }[value] ?? value
  )
}

export function facilityTypeLabel(value: string) {
  return (
    {
      building: t('Gebäude oder Vereinsheim'),
      room: t('Raum'),
      range: t('Schießstand'),
      ground: t('Platz oder Gelände'),
      storage: t('Lager'),
      other: t('Sonstiges'),
    }[value] ?? value
  )
}

export function ownershipLabel(value: string) {
  return (
    {
      own: t('Eigentum'),
      lease: t('Pacht oder Miete'),
      third_party: t('Nutzungsrecht bei Dritten'),
    }[value] ?? value
  )
}

export function laneLabel(key: string) {
  return (
    {
      lg10: `${t('Luftgewehr')} · 10 m`,
      lp10: `${t('Luftpistole')} · 10 m`,
      kk50: `${t('Kleinkaliber')} · 50 m`,
      kk100: `${t('Kleinkaliber')} · 100 m`,
      p25: `${t('Pistole')} · 25 m`,
      p50: `${t('Pistole')} · 50 m`,
      vogel: t('Vogelschießen · Hochstand'),
    }[key] ?? key
  )
}

export function location(item: Material) {
  if (item.location_review) return t('Standort prüfen')
  if (item.location_kind === 'facility')
    return item.kind === 'facility'
      ? t('Bereich von {name}', { name: item.facility_title ?? '' })
      : t('In {name}', { name: item.facility_title ?? '' })
  if (item.location_kind === 'member')
    return item.member_name ? t('Bei {name}', { name: item.member_name }) : t('Bei einem Mitglied')
  return [
    item.address.name,
    item.address.street,
    item.address.postal_code,
    item.address.city,
    item.address.country,
  ]
    .filter(Boolean)
    .join(', ')
}
