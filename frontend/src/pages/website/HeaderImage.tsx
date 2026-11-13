// Webseite › Gestaltung › Kopfbild (Ralf 05.11.2026): ein Bild aus der Bilderverwaltung,
// das die Webseite im Kopf statt Wappen und Vereinsname zeigt, z. B. ein Banner mit
// Schriftzug wie bei der bisherigen Webseite eines Vereins. Dazu optional eine kompaktere
// Fassung für schmale Bildschirme unter 600 px (Webseite #73).
import { contentApi } from '../../api/website.ts'
import { useLoad } from '../../components/forms.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { ImageChoice } from './images.tsx'
import type { Unit } from './images.tsx'

export function HeaderImage({
  value,
  narrow,
  units,
  onChange,
  onNarrowChange,
}: {
  value: number | null
  narrow: number | null
  units: Unit[]
  onChange: (id: number | null) => void
  onNarrowChange: (id: number | null) => void
}) {
  const org = useActiveOrg()
  const images = useLoad(() => contentApi.images(org.id), [org.id])
  return (
    <>
      <p className="muted small">
        {t(
          'Ohne Kopfbild zeigt die Webseite oben Wappen und Vereinsnamen. Mit Kopfbild steht dort nur das Bild, z. B. ein Banner mit Schriftzug. Es sollte den Vereinsnamen enthalten und breit sein, etwa 1200 × 300 Pixel.',
        )}
      </p>
      <ImageChoice
        label={t('Kopfbild')}
        value={value}
        images={images.data ?? []}
        units={units}
        onChange={onChange}
        onImagesChanged={() => void images.reload()}
      />
      {(value !== null || narrow !== null) && (
        <>
          <p className="muted small">
            {t(
              'Auf dem Handy wird ein breites Kopfbild neben dem Menüknopf sehr klein. Optional zeigt die Webseite auf schmalen Bildschirmen (unter 600 Pixel Breite) stattdessen eine kompaktere Fassung, z. B. mit dem Schriftzug über zwei Zeilen. Ohne dieses Bild steht dort das Kopfbild.',
            )}
          </p>
          <ImageChoice
            label={t('Kopfbild für Handys')}
            value={narrow}
            images={images.data ?? []}
            units={units}
            onChange={onNarrowChange}
            onImagesChanged={() => void images.reload()}
          />
        </>
      )}
    </>
  )
}
