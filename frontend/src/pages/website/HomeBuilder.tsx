// Webseite › Gestaltung › Startseite (Konzept webseite-baukasten G3, Ralf 10.11.2026): die
// Startseite aus Abschnitten zusammenstellen. Die festen Bausteine gibt es je einmal, eigene
// Abschnitte (Text, Banner, Kacheln …) beliebig oft. Jeder Abschnitt hat Hintergrund und
// Breite, im Design „Zeitung“ auch die Spalte. Alles landet im Entwurf der Gestaltung (G2).
import { useState } from 'react'
import type {
  HomeKind,
  HomeSection,
  HomeSectionData,
  SectionOptions,
  SectionSite,
} from '../../api/website.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { Modal } from '../../components/Modal.tsx'
import { SortHint } from '../../components/Sortable.tsx'
import { Checkbox } from '../../components/ui.tsx'
import { useSortable } from '../../components/useSortable.tsx'
import { t } from '../../i18n/index.ts'
import {
  emptyFact,
  emptyHours,
  emptyPartner,
  emptyPicture,
  emptyProgram,
  emptyStation,
  emptyTile,
} from './homeBuilderHelpers.ts'
import { SectionDialog } from './SectionDialog.tsx'
import { Sketch } from './Sketch.tsx'

const KINDS: HomeKind[] = [
  'text',
  'text_image',
  'banner',
  'buttons',
  'tiles',
  'event',
  'album',
  'quote',
  'contacts',
  'faq',
  'partners',
  'directions',
  'event_list',
  'document',
  'video',
  'chronicle',
  'facts',
  'divider',
  'countdown',
  'join',
  'donation',
  'hours',
  'columns',
  'table',
  'timeline',
  'program',
  'callout',
  'accordion',
  'images',
  'downloads',
  'unit_honors',
  'competition',
  'albums',
  'posts',
  'app',
  'live_facts',
  'cover',
]

function kindLabel(kind: HomeKind): string {
  return {
    text: t('Text'),
    text_image: t('Text mit Bild'),
    banner: t('Banner'),
    buttons: t('Knopfleiste'),
    tiles: t('Kacheln'),
    event: t('Hervorgehobener Termin'),
    album: t('Album-Auszug'),
    quote: t('Zitat'),
    contacts: t('Ansprechpartner'),
    faq: t('Häufige Fragen'),
    partners: t('Partner und Sponsoren'),
    directions: t('Anfahrt'),
    event_list: t('Termine einer Art'),
    document: t('Dokument zum Herunterladen'),
    video: t('Video als Link'),
    chronicle: t('Auszug aus der Chronik'),
    facts: t('Zahlen auf einen Blick'),
    divider: t('Trenner'),
    countdown: t('Countdown'),
    join: t('Mitglied werden'),
    donation: t('Spendenaufruf'),
    hours: t('Öffnungs- und Trainingszeiten'),
    columns: t('Zwei Spalten'),
    table: t('Tabelle'),
    timeline: t('Zeitstrahl'),
    program: t('Programm'),
    callout: t('Hinweis-Kasten'),
    accordion: t('Aufklappbare Abschnitte'),
    images: t('Bilder'),
    downloads: t('Download-Liste'),
    unit_honors: t('Würdenträger einer Untereinheit'),
    competition: t('Ergebnisse eines Wettbewerbs'),
    albums: t('Galerie-Übersicht'),
    posts: t('Neueste Beiträge'),
    app: t('Mitgliederbereich und App'),
    live_facts: t('Zahlen aus HUBIplan'),
    cover: t('Titelbild'),
  }[kind]
}

function kindHint(kind: HomeKind): string {
  return {
    text: t('Überschrift und Text'),
    text_image: t('Überschrift, Text und ein Bild daneben, darüber oder darunter'),
    banner: t('ein breites Bild, auf Wunsch mit einer Zeile darauf'),
    buttons: t('ein bis drei Knöpfe zu Seiten, zum Kontakt oder nach außen'),
    tiles: t('zwei bis sechs Kacheln mit Bild, Titel, Ziel und auf Wunsch einem Knopf'),
    event: t(
      'ein Termin groß mit „noch N Tage“, bei öffentlicher Anmeldung mit Preisen und Anmeldeknopf; verschwindet danach',
    ),
    album: t('vier bis acht Bilder aus einem Album der Galerie'),
    quote: t('ein kurzer Text mit Namen'),
    contacts: t('ein bis vier Rollen mit Foto, Name und „Nachricht schreiben“'),
    faq: t('Fragen mit Antworten zum Aufklappen'),
    partners: t('Logos mit Link, z. B. Unterstützer und Sponsoren'),
    directions: t('Anschrift eines Orts mit „Route planen“'),
    event_list: t('die nächsten Termine einer Kategorie'),
    document: t('eine Datei aus Webseite › Dokumente als Knopf'),
    video: t('Vorschaubild mit Link zum Video, ohne Einbettung'),
    chronicle: t('die neuesten Einträge der Zeitleiste'),
    facts: t('zwei bis sechs Zahlen mit kurzem Text'),
    divider: t('Linie oder Abstand zwischen Abschnitten'),
    countdown: t('Tage, Stunden, Minuten und Sekunden bis zu einem Termin oder Zeitpunkt'),
    join: t('kurzer Werbetext mit Knopf zum Online-Mitgliedsantrag'),
    donation: t('Spendenzweck, Bankverbindung und auf Wunsch ein Fortschrittsbalken'),
    hours: t('Wochentage mit Uhrzeiten, z. B. für Training oder Probe'),
    columns: t('zwei Textblöcke nebeneinander'),
    table: t('eine einfache Tabelle mit Kopfzeile'),
    timeline: t('eigene Stationen mit Zeitangabe und Text'),
    program: t('Ablauf einer Veranstaltung mit Tagen und Uhrzeiten'),
    callout: t('farbiger Kasten für Info, Achtung oder Erfolg'),
    accordion: t('Überschriften mit Text zum Aufklappen'),
    images: t('ein bis acht eigene Bilder mit Bildunterschrift'),
    downloads: t('mehrere Dateien aus Webseite › Dokumente als Liste'),
    unit_honors: t('die aktuellen Würdenträger einer Untereinheit'),
    competition: t('Sieger und Stand eines bestimmten Wettbewerbs'),
    albums: t('die ersten Alben der Galerie als Kacheln'),
    posts: t('die neuesten eigenen Beiträge und die aus Instagram und Facebook'),
    app: t('Knopf zum Mitgliederbereich, QR-Code und Hinweis auf die App'),
    live_facts: t('Mitgliederzahl, Jahre seit der Gründung und Untereinheiten, immer aktuell'),
    cover: t('ein schmales Bild über der Überschrift der Seite'),
  }[kind]
}

function newKey(value: HomeSection[]): string {
  const used = new Set(value.map((s) => s.key))
  for (;;) {
    const key = `c:${Math.random().toString(36).slice(2, 10)}`
    if (!used.has(key)) return key
  }
}

function defaults(kind: HomeKind): HomeSectionData {
  switch (kind) {
    case 'text':
      return { title: '', text: '' }
    case 'text_image':
      return { title: '', text: '', image: null, side: 'right', size: 'half' }
    case 'banner':
      return { image: null, line: '', height: 'low' }
    case 'buttons':
      return { title: '', buttons: [{ label: '', target: null }], align: 'left' }
    case 'tiles':
      return { title: '', tiles: [emptyTile(), emptyTile()], columns: 3 }
    case 'event':
      return { title: '', event: null }
    case 'album':
      return { title: '', album: null, count: 4 }
    case 'quote':
      return { text: '', name: '' }
    case 'contacts':
      return { title: '', roles: [] }
    case 'faq':
      return { title: '', items: [{ question: '', answer: '' }] }
    case 'partners':
      return { title: '', items: [emptyPartner(), emptyPartner()] }
    case 'directions':
      return { title: '', place: null, text: '' }
    case 'event_list':
      return { title: '', category: null, count: 4 }
    case 'document':
      return { title: '', document: null, label: '' }
    case 'video':
      return { title: '', url: 'https://', image: null, text: '' }
    case 'chronicle':
      return { title: '', count: 3 }
    case 'facts':
      return { title: '', items: [emptyFact(), emptyFact()] }
    case 'divider':
      return { style: 'line', size: 'small' }
    case 'countdown':
      return {
        title: '',
        mode: 'event',
        event: null,
        at: '',
        text: '',
        after: 'hide',
        after_text: '',
      }
    case 'join':
      return { title: '', text: '', label: '' }
    case 'donation':
      return {
        title: '',
        text: '',
        holder: '',
        iban: '',
        bic: '',
        purpose: '',
        goal: null,
        raised: null,
        label: '',
        url: '',
      }
    case 'hours':
      return { title: '', items: [emptyHours()], text: '' }
    case 'columns':
      return {
        title: '',
        items: [
          { title: '', text: '' },
          { title: '', text: '' },
        ],
      }
    case 'table':
      return { title: '', head: ['', ''], rows: [['', '']], text: '' }
    case 'timeline':
      return { title: '', items: [emptyStation(), emptyStation()] }
    case 'program':
      return { title: '', items: [emptyProgram()], text: '' }
    case 'callout':
      return { title: '', text: '', style: 'info' }
    case 'accordion':
      return { title: '', items: [{ title: '', text: '' }] }
    case 'images':
      return { title: '', items: [emptyPicture(), emptyPicture()], columns: 3 }
    case 'downloads':
      return { title: '', documents: [] }
    case 'unit_honors':
      return { title: '', unit: null }
    case 'competition':
      return { title: '', competition: null }
    case 'albums':
      return { title: '', count: 4 }
    case 'posts':
      return { title: '', count: 3, channel: 'all' }
    case 'app':
      return { title: '', text: '', qr: true, store: true }
    case 'live_facts':
      return {
        title: '',
        items: [
          { fact: 'members', label: '' },
          { fact: 'years', label: '' },
        ],
      }
    case 'cover':
      return { image: null }
  }
}

/** Kurzer Inhalt hinter dem Namen in der Liste, damit sich gleiche Arten unterscheiden */
function summary(s: HomeSection): string {
  const d = s.data ?? {}
  return (
    d.title ||
    d.line ||
    d.text?.slice(0, 40) ||
    d.buttons?.[0]?.label ||
    d.items?.[0]?.question ||
    d.items?.[0]?.name ||
    d.items?.[0]?.title ||
    d.items?.[0]?.day ||
    d.label ||
    ''
  )
}

export function HomeBuilder({
  data,
  website,
  value,
  blocks,
  design,
  page = false,
  contentOnly = false,
  onChange,
}: {
  data: SectionOptions
  website: SectionSite
  value: HomeSection[]
  blocks: Record<string, boolean>
  design: string
  /** Abschnitte einer Textseite (G4) statt der Startseite */
  page?: boolean
  /** F7: nur Inhalte vorhandener Abschnitte bearbeiten (Recht „Inhalte bearbeiten“) */
  contentOnly?: boolean
  onChange: (next: HomeSection[]) => void
}) {
  const labels = data.home_labels ?? {}
  // Ein Titelbild gibt es je Seite höchstens einmal (G6)
  const kinds = data.home_kinds
    ? KINDS.filter(
        (k) => k in data.home_kinds! && !(k === 'cover' && value.some((s) => s.kind === 'cover')),
      )
    : []
  const [editing, setEditing] = useState<string | null>(null)
  // Neu gewählter Abschnitt: erst mit „Übernehmen“ Teil der Seite; Abbrechen verwirft ihn
  // (UX-Audit WS-17: kein leerer Abschnitt, kein Speichern vor der ersten Eingabe)
  const [pending, setPending] = useState<HomeSection | null>(null)
  const [adding, setAdding] = useState(false)
  const label = (s: HomeSection) => (s.kind ? kindLabel(s.kind) : (labels[s.key] ?? s.key))
  // Bausteine ohne Bezeichnung gibt es hier nicht (z. B. Ergebnisse ohne Modul)
  const shown = value.filter((s) => s.kind || labels[s.key])
  // Feste Nummer je Schlüssel für das Ziehen (unabhängig von der Reihenfolge)
  const ids = new Map(
    [...value.map((s) => s.key)].sort().map((key, i) => [key, i + 1] as [string, number]),
  )
  const keyOf = new Map([...ids].map(([key, id]) => [id, key]))
  const sortable = useSortable({
    items: shown,
    id: (s) => ids.get(s.key)!,
    label,
    onReorder: async (order) => {
      const byKey = new Map(value.map((s) => [s.key, s]))
      const moved = order.map((id) => byKey.get(keyOf.get(id)!)!)
      onChange([...moved, ...value.filter((s) => !s.kind && !labels[s.key])])
    },
  })

  const update = (key: string, next: HomeSection) =>
    onChange(value.map((x) => (x.key === key ? next : x)))

  async function remove(s: HomeSection) {
    const ok = await confirmDialog({
      final: false,
      title: t('Abschnitt löschen?'),
      message: page
        ? t('„{x}“ verschwindet von der Seite, sobald du sie veröffentlichst.', {
            x: summary(s) || label(s),
          })
        : t('„{x}“ verschwindet von der Startseite, sobald der Entwurf veröffentlicht ist.', {
            x: summary(s) || label(s),
          }),
      confirmLabel: t('Löschen'),
    })
    if (ok) onChange(value.filter((x) => x.key !== s.key))
  }

  function add(kind: HomeKind) {
    const key = newKey(value)
    const section: HomeSection = {
      key,
      kind,
      on: true,
      bg: 'none',
      width: 'content',
      column: [
        'event',
        'contacts',
        'quote',
        'directions',
        'event_list',
        'document',
        'countdown',
        'hours',
        'downloads',
        'join',
        'app',
        'unit_honors',
      ].includes(kind)
        ? 'side'
        : 'main',
      data: defaults(kind),
    }
    setAdding(false)
    setPending(section)
  }

  const current = pending ?? value.find((s) => s.key === editing) ?? null

  if (contentOnly) {
    const custom = value.filter((s) => s.kind)
    return (
      <>
        <p className="muted small">
          {t(
            'Du kannst die Inhalte der eigenen Abschnitte ändern. Welche Abschnitte es gibt, in welcher Reihenfolge und wie sie aussehen, legt die Webseitenverwaltung fest.',
          )}
        </p>
        {custom.length === 0 ? (
          <p className="muted">{t('Noch keine eigenen Abschnitte.')}</p>
        ) : (
          <ul className="plain-list home-sections" aria-label={t('Abschnitte der Startseite')}>
            {custom.map((s) => (
              <li key={s.key} className="home-content-row">
                <span>
                  <strong>{label(s)}</strong>
                  {!s.on && <span className="muted small"> · {t('ausgeblendet')}</span>}
                  <br />
                  <span className="muted small">{summary(s) || kindHint(s.kind!)}</span>
                </span>
                <button
                  type="button"
                  className="button button-ghost"
                  aria-label={t('{x} bearbeiten', { x: label(s) })}
                  onClick={() => setEditing(s.key)}
                >
                  <span aria-hidden="true">✎</span> {t('Bearbeiten')}
                </button>
              </li>
            ))}
          </ul>
        )}
        {current && (
          <SectionDialog
            data={data}
            website={website}
            section={current}
            title={current.kind ? kindLabel(current.kind) : (labels[current.key] ?? current.key)}
            design={design}
            contentOnly
            onSave={(next) => {
              update(current.key, next)
              setEditing(null)
            }}
            onClose={() => setEditing(null)}
          />
        )}
      </>
    )
  }

  return (
    <>
      <SortHint website />
      <ul
        className="sortable-list home-sections"
        aria-label={page ? t('Abschnitte der Seite') : t('Abschnitte der Startseite')}
      >
        {sortable.ordered.map((s) => {
          const needs = s.kind
            ? data.home_kind_needs_block?.[s.kind]
            : data.home_needs_block?.[s.key]
          const blockOff = needs ? blocks[needs] === false : false
          const hint = blockOff
            ? t('Erscheint nicht: Der Bereich „{x}“ ist oben ausgeschaltet.', {
                x: data.block_labels[needs!] ?? needs,
              })
            : s.kind
              ? summary(s) || kindHint(s.kind)
              : data.home_hints?.[s.key]
          const { ref, className } = sortable.rowProps(s)
          return (
            <li key={s.key} ref={ref} className={className}>
              {sortable.handle(s)}
              <div className="sortable-label">
                <Checkbox
                  label={label(s)}
                  hint={hint}
                  checked={s.on}
                  onChange={(on) => update(s.key, { ...s, on })}
                />
              </div>
              <span className="button-row home-section-actions">
                <button
                  type="button"
                  className="button button-ghost"
                  aria-label={t('{x} bearbeiten', { x: label(s) })}
                  onClick={() => setEditing(s.key)}
                >
                  <span aria-hidden="true">✎</span> {t('Bearbeiten')}
                </button>
                {s.kind && (
                  <button
                    type="button"
                    className="button button-ghost"
                    aria-label={t('{x} löschen', { x: label(s) })}
                    onClick={() => void remove(s)}
                  >
                    {t('Löschen')}
                  </button>
                )}
              </span>
            </li>
          )
        })}
      </ul>
      {sortable.status}
      {kinds.length > 0 && (
        <div className="button-row">
          <button type="button" className="button" onClick={() => setAdding(true)}>
            {t('Abschnitt hinzufügen')}
          </button>
        </div>
      )}
      {adding && (
        <Modal title={t('Abschnitt hinzufügen')} onClose={() => setAdding(false)}>
          <ul className="home-kinds">
            {kinds.map((kind) => (
              <li key={kind}>
                <button type="button" className="home-kind" onClick={() => add(kind)}>
                  <Sketch kind={kind} />
                  <strong>{kindLabel(kind)}</strong>
                  <span className="muted small">{kindHint(kind)}</span>
                </button>
              </li>
            ))}
          </ul>
        </Modal>
      )}
      {current && (
        <SectionDialog
          data={data}
          website={website}
          section={current}
          title={current.kind ? kindLabel(current.kind) : (labels[current.key] ?? current.key)}
          design={design}
          fresh={pending !== null}
          onSave={(next) => {
            if (pending) onChange([...value, next])
            else update(current.key, next)
            setPending(null)
            setEditing(null)
          }}
          onClose={() => {
            setPending(null)
            setEditing(null)
          }}
        />
      )}
    </>
  )
}
