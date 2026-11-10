// Webseite › Gestaltung › Startseite (Konzept webseite-baukasten G3, Ralf 10.11.2026): die
// Startseite aus Abschnitten zusammenstellen. Die festen Bausteine gibt es je einmal, eigene
// Abschnitte (Text, Banner, Kacheln …) beliebig oft. Jeder Abschnitt hat Hintergrund und
// Breite, im Design „Zeitung“ auch die Spalte. Alles landet im Entwurf der Gestaltung (G2).
import { useState } from 'react'
import type { ReactNode } from 'react'
import { partnerApi } from '../../api/partners.ts'
import { contentApi } from '../../api/website.ts'
import type {
  HomeButton,
  HomeItem,
  HomeKind,
  HomeSection,
  HomeSectionData,
  HomeTarget,
  HomeTile,
  SectionOptions,
  SectionSite,
} from '../../api/website.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { formatDateTime, useLoad } from '../../components/forms.ts'
import { Modal } from '../../components/Modal.tsx'
import { SortHint } from '../../components/Sortable.tsx'
import { TextEditor } from '../../components/texteditor/TextEditor.tsx'
import { Checkbox, Field, SelectField } from '../../components/ui.tsx'
import { useSortable } from '../../components/useSortable.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { ImageChoice } from './images.tsx'
import type { Unit } from './images.tsx'

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
    cover: t('Titelbild'),
  }[kind]
}

function kindHint(kind: HomeKind): string {
  return {
    text: t('Überschrift und Text'),
    text_image: t('Überschrift, Text und ein Bild daneben'),
    banner: t('ein breites Bild, auf Wunsch mit einer Zeile darauf'),
    buttons: t('ein bis drei Knöpfe zu Seiten, zum Kontakt oder nach außen'),
    tiles: t('zwei bis sechs Kacheln mit Bild, Titel und Ziel'),
    event: t('ein Termin groß mit „noch N Tage“; verschwindet danach'),
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
    cover: t('ein schmales Bild über der Überschrift der Seite'),
  }[kind]
}

/** Skizze je Art für die Auswahl „Abschnitt hinzufügen“ (nur Flächen, Farbe vom Text) */
function Sketch({ kind }: { kind: HomeKind }) {
  const box = (x: number, y: number, w: number, h: number, o = 0.25) => (
    <rect key={`${x}-${y}-${w}`} x={x} y={y} width={w} height={h} rx="1.5" opacity={o} />
  )
  const lines = (x: number, y: number, w: number, n: number) =>
    Array.from({ length: n }, (_, i) => box(x, y + i * 6, i === n - 1 ? w * 0.6 : w, 3, 0.35))
  const shapes: Record<HomeKind, ReactNode[]> = {
    text: [box(8, 6, 40, 5, 0.6), ...lines(8, 16, 64, 4)],
    text_image: [box(6, 8, 30, 28), box(42, 8, 30, 5, 0.6), ...lines(42, 18, 32, 3)],
    banner: [box(2, 8, 76, 28), box(10, 26, 36, 5, 0.7)],
    buttons: [box(10, 18, 18, 9, 0.6), box(31, 18, 18, 9, 0.6), box(52, 18, 18, 9, 0.6)],
    tiles: [box(6, 8, 20, 28), box(30, 8, 20, 28), box(54, 8, 20, 28)],
    event: [box(28, 6, 24, 10, 0.6), ...lines(18, 22, 44, 2), box(30, 34, 20, 5, 0.5)],
    album: [box(6, 10, 15, 15), box(24, 10, 15, 15), box(42, 10, 15, 15), box(60, 10, 15, 15)],
    quote: [box(14, 12, 52, 4, 0.5), box(18, 20, 44, 4, 0.5), box(28, 30, 24, 3, 0.35)],
    contacts: [
      box(6, 6, 32, 32),
      box(42, 6, 32, 32),
      box(14, 12, 16, 12, 0.5),
      box(50, 12, 16, 12, 0.5),
    ],
    faq: [
      box(8, 6, 64, 6, 0.5),
      box(8, 15, 64, 6, 0.5),
      box(8, 24, 64, 6, 0.5),
      box(8, 33, 64, 6, 0.5),
    ],
    partners: [box(6, 14, 14, 14), box(24, 14, 14, 14), box(42, 14, 14, 14), box(60, 14, 14, 14)],
    directions: [
      box(6, 8, 30, 28),
      box(42, 10, 30, 5, 0.6),
      ...lines(42, 20, 30, 2),
      box(42, 32, 20, 5, 0.5),
    ],
    event_list: [
      box(8, 8, 10, 8, 0.5),
      box(22, 10, 50, 4, 0.35),
      box(8, 20, 10, 8, 0.5),
      box(22, 22, 50, 4, 0.35),
      box(8, 32, 10, 8, 0.5),
      box(22, 34, 50, 4, 0.35),
    ],
    document: [box(10, 10, 16, 24, 0.4), box(32, 14, 30, 4, 0.5), box(32, 24, 24, 8, 0.6)],
    video: [box(10, 6, 60, 32), box(34, 16, 12, 12, 0.6)],
    chronicle: [
      box(14, 6, 2, 34, 0.5),
      box(20, 8, 12, 4, 0.6),
      ...lines(20, 15, 48, 1),
      box(20, 22, 12, 4, 0.6),
      ...lines(20, 29, 48, 1),
    ],
    facts: [
      box(8, 12, 16, 10, 0.6),
      box(32, 12, 16, 10, 0.6),
      box(56, 12, 16, 10, 0.6),
      box(8, 26, 16, 3, 0.35),
      box(32, 26, 16, 3, 0.35),
      box(56, 26, 16, 3, 0.35),
    ],
    divider: [box(8, 21, 64, 2, 0.6)],
    cover: [box(2, 4, 76, 14), box(8, 24, 36, 5, 0.6), ...lines(8, 33, 64, 2)],
  }
  return (
    <svg viewBox="0 0 80 44" width="80" height="44" aria-hidden="true" fill="currentColor">
      {shapes[kind]}
    </svg>
  )
}

/** Hintergrund aus der Palette: p0 … p9 */
const paletteKey = (i: number) => 'p' + String(i)

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
    case 'cover':
      return { image: null }
  }
}

function emptyTile(): HomeTile {
  return { title: '', text: '', image: null, target: null }
}

const emptyPartner = (): HomeItem => ({ name: '', image: null, url: '' })
const emptyFact = (): HomeItem => ({ value: '', label: '' })

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
      column: ['event', 'contacts', 'quote', 'directions', 'event_list', 'document'].includes(kind)
        ? 'side'
        : 'main',
      data: defaults(kind),
    }
    onChange([...value, section])
    setAdding(false)
    setEditing(key)
  }

  const current = value.find((s) => s.key === editing) ?? null

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

function Segments<T extends string | number>({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: T
  options: [T, string][]
  onChange: (value: T) => void
}) {
  return (
    <div className="field">
      <span className="field-label">{label}</span>
      <div className={`style-segments style-n${options.length}`} role="group" aria-label={label}>
        {options.map(([key, text]) => (
          <button
            key={String(key)}
            type="button"
            aria-pressed={value === key}
            onClick={() => onChange(key)}
          >
            {text}
          </button>
        ))}
      </div>
    </div>
  )
}

function SectionDialog({
  data,
  website,
  section,
  title,
  design,
  contentOnly = false,
  onSave,
  onClose,
}: {
  data: SectionOptions
  website: SectionSite
  section: HomeSection
  title: string
  design: string
  contentOnly?: boolean
  onSave: (next: HomeSection) => void
  onClose: () => void
}) {
  const org = useActiveOrg()
  const [s, setS] = useState(section)
  const images = useLoad(() => contentApi.images(org.id), [org.id])
  const palette = data.palette ?? []
  const d = s.data ?? {}
  const setData = (patch: Partial<HomeSectionData>) => setS({ ...s, data: { ...d, ...patch } })
  const imageField = (
    fieldLabel: string,
    id: number | null | undefined,
    set: (v: number | null) => void,
  ) => (
    <ImageChoice
      label={fieldLabel}
      value={id ?? null}
      images={images.data ?? []}
      units={data.units as Unit[]}
      onChange={set}
      onImagesChanged={() => void images.reload()}
    />
  )

  // Das Titelbild steht immer oben in voller Breite: kein Aussehen zu wählen
  const looks = !contentOnly && s.kind !== 'cover'

  return (
    <Modal title={title} onClose={onClose}>
      <div className="home-section-dialog">
        {s.kind && (
          <SectionContent
            data={data}
            website={website}
            section={s}
            setData={setData}
            imageField={imageField}
          />
        )}
        {looks && <h3>{t('Aussehen')}</h3>}
        {looks && (
          <div className="field">
            <span className="field-label" id="abschnitt-hg">
              {t('Hintergrund')}
            </span>
            <div className="home-bg-choices" role="radiogroup" aria-labelledby="abschnitt-hg">
              {[
                ['none', t('Keiner'), undefined] as const,
                ['light', t('Hell'), undefined] as const,
                ...palette.map((c, i) => [paletteKey(i), c.name || c.color, c] as const),
              ].map(([key, text, color]) => (
                <label key={key} className="home-bg-choice">
                  <input
                    type="radio"
                    name="abschnitt-hg"
                    checked={(s.bg ?? 'none') === key}
                    onChange={() => setS({ ...s, bg: key })}
                  />
                  <span
                    className={`home-bg-swatch home-bg-${key === 'none' || key === 'light' ? key : 'color'}`}
                    style={color ? { background: color.color, color: color.on_color } : undefined}
                    aria-hidden="true"
                  ></span>
                  <span>{text}</span>
                </label>
              ))}
            </div>
          </div>
        )}
        {looks && (
          <Segments
            label={t('Breite des Abschnitts')}
            value={s.width ?? 'content'}
            options={[
              ['text', t('Textbreite')],
              ['content', t('Inhaltsbreite')],
              ['full', t('Volle Breite')],
            ]}
            onChange={(width) => setS({ ...s, width })}
          />
        )}
        {looks && design === 'newspaper' && (
          <Segments
            label={t('Spalte')}
            value={s.column ?? 'main'}
            options={[
              ['main', t('Hauptspalte')],
              ['side', t('Seitenspalte')],
            ]}
            onChange={(column) => setS({ ...s, column })}
          />
        )}
        <div className="button-row">
          <button type="button" className="button" onClick={() => onSave(s)}>
            {t('Übernehmen')}
          </button>
          <button type="button" className="button button-ghost" onClick={onClose}>
            {t('Abbrechen')}
          </button>
        </div>
      </div>
    </Modal>
  )
}

function SectionContent({
  data,
  website,
  section,
  setData,
  imageField,
}: {
  data: SectionOptions
  website: SectionSite
  section: HomeSection
  setData: (patch: Partial<HomeSectionData>) => void
  imageField: (
    label: string,
    id: number | null | undefined,
    set: (v: number | null) => void,
  ) => ReactNode
}) {
  const d = section.data ?? {}
  const choices = data.home_choices
  const titleField = (optional = true) => (
    <Field
      label={optional ? t('Überschrift (optional)') : t('Überschrift')}
      value={d.title ?? ''}
      maxLength={150}
      onChange={(e) => setData({ title: e.target.value })}
    />
  )
  switch (section.kind) {
    case 'text':
      return (
        <>
          {titleField()}
          <TextEditor
            label={t('Text')}
            value={d.text ?? ''}
            onChange={(text) => setData({ text })}
          />
        </>
      )
    case 'text_image':
      return (
        <>
          {titleField()}
          <TextEditor
            label={t('Text')}
            value={d.text ?? ''}
            rows={6}
            onChange={(text) => setData({ text })}
          />
          {imageField(t('Bild'), d.image, (image) => setData({ image }))}
          <Segments
            label={t('Bild steht')}
            value={d.side ?? 'right'}
            options={[
              ['left', t('links')],
              ['right', t('rechts')],
            ]}
            onChange={(side) => setData({ side })}
          />
          <Segments
            label={t('Bildgröße')}
            value={d.size ?? 'half'}
            options={[
              ['small', t('klein')],
              ['half', t('halbe Breite')],
            ]}
            onChange={(size) => setData({ size })}
          />
        </>
      )
    case 'cover':
      return (
        <>
          {imageField(t('Bild'), d.image, (image) => setData({ image }))}
          <p className="muted small">
            {t(
              'Das Titelbild steht immer ganz oben über der Überschrift, egal an welcher Stelle der Liste.',
            )}
          </p>
        </>
      )
    case 'banner':
      return (
        <>
          {imageField(t('Bild'), d.image, (image) => setData({ image }))}
          <Field
            label={t('Zeile auf dem Bild (optional)')}
            value={d.line ?? ''}
            maxLength={150}
            onChange={(e) => setData({ line: e.target.value })}
          />
          <Segments
            label={t('Höhe')}
            value={d.height ?? 'low'}
            options={[
              ['low', t('niedrig')],
              ['high', t('hoch')],
            ]}
            onChange={(height) => setData({ height })}
          />
        </>
      )
    case 'buttons': {
      const buttons = d.buttons ?? []
      const setButton = (i: number, patch: Partial<HomeButton>) =>
        setData({ buttons: buttons.map((b, j) => (j === i ? { ...b, ...patch } : b)) })
      return (
        <>
          {titleField()}
          {buttons.map((b, i) => (
            <fieldset key={i} className="home-item">
              <legend>{t('Knopf {n}', { n: i + 1 })}</legend>
              <Field
                label={t('Beschriftung')}
                value={b.label}
                maxLength={60}
                onChange={(e) => setButton(i, { label: e.target.value })}
              />
              <TargetField
                data={data}
                website={website}
                value={b.target}
                onChange={(target) => setButton(i, { target })}
              />
              {buttons.length > 1 && (
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() => setData({ buttons: buttons.filter((_, j) => j !== i) })}
                >
                  {t('Knopf entfernen')}
                </button>
              )}
            </fieldset>
          ))}
          {buttons.length < 3 && (
            <div className="button-row">
              <button
                type="button"
                className="button button-ghost"
                onClick={() => setData({ buttons: [...buttons, { label: '', target: null }] })}
              >
                {t('Knopf hinzufügen')}
              </button>
            </div>
          )}
          <Segments
            label={t('Ausrichtung')}
            value={d.align ?? 'left'}
            options={[
              ['left', t('links')],
              ['center', t('mittig')],
              ['right', t('rechts')],
            ]}
            onChange={(align) => setData({ align })}
          />
        </>
      )
    }
    case 'tiles': {
      const tiles = d.tiles ?? []
      const setTile = (i: number, patch: Partial<HomeTile>) =>
        setData({ tiles: tiles.map((k, j) => (j === i ? { ...k, ...patch } : k)) })
      return (
        <>
          {titleField()}
          {tiles.map((k, i) => (
            <fieldset key={i} className="home-item">
              <legend>{t('Kachel {n}', { n: i + 1 })}</legend>
              <Field
                label={t('Titel')}
                value={k.title}
                maxLength={150}
                onChange={(e) => setTile(i, { title: e.target.value })}
              />
              <Field
                label={t('Kurzer Text (optional)')}
                value={k.text}
                maxLength={500}
                onChange={(e) => setTile(i, { text: e.target.value })}
              />
              {imageField(t('Bild (optional)'), k.image, (image) => setTile(i, { image }))}
              <TargetField
                data={data}
                website={website}
                value={k.target}
                onChange={(target) => setTile(i, { target })}
              />
              {tiles.length > 2 && (
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() => setData({ tiles: tiles.filter((_, j) => j !== i) })}
                >
                  {t('Kachel entfernen')}
                </button>
              )}
            </fieldset>
          ))}
          {tiles.length < 6 && (
            <div className="button-row">
              <button
                type="button"
                className="button button-ghost"
                onClick={() => setData({ tiles: [...tiles, emptyTile()] })}
              >
                {t('Kachel hinzufügen')}
              </button>
            </div>
          )}
          <Segments
            label={t('Spalten')}
            value={d.columns ?? 3}
            options={[
              [2, '2'],
              [3, '3'],
            ]}
            onChange={(columns) => setData({ columns })}
          />
        </>
      )
    }
    case 'event':
      return (
        <>
          <SelectField
            label={t('Termin')}
            value={d.event ?? ''}
            hint={t('Nur öffentliche Termine. Nach dem Termin verschwindet der Abschnitt.')}
            onChange={(e) => setData({ event: e.target.value ? Number(e.target.value) : null })}
          >
            <option value="">{t('Bitte wählen')}</option>
            {(choices?.events ?? []).map((e) => (
              <option key={e.id} value={e.id}>
                {e.title} ({formatDateTime(e.starts_at)})
              </option>
            ))}
          </SelectField>
          {titleField()}
        </>
      )
    case 'album':
      return (
        <>
          <SelectField
            label={t('Album')}
            value={d.album ?? ''}
            onChange={(e) => setData({ album: e.target.value ? Number(e.target.value) : null })}
          >
            <option value="">{t('Bitte wählen')}</option>
            {(choices?.albums ?? []).map((a) => (
              <option key={a.id} value={a.id}>
                {a.title}
              </option>
            ))}
          </SelectField>
          {titleField()}
          <SelectField
            label={t('Anzahl der Bilder')}
            value={d.count ?? 4}
            onChange={(e) => setData({ count: Number(e.target.value) })}
          >
            {[4, 5, 6, 7, 8].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </SelectField>
        </>
      )
    case 'quote':
      return (
        <>
          <Field
            label={t('Zitat')}
            value={d.text ?? ''}
            maxLength={1000}
            onChange={(e) => setData({ text: e.target.value })}
          />
          <Field
            label={t('Name (optional)')}
            value={d.name ?? ''}
            maxLength={150}
            onChange={(e) => setData({ name: e.target.value })}
          />
        </>
      )
    case 'contacts':
      return <ContactsField data={data} value={d} setData={setData} titleField={titleField()} />
    case 'faq':
      return (
        <>
          {titleField()}
          <ItemList
            items={d.items ?? []}
            min={1}
            max={12}
            legend={(n) => t('Frage {n}', { n })}
            addLabel={t('Frage hinzufügen')}
            removeLabel={t('Frage entfernen')}
            empty={() => ({ question: '', answer: '' })}
            onChange={(items) => setData({ items })}
            render={(item, set) => (
              <>
                <Field
                  label={t('Frage')}
                  value={item.question ?? ''}
                  maxLength={150}
                  onChange={(e) => set({ question: e.target.value })}
                />
                <TextEditor
                  label={t('Antwort')}
                  value={item.answer ?? ''}
                  rows={4}
                  onChange={(answer) => set({ answer })}
                />
              </>
            )}
          />
        </>
      )
    case 'partners':
      return (
        <>
          {titleField()}
          <ItemList
            items={d.items ?? []}
            min={1}
            max={12}
            legend={(n) => t('Partner {n}', { n })}
            addLabel={t('Partner hinzufügen')}
            removeLabel={t('Partner entfernen')}
            empty={emptyPartner}
            onChange={(items) => setData({ items })}
            render={(item, set) => (
              <>
                <Field
                  label={t('Name')}
                  value={item.name ?? ''}
                  maxLength={120}
                  onChange={(e) => set({ name: e.target.value })}
                />
                {imageField(t('Logo (optional)'), item.image, (image) => set({ image }))}
                <Field
                  label={t('Link (optional)')}
                  type="url"
                  placeholder="https://"
                  value={item.url ?? ''}
                  maxLength={500}
                  onChange={(e) => set({ url: e.target.value })}
                />
              </>
            )}
          />
          <PartnerImport items={d.items ?? []} onChange={(items) => setData({ items })} />
        </>
      )
    case 'directions':
      return (
        <>
          <SelectField
            label={t('Ort')}
            value={d.place ?? ''}
            hint={t('Orte pflegst du unter Einstellungen › Orte.')}
            onChange={(e) => setData({ place: e.target.value ? Number(e.target.value) : null })}
          >
            <option value="">{t('Bitte wählen')}</option>
            {(choices?.places ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </SelectField>
          {titleField()}
          <Field
            label={t('Hinweis zur Anfahrt (optional)')}
            value={d.text ?? ''}
            maxLength={1000}
            onChange={(e) => setData({ text: e.target.value })}
          />
        </>
      )
    case 'event_list':
      return (
        <>
          <SelectField
            label={t('Kategorie')}
            value={d.category ?? ''}
            hint={t('Nur öffentliche Termine, die noch kommen.')}
            onChange={(e) => setData({ category: e.target.value ? Number(e.target.value) : null })}
          >
            <option value="">{t('Bitte wählen')}</option>
            {(choices?.categories ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </SelectField>
          {titleField()}
          <SelectField
            label={t('Anzahl der Termine')}
            value={d.count ?? 4}
            onChange={(e) => setData({ count: Number(e.target.value) })}
          >
            {[2, 3, 4, 5, 6, 8, 10].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </SelectField>
        </>
      )
    case 'document':
      return (
        <>
          <SelectField
            label={t('Dokument')}
            value={d.document ?? ''}
            hint={t('Nur veröffentlichte Dokumente aus Webseite › Dokumente.')}
            onChange={(e) => setData({ document: e.target.value ? Number(e.target.value) : null })}
          >
            <option value="">{t('Bitte wählen')}</option>
            {(choices?.documents ?? []).map((doc) => (
              <option key={doc.id} value={doc.id}>
                {doc.title}
              </option>
            ))}
          </SelectField>
          {titleField()}
          <Field
            label={t('Beschriftung des Knopfs (optional)')}
            value={d.label ?? ''}
            maxLength={60}
            onChange={(e) => setData({ label: e.target.value })}
          />
        </>
      )
    case 'video':
      return (
        <>
          <Field
            label={t('Adresse des Videos')}
            type="url"
            value={d.url ?? ''}
            maxLength={500}
            hint={t(
              'Die Webseite bettet das Video nicht ein. Wer auf das Bild klickt, schaut es beim Anbieter an.',
            )}
            onChange={(e) => setData({ url: e.target.value })}
          />
          {titleField()}
          {imageField(t('Vorschaubild (optional)'), d.image, (image) => setData({ image }))}
          <Field
            label={t('Kurzer Text (optional)')}
            value={d.text ?? ''}
            maxLength={500}
            onChange={(e) => setData({ text: e.target.value })}
          />
        </>
      )
    case 'chronicle':
      return (
        <>
          <p className="muted small">
            {t(
              'Zeigt die neuesten Einträge der Zeitleiste von Verein › Chronik mit einem Link zur ganzen Chronik.',
            )}
          </p>
          {titleField()}
          <SelectField
            label={t('Anzahl der Einträge')}
            value={d.count ?? 3}
            onChange={(e) => setData({ count: Number(e.target.value) })}
          >
            {[2, 3, 4, 5, 6].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </SelectField>
        </>
      )
    case 'facts':
      return (
        <>
          {titleField()}
          <ItemList
            items={d.items ?? []}
            min={2}
            max={6}
            legend={(n) => t('Zahl {n}', { n })}
            addLabel={t('Zahl hinzufügen')}
            removeLabel={t('Zahl entfernen')}
            empty={emptyFact}
            onChange={(items) => setData({ items })}
            render={(item, set) => (
              <>
                <Field
                  label={t('Zahl')}
                  value={item.value ?? ''}
                  maxLength={20}
                  hint={t('z. B. 1920 oder 350+')}
                  onChange={(e) => set({ value: e.target.value })}
                />
                <Field
                  label={t('Text')}
                  value={item.label ?? ''}
                  maxLength={60}
                  onChange={(e) => set({ label: e.target.value })}
                />
              </>
            )}
          />
        </>
      )
    case 'divider':
      return (
        <>
          <Segments
            label={t('Art')}
            value={d.style ?? 'line'}
            options={[
              ['line', t('Linie')],
              ['space', t('Abstand')],
            ]}
            onChange={(style) => setData({ style })}
          />
          <Segments
            label={t('Größe')}
            value={d.size === 'large' ? 'large' : 'small'}
            options={[
              ['small', t('klein')],
              ['large', t('groß')],
            ]}
            onChange={(size) => setData({ size })}
          />
        </>
      )
    default:
      return null
  }
}

/** Liste gleichartiger Einträge (Fragen, Partner, Zahlen) mit Hinzufügen und Entfernen */
// Geschäftspartner mit Einwilligung übernehmen (konzepte/geschaeftspartner.md, P4)
function PartnerImport({
  items,
  onChange,
}: {
  items: HomeItem[]
  onChange: (items: HomeItem[]) => void
}) {
  const org = useActiveOrg()
  const [note, setNote] = useState('')
  return (
    <div className="stack">
      <div className="button-row">
        <button
          type="button"
          className="button"
          onClick={async () => {
            setNote('')
            try {
              const logos = await partnerApi.websiteLogos(org.id)
              const known = new Set(items.map((i) => (i.name ?? '').trim().toLowerCase()))
              const kept = items.filter((i) => (i.name ?? '').trim())
              const added = logos
                .filter((p) => !known.has(p.name.trim().toLowerCase()))
                .map((p) => ({ name: p.name, image: null, url: p.url }))
              const next = [...kept, ...added].slice(0, 12)
              onChange(next.length ? next : items)
              setNote(
                added.length
                  ? t('{n} Geschäftspartner übernommen. Bitte noch die Logos wählen.', {
                      n: Math.min(added.length, next.length - kept.length),
                    })
                  : t('Keine weiteren Geschäftspartner mit Einwilligung für die Webseite.'),
              )
            } catch {
              setNote(t('Geschäftspartner konnten nicht geladen werden.'))
            }
          }}
        >
          {t('Aus Geschäftspartnern übernehmen')}
        </button>
      </div>
      {note && <p className="muted small">{note}</p>}
    </div>
  )
}

function ItemList({
  items,
  min,
  max,
  legend,
  addLabel,
  removeLabel,
  empty,
  onChange,
  render,
}: {
  items: HomeItem[]
  min: number
  max: number
  legend: (n: number) => string
  addLabel: string
  removeLabel: string
  empty: () => HomeItem
  onChange: (items: HomeItem[]) => void
  render: (item: HomeItem, set: (patch: Partial<HomeItem>) => void) => ReactNode
}) {
  return (
    <>
      {items.map((item, i) => (
        <fieldset key={i} className="home-item">
          <legend>{legend(i + 1)}</legend>
          {render(item, (patch) =>
            onChange(items.map((x, j) => (j === i ? { ...x, ...patch } : x))),
          )}
          {items.length > min && (
            <button
              type="button"
              className="button button-ghost"
              onClick={() => onChange(items.filter((_, j) => j !== i))}
            >
              {removeLabel}
            </button>
          )}
        </fieldset>
      ))}
      {items.length < max && (
        <div className="button-row">
          <button
            type="button"
            className="button button-ghost"
            onClick={() => onChange([...items, empty()])}
          >
            {addLabel}
          </button>
        </div>
      )}
    </>
  )
}

function ContactsField({
  data,
  value,
  setData,
  titleField,
}: {
  data: SectionOptions
  value: HomeSectionData
  setData: (patch: Partial<HomeSectionData>) => void
  titleField: ReactNode
}) {
  const roles = data.home_choices?.roles ?? []
  const chosen = value.roles ?? []
  const name = new Map(roles.map((r) => [r.id, r.name]))
  const items = chosen.filter((id) => name.has(id))
  const sortable = useSortable({
    items,
    id: (id) => id,
    label: (id) => name.get(id) ?? '',
    onReorder: async (order) => setData({ roles: order }),
  })
  return (
    <>
      {titleField}
      <p className="muted small">
        {t(
          'Bis zu vier Rollen, die auf der Webseite stehen. Personen erscheinen nur mit Einwilligung, wie auf der Vorstandsseite.',
        )}
      </p>
      {roles.length === 0 && (
        <p className="muted">{t('Keine Rolle ist für die Webseite freigegeben.')}</p>
      )}
      {roles.map((r) => (
        <Checkbox
          key={r.id}
          label={r.name}
          checked={chosen.includes(r.id)}
          disabled={!chosen.includes(r.id) && chosen.length >= 4}
          onChange={(on) =>
            setData({ roles: on ? [...chosen, r.id] : chosen.filter((x) => x !== r.id) })
          }
        />
      ))}
      {items.length > 1 && (
        <>
          <SortHint />
          <ul className="sortable-list" aria-label={t('Reihenfolge der Ansprechpartner')}>
            {sortable.ordered.map((id) => {
              const { ref, className } = sortable.rowProps(id)
              return (
                <li key={id} ref={ref} className={className}>
                  {sortable.handle(id)}
                  <div className="sortable-label">{name.get(id)}</div>
                </li>
              )
            })}
          </ul>
          {sortable.status}
        </>
      )}
    </>
  )
}

/** Ziel eines Knopfs oder einer Kachel: Seite der Webseite, Termin oder Link nach außen */
export function TargetField({
  data,
  website,
  value,
  onChange,
}: {
  data: SectionOptions
  website: SectionSite
  value: HomeTarget
  onChange: (target: HomeTarget) => void
}) {
  const pages = (website.menu_items ?? []).filter(
    (it) => !it.heading && !it.key.startsWith('link:'),
  )
  const events = data.home_choices?.events ?? []
  const current =
    value && 'page' in value
      ? `page:${value.page}`
      : value && 'event' in value
        ? `event:${value.event}`
        : value && 'url' in value
          ? 'url'
          : ''
  return (
    <>
      <SelectField
        label={t('Ziel')}
        value={current}
        onChange={(e) => {
          const v = e.target.value
          if (!v) onChange(null)
          else if (v === 'url') onChange({ url: 'https://' })
          else if (v.startsWith('event:')) onChange({ event: Number(v.slice(6)) })
          else onChange({ page: v.slice(5) })
        }}
      >
        <option value="">{t('Kein Ziel')}</option>
        <optgroup label={t('Seite der Webseite')}>
          {pages.map((p) => (
            <option key={p.key} value={`page:${p.key}`}>
              {p.label}
            </option>
          ))}
        </optgroup>
        {events.length > 0 && (
          <optgroup label={t('Termin')}>
            {events.map((e) => (
              <option key={e.id} value={`event:${e.id}`}>
                {e.title}
              </option>
            ))}
          </optgroup>
        )}
        <option value="url">{t('Link nach außen')}</option>
      </SelectField>
      {value && 'url' in value && (
        <Field
          label={t('Adresse')}
          type="url"
          value={value.url}
          maxLength={500}
          onChange={(e) => onChange({ url: e.target.value })}
        />
      )}
    </>
  )
}
