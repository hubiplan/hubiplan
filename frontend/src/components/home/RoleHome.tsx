// Startseite als Arbeitsplatz je Rolle (Konzept S-04): feste Reihenfolge Zu erledigen ›
// Schnellaktionen › Nächste Termine › Hinweise. Die Rolle ergibt sich aus den Rechten; ohne
// eigene Auswahl teilen sich mehrere Rollen vier Schnellaktionen, Kasse vor Vorstand.
import { useState } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { PERM } from '../../api/orgs.ts'
import type { OrgSummary } from '../../api/orgs.ts'
import { imprintApi } from '../../api/imprint.ts'
import { letterheadApi, optionKey } from '../../api/letterhead.ts'
import { fieldApi } from '../../api/fields.ts'
import { BirthdayList, JubileeList } from '../../pages/members/JubileesPage.tsx'
import type { CatalogAction, QuickAction } from './roleActions.ts'
import { MAX_ACTIONS, shownActions } from './roleActions.ts'
import { homeActionsApi } from '../../api/homeActions.ts'
import { Alert, Checkbox } from '../ui.tsx'
import { todayIso } from '../../api/members.ts'
import { errorMessage, useLoad } from '../forms.ts'
import { t } from '../../i18n/index.ts'

/**
 * Schnellaktionen (S-04): ohne eigene Auswahl der Vorschlag der Rollen (höchstens vier). Unter
 * „Anpassen“ wählt jede Person bis zu sechs Aktionen aus allem, was ihre Rechte erlauben, und
 * legt die Reihenfolge fest; den ganzen Block blendet sie dort aus und unter Mein Konto › Profil
 * wieder ein. Die Auswahl gilt je Arbeitsbereich.
 */
export function QuickActions({
  candidates,
  catalog,
  scope,
  label,
}: {
  candidates: QuickAction[]
  catalog: CatalogAction[]
  scope: string
  label?: string
}) {
  const { data, error: loadError, setData } = useLoad(() => homeActionsApi.get(), [])
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (catalog.length === 0 || (!data && !loadError)) return null
  const hidden = data?.hidden ?? []
  const chosen = data?.chosen?.[scope]
  if (hidden.includes('*')) return null
  const actions = shownActions(candidates, catalog, hidden, chosen)
  const keys = actions.map((a) => a.key)

  async function save(body: Parameters<typeof homeActionsApi.update>[0]) {
    setBusy(true)
    setError(null)
    try {
      setData(await homeActionsApi.update(body))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  const choose = (next: string[]) => void save({ chosen: { [scope]: next } })
  const toggle = (key: string, on: boolean) =>
    choose(on ? [...keys, key] : keys.filter((k) => k !== key))
  const move = (i: number, by: number) => {
    const next = [...keys]
    ;[next[i], next[i + by]] = [next[i + by], next[i]]
    choose(next)
  }
  const full = keys.length >= MAX_ACTIONS
  const groups = [...new Set(catalog.map((a) => a.group))]

  return (
    <div className="card tile tile-wide home-actions">
      <div className="card-head">
        <h2>{label ?? t('Schnellaktionen')}</h2>
        <button
          type="button"
          className="link-button push-right"
          onClick={() => setEditing(!editing)}
        >
          {editing ? t('Fertig') : t('Anpassen')}
        </button>
      </div>
      {editing ? (
        <>
          <p className="muted small">
            {t('Wähle bis zu {n} Aktionen und lege ihre Reihenfolge fest.', { n: MAX_ACTIONS })}
          </p>
          {actions.length > 0 && (
            <ol className="plain-list home-actions-order" aria-label={t('Reihenfolge')}>
              {actions.map((a, i) => (
                <li key={a.key} className="role-row">
                  <span>
                    {i + 1}. {a.label}
                  </span>
                  <span className="push-right">
                    <button
                      type="button"
                      className="link-button"
                      disabled={busy || i === 0}
                      aria-label={t('{label} nach oben', { label: a.label })}
                      onClick={() => move(i, -1)}
                    >
                      ↑
                    </button>{' '}
                    <button
                      type="button"
                      className="link-button"
                      disabled={busy || i === actions.length - 1}
                      aria-label={t('{label} nach unten', { label: a.label })}
                      onClick={() => move(i, 1)}
                    >
                      ↓
                    </button>
                  </span>
                </li>
              ))}
            </ol>
          )}
          {groups.map((group) => (
            <fieldset key={group} className="home-actions-group">
              <legend>{group}</legend>
              <div className="home-actions-choice">
                {catalog
                  .filter((a) => a.group === group)
                  .map((a) => {
                    const on = keys.includes(a.key)
                    return (
                      <Checkbox
                        key={a.key}
                        label={a.label}
                        checked={on}
                        disabled={!on && full}
                        busy={busy}
                        onChange={(v) => toggle(a.key, v)}
                      />
                    )
                  })}
              </div>
            </fieldset>
          ))}
          {full && (
            <p className="muted small">{t('Für eine weitere Aktion nimm zuerst eine heraus.')}</p>
          )}
          <div className="button-row">
            {chosen && (
              <button
                type="button"
                className="button"
                disabled={busy}
                onClick={() =>
                  void save({ hidden: hidden.filter((k) => k === '*'), chosen: { [scope]: null } })
                }
              >
                {t('Vorschlag wiederherstellen')}
              </button>
            )}
            <button
              type="button"
              className="button"
              disabled={busy}
              onClick={() => void save({ hidden: [...hidden, '*'] })}
            >
              {t('Schnellaktionen ganz ausblenden')}
            </button>
          </div>
          <p className="muted small">
            {t('Wieder einschalten kannst du sie unter Mein Konto › Profil › Startseite.')}
          </p>
        </>
      ) : actions.length === 0 ? (
        <p className="muted">{t('Keine Schnellaktion gewählt.')}</p>
      ) : (
        <div className="button-row">
          {actions.map((a, i) => (
            <Link key={a.key} to={a.to} className={i === 0 ? 'button button-primary' : 'button'}>
              {a.label}
            </Link>
          ))}
        </div>
      )}
      {error && <Alert kind="error">{error}</Alert>}
    </div>
  )
}

interface Notice {
  key: string
  text: ReactNode
  to?: string
  link?: string
  onLater?: () => void
}

const BIRTHDAY_DAYS = 30
/** Ab diesem Monat zeigt die Startseite auch die Jubiläen des nächsten Jahres (Vorbereitung). */
const NEXT_YEAR_FROM_MONTH = 10

function plusDays(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00`)
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}

/** Jahre, deren Jubiläen die Startseite zeigt: das laufende, ab Oktober auch das nächste. */
export function jubileeYears(today: string): number[] {
  const year = Number(today.slice(0, 4))
  return Number(today.slice(5, 7)) >= NEXT_YEAR_FROM_MONTH ? [year, year + 1] : [year]
}

/**
 * Eine Karte „Hinweise (n)“ statt gestapelter Bänder (S-04): fehlende Angaben im Impressum
 * und Briefvorlage. Jubiläen und Geburtstage haben eine eigene Karte. Ohne Hinweis keine Karte.
 */
export function NoticesCard({ org }: { org: OrgSummary | null }) {
  const club = !!org && (org.type === 'club' || org.type === 'federation')
  const imprintShown = club && !!org && org.permissions.includes(PERM.orgEdit)
  const imprint = useLoad(
    () => (imprintShown && org ? imprintApi.get(org.id) : Promise.resolve(null)),
    [org?.id, imprintShown],
  )
  const letters = useLoad(() => letterheadApi.mine(), [])
  const notices: Notice[] = []
  const missing = imprint.data?.missing ?? []
  if (missing.length > 0) {
    notices.push({
      key: 'imprint',
      text: t('Im Impressum fehlen noch Angaben: {x}.', { x: missing.join(', ') }),
      to: '/einstellungen/impressum',
      link: t('Impressum ergänzen'),
    })
  }
  for (const n of letters.data?.notices ?? []) {
    notices.push({
      key: `letter-${n.kind}-${n.context}-${n.unit.id}`,
      text:
        n.kind === 'outdated'
          ? `${t('Deine Briefvorlage für {name} ist veraltet:', { name: n.unit.name })} ${n.changes.join(', ')} ${t('geändert.')}`
          : t(
              'Für deine Funktion „{function}“ in {name} kannst du dir eine Briefvorlage erstellen.',
              {
                function: n.function,
                name: n.unit.name,
              },
            ),
      to: `/briefvorlage?fuer=${encodeURIComponent(optionKey(n.context, n.unit.id))}`,
      link: n.kind === 'outdated' ? t('Neu erstellen') : t('Jetzt erstellen'),
      onLater: () => void letterheadApi.dismiss(n.unit.id, n.context).then(letters.reload),
    })
  }
  if (notices.length === 0) return null
  return (
    <div className="card tile home-notices">
      <h2>
        {t('Hinweise')} <span className="badge">{notices.length}</span>
      </h2>
      <ul className="plain-list home-notice-list">
        {notices.map((n) => (
          <li key={n.key}>
            {n.text}
            {n.to && (
              <>
                {' '}
                <Link to={n.to}>{n.link}</Link>
              </>
            )}
            {n.onLater && (
              <>
                {' · '}
                <button type="button" className="link-button" onClick={n.onLater}>
                  {t('Später')}
                </button>
              </>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * Jubiläen (je Kalenderjahr, sie haben keinen Stichtag) und Geburtstage der nächsten 30 Tage.
 * Ohne Eintrag keine Karte.
 */
export function AnniversariesCard({ org }: { org: OrgSummary }) {
  const today = todayIso()
  const years = jubileeYears(today)
  const von = `${years[0]}-01-01`
  const bis = `${years[years.length - 1]}-12-31`
  const people =
    org.type === 'club' &&
    org.modules.includes('members') &&
    org.permissions.includes(PERM.membersView)
  const awards = people && org.modules.includes('awards')
  const jubilees = useLoad(
    () => (awards ? fieldApi.jubilees(org.id, von, bis) : Promise.resolve(null)),
    [org.id, awards, von, bis],
  )
  const unitJubilees = useLoad(
    () => (awards ? fieldApi.unitJubilees(org.id, von, bis) : Promise.resolve(null)),
    [org.id, awards, von, bis],
  )
  const birthdays = useLoad(
    () =>
      people
        ? fieldApi.birthdays(org.id, today, plusDays(today, BIRTHDAY_DAYS))
        : Promise.resolve(null),
    [org.id, people, today],
  )
  const jubileeRows = jubilees.data?.results ?? []
  const unitRows = unitJubilees.data?.results ?? []
  const byYear = years
    .map((year) => ({
      year,
      rows: jubileeRows.filter((r) => Number(r.date.slice(0, 4)) === year),
      unitRows: unitRows.filter((r) => r.year === year),
    }))
    .filter((g) => g.rows.length + g.unitRows.length > 0)
  const birthdayRows = birthdays.data?.results ?? []
  if (byYear.length === 0 && birthdayRows.length === 0) return null
  const title =
    byYear.length === 0
      ? t('Geburtstage')
      : birthdayRows.length === 0
        ? t('Jubiläen')
        : t('Jubiläen und Geburtstage')
  return (
    <div className="card tile home-notices">
      <h2>{title}</h2>
      <ul className="plain-list home-notice-list">
        {byYear.length > 0 && (
          <li>
            {byYear.map((g) => (
              <section key={g.year} className="home-jubilee-year">
                <h3>{t('Jubiläen {year}', { year: g.year })}</h3>
                <JubileeList rows={g.rows} unitRows={g.unitRows} year={g.year} />
              </section>
            ))}
            <Link to="/mitglieder/jubilaeen">{t('Alle Jubiläen')}</Link>
          </li>
        )}
        {birthdayRows.length > 0 && (
          <li>
            <h3>{t('Geburtstage in den nächsten {n} Tagen', { n: BIRTHDAY_DAYS })}</h3>
            <BirthdayList rows={birthdayRows} today={today} />
          </li>
        )}
      </ul>
    </div>
  )
}
