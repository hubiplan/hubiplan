// Unterpunkte von Musik in der Seitenleiste, mit echten Pfaden (Menüprüfung M-08).
import type { OrgSummary } from '../../api/orgs.ts'
import { t } from '../../i18n/index.ts'

/** Notenarchiv als eigener Menüpunkt „Noten“: nur, wenn es den Menüpunkt Musik nicht gibt. */
export function scoresOwnEntry(org: OrgSummary | null) {
  if (!org || (org.type !== 'club' && org.type !== 'federation')) return false
  const music = org.modules.includes('music') && org.permissions.includes('music.view')
  return !music && org.modules.includes('scores') && org.permissions.includes('scores.view')
}

export function musicSections(org: OrgSummary | null) {
  if (!org) return []
  const has = (module: string, ...perms: string[]) =>
    org.modules.includes(module) && perms.every((p) => org.permissions.includes(p))
  const performances = t('Auftritte')
  const musicians = t('Musiker')
  const scores = t('Noten')
  const more = t('Ausstattung und Abrechnung')
  const setup = t('Einrichtung')
  return [
    { to: '/musik/uebersicht', label: t('Übersicht'), section: performances },
    { to: '/musik', label: t('Auftritte'), section: performances },
    { to: '/musik/verfuegbarkeit', label: t('Verfügbarkeiten'), section: performances },
    { to: '/musik/musiker', label: t('Musiker'), section: musicians },
    { to: '/musik/proben', label: t('Proben und Notenausgabe'), section: musicians },
    ...(has('scores', 'scores.view')
      ? [{ to: '/musik/noten', label: t('Notenbestand'), section: scores }]
      : []),
    ...(has('todos', 'todos.view')
      ? [{ to: '/musik/erinnerungen', label: t('Erinnerungen'), section: scores }]
      : []),
    ...(has('material', 'material.view')
      ? [{ to: '/musik/ausstattung', label: t('Instrumente und Uniformen'), section: more }]
      : []),
    ...(has('finance', 'finance.view', 'events.view')
      ? [{ to: '/musik/auszahlungen', label: t('Sammelauszahlungen'), section: more }]
      : []),
    { to: '/musik/vorlagen', label: t('Besetzungsvorlagen'), section: setup },
  ]
}
