// Webseite › Gestaltung › Kopfbild (Ralf 05.11.2026): ein Bild aus der Bilderverwaltung,
// das die Webseite im Kopf statt Wappen und Vereinsname zeigt, z. B. ein Banner mit
// Schriftzug wie bei der bisherigen Webseite eines Vereins.
import { contentApi } from '../../api/website.ts'
import { useLoad } from '../../components/forms.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { ImageChoice } from './images.tsx'
import type { Unit } from './images.tsx'

export function HeaderImage({
  value,
  units,
  onChange,
}: {
  value: number | null
  units: Unit[]
  onChange: (id: number | null) => void
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
    </>
  )
}
