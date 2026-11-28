import { useState } from 'react'
import type { ReactNode } from 'react'
import { Navigate, Route, Routes, useParams } from 'react-router-dom'
import { SubpageUnavailable } from '../NoticePages.tsx'
import { websiteApi } from '../../api/website.ts'
import type { HomeSection, Website, WebsiteData } from '../../api/website.ts'
import { errorMessage } from '../../components/forms.ts'
import { Alert, Field } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { ContentPage } from './ContentPage.tsx'
import { ImagesPage } from './ImagesPage.tsx'
import { DesignChooser } from './DesignChooser.tsx'
import { HeaderImage } from './HeaderImage.tsx'
import { StyleTuning } from './StyleTuning.tsx'
import { tuningAreaNames } from './styleTuningHelpers.ts'
import { DesignVersions, DraftBar, PreviewFrame, TextVersions } from './DesignPreview.tsx'
import { UndoBar } from './designHistory.tsx'
import { DesignFile } from './DesignFile.tsx'
import { HomeBuilder } from './HomeBuilder.tsx'
import { t, tc } from '../../i18n/index.ts'
import { GalleryPage } from './GalleryPage.tsx'
import { DocumentsPage } from './DocumentsPage.tsx'
import { SocialPage } from './SocialPage.tsx'
import { NewsPage } from './NewsPage.tsx'
import { HeldCard } from './HeldCard.tsx'
import { DomainsCard } from './DomainsCard.tsx'
import { useWebsiteAdmin, type WebsiteAdminProps } from './useWebsiteAdmin.tsx'
import { WebsiteStructure } from './WebsiteStructure.tsx'
import { WebsiteOverview } from './WebsiteOverview.tsx'

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
      <h2 id="startseite-inhalte">{tc('Webseite', 'Startseite')}</h2>
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

/** Bereich der Feinabstimmung aus der Adresse */
function WithArea({ render }: { render: (area?: string) => ReactNode }) {
  const { bereich } = useParams()
  return <>{render(bereich)}</>
}

export function WebsiteAdmin(props: WebsiteAdminProps) {
  const { data, website, onReset, reload } = props
  const admin = useWebsiteAdmin(props)
  const { v, set, errors, auto, focus, setFocus, navigate, history, settings } = admin
  const model = { ...props, ...admin }
  const overview = <WebsiteOverview m={model} />

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

  /** Gestaltung (S1, Ralf 14.11.): Entwurfsleiste oben, Einstellungen links, Vorschau rechts.
   * ``undo``: Rückgängig/Wiederholen zeigen; ``tuning``: breitere Einstellungen mit Bereichsleiste
   * und „Zeigen“ in der Vorschau (Feinabstimmung, Ralf 16.11.2026). */
  const shell = (
    children: React.ReactNode,
    preview = true,
    options: { undo?: boolean; tuning?: boolean } = {},
  ) => (
    <div className={`design-split${options.tuning ? ' design-split-tuning' : ''}`}>
      <div className="design-split-grid">
        <div className="design-split-settings">
          {draftBar}
          {options.undo && data.can_manage && <UndoBar history={history} />}
          {children}
        </div>
        {preview && website.draft !== undefined && (
          <aside className="design-split-preview" aria-label={t('Vorschau')}>
            <PreviewFrame
              website={website}
              focus={focus}
              pickNames={options.tuning ? tuningAreaNames() : undefined}
              onPick={
                options.tuning
                  ? (area) => void navigate(`/webseite/feinabstimmung/${area}`)
                  : undefined
              }
            />
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
            history.track('design', key)
          }}
          onColorRoles={(next) => {
            setFocus({})
            history.track('color_roles', next)
          }}
          onPackagesChanged={reload}
        />,
      )
    ) : (
      <Alert kind="info">{t('Auf diesem Server gibt es keine Designs zur Auswahl.')}</Alert>
    ),
    true,
    { undo: true },
  )

  // Feinabstimmung mit Bereich aus der Adresse; die Darstellung der Bereiche steht mit darin (F2)
  const tuning = (area?: string) =>
    shell(
      data.style_catalog
        ? settings(
            t('Feinabstimmung'),
            <StyleTuning
              catalog={data.style_catalog}
              design={v.design ?? 'classic'}
              designLabel={designLabel}
              value={v.style ?? {}}
              onChange={(next) => history.track('style', next)}
              headerImage={headerImage}
              homeSections={v.home_sections}
              blocks={v.blocks}
              onFocus={setFocus}
              area={area}
              layoutCatalog={data.layout_catalog}
              layouts={v.layouts ?? {}}
              onLayouts={(next) => history.track('layouts', next)}
              onUndo={data.can_manage ? history.undo : undefined}
            />,
          )
        : settings(t('Kopfbild'), headerImage),
      true,
      { undo: true, tuning: true },
    )

  // S3: Frühere Fassungen und Gestaltung als Datei betreffen alles Gestaltete
  const versions = shell(
    <>
      {settings(
        t('Frühere Fassungen der Gestaltung'),
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
      {settings(t('Texte und Textseiten'), <TextVersions website={website} />)}
      <p className="muted small">
        {t(
          'Keine Fassungen haben Einstellungen, Bilder, Designpakete und die Farben und das Logo der Einheit: Sie wirken sofort. Was geändert wurde, steht im Protokoll.',
        )}
      </p>
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
            tc('Webseite', 'Startseite'),
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

  const structure = <WebsiteStructure m={model} />

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
          path="aktuelles"
          element={
            data.can_edit_content ? (
              <NewsPage />
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
        <Route path="feinabstimmung/:bereich?" element={<WithArea render={tuning} />} />
        <Route
          path="bereiche"
          element={<Navigate to="/webseite/feinabstimmung/bereiche" replace />}
        />
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
