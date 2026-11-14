// Webseite der Einheit: einrichten, dann Unterpunkte (Seitenleiste) Übersicht (Prüfliste, Zustand, Vorschau),
// Inhalte, Gestaltung (Design), Aufbau (Bausteine, Personen, Untereinheiten), Domain und Kontakt. Die Datenschutzhinweise
// der Webseite stehen unter Einstellungen › Datenschutz (WebsitePrivacy.tsx).
// Die Seite selbst zeigt das Projekt „hubiplan-website“.
import { useState } from 'react'
import { Link, Navigate, Route, Routes } from 'react-router-dom'
import { SubpageUnavailable } from '../NoticePages.tsx'
import { DRAFT_FIELDS, hasDraft, heldApi, websiteApi } from '../../api/website.ts'
import type {
  HomeSection,
  HomeTarget,
  DesignDraft,
  MenuItem,
  MenuNode,
  MenuPlace,
  PreviewLink,
  Website,
  WebsiteData,
  WebsiteSettings,
} from '../../api/website.ts'
import { confirmDialog } from '../../components/dialog.ts'
import {
  errorMessage,
  formatDateTime,
  useAutoSave,
  useForm,
  useLoad,
} from '../../components/forms.ts'
import {
  Alert,
  Checkbox,
  Field,
  LoadError,
  SaveStatus,
  SelectField,
  Loading,
} from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { Term, Why } from '../../learning/Aids.tsx'
import type { TermKey } from '../../learning/content.ts'
import { ContentPage } from './ContentPage.tsx'
import { ImagesPage } from './images.tsx'
import { DesignChooser } from './DesignChooser.tsx'
import { HeaderImage } from './HeaderImage.tsx'
import { StyleTuning } from './StyleTuning.tsx'
import type { PreviewFocus } from './StyleTuning.tsx'
import { DesignVersions, DraftBar, PreviewFrame } from './DesignPreview.tsx'
import { SiteLanguage } from './SiteLanguage.tsx'
import { AreaLayouts } from './AreaLayouts.tsx'
import { DesignFile } from './DesignFile.tsx'
import { HomeBuilder, TargetField } from './HomeBuilder.tsx'
import { t } from '../../i18n/index.ts'
import { GalleryPage } from './GalleryPage.tsx'
import { DocumentsPage } from './DocumentsPage.tsx'
import { SocialPage } from './SocialPage.tsx'
import { ImageHosts } from './ImageHosts.tsx'
import { LINK, MenuTree } from './MenuTree.tsx'
import { normalizeMenu } from './menuTree.ts'
import { PageHeader } from '../../components/PageHeader.tsx'
import { TextEditor } from '../../components/texteditor/TextEditor.tsx'

const STATE_TEXT: Record<string, string> = {
  off: t('Aus: Die Webseite ist nicht erreichbar.'),
  maintenance: t('Wartung: Besucher sehen nur eine Wartungsseite mit Impressum und Datenschutz.'),
  public: t('Öffentlich: Die Webseite ist für alle sichtbar.'),
}

export function WebsitePage() {
  const org = useActiveOrg()
  const { data, error, reload, setData } = useLoad(() => websiteApi.get(org.id), [org.id])
  // Zählt hoch, wenn der Entwurf von außen wechselt: die Eingaben starten dann neu
  const [generation, setGeneration] = useState(0)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  // Der Kopf steht auch beim Laden und bei Fehlern (Seitenkopf S-05)
  if (error)
    return (
      <section>
        <PageHeader />
        <LoadError message={error} onRetry={() => void reload()} />
      </section>
    )
  if (!data)
    return (
      <section>
        <PageHeader />
        <Loading />
      </section>
    )

  async function setup() {
    setBusy(true)
    setMessage(null)
    try {
      setData(await websiteApi.setup(org.id))
    } catch (err) {
      setMessage(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <PageHeader />
      {!data.module_enabled && (
        <Alert kind="info">
          {t(
            'Das Modul „Webseite“ ist für {name} nicht freigeschaltet. Die Plattform schaltet es für Einheiten frei, die eine eigene Webseite bekommen sollen.',
            { name: org.name },
          )}
        </Alert>
      )}
      {data.module_enabled && !data.website && (
        <div className="card card-wide">
          <h2>{t('Webseite einrichten')}</h2>
          <p>
            {t(
              'HUBIplan stellt Vorstand, Untereinheiten, Termine mit Kalender-Abo, Social-Media-Links und ein Kontaktformular für eine öffentliche Webseite bereit. Personendaten erscheinen nur nach den Regeln zu Einwilligung und Widerspruch.',
            )}
          </p>
          <p className="muted small">
            {t(
              'Eine neue Webseite startet im Wartungsmodus: Besucher sehen nur einen Hinweis, du selbst kannst sie in der Vorschau ansehen.',
            )}
          </p>
          {message && <Alert kind="error">{message}</Alert>}
          {data.can_manage && (
            <button type="button" className="button" disabled={busy} onClick={() => void setup()}>
              {t('Webseite einrichten')}
            </button>
          )}
        </div>
      )}
      {data.website && (
        <WebsiteAdmin
          key={`${data.website.public_key}:${generation}`}
          data={data}
          website={data.website}
          onChange={setData}
          onReset={(next) => {
            setData(next)
            setGeneration((g) => g + 1)
          }}
          reload={() => void reload()}
        />
      )}
    </section>
  )
}

/** Eigene Überschrift im Menü (Ralf 05.11.): ``heading:<Nummer>``, Name in ``block_names`` */
const HEADING = /^heading:[1-9][0-9]{0,2}$/

/** Eigene Überschrift oder Link nach außen: lebt nur, solange er einen Namen hat */
const isOwn = (key: string) => HEADING.test(key) || LINK.test(key)

/** Menüpunkte vom Server plus noch nicht gespeicherte eigene Überschriften und Links;
 * gelöschte fallen weg */
function menuItems(
  items: MenuItem[],
  names: Record<string, string>,
  links: Record<string, string>,
): MenuItem[] {
  const known = new Set(items.map((it) => it.key))
  const added: MenuItem[] = Object.keys(names)
    .filter((key) => isOwn(key) && !known.has(key))
    .map((key) => ({
      key,
      label: names[key],
      default_label: '',
      renamable: true,
      hint: HEADING.test(key)
        ? t('eigene Überschrift ohne eigene Seite; Name leer lassen entfernt sie')
        : '',
      toggle: null,
      heading: HEADING.test(key),
      parent: null,
      url: links[key] ?? '',
    }))
  return [...items.filter((it) => !isOwn(it.key) || it.key in names), ...added]
}

/** Nächste freie Nummer für ``heading:`` oder ``link:`` */
function withNew(
  names: Record<string, string>,
  pattern: RegExp,
  prefix: string,
  label: string,
): Record<string, string> {
  const used = Object.keys(names)
    .filter((key) => pattern.test(key))
    .map((key) => Number(key.split(':')[1]))
  const next = Math.max(0, ...used) + 1
  return { ...names, [`${prefix}:${next}`]: label }
}

const SETTINGS: (keyof WebsiteSettings)[] = [
  'state',
  'maintenance_text',
  'blocks',
  'menu',
  'block_names',
  'menu_links',
  'menu_button',
  'menu_places',
  'home_sections',
  'design',
  'color_roles',
  'style',
  'layouts',
  'header_image',
  'header_image_narrow',
  'name_format',
  'show_vacant',
  'show_instrument',
  'show_titles',
  'show_address',
  'show_member_since',
  'missing_consent',
  'units_mode',
  'unit_ids',
  'include_unit_events',
  'include_parent_events',
  'include_parent_honors',
  'allow_indexing',
  'language',
  'contact_limit_per_hour',
  'notice_text',
  'notice_target',
  'notice_from',
  'notice_until',
  'image_hosts',
]

function pick(w: Website): WebsiteSettings {
  const values = Object.fromEntries(SETTINGS.map((k) => [k, w[k]])) as unknown as WebsiteSettings
  // Gestaltung: was im Entwurf steht, sonst der veröffentlichte Stand (G2)
  return { ...values, ...(w.draft ?? {}) }
}

/** Geänderte Felder der Gestaltung gehen in den Entwurf, alles andere wie bisher */
function splitDraft(website: Website, changes: Partial<WebsiteSettings>) {
  if (website.draft === undefined) return changes
  const rest: Partial<WebsiteSettings> & { draft?: DesignDraft } = {}
  const draft: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(changes)) {
    if ((DRAFT_FIELDS as readonly string[]).includes(key)) draft[key] = value
    else (rest as Record<string, unknown>)[key] = value
  }
  if (Object.keys(draft).length > 0) rest.draft = draft as DesignDraft
  return rest
}

/** F7: Inhalte der Startseiten-Abschnitte mit dem Recht „Inhalte bearbeiten“ (in den Entwurf) */
function HomeContentCard({
  data,
  website,
  design,
  onReset,
}: {
  data: WebsiteData
  website: Website
  design: string
  onReset: (data: WebsiteData) => void
}) {
  const org = useActiveOrg()
  const [error, setError] = useState<string | null>(null)
  const value = website.draft?.home_sections ?? website.home_sections

  async function save(next: HomeSection[]) {
    setError(null)
    try {
      onReset(await websiteApi.saveHomeContent(org.id, next))
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <section className="card card-wide" aria-labelledby="startseite-inhalte">
      <h2 id="startseite-inhalte">{t('Startseite')}</h2>
      <HomeBuilder
        data={data}
        website={website}
        value={value}
        blocks={website.blocks}
        design={design}
        contentOnly
        onChange={(next) => void save(next)}
      />
      {error && <Alert kind="error">{error}</Alert>}
    </section>
  )
}

function WebsiteAdmin({
  data,
  website,
  onChange,
  onReset,
  reload,
}: {
  data: WebsiteData
  website: Website
  onChange: (data: WebsiteData) => void
  /** Neuer Stand von außen (Entwurf veröffentlicht, verworfen, Fassung zurückgeholt) */
  onReset: (data: WebsiteData) => void
  reload: () => void
}) {
  const org = useActiveOrg()
  const form = useForm(pick(website))
  const { values: v, set, errors } = form
  const auto = useAutoSave(
    form,
    (changes) => websiteApi.save(org.id, splitDraft(website, changes)),
    {
      enabled: data.can_manage,
      onSaved: (saved) => onChange(saved as WebsiteData),
    },
  )
  const [message, setMessage] = useState<string | null>(null)
  // Punkt 5 (Ralf 14.11.): Stelle, die die Vorschau nach der letzten Änderung zeigt
  const [focus, setFocus] = useState<PreviewFocus>({})

  async function remove() {
    const ok = await confirmDialog({
      title: t('Webseite entfernen?'),
      message: t(
        'Einstellungen, Domains und Vorschau-Links werden gelöscht. Die Daten in HUBIplan (Mitglieder, Termine, Einwilligungen) bleiben erhalten.',
      ),
      confirmLabel: t('Entfernen'),
    })
    if (!ok) return
    try {
      await websiteApi.remove(org.id)
      reload()
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }

  const settings = (title: string, children: React.ReactNode) => (
    <form className="card card-wide" onSubmit={(e) => e.preventDefault()}>
      {data.can_manage && <SaveStatus auto={auto} />}
      <h2>{title}</h2>
      <fieldset disabled={!data.can_manage}>{children}</fieldset>
    </form>
  )

  const overview = (
    <>
      <ChecklistCard website={website} />
      {settings(
        t('Zustand'),
        <>
          <SelectField
            label={t('Zustand der Webseite')}
            value={v.state}
            error={errors.state}
            hint={STATE_TEXT[v.state]}
            onChange={(e) => set('state', e.target.value as WebsiteSettings['state'])}
          >
            <option value="off">{t('Aus')}</option>
            <option value="maintenance">{t('Wartung')}</option>
            <option value="public">{t('Öffentlich')}</option>
          </SelectField>
          {data.preview_only && (
            <Alert kind="info">
              {t(
                'Auf diesem Server sind alle Webseiten nur in der Vorschau sichtbar (Testserver).',
              )}
            </Alert>
          )}
          <TextEditor
            label={t('Hinweis auf der Wartungsseite')}
            value={v.maintenance_text}
            error={errors.maintenance_text}
            rows={3}
            onChange={(text) => set('maintenance_text', text)}
          />
          <p className="muted small">
            {t('Schlüssel der Webseite in der öffentlichen Schnittstelle:')}{' '}
            <code>{website.public_key}</code>
          </p>
        </>,
      )}
      {/* S4 (Ralf 14.11.): Grundeinstellungen stehen bei „Zustand“ */}
      <SiteLanguage
        value={v.language ?? 'de'}
        error={errors.language}
        render={(field) => settings(t('Sprache der Webseite'), field)}
        onChange={(lang) => set('language', lang)}
      />
      {settings(
        t('Suchmaschinen'),
        <>
          <Checkbox
            label={t('Suchmaschinen dürfen die Webseite aufnehmen')}
            checked={v.allow_indexing}
            onChange={(on) => set('allow_indexing', on)}
          />
          <Why k="web_indexing" />
        </>,
      )}
      {settings(
        t('Bilder für KI-Assistenten'),
        <ImageHosts
          value={v.image_hosts ?? []}
          error={errors.image_hosts}
          disabled={!data.can_manage}
          onChange={(next) => set('image_hosts', next)}
        />,
      )}
      {settings(
        t('Hinweisleiste'),
        <>
          <p className="muted small">
            {t(
              'Ein kurzer Hinweis oben auf allen Seiten, z. B. „Schützenfest 22.–25.8.: Programm“. Er erscheint nur im Zeitraum und verschwindet danach von selbst.',
            )}
          </p>
          <Field
            label={t('Text der Hinweisleiste')}
            value={v.notice_text ?? ''}
            maxLength={200}
            error={errors.notice_text}
            hint={t('leer = keine Hinweisleiste')}
            onChange={(e) => set('notice_text', e.target.value)}
          />
          <TargetField
            data={data}
            website={website}
            value={
              v.notice_target && Object.keys(v.notice_target).length > 0
                ? (v.notice_target as HomeTarget)
                : null
            }
            onChange={(target) => set('notice_target', target ?? {})}
          />
          {errors.notice_target && <Alert kind="error">{errors.notice_target}</Alert>}
          <div className="grid-2">
            <Field
              label={t('Zeigen ab')}
              type="date"
              value={v.notice_from ?? ''}
              error={errors.notice_from}
              hint={t('leer = sofort')}
              onChange={(e) => set('notice_from', e.target.value || null)}
            />
            <Field
              label={t('Zeigen bis')}
              type="date"
              value={v.notice_until ?? ''}
              error={errors.notice_until}
              hint={t('leer = ohne Ende')}
              onChange={(e) => set('notice_until', e.target.value || null)}
            />
          </div>
        </>,
      )}
      <PreviewCard data={data} website={website} onChange={reload} />
      {data.can_manage && (
        <div className="card card-wide">
          <h2>{t('Webseite entfernen')}</h2>
          {message && <Alert kind="error">{message}</Alert>}
          <button type="button" className="button button-danger" onClick={() => void remove()}>
            {t('Webseite entfernen')}
          </button>
        </div>
      )}
    </>
  )

  const headerImage = (
    <HeaderImage
      value={v.header_image ?? null}
      narrow={v.header_image_narrow ?? null}
      units={data.units}
      onChange={(id) => set('header_image', id)}
      onNarrowChange={(id) => set('header_image_narrow', id)}
    />
  )

  const draftBar = (
    <DraftBar website={website} auto={auto} canManage={data.can_manage} onReset={onReset} />
  )

  /** Gestaltung (S1, Ralf 14.11.): Entwurfsleiste oben, Einstellungen links, Vorschau rechts */
  const shell = (children: React.ReactNode, preview = true) => (
    <div className="design-split">
      <div className="design-split-grid">
        <div className="design-split-settings">
          {draftBar}
          {children}
        </div>
        {preview && website.draft !== undefined && (
          <aside className="design-split-preview" aria-label={t('Vorschau')}>
            <PreviewFrame website={website} focus={focus} />
          </aside>
        )}
      </div>
    </div>
  )

  const designLabel =
    data.designs?.find((d) => d.key === (v.design ?? 'classic'))?.label ?? v.design ?? ''

  const design = shell(
    data.designs ? (
      settings(
        t('Design und Farben'),
        <DesignChooser
          data={data}
          design={v.design ?? 'classic'}
          colorRoles={v.color_roles ?? {}}
          onDesign={(key) => {
            setFocus({})
            set('design', key)
          }}
          onColorRoles={(next) => {
            setFocus({})
            set('color_roles', next)
          }}
          onPackagesChanged={reload}
        />,
      )
    ) : (
      <Alert kind="info">{t('Auf diesem Server gibt es keine Designs zur Auswahl.')}</Alert>
    ),
  )

  const tuning = shell(
    data.style_catalog
      ? settings(
          t('Feinabstimmung'),
          <StyleTuning
            catalog={data.style_catalog}
            design={v.design ?? 'classic'}
            designLabel={designLabel}
            value={v.style ?? {}}
            onChange={(next) => set('style', next)}
            headerImage={headerImage}
            homeSections={v.home_sections}
            blocks={v.blocks}
            onFocus={setFocus}
          />,
        )
      : settings(t('Kopfbild'), headerImage),
  )

  const areas = shell(
    data.layout_catalog ? (
      settings(
        t('Darstellung der Bereiche'),
        <AreaLayouts
          catalog={data.layout_catalog}
          labels={data.block_labels}
          blocks={v.blocks}
          value={v.layouts ?? {}}
          onChange={(next) => {
            setFocus({ target: 'inhalt' })
            set('layouts', next)
          }}
        />,
      )
    ) : (
      <Alert kind="info">{t('Auf diesem Server gibt es keine Darstellungen zur Auswahl.')}</Alert>
    ),
  )

  // S3: Frühere Fassungen und Gestaltung als Datei betreffen alles Gestaltete
  const versions = shell(
    <>
      {settings(
        t('Frühere Fassungen'),
        (website.design_versions?.length ?? 0) > 0 ? (
          <DesignVersions
            website={website}
            auto={auto}
            canManage={data.can_manage}
            onReset={onReset}
          />
        ) : (
          <p className="muted">
            {t('Noch keine früheren Fassungen. Jedes „Veröffentlichen“ legt eine an.')}
          </p>
        ),
      )}
      {data.can_manage &&
        settings(
          t('Gestaltung als Datei'),
          <DesignFile
            values={{
              design: v.design ?? 'classic',
              color_roles: v.color_roles ?? {},
              style: v.style ?? {},
              layouts: v.layouts ?? {},
            }}
            designs={Object.fromEntries((data.designs ?? []).map((d) => [d.key, d.label]))}
            onLoad={(loaded) => {
              if (loaded.design !== undefined) set('design', loaded.design)
              if (loaded.color_roles !== undefined) set('color_roles', loaded.color_roles)
              if (loaded.style !== undefined) set('style', loaded.style)
              if (loaded.layouts !== undefined) set('layouts', loaded.layouts)
            }}
          />,
        )}
    </>,
    false,
  )

  // S2: eine Startseite für alle. Verwalter stellen zusammen, wer nur Inhalte pflegt,
  // ändert den Inhalt der vorhandenen Abschnitte.
  const homeManage =
    data.can_manage && data.home_labels && v.home_sections
      ? shell(
          settings(
            t('Startseite'),
            <HomeBuilder
              data={data}
              website={website}
              value={v.home_sections}
              blocks={v.blocks}
              design={v.design ?? 'classic'}
              onChange={(next) => {
                setFocus({ target: 'inhalt' })
                set('home_sections', next)
              }}
            />,
          ),
        )
      : null

  // F7: Inhalte der Startseiten-Abschnitte für alle mit „Inhalte bearbeiten“
  const homeContent = (
    <div className="design-split">
      <div className="design-split-grid">
        <div className="design-split-settings">
          {draftBar}
          {data.home_labels && (
            <HomeContentCard
              data={data}
              website={website}
              design={v.design ?? 'classic'}
              onReset={onReset}
            />
          )}
        </div>
        {website.draft !== undefined && (
          <aside className="design-split-preview" aria-label={t('Vorschau')}>
            <PreviewFrame website={website} />
          </aside>
        )}
      </div>
    </div>
  )

  const hasUnits = data.units.length > 0
  // Ältere Server liefern has_parent_units nicht: dann wie bisher zeigen
  const hasParents = data.has_parent_units ?? true

  const structure = (
    <>
      {/* Lange Seite: der Hinweis steht oben und bleibt beim Scrollen unter der Kopfzeile */}
      {hasDraft(website) && (
        <DraftBar
          website={website}
          auto={auto}
          canManage={data.can_manage}
          onReset={onReset}
          sticky
        />
      )}
      {settings(
        t('Bausteine'),
        <>
          <p className="muted small">
            {t(
              'Welche Bereiche die Webseite zeigt, in der Reihenfolge des Menüs. Mit dem Stift gibst du einem Baustein einen eigenen Namen für Menü und Überschrift.',
            )}
          </p>
          <p className="muted small">
            {t(
              'Reihenfolge, Namen, Links und Knopf des Menüs kommen in den Entwurf und erscheinen erst nach „Veröffentlichen“. Die Häkchen (Baustein an oder aus) gelten sofort.',
            )}
          </p>
          {website.menu_items && (
            <>
              <MenuTree
                items={menuItems(website.menu_items, v.block_names ?? {}, v.menu_links ?? {})}
                value={v.menu ?? []}
                blocks={v.blocks}
                names={v.block_names ?? {}}
                links={v.menu_links ?? {}}
                button={v.menu_button ?? ''}
                disabled={!data.can_manage}
                onChange={(next) => set('menu', next)}
                onRename={(key, name) => {
                  const next = { ...(v.block_names ?? {}) }
                  // Eigene Überschrift oder Link: leer lassen entfernt sie beim Speichern
                  if (name.trim() || isOwn(key)) next[key] = name
                  else delete next[key]
                  set('block_names', next)
                }}
                onLinkUrl={(key, url) => set('menu_links', { ...(v.menu_links ?? {}), [key]: url })}
                onToggle={(key, on) => set('blocks', { ...v.blocks, [key]: on })}
              />
              {data.can_manage && (
                <div className="actions">
                  <button
                    type="button"
                    className="button button-ghost"
                    onClick={() =>
                      set(
                        'block_names',
                        withNew(v.block_names ?? {}, HEADING, 'heading', t('Neue Überschrift')),
                      )
                    }
                  >
                    {t('Überschrift hinzufügen')}
                  </button>
                  <button
                    type="button"
                    className="button button-ghost"
                    onClick={() =>
                      set(
                        'block_names',
                        withNew(v.block_names ?? {}, LINK, 'link', t('Neuer Link')),
                      )
                    }
                  >
                    {t('Link nach außen hinzufügen')}
                  </button>
                </div>
              )}
              {errors.menu_links && <Alert kind="error">{errors.menu_links}</Alert>}
              <MenuButtonField
                items={menuItems(website.menu_items, v.block_names ?? {}, v.menu_links ?? {})}
                menu={v.menu ?? []}
                names={v.block_names ?? {}}
                value={v.menu_button ?? ''}
                error={errors.menu_button}
                disabled={!data.can_manage}
                onChange={(key) => set('menu_button', key)}
              />
              <MenuPlacesField
                items={menuItems(website.menu_items, v.block_names ?? {}, v.menu_links ?? {})}
                menu={v.menu ?? []}
                names={v.block_names ?? {}}
                value={v.menu_places ?? {}}
                error={errors.menu_places}
                disabled={!data.can_manage}
                onChange={(next) => set('menu_places', next)}
              />
            </>
          )}
          {errors.block_names && <Alert kind="error">{errors.block_names}</Alert>}
          {Object.entries(data.block_labels)
            .filter(([key]) => !website.menu_items?.some((it) => it.toggle === key))
            .map(([key, label]) => (
              <Checkbox
                key={key}
                label={label}
                hint={data.block_hints?.[key]}
                checked={v.blocks[key] ?? true}
                onChange={(on) => set('blocks', { ...v.blocks, [key]: on })}
              />
            ))}
        </>,
      )}
      {settings(
        t('Personen'),
        <>
          <div className="grid-2">
            <SelectField
              label={t('Namensform')}
              value={v.name_format}
              onChange={(e) => set('name_format', e.target.value as WebsiteSettings['name_format'])}
            >
              <option value="full">{t('Vorname Name')}</option>
              <option value="initial">{t('Vorname N.')}</option>
            </SelectField>
            <SelectField
              label={t('Personen ohne Einwilligung (z. B. in der Chronik)')}
              value={v.missing_consent}
              onChange={(e) =>
                set('missing_consent', e.target.value as WebsiteSettings['missing_consent'])
              }
            >
              <option value="omit">{t('auslassen')}</option>
              <option value="nn">{t('als „N. N.“ zeigen')}</option>
            </SelectField>
          </div>
          <div className="aid-row">
            <Why k="web_names" />
            <Why k="web_consent" />
          </div>
          <Checkbox
            label={t('Titel vor dem Namen nennen')}
            hint={t('z. B. „Dr. Max Muster“; Titel aus der Mitgliedsakte')}
            checked={v.show_titles ?? false}
            onChange={(on) => set('show_titles', on)}
          />
          <Checkbox
            label={t('Unbesetzte Funktionen als „derzeit unbesetzt“ zeigen')}
            checked={v.show_vacant}
            onChange={(on) => set('show_vacant', on)}
          />
          {org.modules.includes('music') && (
            <Checkbox
              label={t('Hauptinstrument unter dem Namen zeigen')}
              hint={t('aus Musik › Musiker; bei Vorstand und Mitgliederlisten')}
              checked={v.show_instrument ?? false}
              onChange={(on) => set('show_instrument', on)}
            />
          )}
          <Checkbox
            label={t('Anschrift beim Vorstand zeigen')}
            hint={t('nur bei Personen mit Einwilligung „Anschrift“')}
            checked={v.show_address ?? false}
            onChange={(on) => set('show_address', on)}
          />
          <Checkbox
            label={t('Mitgliederlisten mit Eintrittsjahr')}
            checked={v.show_member_since ?? true}
            onChange={(on) => set('show_member_since', on)}
          />
          <p className="muted small">
            {t(
              'Welche Funktionen erscheinen, legst du an den Rollen fest („auf der Webseite zeigen“). Einwilligungen und Widersprüche stehen in der Mitgliederakte unter „Veröffentlichung“.',
            )}
          </p>
        </>,
      )}
      {settings(
        t('Untereinheiten'),
        <>
          <SelectField
            label={t('Untereinheiten auf der Webseite')}
            value={v.units_mode}
            onChange={(e) => set('units_mode', e.target.value as WebsiteSettings['units_mode'])}
          >
            <option value="all">{t('alle')}</option>
            <option value="selected">{t('ausgewählte')}</option>
            <option value="none">{t('keine')}</option>
          </SelectField>
          {v.units_mode === 'selected' &&
            data.units.map((u) => (
              <Checkbox
                key={u.id}
                label={u.name}
                checked={v.unit_ids.includes(u.id)}
                onChange={(on) =>
                  set(
                    'unit_ids',
                    on ? [...v.unit_ids, u.id] : v.unit_ids.filter((id) => id !== u.id),
                  )
                }
              />
            ))}
          {errors.unit_ids && <Alert kind="error">{errors.unit_ids}</Alert>}
        </>,
      )}
      {/* Häkchen nur, wenn es Einheiten darunter bzw. darüber gibt; sonst entfällt der Block.
          Gespeicherte Werte bleiben unverändert. */}
      {org.modules.includes('events') &&
        (hasUnits || hasParents) &&
        settings(
          t('Termine'),
          <>
            {hasUnits && (
              <Checkbox
                label={t('Öffentliche Termine der Untereinheiten im Kalender der Webseite')}
                checked={v.include_unit_events}
                onChange={(on) => set('include_unit_events', on)}
              />
            )}
            {hasParents && (
              <Checkbox
                label={t(
                  'Öffentliche Termine der übergeordneten Einheiten im Kalender der Webseite',
                )}
                hint={t('z. B. Dachverband; nur Termine, die nach unten freigegeben sind')}
                checked={v.include_parent_events}
                onChange={(on) => set('include_parent_events', on)}
              />
            )}
          </>,
        )}
      {org.modules.includes('honors') &&
        settings(
          t('Würdenträger'),
          <>
            <Checkbox
              label={t('Weitergegebene Würden der übergeordneten Einheiten zeigen')}
              hint={t('z. B. Könige des Dachverbands; nur die Träger, die aus eurer Einheit kamen')}
              checked={v.include_parent_honors}
              onChange={(on) => set('include_parent_honors', on)}
            />
          </>,
        )}
    </>
  )

  const domain = (
    <>
      <DomainsCard data={data} website={website} onChange={reload} />
    </>
  )

  const contact = (
    <>
      {settings(
        t('Kontaktformular'),
        <Field
          label={t('Höchstens Mails aus dem Kontaktformular je Stunde')}
          type="number"
          min={1}
          max={100}
          value={v.contact_limit_per_hour}
          error={errors.contact_limit_per_hour}
          hint={t(
            'Schützt das Postfach vor Massenversand (Mails von Rundschreiben zählen beim Anbieter mit).',
          )}
          onChange={(e) => set('contact_limit_per_hour', Number(e.target.value))}
        />,
      )}
      {data.can_manage && <HeldCard />}
    </>
  )

  return (
    <>
      <Routes>
        <Route index element={overview} />
        <Route
          path="inhalte"
          element={
            data.can_edit_content ? (
              <ContentPage />
            ) : (
              <Alert kind="info">{t('Dafür fehlt dir das Recht „Inhalte bearbeiten“.')}</Alert>
            )
          }
        />
        <Route
          path="bilder"
          element={
            data.can_edit_content ? (
              <ImagesPage />
            ) : (
              <Alert kind="info">{t('Dafür fehlt dir das Recht „Inhalte bearbeiten“.')}</Alert>
            )
          }
        />
        <Route
          path="galerie"
          element={
            data.can_edit_content ? (
              <GalleryPage />
            ) : (
              <Alert kind="info">{t('Dafür fehlt dir das Recht „Inhalte bearbeiten“.')}</Alert>
            )
          }
        />
        <Route
          path="dokumente"
          element={
            data.can_edit_content ? (
              <DocumentsPage />
            ) : (
              <Alert kind="info">{t('Dafür fehlt dir das Recht „Inhalte bearbeiten“.')}</Alert>
            )
          }
        />
        <Route
          path="beitraege"
          element={
            data.can_edit_content ? (
              <SocialPage />
            ) : (
              <Alert kind="info">{t('Dafür fehlt dir das Recht „Inhalte bearbeiten“.')}</Alert>
            )
          }
        />
        <Route
          path="startseite"
          element={
            homeManage ? (
              homeManage
            ) : data.can_edit_home_content ? (
              homeContent
            ) : (
              <Alert kind="info">{t('Dafür fehlt dir das Recht „Inhalte bearbeiten“.')}</Alert>
            )
          }
        />
        <Route path="gestaltung" element={design} />
        <Route path="feinabstimmung" element={tuning} />
        <Route path="bereiche" element={areas} />
        <Route path="fassungen" element={versions} />
        <Route path="aufbau" element={structure} />
        <Route path="domain" element={domain} />
        <Route path="kontakt" element={contact} />
        {/* Datenschutzhinweise stehen jetzt unter Einstellungen › Datenschutz */}
        <Route path="datenschutz" element={<Navigate to="/einstellungen/datenschutz" replace />} />
        <Route path="*" element={<SubpageUnavailable to="/webseite" label={t('Zur Webseite')} />} />
      </Routes>
    </>
  )
}

/** Ein Hauptpunkt des Menüs als Knopf (Ralf 10.11.), z. B. „Mitglied werden“ */
function MenuButtonField({
  items,
  menu,
  names,
  value,
  error,
  disabled,
  onChange,
}: {
  items: MenuItem[]
  menu: MenuNode[]
  names: Record<string, string>
  value: string
  error?: string
  disabled: boolean
  onChange: (key: string) => void
}) {
  const byKey = new Map(items.map((it) => [it.key, it]))
  // Nur einfache Hauptpunkte: keine Überschrift, kein Aufklappmenü
  const options = normalizeMenu(menu, items)
    .filter((n) => n.children.length === 0 && byKey.has(n.key) && !byKey.get(n.key)!.heading)
    .map((n) => {
      const it = byKey.get(n.key)!
      return { key: n.key, label: (it.renamable && names[n.key]?.trim()) || it.label }
    })
  return (
    <SelectField
      label={t('Menüpunkt als Knopf hervorheben')}
      hint={t(
        'Ein Hauptpunkt erscheint im Menü als farbiger Knopf, z. B. „Kontakt“ oder ein Link „Mitglied werden“. Punkte mit Unterpunkten und Überschriften gehen nicht.',
      )}
      value={options.some((o) => o.key === value) ? value : ''}
      error={error}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">{t('keiner')}</option>
      {options.map((o) => (
        <option key={o.key} value={o.key}>
          {o.label}
        </option>
      ))}
    </SelectField>
  )
}

/** Platz der Hauptpunkte (Webseite #75): nur im Menü, nur im Fuß (neben Impressum und
 * Datenschutz) oder in beiden; z. B. „Kontakt“ aus der vollen Menüleiste in den Fuß. */
function MenuPlacesField({
  items,
  menu,
  names,
  value,
  error,
  disabled,
  onChange,
}: {
  items: MenuItem[]
  menu: MenuNode[]
  names: Record<string, string>
  value: Record<string, MenuPlace>
  error?: string
  disabled: boolean
  onChange: (next: Record<string, MenuPlace>) => void
}) {
  const byKey = new Map(items.map((it) => [it.key, it]))
  // Wie beim Knopf nur einfache Hauptpunkte: keine Überschrift, kein Aufklappmenü
  const rows = normalizeMenu(menu, items)
    .filter((n) => n.children.length === 0 && byKey.has(n.key) && !byKey.get(n.key)!.heading)
    .map((n) => {
      const it = byKey.get(n.key)!
      return { key: n.key, label: (it.renamable && names[n.key]?.trim()) || it.label }
    })
  if (rows.length === 0) return null
  return (
    <details className="menue-plaetze">
      <summary>{t('Menüpunkte im Fuß')}</summary>
      <p className="muted small">
        {t(
          'Ein Punkt kann statt im Menü im Fuß neben Impressum und Datenschutz stehen, oder in beiden. Die Seite bleibt erreichbar und ihr Baustein bleibt an.',
        )}
      </p>
      <div className="grid-2">
        {rows.map((row) => (
          <SelectField
            key={row.key}
            label={row.label}
            value={value[row.key] ?? ''}
            disabled={disabled}
            onChange={(e) => {
              const next = { ...value }
              const place = e.target.value as MenuPlace | ''
              if (place) next[row.key] = place
              else delete next[row.key]
              onChange(next)
            }}
          >
            <option value="">{t('im Menü')}</option>
            <option value="footer">{t('nur im Fuß')}</option>
            <option value="both">{t('im Menü und im Fuß')}</option>
          </SelectField>
        ))}
      </div>
      {error && <Alert kind="error">{error}</Alert>}
    </details>
  )
}

/** Bausteine der Startseite: ein/aus und Reihenfolge per Ziehen (Ralf 10.11., wie das Menü). */
function DomainsCard({
  data,
  website,
  onChange,
}: {
  data: WebsiteData
  website: Website
  onChange: () => void
}) {
  const org = useActiveOrg()
  const [host, setHost] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function run(action: () => Promise<unknown>) {
    setError(null)
    try {
      await action()
      onChange()
      return true
    } catch (err) {
      setError(errorMessage(err))
      return false
    }
  }

  return (
    <div className="card card-wide">
      <h2>{t('Domains')}</h2>
      <p className="muted small">
        {t(
          'Unter diesen Adressen erkennt die Webseite {name}. Die Domain muss beim Anbieter auf den Server der Webseite zeigen.',
          { name: org.name },
        )}
      </p>
      {website.domains.length === 0 && (
        <p className="muted">{t('Noch keine Domain eingetragen.')}</p>
      )}
      <ul className="plain-list">
        {website.domains.map((d) => (
          <li key={d.id}>
            <strong>{d.hostname}</strong>
            {d.is_primary ? t(' (Hauptadresse)') : ''}
            {data.can_manage && (
              <span className="button-row">
                {!d.is_primary && (
                  <button
                    type="button"
                    className="button button-ghost"
                    onClick={() => void run(() => websiteApi.makePrimary(org.id, d.id))}
                  >
                    {t('Als Hauptadresse')}
                  </button>
                )}
                <button
                  type="button"
                  className="button button-ghost"
                  aria-label={t('{hostname} entfernen', { hostname: d.hostname })}
                  onClick={() => void run(() => websiteApi.removeDomain(org.id, d.id))}
                >
                  {t('Entfernen')}
                </button>
              </span>
            )}
          </li>
        ))}
      </ul>
      {error && <Alert kind="error">{error}</Alert>}
      {data.can_manage && (
        <form
          className="inline-form"
          onSubmit={(e) => {
            e.preventDefault()
            void run(() => websiteApi.addDomain(org.id, host)).then((ok) => ok && setHost(''))
          }}
        >
          <Field
            label={t('Domain hinzufügen')}
            placeholder="www.beispiel-verein.de"
            value={host}
            onChange={(e) => setHost(e.target.value)}
          />
          <button type="submit" className="button" disabled={!host.trim()}>
            {t('Hinzufügen')}
          </button>
        </form>
      )}
    </div>
  )
}

/** Was vor dem Schalten auf „öffentlich“ erledigt sein muss. */
const CHECK_LINKS: Record<string, string> = {
  imprint: '/einstellungen/impressum',
  responsible: '/einstellungen/impressum?feld=verantwortlich',
  privacy: '/einstellungen/datenschutz',
  privacy_outdated: '/einstellungen/datenschutz',
  domain: '/webseite/domain',
}

/** Begriffe mit „?“ an den Punkten der Prüfliste */
const CHECK_TERMS: Partial<Record<string, TermKey>> = {
  imprint: 'imprint',
  responsible: 'responsible',
}

function ChecklistCard({ website }: { website: Website }) {
  const open = website.checks.filter((c) => !c.ok)
  return (
    <div className="card card-wide">
      <h2>{t('Prüfliste vor dem Veröffentlichen')}</h2>
      {open.length === 0 && <Alert kind="success">{t('Alles erledigt.')}</Alert>}
      <ul className="plain-list">
        {website.checks.map((c) => (
          <li key={c.key}>
            <span aria-hidden="true">{c.ok ? '✓' : c.blocking ? '✗' : '!'}</span>{' '}
            <strong>
              {CHECK_TERMS[c.key] ? <Term k={CHECK_TERMS[c.key]!}>{c.label}</Term> : c.label}
            </strong>
            {!c.ok && (
              <>
                {' '}
                <span className="muted small">
                  {c.blocking ? t('(nötig) ') : t('(Empfehlung) ')}
                  {c.hint}
                </span>
                {CHECK_LINKS[c.key] && (
                  <>
                    {' '}
                    <Link to={CHECK_LINKS[c.key]} className="small">
                      {t('Erledigen')}
                    </Link>
                  </>
                )}
              </>
            )}
          </li>
        ))}
      </ul>
      {open.some((c) => c.blocking) && (
        <p className="muted small">
          {t(
            'Solange ein nötiger Punkt offen ist, lässt sich die Webseite nicht auf „Öffentlich“ schalten.',
          )}
        </p>
      )}
    </div>
  )
}

function PreviewCard({
  data,
  website,
  onChange,
}: {
  data: WebsiteData
  website: Website
  onChange: () => void
}) {
  const org = useActiveOrg()
  const [label, setLabel] = useState('')
  const [days, setDays] = useState(7)
  const [created, setCreated] = useState<PreviewLink | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Nach dem Warten blockt mancher Browser das neue Fenster: dann hilft der Link
  const [opened, setOpened] = useState<string | null>(null)

  async function open() {
    setError(null)
    setOpened(null)
    try {
      const result = await websiteApi.openPreview(org.id)
      if (result.url) {
        window.open(result.url, '_blank', 'noopener')
        setOpened(result.url)
      } else setError(t('Für die Vorschau fehlt noch eine Domain.'))
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  async function create() {
    setError(null)
    try {
      setCreated(await websiteApi.addPreviewLink(org.id, label, days))
      setLabel('')
      onChange()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  async function revoke(link: PreviewLink) {
    setError(null)
    try {
      await websiteApi.revokePreviewLink(org.id, link.id)
      onChange()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <div className="card card-wide">
      <h2>{t('Vorschau')}</h2>
      <p className="muted small">
        {t(
          'In der Vorschau siehst du die vollständige Webseite, auch im Wartungsmodus, mit dem Hinweis „Vorschau – nicht öffentlich“.',
        )}
      </p>
      {error && <Alert kind="error">{error}</Alert>}
      <button type="button" className="button" onClick={() => void open()}>
        {t('Vorschau öffnen')}
      </button>
      {opened && (
        <p className="muted small">
          {t('Kein neues Fenster?')}{' '}
          <a href={opened} target="_blank" rel="noopener noreferrer">
            {t('Vorschau hier öffnen')}
          </a>
          .
        </p>
      )}
      {data.can_manage && (
        <>
          <h3>{t('Vorschau-Links zum Weitergeben')}</h3>
          <p className="muted small">
            {t(
              'Zum Beispiel für Vorstandsmitglieder ohne Zugang zu HUBIplan. Jeder Link gilt höchstens 14 Tage und lässt sich jederzeit widerrufen.',
            )}
          </p>
          {created?.url && (
            <Alert kind="success">
              {t('Neuer Link (wird nur jetzt angezeigt):')} <code>{created.url}</code>
            </Alert>
          )}
          {created && !created.url && (
            <Alert kind="info">
              {t('Link angelegt. Für eine Adresse fehlt noch eine Domain; Schlüssel:')}{' '}
              <code>{created.token}</code>
            </Alert>
          )}
          <ul className="plain-list">
            {website.preview_links.map((link) => (
              <li key={link.id}>
                {link.label || t('Vorschau-Link')} {t('· gültig bis')}{' '}
                {formatDateTime(link.expires_at)}
                {!link.is_active ? t(' (abgelaufen)') : ''}{' '}
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() => void revoke(link)}
                >
                  {t('Widerrufen')}
                </button>
              </li>
            ))}
          </ul>
          <div className="grid-2">
            <Field
              label={t('Bezeichnung (z. B. für wen)')}
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />
            <Field
              label={t('Gültig (Tage)')}
              type="number"
              min={1}
              max={14}
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
            />
          </div>
          <button type="button" className="button" onClick={() => void create()}>
            {t('Vorschau-Link erzeugen')}
          </button>
        </>
      )}
    </div>
  )
}

function HeldCard() {
  const org = useActiveOrg()
  const { data, error, reload } = useLoad(() => heldApi.list(org.id), [org.id])
  const [message, setMessage] = useState<string | null>(null)

  async function run(action: () => Promise<unknown>) {
    setMessage(null)
    try {
      await action()
      void reload()
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }

  return (
    <div className="card card-wide">
      <h2>{t('Zurückgehaltene Nachrichten')}</h2>
      <p className="muted small">
        {t(
          'Nachrichten aus dem Kontaktformular, die nach Spam aussehen oder über der Obergrenze je Stunde lagen. Sie werden nach 7 Tagen automatisch gelöscht.',
        )}
      </p>
      {error && <LoadError message={error} onRetry={() => void reload()} />}
      {data && data.length === 0 && <p className="muted">{t('Keine.')}</p>}
      <ul className="plain-list">
        {(data ?? []).map((m) => (
          <li key={m.id}>
            <strong>{m.subject}</strong>{' '}
            {t('· von {sender_name} ({sender_email}) an  {recipient_name} ·', {
              sender_name: m.sender_name,
              sender_email: m.sender_email,
              recipient_name: m.recipient_name,
            })}{' '}
            {formatDateTime(m.created_at)}
            <br />
            <small className="muted">
              {t('Grund:')} {m.reason}
            </small>
            <p className="mail-body">{m.body}</p>
            <div className="button-row">
              <button
                type="button"
                className="button"
                onClick={() => void run(() => heldApi.release(org.id, m.id))}
              >
                {t('Zustellen')}
              </button>
              <button
                type="button"
                className="button button-ghost"
                onClick={() => void run(() => heldApi.discard(org.id, m.id))}
              >
                {t('Verwerfen')}
              </button>
            </div>
          </li>
        ))}
      </ul>
      {message && <Alert kind="error">{message}</Alert>}
    </div>
  )
}
