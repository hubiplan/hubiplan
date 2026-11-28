// Abschnitt bearbeiten (Startseite und Textseiten): gemeinsame Angaben der Formularteile.
import { useState } from 'react'
import type { ReactNode } from 'react'
import { partnerApi } from '../../api/partners.ts'
import type {
  HomeItem,
  HomeSection,
  HomeSectionData,
  SectionOptions,
  SectionSite,
} from '../../api/website.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { Why } from '../../learning/Aids.tsx'

export type SectionContentProps = {
  data: SectionOptions
  website: SectionSite
  section: HomeSection
  setData: (patch: Partial<HomeSectionData>) => void
  imageField: (
    label: string,
    id: number | null | undefined,
    set: (v: number | null) => void,
  ) => ReactNode
}

/** Liste gleichartiger Einträge (Fragen, Partner, Zahlen) mit Hinzufügen und Entfernen */
// Geschäftspartner mit Einwilligung übernehmen (konzepte/geschaeftspartner.md, P4)
export function PartnerImport({
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
        <Why k="partner_logos" />
      </div>
      {note && <p className="muted small">{note}</p>}
    </div>
  )
}

export function ItemList({
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
