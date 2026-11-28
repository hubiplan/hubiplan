// Webseite › Texte: Begrüßung, Textseiten (z. B. Chronik) und Texte der
// Untereinheiten. Änderungen sind erst nach „Veröffentlichen“ sichtbar; frühere
// Fassungen lassen sich zurückholen. Bilder verwaltet Webseite › Bilder (ImagesPage.tsx).
import { useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { contentApi } from '../../api/website.ts'
import type { WebsiteText, WebsiteTextSummary } from '../../api/website.ts'
import { useForm, useLoad } from '../../components/forms.ts'
import { Alert, Field, LoadError, SelectField, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t, tc } from '../../i18n/index.ts'
import { TextPanel } from './TextPanel.tsx'

function status(tm: WebsiteTextSummary): string {
  if (!tm.is_published) return t('Entwurf, nicht veröffentlicht')
  return tm.has_changes ? t('veröffentlicht, Entwurf mit Änderungen') : t('veröffentlicht')
}

export function ContentPage() {
  const org = useActiveOrg()
  const { data, error, reload } = useLoad(() => contentApi.texts(org.id), [org.id])
  const [open, setOpen] = useState<number | null>(null)
  const [adding, setAdding] = useState<'page' | 'unit' | 'intro' | null>(null)
  // ?einheit=<id> (Link aus der Untereinheit): deren Text öffnen oder anlegen
  const [params] = useSearchParams()
  const wantedUnit = Number(params.get('einheit')) || null
  // ?text=<id> (Link aus „Bild bearbeiten › Verwendet in“): diesen Text öffnen
  const wantedText = Number(params.get('text')) || null
  const [handled, setHandled] = useState('')
  const wanted = `${wantedUnit ?? ''}/${wantedText ?? ''}`
  if (data && (wantedUnit || wantedText) && handled !== wanted) {
    setHandled(wanted)
    if (wantedText && data.texts.some((tm) => tm.id === wantedText)) setOpen(wantedText)
    else if (wantedUnit) {
      const text = data.texts.find((tm) => tm.kind === 'unit' && tm.department === wantedUnit)
      if (text) setOpen(text.id)
      else if (data.units.some((u) => u.id === wantedUnit)) setAdding('unit')
    }
  }

  if (error) return <LoadError message={error} onRetry={() => void reload()} />
  if (!data) return <Loading />

  const groups: { title: string; kind: string }[] = [
    { title: tc('Webseite', 'Startseite'), kind: 'greeting' },
    { title: t('Textseiten'), kind: 'page' },
    { title: t('Texte der Untereinheiten'), kind: 'unit' },
    ...(data.intro_areas ? [{ title: t('Einleitungen der Bereiche'), kind: 'intro' }] : []),
  ]
  const freeAreas = (data.intro_areas ?? []).filter(
    (a) => !data.texts.some((tm) => tm.kind === 'intro' && tm.slug === a.area),
  )

  return (
    <>
      <div className="card card-wide">
        <p className="muted small">
          {t(
            'Texte gestaltest du mit den Knöpfen über dem Text: Überschriften, fett, kursiv, Listen, Links und Bilder. Wer lieber Markdown schreibt, schaltet mit „Markdown“ um. Besucher sehen erst, was du veröffentlichst. Bilder lädst und bearbeitest du unter',
          )}{' '}
          <Link to="/webseite/bilder">{t('Webseite › Bilder')}</Link>.
        </p>
        {groups.map((g) => {
          const items = data.texts.filter((tm) => tm.kind === g.kind)
          return (
            <div key={g.kind}>
              <h2>{g.title}</h2>
              {g.kind === 'intro' && (
                <p className="muted small">
                  {t(
                    'Eine Einleitung steht oben über Vorstand, Terminen, Untereinheiten oder Galerie; die Einleitung „Kontakt“ steht als Kasten neben dem Kontaktformular, ein Link allein im letzten Absatz wird dort zum Knopf. Wie diese Bereiche aussehen, wählst du unter',
                  )}{' '}
                  <Link to="/webseite/gestaltung">{t('Webseite › Gestaltung')}</Link>.
                </p>
              )}
              {items.length === 0 && <p className="muted">{t('Noch keine.')}</p>}
              {g.kind === 'page' && items.length > 0 && (
                <p className="muted small">
                  {t('Die Position der Textseiten im Menü legst du hier fest:')}{' '}
                  <Link to="/webseite/aufbau">{t('Webseite › Menü und Seiten')}</Link>.
                </p>
              )}
              <TextList
                items={items}
                render={(tm) => (
                  <>
                    <button
                      type="button"
                      className="link-button"
                      aria-expanded={open === tm.id}
                      onClick={() => setOpen(open === tm.id ? null : tm.id)}
                    >
                      {tm.kind === 'unit'
                        ? tm.department_name
                        : tm.kind === 'intro'
                          ? tm.area_label || tm.slug
                          : tm.title || tm.kind_label}
                    </button>
                    {tm.kind === 'page' && <span className="muted small"> /{tm.slug}</span>}
                    {tm.event && <span className="muted small"> · {t('Veranstaltungsseite')}</span>}
                    <span className="muted small"> · {status(tm)}</span>
                    {open === tm.id && (
                      <TextPanel
                        id={tm.id}
                        units={data.units}
                        linkTargets={data.link_targets ?? []}
                        sectionOptions={
                          tm.kind === 'unit' ? data.unit_section_options : data.section_options
                        }
                        onChanged={() => void reload()}
                        onDeleted={() => {
                          setOpen(null)
                          void reload()
                        }}
                      />
                    )}
                  </>
                )}
              />
            </div>
          )
        })}
        {adding ? (
          <NewText
            kind={adding}
            initialUnit={wantedUnit}
            areas={freeAreas}
            units={data.units.filter(
              (u) => !data.texts.some((tm) => tm.kind === 'unit' && tm.department === u.id),
            )}
            onDone={(id) => {
              setAdding(null)
              if (id) setOpen(id)
              void reload()
            }}
          />
        ) : (
          <div className="button-row">
            <button type="button" className="button" onClick={() => setAdding('page')}>
              {t('Neue Textseite')}
            </button>
            {data.units.length > 0 && (
              <button
                type="button"
                className="button button-ghost"
                onClick={() => setAdding('unit')}
              >
                {t('Text für eine Untereinheit')}
              </button>
            )}
            {freeAreas.length > 0 && (
              <button
                type="button"
                className="button button-ghost"
                onClick={() => setAdding('intro')}
              >
                {t('Einleitung für einen Bereich')}
              </button>
            )}
          </div>
        )}
      </div>
    </>
  )
}

/** Liste der Texte (die Reihenfolge der Textseiten im Menü steht unter Menü und Seiten). */
function TextList({
  items,
  render,
}: {
  items: WebsiteTextSummary[]
  render: (tm: WebsiteTextSummary) => ReactNode
}) {
  return (
    <ul className="plain-list">
      {items.map((tm) => (
        <li key={tm.id}>{render(tm)}</li>
      ))}
    </ul>
  )
}

function NewText({
  kind,
  units,
  areas,
  initialUnit,
  onDone,
}: {
  kind: 'page' | 'unit' | 'intro'
  units: { id: number; name: string }[]
  /** Bereiche ohne Einleitung (G5) */
  areas: { area: string; label: string }[]
  /** vorgewählte Untereinheit, falls sie zur Wahl steht */
  initialUnit?: number | null
  onDone: (id: number | null) => void
}) {
  const org = useActiveOrg()
  const form = useForm({
    title: '',
    slug: '',
    department: units.find((u) => u.id === initialUnit)?.id ?? units[0]?.id ?? 0,
    area: areas[0]?.area ?? '',
  })
  const { values: v, set, errors } = form

  async function save() {
    const created = (await form.submit(() =>
      contentApi.create(
        org.id,
        kind === 'page'
          ? { kind, title: v.title, slug: v.slug }
          : kind === 'intro'
            ? { kind, slug: v.area }
            : {
                kind,
                department: v.department,
                title: units.find((u) => u.id === v.department)?.name ?? '',
              },
      ),
    )) as WebsiteText | undefined
    if (created) onDone(created.id)
  }

  return (
    <form
      className="subcard"
      onSubmit={(e) => {
        e.preventDefault()
        void save()
      }}
    >
      <h3>
        {kind === 'page'
          ? t('Neue Textseite')
          : kind === 'intro'
            ? t('Einleitung für einen Bereich')
            : t('Text für eine Untereinheit')}
      </h3>
      {kind === 'intro' ? (
        <SelectField
          label={t('Bereich')}
          value={v.area}
          error={errors.slug}
          onChange={(e) => set('area', e.target.value)}
        >
          {areas.map((a) => (
            <option key={a.area} value={a.area}>
              {a.label}
            </option>
          ))}
        </SelectField>
      ) : kind === 'page' ? (
        <div className="grid-2">
          <Field
            label={t('Titel')}
            required
            value={v.title}
            error={errors.title}
            onChange={(e) => {
              const title = e.target.value
              set('title', title)
              set(
                'slug',
                title
                  .toLowerCase()
                  .replace(/ä/g, 'ae')
                  .replace(/ö/g, 'oe')
                  .replace(/ü/g, 'ue')
                  .replace(/ß/g, 'ss')
                  .replace(/[^a-z0-9]+/g, '-')
                  .replace(/^-|-$/g, '')
                  // Die Chronik der Webseite liest die Textseite „geschichte“
                  .replace(/^chronik$/, 'geschichte'),
              )
            }}
          />
          <Field
            label={t('Adresse (z. B. anfahrt; „geschichte“ erscheint als Chronik)')}
            required
            value={v.slug}
            error={errors.slug}
            onChange={(e) => set('slug', e.target.value)}
          />
        </div>
      ) : (
        <SelectField
          label={t('Untereinheit')}
          value={v.department}
          error={errors.department}
          onChange={(e) => set('department', Number(e.target.value))}
        >
          {units.map((u) => (
            <option key={u.id} value={u.id}>
              {u.name}
            </option>
          ))}
        </SelectField>
      )}
      {form.message?.kind === 'error' && <Alert kind="error">{form.message.text}</Alert>}
      <div className="button-row">
        <button type="submit" className="button button-primary" disabled={form.busy}>
          {t('Anlegen')}
        </button>
        <button type="button" className="button button-ghost" onClick={() => onDone(null)}>
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}
