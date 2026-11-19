// Hilfe-Seite /hilfe mit vier Reitern (konzepte/hilfe-neustruktur.md): Anleitungen, Seiten,
// Begriffe (Glossar) und Neuigkeiten; eine Suche über alles. Gegliedert wie die Seitenleiste.
// Einzelne Anleitung unter /hilfe/<name>, Seitenhilfe unter /hilfe/seite/<name>.
import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { Field } from '../components/ui.tsx'
import { usePageTitle } from '../components/pageTitle.ts'
import { t } from '../i18n/index.ts'
import { DECISIONS, TERMS, decisionAnchor, termAnchor, tr } from '../learning/content.ts'
import type { DecisionKey, TermKey } from '../learning/content.ts'
import { GlossaryPage } from '../learning/GlossaryPage.tsx'
import { useLearning } from '../learning/LearningContext.tsx'
import { NewsPage } from '../news/NewsPage.tsx'
import { useOptionalOrg } from '../org/OrgContext.tsx'
import { guidesOfPage, matchesQuery, pageHelpFor } from './content.ts'
import type { HelpEntry } from './content.ts'
import { MEMBER_TOPICS, useBlocked } from './extras.ts'
import { useHelp } from './HelpContext.tsx'
import { BlockedGuide, ForYou, GuideNotes, HelpContacts, RightsHint } from './HelpExtras.tsx'
import { HelpSections } from './HelpMarkdown.tsx'
import { byMenu, groupLabel, itemLabel, partOf, partRank, placeOf } from './menu.ts'
import type { HelpGroup } from './menu.ts'
const byTitle = (a: HelpEntry, b: HelpEntry) => a.title.localeCompare(b.title)

export type HelpTab = 'anleitungen' | 'seiten' | 'begriffe' | 'neuigkeiten'

const TABS: { tab: HelpTab; to: string; label: () => string }[] = [
  { tab: 'anleitungen', to: '/hilfe/anleitungen', label: () => t('Anleitungen') },
  { tab: 'seiten', to: '/hilfe/seiten', label: () => t('Seiten') },
  { tab: 'begriffe', to: '/hilfe/begriffe', label: () => t('Begriffe') },
  { tab: 'neuigkeiten', to: '/hilfe/neuigkeiten', label: () => t('Neuigkeiten') },
]

/** Sichtbare Einträge laden (auch ohne geöffnete Leiste). */
function useEntries() {
  const help = useHelp()
  useEffect(() => {
    if (help && !help.entries && !help.failed) help.load()
  }, [help])
  return {
    entries: help?.entries?.filter(help.visible) ?? null,
    failed: !!help?.failed,
    retry: () => help?.load(),
  }
}

function LoadState({ failed, retry }: { failed: boolean; retry: () => void }) {
  return failed ? (
    <p role="alert">
      {t('Die Hilfe konnte nicht geladen werden.')}{' '}
      <button type="button" className="link-button" onClick={retry}>
        {t('Erneut versuchen')}
      </button>
    </p>
  ) : (
    <p className="muted" role="status">
      {t('Wird geladen …')}
    </p>
  )
}

/** Nur Mitglied: kein Eintrag, für den es ein Recht braucht, außerhalb von Alltag (Startseite,
 *  Mein Bereich) und Mein Konto. Einträge ohne Rechte sieht jede Person und zählen nicht. */
// oxlint-disable-next-line react/only-export-components
export function memberOnly(entries: HelpEntry[]): boolean {
  return !entries.some((e) => {
    const g = placeOf(e)?.group
    return e.rights.length > 0 && g !== 'alltag' && g !== 'konto'
  })
}

/** Treffer im Titel zuerst, dann in den Stichworten, dann im Text. */
// oxlint-disable-next-line react/only-export-components
export function searchRank(query: string, e: Pick<HelpEntry, 'title' | 'keywords'>): number {
  if (matchesQuery(query, e.title)) return 0
  return matchesQuery(query, e.title, e.keywords.join(' ')) ? 1 : 2
}

const entryLink = (e: HelpEntry) => <Link to={`/hilfe/${e.slug}`}>{e.title}</Link>

export function HelpPage({ tab = 'anleitungen' }: { tab?: HelpTab }) {
  const { pathname } = useLocation()
  const { entries, failed, retry } = useEntries()
  const org = useOptionalOrg()?.active ?? null
  const learning = useLearning()
  const hasFeature = learning?.hasFeature
  const has = useCallback(
    (f: Parameters<NonNullable<typeof hasFeature>>[0]) => (hasFeature ? hasFeature(f) : true),
    [hasFeature],
  )
  const [query, setQuery] = useState('')
  const searching = query.trim().length > 0
  const found = useMemo(
    () =>
      (entries ?? [])
        .filter((e) => matchesQuery(query, e.title, e.body, e.keywords.join(' ')))
        .sort((a, b) => searchRank(query, a) - searchRank(query, b) || byTitle(a, b)),
    [entries, query],
  )
  const terms = useMemo(
    () =>
      searching
        ? (Object.keys(TERMS) as TermKey[]).filter(
            (k) =>
              has(TERMS[k].feature) && matchesQuery(query, tr(TERMS[k].name), tr(TERMS[k].meaning)),
          )
        : [],
    [query, searching, has],
  )
  const decisions = useMemo(
    () =>
      searching
        ? (Object.keys(DECISIONS) as DecisionKey[]).filter(
            (k) =>
              has(DECISIONS[k].feature) &&
              matchesQuery(query, tr(DECISIONS[k].title), tr(DECISIONS[k].text)),
          )
        : [],
    [query, searching, has],
  )
  // Anleitungen, für die ein Recht fehlt: nur bei passender Suche, ausgegraut (F1)
  const blocked = useBlocked(
    (e) => searching && matchesQuery(query, e.title, e.body, e.keywords.join(' ')),
  ).sort(byTitle)
  const sub =
    pathname.replace(/\/$/, '') === '/hilfe'
      ? null
      : (TABS.find((x) => x.tab === tab)?.label() ?? null)
  const where = (e: HelpEntry) => {
    const place = placeOf(e)
    const item = place ? itemLabel(place.item, org) : ''
    return e.kind === 'page' ? t('Seite') : item
  }
  const foundGuides = found.filter((e) => e.kind === 'guide')
  const foundPages = found.filter((e) => e.kind === 'page')

  return (
    <section className="help-page">
      {/* Unterseiten mit eigener H1, „Hilfe“ darüber (UX-Audit 08.11., W-02) */}
      {sub ? (
        <div>
          <p className="muted small eyebrow">{t('Hilfe')}</p>
          <h1>{sub}</h1>
        </div>
      ) : (
        <h1>{t('Hilfe')}</h1>
      )}
      <p className="muted">
        {t(
          'Anleitungen Schritt für Schritt, Erklärungen zu jeder Seite und das Glossar. Auf jeder Seite öffnet „Hilfe zu dieser Seite“ oben (oder die Taste ?) die passende Hilfe.',
        )}
      </p>
      <div className="help-search">
        <Field
          label={t('Hilfe durchsuchen')}
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      <nav className="tabs" aria-label={t('Teile der Hilfe')}>
        {TABS.map((x) => (
          <Link
            key={x.tab}
            to={x.to}
            className={x.tab === tab ? 'tab active' : 'tab'}
            aria-current={x.tab === tab ? 'page' : undefined}
            onClick={() => setQuery('')}
          >
            {x.label()}
          </Link>
        ))}
      </nav>
      {searching ? (
        entries ? (
          <div className="help-results">
            {found.length + terms.length + decisions.length + blocked.length === 0 && (
              <p role="status">{t('Nichts gefunden.')}</p>
            )}
            {foundGuides.length > 0 && (
              <section>
                <h2>
                  {t('Anleitungen')} <span className="muted small">({foundGuides.length})</span>
                </h2>
                <ul className="help-list">
                  {foundGuides.map((e) => (
                    <li key={e.key}>
                      {entryLink(e)} <span className="muted small">({where(e)})</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
            {foundPages.length > 0 && (
              <section>
                <h2>
                  {t('Seiten')} <span className="muted small">({foundPages.length})</span>
                </h2>
                <ul className="help-list">
                  {foundPages.map((e) => (
                    <li key={e.key}>{entryLink(e)}</li>
                  ))}
                </ul>
              </section>
            )}
            {blocked.length > 0 && (
              <section>
                <h2>{t('Dafür fehlt dir ein Recht')}</h2>
                <ul className="help-list">
                  {blocked.map((e) => (
                    <BlockedGuide key={e.key} entry={e} />
                  ))}
                </ul>
              </section>
            )}
            {terms.length + decisions.length > 0 && (
              <section>
                <h2>{t('Im Glossar')}</h2>
                <ul className="help-list">
                  {terms.map((k) => (
                    <li key={k}>
                      <Link to={`/hilfe/begriffe#${termAnchor(k)}`}>{tr(TERMS[k].name)}</Link>
                    </li>
                  ))}
                  {decisions.map((k) => (
                    <li key={k}>
                      <Link to={`/hilfe/begriffe#${decisionAnchor(k)}`}>
                        {tr(DECISIONS[k].title)}
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        ) : (
          <LoadState failed={failed} retry={retry} />
        )
      ) : (
        <>
          {tab === 'begriffe' && <GlossaryPage embedded />}
          {tab === 'neuigkeiten' && <NewsPage />}
          {(tab === 'anleitungen' || tab === 'seiten') &&
            (entries ? (
              tab === 'anleitungen' ? (
                <GuidesTab entries={entries} />
              ) : (
                <PagesTab entries={entries} />
              )
            ) : (
              <LoadState failed={failed} retry={retry} />
            ))}
        </>
      )}
    </section>
  )
}

/** Anker einer Gruppe auf der Hilfe-Seite (Sprungleiste). */
const groupAnchor = (g: HelpGroup) => `hilfe-gruppe-${g}`

/**
 * Gruppen und Menüpunkte als Überschriften, darunter die Einträge. Davor eine Sprungleiste zu
 * den Gruppen. Mit `collapsible` sind die Menüpunkte zugeklappt (Reiter „Seiten“); der Punkt
 * aus der Adresse (#hilfe-<menüpunkt>) ist offen.
 */
function MenuList({
  entries,
  render,
  anchors = false,
  collapsible = false,
}: {
  entries: HelpEntry[]
  render: (items: HelpEntry[], item: string) => ReactNode
  anchors?: boolean
  collapsible?: boolean
}) {
  const org = useOptionalOrg()?.active ?? null
  const sections = byMenu(entries)
  const wanted = useLocation().hash.slice(1)
  return (
    <>
      {sections.length > 2 && (
        <nav className="help-jump" aria-label={t('Springe zu')}>
          <span className="muted small">{t('Springe zu')}</span>
          {sections.map((s) => (
            <a key={s.group} href={`#${groupAnchor(s.group)}`}>
              {groupLabel(s.group)}
            </a>
          ))}
        </nav>
      )}
      {sections.map((s) => (
        <section key={s.group} className="help-area" id={groupAnchor(s.group)}>
          <h2>{groupLabel(s.group)}</h2>
          {s.items.map((i) =>
            collapsible ? (
              <details
                key={i.item}
                className="help-item help-item-fold"
                id={anchors ? `hilfe-${i.item}` : undefined}
                open={wanted === `hilfe-${i.item}`}
              >
                <summary>
                  <h3>{itemLabel(i.item, org)}</h3>{' '}
                  <span className="muted small">({i.entries.length})</span>
                </summary>
                {render(i.entries, i.item)}
              </details>
            ) : (
              <div key={i.item} className="help-item" id={anchors ? `hilfe-${i.item}` : undefined}>
                <h3>{itemLabel(i.item, org)}</h3>
                {render(i.entries, i.item)}
              </div>
            ),
          )}
        </section>
      ))}
    </>
  )
}

function EntryList({ items }: { items: HelpEntry[] }) {
  return (
    <ul className="help-list">
      {items.map((e) => (
        <li key={e.key}>{entryLink(e)}</li>
      ))}
    </ul>
  )
}

/** Anleitungen eines Menüpunkts; bei Finanzen geteilt nach den Gruppen der Seitenleiste. */
function GuideItems({ items, item }: { items: HelpEntry[]; item: string }) {
  const parts = [...new Set(items.map((e) => partOf(e, item)))].sort(
    (a, b) => partRank(a) - partRank(b),
  )
  if (parts.length < 2) return <EntryList items={items} />
  return (
    <>
      {parts.map((p) => (
        <div key={p ?? ''}>
          <h4>{p}</h4>
          <EntryList items={items.filter((e) => partOf(e, item) === p)} />
        </div>
      ))}
    </>
  )
}

function GuidesTab({ entries }: { entries: HelpEntry[] }) {
  const guides = entries.filter((e) => e.kind === 'guide')
  if (memberOnly(entries)) {
    const byKey = new Map(guides.map((e) => [e.key, e]))
    const topics = MEMBER_TOPICS.map((k) => byKey.get(k)).filter((e): e is HelpEntry => !!e)
    return (
      <>
        <section className="help-area" aria-labelledby="hilfe-mitglieder">
          <h2 id="hilfe-mitglieder">{t('Hilfe für Mitglieder')}</h2>
          <ul className="help-tiles">
            {topics.map((e) => (
              <li key={e.key}>{entryLink(e)}</li>
            ))}
          </ul>
        </section>
        <HelpContacts />
        <MenuList entries={guides} render={(items) => <EntryList items={items} />} />
      </>
    )
  }
  return (
    <>
      <ForYou linkTo={entryLink} />
      <HelpContacts />
      <MenuList
        entries={guides}
        render={(items, item) => <GuideItems items={items} item={item} />}
      />
    </>
  )
}

function PagesTab({ entries }: { entries: HelpEntry[] }) {
  // Sprung zum Menüpunkt („Mehr zu …“ aus der Seitenhilfe)
  useEffect(() => {
    const id = window.location.hash.slice(1)
    if (id) document.getElementById(id)?.scrollIntoView?.()
  }, [])
  return (
    <>
      <p className="muted">
        {t('Zu jeder Seite eine kurze Erklärung, geordnet wie die Seitenleiste.')}
      </p>
      <MenuList
        entries={entries.filter((e) => e.kind === 'page')}
        render={(items) => <EntryList items={items} />}
        anchors
        collapsible
      />
    </>
  )
}

/** Eine Anleitung oder Seitenhilfe unter /hilfe/<name> */
export function HelpEntryPage() {
  const { '*': slug = '' } = useParams()
  const { entries, failed, retry } = useEntries()
  const help = useHelp()
  const navigate = useNavigate()
  const entry = entries?.find((e) => e.slug === slug)
  // Nicht sichtbar, weil ein Recht fehlt? Dann sagen, welches (F1)
  const hidden = !entry ? help?.entries?.find((e) => e.slug === slug) : undefined
  const missing = hidden ? (help?.missing(hidden) ?? []) : []
  const target = entry?.routes.find((r) => !r.includes(':') && r !== '/hilfe')
  const org = useOptionalOrg()?.active ?? null
  const place = entry ? placeOf(entry) : null
  const sameItem = (e: HelpEntry) => {
    const p = placeOf(e)
    return !!place && p?.group === place.group && p.item === place.item
  }
  // Seitenhilfe: Anleitungen ihrer Seiten. Anleitung: die übrigen Anleitungen des Menüpunkts.
  const related = !entry
    ? []
    : entry.kind === 'page'
      ? guidesOfPage(
          entries ?? [],
          entry,
          (entries ?? []).filter(
            (e) => e.kind === 'guide' && e.routes.some((r) => entry.routes.includes(r)),
          ),
        )
      : (entries ?? []).filter((e) => e.kind === 'guide' && e.key !== entry.key && sameItem(e))
  // Anleitung: die Erklärung der Seite, auf der sie beginnt
  const pageHelp = entry?.kind === 'guide' && target ? pageHelpFor(entries ?? [], target) : null
  // Tab-Titel nennt die Anleitung (UX-Audit 05.11. W-04)
  const articleTitle = entry?.title ?? hidden?.title ?? null
  usePageTitle(
    articleTitle ? t('{label} · {modLabel}', { label: articleTitle, modLabel: t('Hilfe') }) : null,
  )
  return (
    <section className="help-page">
      <nav className="help-crumbs" aria-label={t('Du bist hier')}>
        <Link to="/hilfe">{t('Hilfe')}</Link>
        {entry && place && (
          <>
            {' › '}
            <Link
              to={
                entry.kind === 'page'
                  ? `/hilfe/seiten#hilfe-${place.item}`
                  : `/hilfe/anleitungen#hilfe-gruppe-${place.group}`
              }
            >
              {groupLabel(place.group) === itemLabel(place.item, org)
                ? itemLabel(place.item, org)
                : `${groupLabel(place.group)} › ${itemLabel(place.item, org)}`}
            </Link>
          </>
        )}
      </nav>
      {!entries && <LoadState failed={failed} retry={retry} />}
      {entries && !entry && hidden && missing.length > 0 && (
        <>
          <h1>{hidden.title}</h1>
          <p role="status">
            <RightsHint rights={missing} />
          </p>
        </>
      )}
      {entries && !entry && !(hidden && missing.length > 0) && (
        <>
          <h1>{t('Hilfe')}</h1>
          <p role="status">
            {t('Diese Hilfe gibt es nicht, oder sie gehört zu einer Funktion, die du nicht nutzt.')}
          </p>
        </>
      )}
      {entry && (
        <article>
          <h1>{entry.title}</h1>
          <HelpSections body={entry.body} />
          <GuideNotes entry={entry} editable />
          {target && (
            <p className="help-actions">
              <Link to={target}>{t('Zur Seite in HUBIplan')}</Link>
              {entry.kind === 'guide' && help && (
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() => {
                    navigate(target)
                    help.openGuide({ key: entry.key, path: target })
                  }}
                >
                  {t('Zeig es mir')}
                </button>
              )}
            </p>
          )}
          {pageHelp && (
            <p>
              {t('Die Seite erklärt:')} <Link to={`/hilfe/${pageHelp.slug}`}>{pageHelp.title}</Link>
            </p>
          )}
          {related.length > 0 && (
            <section>
              <h2>
                {entry.kind === 'page'
                  ? t('Häufige Aufgaben')
                  : t('Weitere Anleitungen zu {x}', {
                      x: place ? itemLabel(place.item, org) : '',
                    })}
              </h2>
              <ul className="help-list">
                {related.map((g) => (
                  <li key={g.key}>
                    <Link to={`/hilfe/${g.slug}`}>{g.title}</Link>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </article>
      )}
    </section>
  )
}
