import type { HomeTarget, SectionOptions, SectionSite } from '../../api/website.ts'
import { Field, SelectField } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

/** Ziel eines Knopfs oder einer Kachel: Seite der Webseite, Untereinheit, Termin oder Link */
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
  const units = data.home_choices?.units ?? []
  const current =
    value && 'page' in value
      ? `page:${value.page}`
      : value && 'unit' in value
        ? `unit:${value.unit}`
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
          else if (v.startsWith('unit:')) onChange({ unit: Number(v.slice(5)) })
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
        {units.length > 0 && (
          <optgroup label={t('Untereinheit')}>
            {units.map((u) => (
              <option key={u.id} value={`unit:${u.id}`}>
                {u.name}
              </option>
            ))}
          </optgroup>
        )}
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
