import { useEffect, useRef, useState } from 'react'
import { gradientCss } from '../../api/orgs.ts'
import { contentApi } from '../../api/website.ts'
import type {
  HomeSection,
  HomeSectionData,
  SectionOptions,
  SectionSite,
} from '../../api/website.ts'
import { useLoad } from '../../components/forms.ts'
import { Modal } from '../../components/Modal.tsx'
import { Field } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { ImageChoice } from './ImageChoice.tsx'
import type { Unit } from './imagesHelpers.ts'
import { Segments } from './Segments.tsx'
import { SectionContent } from './SectionContent.tsx'
import { DaysField } from './DaysField.tsx'

/** Hintergrund aus der Palette: p0 … p9 */
const paletteKey = (i: number) => 'p' + String(i)
const gradientKey = (i: number) => 'g' + String(i)

export function SectionDialog({
  data,
  website,
  section,
  title,
  design,
  contentOnly = false,
  fresh = false,
  onSave,
  onClose,
}: {
  data: SectionOptions
  website: SectionSite
  section: HomeSection
  title: string
  design: string
  contentOnly?: boolean
  /** Gerade gewählter, neuer Abschnitt: Fokus ins erste Feld (UX-Audit WS-17) */
  fresh?: boolean
  onSave: (next: HomeSection) => void
  onClose: () => void
}) {
  const org = useActiveOrg()
  const [s, setS] = useState(section)
  const body = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!fresh) return
    body.current?.querySelector<HTMLElement>('input, textarea, select')?.focus()
  }, [fresh])
  // Wasserzeichen „Bild“ auch, solange noch keins gewählt ist (Webseite #123)
  const [markImage, setMarkImage] = useState(typeof section.mark === 'number')
  const images = useLoad(() => contentApi.images(org.id), [org.id])
  const palette = data.palette ?? []
  const gradients = data.gradients ?? []
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
      <div className="home-section-dialog" ref={body}>
        {s.kind && (
          <SectionContent
            data={data}
            website={website}
            section={s}
            setData={setData}
            imageField={imageField}
          />
        )}
        {s.key === 'results' && !s.kind && (
          <DaysField
            value={s.days}
            hint={t(
              'Ein Wettbewerb verschwindet so viele Tage nach dem Wettbewerbstag. Laufende und vorläufige Wettbewerbe bleiben stehen. Ist nichts mehr aktuell, verschwindet der Abschnitt.',
            )}
            onChange={(days) => setS({ ...s, days })}
          />
        )}
        {s.key === 'carousel' && !s.kind && !contentOnly && (
          <>
            <div className="field">
              <label className="field-label" htmlFor="abschnitt-titelzeilen">
                {t('Titelzeilen auf dem Titelfoto (optional)')}
              </label>
              <textarea
                id="abschnitt-titelzeilen"
                rows={4}
                value={s.title ?? ''}
                aria-describedby="abschnitt-titelzeilen-hinweis"
                onChange={(e) => setS({ ...s, title: e.target.value })}
              />
              <small className="muted" id="abschnitt-titelzeilen-hinweis">
                {t(
                  'Nur bei Feinabstimmung › Titelbild und Startseite › Breite „randlos“ oder „in Inhaltsbreite“. Eine Zeile je Titel, höchstens 6; mehrere wechseln mit den Bildern des Karussells.',
                )}
              </small>
            </div>
            <Field
              label={t('Oberzeile (optional)')}
              hint={t('Kleine Zeile über dem Titel, z. B. „Gegründet 1920“.')}
              value={s.kicker ?? ''}
              maxLength={60}
              onChange={(e) => setS({ ...s, kicker: e.target.value })}
            />
          </>
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
                ...palette.map(
                  (c, i) =>
                    [
                      paletteKey(i),
                      c.name || c.color,
                      { background: c.color, color: c.on_color },
                    ] as const,
                ),
                ...gradients.map(
                  (g, i) =>
                    [
                      gradientKey(i),
                      g.name || t('Verlauf {x}', { x: i + 1 }),
                      {
                        background: gradientCss(g.colors[0], g.colors[1], g.direction),
                        color: g.on_color,
                      },
                    ] as const,
                ),
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
                    style={color}
                    aria-hidden="true"
                  ></span>
                  <span>{text}</span>
                </label>
              ))}
            </div>
          </div>
        )}
        {looks && !!s.bg && !['none'].includes(s.bg) && (
          <>
            <Segments
              label={t('Wasserzeichen')}
              value={s.mark === 'logo' ? 'logo' : markImage ? 'image' : 'none'}
              options={[
                ['none', t('keins')],
                ['logo', t('Wappen')],
                ['image', t('Bild')],
              ]}
              onChange={(v) => {
                setMarkImage(v === 'image')
                setS({
                  ...s,
                  mark:
                    v === 'logo'
                      ? 'logo'
                      : v === 'image' && typeof s.mark === 'number'
                        ? s.mark
                        : null,
                })
              }}
            />
            {markImage &&
              imageField(
                t('Bild für das Wasserzeichen'),
                typeof s.mark === 'number' ? s.mark : null,
                (v) => setS({ ...s, mark: v }),
              )}
            <small className="muted">
              {t(
                'Groß, zart und rechts angeschnitten hinter dem Text, z. B. ein einfarbig weißes Wappentier mit durchsichtigem Hintergrund.',
              )}
            </small>
          </>
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
