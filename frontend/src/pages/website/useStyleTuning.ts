// Zustand und Abläufe von StyleTuning (StyleTuning.tsx); die Darstellung steht dort.
import { useMemo, useState, type ReactNode } from 'react'
import type { HomeSection, LayoutArea, StyleCatalog, StyleValues } from '../../api/website.ts'
import { t, tc } from '../../i18n/index.ts'
import {
  AREAS,
  layoutKey,
  s,
  type Area,
  type Part,
  type PreviewFocus,
  type Slot,
} from './styleTuningHelpers.ts'
import {
  LAYOUT_LABELS,
  MOVED,
  PRESET_LABELS,
  ROWS,
  SWITCH_BY_DESIGN,
  SWITCH_DEFAULTS,
  type Row,
  previewFocus,
} from './styleTuningCatalog.ts'

export const SHOW_ALL = 'hubiplan.feinabstimmung.alle'

export function readShowAll(): boolean {
  try {
    return window.localStorage.getItem(SHOW_ALL) === '1'
  } catch {
    return false
  }
}
export function writeShowAll(on: boolean) {
  try {
    if (on) window.localStorage.setItem(SHOW_ALL, '1')
    else window.localStorage.removeItem(SHOW_ALL)
  } catch {
    // ohne Speicher gilt die Wahl bis zum Neuladen
  }
}

/** Grund, warum ein Regler gerade nicht greift, mit Sprung zum Regler oder Link zur Stelle */
export type Why = { text: string; jump?: string; link?: { to: string; label: string } }

export type StyleTuningProps = {
  catalog: StyleCatalog
  design: string
  designLabel: string
  value: StyleValues
  onChange: (next: StyleValues) => void
  /** Bildauswahl für „Hintergrund des Kopfes: Kopfbild“ */
  headerImage: ReactNode
  /** Abschnitte der Startseite (Titelbild vorhanden?); fehlt bei älteren Ständen */
  homeSections?: HomeSection[]
  /** Eingeschaltete Bausteine (Suche, Termine) */
  blocks?: Record<string, boolean>
  /** Nach einer Änderung: welche Stelle die Vorschau zeigen soll */
  onFocus?: (focus: PreviewFocus) => void
  /** Gewählter Bereich aus der Adresse (/webseite/feinabstimmung/<bereich>) */
  area?: string
  /** Darstellungen der Bereiche (variants.py); fehlt bei älteren Ständen */
  layoutCatalog?: LayoutArea[]
  layouts?: Record<string, string>
  onLayouts?: (next: Record<string, string>) => void
  /** Rückgängig (Gestaltung), für den Hinweis nach Voreinstellung und Zurücksetzen */
  onUndo?: () => void
}

export function useStyleTuning({
  catalog,
  design,
  designLabel,
  value,
  onChange,
  homeSections,
  blocks,
  onFocus,
  area,
  layoutCatalog,
  layouts,
  onLayouts,
}: StyleTuningProps) {
  const areas = useMemo(() => AREAS(), [])
  const rows = useMemo(() => ROWS(), [])
  const moved = MOVED()
  const presets = PRESET_LABELS()
  const layoutLabels = LAYOUT_LABELS()
  const locks = catalog.locks[design] ?? {}
  const layoutValue = layouts ?? {}
  const layoutByArea = Object.fromEntries((layoutCatalog ?? []).map((a) => [a.area, a]))
  // Knöpfe am Karussell ohne Regler: auf der Bühne immer sichtbar, sonst bei Mauszeiger
  const designDefaults = catalog.defaults?.[design]
  const stageWidth =
    'hero_width' in locks ? undefined : (value.hero_width ?? designDefaults?.hero_width)
  const defaults: StyleValues = designDefaults
    ? {
        ...designDefaults,
        carousel_controls: stageWidth === 'stage' || stageWidth === 'full' ? 'always' : 'hover',
      }
    : {}
  const [query, setQuery] = useState('')
  const [showAll, setShowAll] = useState(readShowAll)
  const [openMore, setOpenMore] = useState<Record<string, boolean>>({})
  const [openHint, setOpenHint] = useState<Record<string, boolean>>({})
  const [notice, setNotice] = useState<string | null>(null)

  const rowByKey = useMemo(() => {
    const result: Record<string, Row> = Object.fromEntries(rows.map((r) => [r.key, r]))
    for (const [areaKey, label] of Object.entries(layoutLabels)) {
      result[layoutKey(areaKey)] = { key: layoutKey(areaKey), label }
    }
    return result
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [rows])
  // Bereich und Abschnitt je Regler; Darstellungen ohne festen Platz kommen zu „Bereiche“
  const placed = useMemo(() => {
    const result: { area: Area; part: Part; slot: Slot }[] = []
    const all = areas.map((a) => ({
      ...a,
      parts: a.parts.map((p) => ({ ...p, slots: [...p.slots] })),
    }))
    const known = new Set(all.flatMap((a) => a.parts.flatMap((p) => p.slots.map((x) => x.key))))
    const extra = (layoutCatalog ?? []).filter((l) => !known.has(layoutKey(l.area)))
    if (extra.length > 0) {
      const target = all.find((a) => a.id === 'bereiche')
      target?.parts.push({
        id: 'weitere',
        title: t('Weitere Bereiche'),
        slots: extra.map((l) => s(layoutKey(l.area))),
      })
    }
    for (const a of all)
      for (const p of a.parts) for (const x of p.slots) result.push({ area: a, part: p, slot: x })
    return { areas: all, list: result }
  }, [areas, layoutCatalog])

  /** Gibt es den Regler auf diesem Server? */
  function known(key: string): boolean {
    if (key.startsWith('layout:')) return key.slice(7) in layoutByArea
    return !!catalog.options[key] && key in rowByKey
  }
  function labelOf(key: string): string {
    if (key.startsWith('layout:')) {
      const areaKey = key.slice(7)
      return layoutLabels[areaKey] ?? areaKey
    }
    return rowByKey[key]?.label ?? key
  }

  function switchValue(style: StyleValues, key: string): boolean {
    const own = style[key]
    if (typeof own === 'boolean') return own
    const given = defaults[key]
    if (typeof given === 'boolean') return given
    return SWITCH_BY_DESIGN[design]?.[key] ?? SWITCH_DEFAULTS[key] ?? false
  }
  /** Wirksame Stufe: eigene Wahl, sonst Vorgabe des Designs */
  const effective = (key: string) => value[key] ?? defaults[key]
  /** Selbst verstellt? */
  const own = (key: string) =>
    key.startsWith('layout:') ? key.slice(7) in layoutValue : key in value

  const locked = (key: string, option?: string) => {
    if (!(key in locks)) return false
    const values = locks[key]
    return values === null || (option !== undefined && values.includes(option))
  }
  const wholeLocked = (key: string) =>
    !key.startsWith('layout:') && key in locks && locks[key] === null
  const lockedHint = t('Legt das Design „{design}“ selbst fest.', { design: designLabel })

  const hasHero =
    design === 'stage' ||
    homeSections === undefined ||
    homeSections.some((x) => x.key === 'carousel' && x.on)
  const eventsOn = blocks?.events !== false
  const toStructure = { to: '/webseite/aufbau', label: t('Menü und Seiten') }
  const noHero: Why = {
    text: t('Die Startseite zeigt kein Titelbild (Baustein „Bilderkarussell“).'),
    link: { to: '/webseite/startseite', label: tc('Webseite', 'Startseite') },
  }

  // U3 (F7): nicht verstecken, sondern sagen, warum es gerade nicht greift
  function why(key: string): Why | null {
    switch (key) {
      case 'logo_pos':
        return switchValue(value, 'logo')
          ? null
          : { text: t('Erst „Wappen“ einschalten.'), jump: 'logo' }
      case 'hero':
      case 'hero_width':
      case 'hero_shade':
      case 'hero_focus':
      case 'hero_name':
        return hasHero ? null : noHero
      case 'hero_tint':
        if (!hasHero) return noHero
        return (effective('hero_shade') ?? 'none') !== 'none'
          ? null
          : { text: t('Erst „Abdunkeln“ wählen.'), jump: 'hero_shade' }
      case 'hero_text':
        if (!hasHero) return noHero
        return design === 'stage' || switchValue(value, 'hero_name')
          ? null
          : { text: t('Erst „Name auf dem Titelbild“ einschalten.'), jump: 'hero_name' }
      case 'hero_side':
      case 'hero_stage_width':
        if (!hasHero) return noHero
        return effective('hero_width') === 'stage'
          ? null
          : { text: t('Nur bei Breite „in Inhaltsbreite“.'), jump: 'hero_width' }
      case 'search':
        return blocks === undefined || blocks.search !== false
          ? null
          : { text: t('Die Suche ist ausgeschaltet.'), link: toStructure }
      case 'date':
      case 'date_text':
        return eventsOn ? null : { text: t('Termine sind ausgeschaltet.'), link: toStructure }
      case 'footer_name':
      case 'footer_founded':
        return effective('footer_layout') === 'full'
          ? null
          : { text: t('Nur beim Aufbau „mit Wappen und Name“.'), jump: 'footer_layout' }
      default:
        if (key.startsWith('layout:') && blocks?.[key.slice(7)] === false)
          return { text: t('Der Bereich ist zurzeit ausgeschaltet.'), link: toStructure }
        return null
    }
  }

  function setKey(key: string, next: string | boolean | null) {
    setNotice(null)
    if (key.startsWith('layout:')) {
      const areaKey = key.slice(7)
      const result = { ...layoutValue }
      // Standard (erste Darstellung) wird nicht gespeichert
      if (next === null || next === layoutByArea[areaKey]?.variants[0]?.key) delete result[areaKey]
      else result[areaKey] = String(next)
      onLayouts?.(result)
      onFocus?.(previewFocus(key, eventsOn))
      return
    }
    const result = { ...value }
    if (next === null) delete result[key]
    else result[key] = next
    // Wappen und Vereinsname nie beide aus: der andere Schalter geht wieder an
    if (next === false && key === 'logo' && switchValue(result, 'name') === false)
      result.name = true
    if (next === false && key === 'name' && switchValue(result, 'logo') === false)
      result.logo = true
    onChange(result)
    onFocus?.(previewFocus(key, eventsOn))
  }

  /** Mehrere Regler auf einmal zurück (Abschnitt, Bereich, alles) */
  function resetKeys(keys: string[], message: string) {
    const styleKeys = keys.filter((k) => !k.startsWith('layout:'))
    const layoutKeys = keys.filter((k) => k.startsWith('layout:')).map((k) => k.slice(7))
    if (styleKeys.some((k) => k in value)) {
      const result = { ...value }
      for (const k of styleKeys) delete result[k]
      onChange(result)
    }
    if (layoutKeys.some((k) => k in layoutValue)) {
      const result = { ...layoutValue }
      for (const k of layoutKeys) delete result[k]
      onLayouts?.(result)
    }
    setNotice(message)
    onFocus?.({})
  }

  function applyPreset(name: string) {
    const preset = catalog.presets?.[name] ?? {}
    const result: StyleValues = { ...value }
    for (const [key, v] of Object.entries(preset)) {
      if (!(key in catalog.options)) continue
      if (typeof v === 'string' && locked(key, v)) continue
      if (locked(key)) continue
      result[key] = v
    }
    if (switchValue(result, 'logo') === false && switchValue(result, 'name') === false)
      result.name = true
    onChange(result)
    onFocus?.({})
    setNotice(t('Voreinstellung „{name}“ übernommen.', { name: presets[name]?.label ?? name }))
  }

  function toggleShowAll(on: boolean) {
    setShowAll(on)
    writeShowAll(on)
  }

  /** Text einer Stufe für Liste und Suche */
  function optionLabel(key: string, option: string | boolean): string {
    if (typeof option === 'boolean') return option ? t('an') : t('aus')
    if (key.startsWith('layout:'))
      return (
        layoutByArea[key.slice(7)]?.variants.find((v) => v.key === option)?.label ?? String(option)
      )
    return rowByKey[key]?.options?.[option] ?? option
  }

  function jumpTo(key: string) {
    setQuery('')
    const where = placed.list.find((x) => x.slot.key === key)
    if (where) setOpenMore((o) => ({ ...o, [`${where.area.id}/${where.part.id}`]: true }))
    window.setTimeout(() => {
      const el = document.getElementById(`style-row-${key}`)
      el?.scrollIntoView?.({ block: 'center' })
      el?.querySelector<HTMLElement>('button:not(.style-info), input, select')?.focus()
    }, 0)
  }

  const changedKeys = placed.list.map((x) => x.slot.key).filter((k) => known(k) && own(k))
  const changed = changedKeys.length
  const countIn = (a: Area) =>
    a.parts.reduce((n, p) => n + p.slots.filter((x) => known(x.key) && own(x.key)).length, 0)
  const current = placed.areas.find((a) => a.id === area)
  const showChanged = area === 'verstellt'
  // Ohne Bereich in der Adresse: am Bildschirm Schnellstart, auf dem Handy die Liste der Bereiche
  const isIndex = !current && !showChanged && area !== 'schnellstart'

  // Suche über Namen, Hinweise, Stufen und Abschnitte (Punkt 8)
  const q = query.trim().toLowerCase()
  function matches(key: string, part: Part, inArea: Area): boolean {
    const row = rowByKey[key]
    const options = key.startsWith('layout:')
      ? (layoutByArea[key.slice(7)]?.variants.map((v) => v.label) ?? [])
      : Object.values(row?.options ?? {})
    return [labelOf(key), row?.hint ?? '', part.title, inArea.title, ...options].some((x) =>
      x.toLowerCase().includes(q),
    )
  }

  return {
    areas,
    rows,
    moved,
    presets,
    layoutLabels,
    locks,
    layoutValue,
    layoutByArea,
    designDefaults,
    stageWidth,
    defaults,
    query,
    setQuery,
    showAll,
    setShowAll,
    openMore,
    setOpenMore,
    openHint,
    setOpenHint,
    notice,
    setNotice,
    rowByKey,
    placed,
    known,
    labelOf,
    switchValue,
    effective,
    own,
    locked,
    wholeLocked,
    lockedHint,
    hasHero,
    eventsOn,
    toStructure,
    noHero,
    why,
    setKey,
    resetKeys,
    applyPreset,
    toggleShowAll,
    optionLabel,
    jumpTo,
    changedKeys,
    changed,
    countIn,
    current,
    showChanged,
    isIndex,
    q,
    matches,
  }
}
