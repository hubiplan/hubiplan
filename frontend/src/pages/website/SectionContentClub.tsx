// Abschnitt bearbeiten: Inhalte, die HUBIplan selbst liefert.
import { formatDate, formatDateTime } from '../../components/forms.ts'
import { Checkbox, Field, SelectField } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { Segments } from './Segments.tsx'
import { DaysField } from './DaysField.tsx'

import type { SectionContentProps } from './sectionContentShared.tsx'

export function SectionContentClub({ data, section, setData }: SectionContentProps) {
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
    case 'chronicle':
      return (
        <>
          <p className="muted small">
            {t(
              'Zeigt die neuesten Einträge der Zeitleiste von Vereinsleben › Chronik mit einem Link zur ganzen Chronik.',
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
    case 'unit_honors':
      return (
        <>
          <SelectField
            label={t('Untereinheit')}
            value={d.unit ?? ''}
            hint={t('Nur Untereinheiten, die auf der Webseite stehen.')}
            onChange={(e) => setData({ unit: e.target.value ? Number(e.target.value) : null })}
          >
            <option value="">{t('Bitte wählen')}</option>
            {(choices?.units ?? []).map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </SelectField>
          {titleField()}
        </>
      )
    case 'competition':
      return (
        <>
          <SelectField
            label={t('Wettbewerb')}
            value={d.competition ?? ''}
            hint={t('Erscheint, sobald der Wettbewerb auf der Webseite veröffentlicht ist.')}
            onChange={(e) =>
              setData({ competition: e.target.value ? Number(e.target.value) : null })
            }
          >
            <option value="">{t('Bitte wählen')}</option>
            {(choices?.competitions ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.title} ({formatDate(c.date)})
              </option>
            ))}
          </SelectField>
          {titleField()}
          <DaysField
            value={d.days}
            hint={t(
              'Der Abschnitt verschwindet so viele Tage nach dem Wettbewerbstag. Solange der Wettbewerb läuft oder vorläufig ist, bleibt er stehen.',
            )}
            onChange={(days) => setData({ days })}
          />
        </>
      )
    case 'albums':
      return (
        <>
          {titleField()}
          <SelectField
            label={t('Anzahl Alben')}
            value={d.count ?? 4}
            onChange={(e) => setData({ count: Number(e.target.value) })}
          >
            {[2, 3, 4, 5, 6, 7, 8].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </SelectField>
          <DaysField
            value={d.days}
            hint={t(
              'Nur Alben, deren Datum höchstens so viele Tage zurückliegt; Alben ohne Datum fallen dann weg. Ist keins mehr aktuell, verschwindet der Abschnitt.',
            )}
            onChange={(days) => setData({ days })}
          />
        </>
      )
    case 'posts':
      return (
        <>
          {titleField()}
          <Segments
            label={t('Kanal')}
            value={
              d.channel === 'own' || d.channel === 'instagram' || d.channel === 'facebook'
                ? d.channel
                : 'all'
            }
            options={[
              ['all', t('Alle')],
              ['own', t('Eigene')],
              ['instagram', 'Instagram'],
              ['facebook', 'Facebook'],
            ]}
            onChange={(channel) => setData({ channel })}
          />
          <SelectField
            label={t('Anzahl Beiträge')}
            value={d.count ?? 3}
            onChange={(e) => setData({ count: Number(e.target.value) })}
          >
            {[1, 2, 3, 4, 5, 6].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </SelectField>
          <DaysField
            value={d.days}
            hint={t(
              'Nur Beiträge, die höchstens so viele Tage alt sind. Ist keiner mehr aktuell, verschwindet der Abschnitt.',
            )}
            onChange={(days) => setData({ days })}
          />
        </>
      )
    case 'live_facts': {
      const labels: [string, string][] = [
        ['members', t('Mitglieder')],
        ['years', t('Jahre Vereinsgeschichte')],
        ['units', t('Untereinheiten')],
      ]
      const items = d.items ?? []
      return (
        <>
          {titleField()}
          <p className="muted small">
            {t('Die Zahlen kommen immer aktuell aus HUBIplan, nur als Summe.')}
          </p>
          {labels.map(([fact, name]) => {
            const item = items.find((i) => i.fact === fact)
            return (
              <div key={fact}>
                <Checkbox
                  label={name}
                  checked={!!item}
                  onChange={(on) =>
                    setData({
                      items: on
                        ? [...items, { fact, label: '' }]
                        : items.filter((i) => i.fact !== fact),
                    })
                  }
                />
                {item && (
                  <Field
                    label={t('Text (optional)')}
                    value={item.label ?? ''}
                    maxLength={60}
                    placeholder={name}
                    onChange={(e) =>
                      setData({
                        items: items.map((i) =>
                          i.fact === fact ? { ...i, label: e.target.value } : i,
                        ),
                      })
                    }
                  />
                )}
              </div>
            )
          })}
        </>
      )
    }
    default:
      return null
  }
}
