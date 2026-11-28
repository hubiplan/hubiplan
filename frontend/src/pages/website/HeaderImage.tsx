// Webseite › Gestaltung › Kopfbild (Ralf 05.11.2026): ein Bild aus der Bilderverwaltung,
// das die Webseite im Kopf statt Wappen und Vereinsname zeigt, z. B. ein Banner mit
// Schriftzug wie bei der bisherigen Webseite eines Vereins. Dazu optional eine kompaktere
// Fassung für schmale Bildschirme unter 600 px (Webseite #73). Seit #480 auch mehrere Bilder:
// die Webseite zeigt dann bei jedem Aufruf eines davon.
import { contentApi } from '../../api/website.ts'
import type { HeaderImageValue, WebsiteImage } from '../../api/website.ts'
import { useLoad } from '../../components/forms.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { ImageChoice } from './ImageChoice.tsx'
import type { Unit } from './imagesHelpers.ts'

/** Höchstens so viele Kopfbilder (wie im Server, website/models.py) */
export const MAX_HEADER_IMAGES = 10

/** Kopfbilder als Liste: aus null, einer Nummer oder einer Liste */
export function headerIds(value: HeaderImageValue | undefined): number[] {
  if (value === null || value === undefined) return []
  return Array.isArray(value) ? value : [value]
}

/** Kurzform wie im Server: null, eine Nummer oder ab zwei Bildern eine Liste (sortiert) */
export function headerValue(ids: number[]): HeaderImageValue {
  const unique = [...new Set(ids)].sort((a, b) => a - b)
  if (unique.length === 0) return null
  return unique.length === 1 ? unique[0] : unique
}

function HeaderImageList({
  label,
  more,
  value,
  images,
  units,
  onChange,
  onImagesChanged,
}: {
  label: string
  more: string
  value: HeaderImageValue
  images: WebsiteImage[]
  units: Unit[]
  onChange: (value: HeaderImageValue) => void
  onImagesChanged: () => void
}) {
  const ids = headerIds(value)
  return (
    <>
      {ids.map((id, i) => (
        <ImageChoice
          key={id}
          label={ids.length > 1 ? `${label} ${i + 1}` : label}
          value={id}
          images={images}
          units={units}
          onChange={(next) =>
            onChange(
              headerValue(
                next === null ? ids.filter((x) => x !== id) : ids.map((x) => (x === id ? next : x)),
              ),
            )
          }
          onImagesChanged={onImagesChanged}
        />
      ))}
      {ids.length < MAX_HEADER_IMAGES && (
        <ImageChoice
          key={`neu-${ids.length}`}
          label={ids.length === 0 ? label : more}
          value={null}
          images={images}
          units={units}
          onChange={(next) => {
            if (next !== null) onChange(headerValue([...ids, next]))
          }}
          onImagesChanged={onImagesChanged}
        />
      )}
    </>
  )
}

export function HeaderImage({
  value,
  narrow,
  units,
  onChange,
  onNarrowChange,
}: {
  value: HeaderImageValue
  narrow: HeaderImageValue
  units: Unit[]
  onChange: (value: HeaderImageValue) => void
  onNarrowChange: (value: HeaderImageValue) => void
}) {
  const org = useActiveOrg()
  const images = useLoad(() => contentApi.images(org.id), [org.id])
  const reload = () => void images.reload()
  return (
    <>
      <p className="muted small">
        {t(
          'Ohne Kopfbild zeigt die Webseite oben Wappen und Vereinsnamen. Mit Kopfbild steht dort nur das Bild, z. B. ein Banner mit Schriftzug. Es sollte den Vereinsnamen enthalten und breit sein, etwa 1200 × 300 Pixel.',
        )}
      </p>
      <p className="muted small">
        {t(
          'Mit mehreren Kopfbildern zeigt die Webseite bei jedem Aufruf ein anderes davon, auf allen Seiten.',
        )}
      </p>
      <HeaderImageList
        label={t('Kopfbild')}
        more={t('Weiteres Kopfbild')}
        value={value}
        images={images.data ?? []}
        units={units}
        onChange={onChange}
        onImagesChanged={reload}
      />
      {(value !== null || narrow !== null) && (
        <>
          <p className="muted small">
            {t(
              'Auf dem Handy wird ein breites Kopfbild neben dem Menüknopf sehr klein. Optional zeigt die Webseite auf schmalen Bildschirmen (unter 600 Pixel Breite) stattdessen eine kompaktere Fassung, z. B. mit dem Schriftzug über zwei Zeilen. Ohne dieses Bild steht dort das Kopfbild.',
            )}
          </p>
          <HeaderImageList
            label={t('Kopfbild für Handys')}
            more={t('Weiteres Kopfbild für Handys')}
            value={narrow}
            images={images.data ?? []}
            units={units}
            onChange={onNarrowChange}
            onImagesChanged={reload}
          />
        </>
      )}
    </>
  )
}
