// Einstellungen › Menü: Hauptmenüpunkte und Menüpunkte frei anordnen
// (konzepte/menue-frei-anordnen.md). Die Anordnung gilt für alle in der Einheit und bestimmt nur
// den Ort im Menü; was jemand sieht, entscheiden weiter Module und Rechte.
import { useState } from 'react'
import type { DragEvent } from 'react'
import { orgApi, PERM } from '../../api/orgs.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { Alert, Field, LoadError, Loading, SelectField } from '../../components/ui.tsx'
import { modules } from '../../modules.tsx'
import {
  arrangedAreas,
  fromArrangement,
  iconOf,
  ICON_KEYS,
  kindOf,
  MAX_AREAS,
  MAX_LABEL,
  MIN_AREAS,
  nextCustomId,
  freeIcon,
  iconLabel,
  shownIcon,
  toArrangement,
} from '../../menuLayout.ts'
import type { Arrangement, MenuLayout, MenuLayoutArea } from '../../menuLayout.ts'
import { useActiveOrg, useOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { NoAccessPage } from '../NoticePages.tsx'

/** Menüpunkte, die im Editor nicht erscheinen: fest (Start, Plattform) oder nie im Menü der
 *  Verwaltung (Mein Bereich gehört zur Sicht „Mein Verein“, Abteilung zu Untereinheiten). */
const HIDDEN = new Set(['start', 'plattform', 'mein-bereich', 'abteilung'])
const OWN_AREA = '__eigen__'
const NO_WS = { dept: null, portal: null }

export function MenuLayoutPage() {
  const org = useActiveOrg()
  const { refresh } = useOrg()
  const canEdit = org.permissions.includes(PERM.settingsEdit)
  const load = useLoad(() => orgApi.menuLayout(org.id), [org.id])
  const [draft, setDraft] = useState<Arrangement | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ kind: 'error' | 'success'; text: string } | null>(null)
  const [dragged, setDragged] = useState<string | null>(null)

  const saved = load.data?.layout ?? null

  if (org.type !== 'club' && org.type !== 'federation')
    return <NoAccessPage reason="right" embedded />
  if (load.error) return <LoadError message={load.error} onRetry={load.reload} />
  if (!load.data) return <Loading />
  // Ohne eigene Änderung gilt die gespeicherte Anordnung
  const current = draft ?? toArrangement(saved)

  const next = fromArrangement(current)
  const changed = JSON.stringify(next) !== JSON.stringify(saved)
  const moduleOf = (id: string) => modules.find((m) => m.id === id)
  const itemLabel = (id: string) => {
    const m = moduleOf(id)
    return m ? (m.labelFor?.(org, NO_WS) ?? m.label) : id
  }
  const shownFor = (id: string) => !!moduleOf(id)?.visible(org, NO_WS)
  const areaName = (a: MenuLayoutArea) =>
    arrangedAreas({ v: 1, areas: [a], items: {} })[0]?.label ?? a.id
  const missingName = current.areas.some((a) => kindOf(a.id) === 'custom' && !a.label?.trim())

  const update = (fn: (d: Arrangement) => Arrangement) => {
    setMessage(null)
    setDraft((d) => fn(d ?? toArrangement(saved)))
  }

  /** Menüpunkt in einen Bereich legen; leere eigene Hauptmenüpunkte entfallen dabei */
  function moveItem(id: string, target: string) {
    update((d) => {
      let areas = d.areas
      const items = Object.fromEntries(
        Object.entries(d.items).map(([k, v]) => [k, v.filter((x) => x !== id)]),
      )
      if (target === OWN_AREA) {
        if (areas.length >= MAX_AREAS) {
          setMessage({
            kind: 'error',
            text: t('Höchstens {n} Hauptmenüpunkte.', { n: MAX_AREAS }),
          })
          return d
        }
        target = id
        if (!areas.some((a) => a.id === id)) areas = [...areas, { id }]
      }
      const order = modules.map((m) => m.id)
      items[target] = [...(items[target] ?? []), id].sort(
        (x, y) => order.indexOf(x) - order.indexOf(y),
      )
      // Ein Menüpunkt-Bereich, der seinen Menüpunkt verliert und leer ist, entfällt
      areas = areas.filter(
        (a) => kindOf(a.id) !== 'item' || a.id === target || (items[a.id] ?? []).length > 0,
      )
      return { areas, items }
    })
  }

  function moveArea(index: number, by: -1 | 1) {
    update((d) => {
      const to = index + by
      if (to < 1 || to >= d.areas.length) return d
      const areas = [...d.areas]
      ;[areas[index], areas[to]] = [areas[to], areas[index]]
      return { ...d, areas }
    })
  }

  function addArea() {
    update((d) => {
      if (d.areas.length >= MAX_AREAS) return d
      const id = nextCustomId(d.areas)
      return {
        areas: [...d.areas, { id, label: '', icon: freeIcon(d.areas) }],
        items: { ...d.items, [id]: [] },
      }
    })
  }

  function removeArea(id: string) {
    update((d) => {
      if ((d.items[id] ?? []).some((x) => x !== 'plattform') || d.areas.length <= MIN_AREAS)
        return d
      const items = { ...d.items }
      delete items[id]
      return { areas: d.areas.filter((a) => a.id !== id), items }
    })
  }

  function setArea(id: string, patch: Partial<MenuLayoutArea>) {
    update((d) => ({
      ...d,
      areas: d.areas.map((a) => {
        if (a.id !== id) return a
        const merged = { ...a, ...patch }
        // Leere Felder nicht speichern: dann gilt der Standardname
        for (const k of ['label', 'label_en', 'icon'] as const) if (!merged[k]) delete merged[k]
        if (kindOf(id) === 'custom') merged.label = merged.label ?? ''
        return merged
      }),
    }))
  }

  async function run(action: () => Promise<{ layout: MenuLayout | null }>, done: string) {
    setBusy(true)
    setMessage(null)
    try {
      const data = await action()
      load.setData({ ...load.data!, ...data })
      setDraft(null)
      setMessage({ kind: 'success', text: done })
      await refresh()
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
    } finally {
      setBusy(false)
    }
  }

  const save = () => run(() => orgApi.saveMenuLayout(org.id, next), t('Menü gespeichert.'))
  const undo = () =>
    run(() => orgApi.undoMenuLayout(org.id), t('Vorige Anordnung wiederhergestellt.'))
  async function reset() {
    if (
      !(await confirmDialog({
        message: t('Das Menü wieder wie in HUBIplan vorgegeben anordnen? Das gilt für alle.'),
        confirmLabel: t('Standard wiederherstellen'),
        danger: false,
      }))
    )
      return
    await run(() => orgApi.saveMenuLayout(org.id, null), t('Standard wiederhergestellt.'))
  }

  const onDrop = (area: string) => (e: DragEvent) => {
    e.preventDefault()
    const id = dragged ?? e.dataTransfer.getData('text/plain')
    setDragged(null)
    if (id && !HIDDEN.has(id)) moveItem(id, area)
  }

  const preview = arrangedAreas(next)
    .map((a) => ({
      ...a,
      count: (current.items[a.id] ?? []).filter((id) => !HIDDEN.has(id) && shownFor(id)).length,
    }))
    .filter((a) => a.id === 'start' || a.count > 0)

  return (
    <div className="card card-wide stack">
      <h2>{t('Menü')}</h2>
      <p className="muted small">
        {t(
          'Legt fest, welche Hauptmenüpunkte es gibt und wo jeder Menüpunkt steht. Ein Menüpunkt kann auch selbst Hauptmenüpunkt sein. Die Anordnung gilt für alle in eurer Einheit; wer was sieht, entscheiden weiter Module und Rollen.',
        )}
      </p>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      <div className="menu-layout">
        <ol className="menu-layout-areas">
          {current.areas.map((area, index) => {
            const kind = kindOf(area.id)
            const items = (current.items[area.id] ?? []).filter((id) => !HIDDEN.has(id))
            const fixed = area.id === 'start'
            return (
              <li
                key={area.id}
                className={`menu-layout-area${dragged ? ' menu-layout-drop' : ''}`}
                onDragOver={(e) => canEdit && !fixed && e.preventDefault()}
                onDrop={fixed ? undefined : onDrop(area.id)}
              >
                <div className="menu-layout-head">
                  <span className="menu-layout-icon">{iconOf(area.icon) ?? iconOf(area.id)}</span>
                  <strong>{areaName(area) || t('Neuer Hauptmenüpunkt')}</strong>
                  <span className="muted small">
                    {kind === 'item'
                      ? t('Menüpunkt als Hauptmenüpunkt')
                      : kind === 'custom'
                        ? t('eigener Hauptmenüpunkt')
                        : null}
                  </span>
                  {canEdit && !fixed && (
                    <span className="menu-layout-tools">
                      <button
                        type="button"
                        className="button button-ghost"
                        disabled={index <= 1}
                        onClick={() => moveArea(index, -1)}
                        aria-label={t('„{x}“ nach oben', { x: areaName(area) })}
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        className="button button-ghost"
                        disabled={index >= current.areas.length - 1}
                        onClick={() => moveArea(index, 1)}
                        aria-label={t('„{x}“ nach unten', { x: areaName(area) })}
                      >
                        ↓
                      </button>
                      {kind !== 'item' && items.length === 0 && (
                        <button
                          type="button"
                          className="button button-ghost"
                          onClick={() => removeArea(area.id)}
                        >
                          {t('Entfernen')}
                        </button>
                      )}
                    </span>
                  )}
                </div>
                {canEdit && kind !== 'item' && !fixed && (
                  <div className="menu-layout-names">
                    <Field
                      label={t('Name')}
                      value={area.label ?? ''}
                      maxLength={MAX_LABEL}
                      placeholder={kind === 'standard' ? areaName({ id: area.id }) : ''}
                      required={kind === 'custom'}
                      error={
                        kind === 'custom' && !area.label?.trim()
                          ? t('Bitte einen Namen angeben.')
                          : undefined
                      }
                      onChange={(e) => setArea(area.id, { label: e.target.value })}
                    />
                    <Field
                      label={t('Name auf Englisch')}
                      value={area.label_en ?? ''}
                      maxLength={MAX_LABEL}
                      hint={t('Leer: wie der deutsche Name')}
                      onChange={(e) => setArea(area.id, { label_en: e.target.value })}
                    />
                    <SelectField
                      label={t('Zeichen')}
                      value={area.icon ?? ''}
                      onChange={(e) => setArea(area.id, { icon: e.target.value })}
                    >
                      {kind === 'standard' && <option value="">{t('wie vorgegeben')}</option>}
                      {ICON_KEYS.map((key) => {
                        const taken = current.areas.some(
                          (other) => other.id !== area.id && shownIcon(other) === key,
                        )
                        return (
                          <option key={key} value={key}>
                            {taken
                              ? t('{x} (schon vergeben)', { x: iconLabel(key) })
                              : iconLabel(key)}
                          </option>
                        )
                      })}
                    </SelectField>
                  </div>
                )}
                <ul className="menu-layout-items">
                  {fixed && <li className="muted small">{t('Startseite (bleibt hier)')}</li>}
                  {items.map((id) => (
                    <li
                      key={id}
                      draggable={canEdit}
                      onDragStart={(e) => {
                        setDragged(id)
                        e.dataTransfer.setData('text/plain', id)
                      }}
                      onDragEnd={() => setDragged(null)}
                      className="menu-layout-item"
                    >
                      <span className="menu-layout-icon">{iconOf(id)}</span>
                      <span>
                        {itemLabel(id)}
                        {!shownFor(id) && (
                          <span className="muted small"> · {t('für dich nicht sichtbar')}</span>
                        )}
                      </span>
                      {canEdit && (
                        <select
                          className="menu-layout-move"
                          aria-label={t('„{x}“ verschieben nach', { x: itemLabel(id) })}
                          value={area.id === id ? OWN_AREA : area.id}
                          onChange={(e) => moveItem(id, e.target.value)}
                        >
                          {current.areas
                            .filter(
                              (a) => a.id !== 'start' && (kindOf(a.id) !== 'item' || a.id === id),
                            )
                            .map((a) =>
                              a.id === id ? null : (
                                <option key={a.id} value={a.id}>
                                  {areaName(a) || t('Neuer Hauptmenüpunkt')}
                                </option>
                              ),
                            )}
                          <option value={OWN_AREA}>{t('Eigener Hauptmenüpunkt')}</option>
                        </select>
                      )}
                    </li>
                  ))}
                  {!fixed && items.length === 0 && (
                    <li className="muted small">
                      {t('Noch leer: Menüpunkte hierher ziehen oder verschieben.')}
                    </li>
                  )}
                </ul>
              </li>
            )
          })}
        </ol>
        <aside className="menu-layout-preview" aria-label={t('Vorschau')}>
          <h3 className="small">{t('Vorschau für dich')}</h3>
          <ul>
            {preview.map((a) => (
              <li key={a.id}>
                {a.icon}
                <span>{a.label || t('Neuer Hauptmenüpunkt')}</span>
              </li>
            ))}
          </ul>
          <p className="muted small">
            {t(
              'Wie eine Rolle das Menü sieht, zeigt „Ansicht als Rolle“ im Kontomenü oben rechts.',
            )}
          </p>
        </aside>
      </div>
      {canEdit && (
        <div className="actions">
          <button
            type="button"
            className="button"
            disabled={busy || !changed || missingName}
            onClick={() => void save()}
          >
            {t('Speichern')}
          </button>
          <button
            type="button"
            className="button button-ghost"
            disabled={busy || current.areas.length >= MAX_AREAS}
            onClick={addArea}
          >
            {t('Hauptmenüpunkt hinzufügen')}
          </button>
          {changed && (
            <button
              type="button"
              className="button button-ghost"
              disabled={busy}
              onClick={() => setDraft(null)}
            >
              {t('Verwerfen')}
            </button>
          )}
          {load.data.can_undo && !changed && (
            <button
              type="button"
              className="button button-ghost"
              disabled={busy}
              onClick={() => void undo()}
            >
              {t('Rückgängig')}
            </button>
          )}
          {saved && (
            <button
              type="button"
              className="button button-ghost"
              disabled={busy}
              onClick={() => void reset()}
            >
              {t('Standard wiederherstellen')}
            </button>
          )}
        </div>
      )}
      <p className="muted small">
        {t('Höchstens {n} Hauptmenüpunkte. Start bleibt vorn.', { n: MAX_AREAS })}
      </p>
    </div>
  )
}
