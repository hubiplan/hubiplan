import { orgApi, PERM, type OrgDetail } from '../../api/orgs.ts'
import { competitionsApi } from '../../api/competitions.ts'
import { useAutoSave, useForm } from '../../components/forms.ts'
import { Checkbox, SaveStatus } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

export function ShootingFacilitiesCard({
  detail,
  onSaved,
}: {
  detail: OrgDetail
  onSaved: (d: OrgDetail) => void
}) {
  const org = useActiveOrg()
  const editable = org.permissions.includes(PERM.orgEdit)
  const form = useForm({ shooting_facilities: detail.shooting_facilities ?? null })
  const selected = form.values.shooting_facilities
  const auto = useAutoSave(form, (changes) => orgApi.update(org.id, changes), {
    enabled: editable,
    onSaved: (result) => {
      competitionsApi.clearTargetCache(org.id)
      onSaved(result as OrgDetail)
    },
  })
  const facilities = [
    ['lg10', t('Luftgewehr'), 10],
    ['lp10', t('Luftpistole'), 10],
    ['kk50', t('Kleinkaliber'), 50],
    ['kk100', t('Kleinkaliber'), 100],
    ['p25', t('Pistole'), 25],
    ['p50', t('Pistole'), 50],
  ] as const
  const labels: [string, string][] = [
    ...facilities.map(([key, label, distance]): [string, string] => [
      key,
      `${label} · ${distance} m`,
    ]),
    ['vogel', t('Vogelschießen · Hochstand')],
  ]
  return (
    <section className="card card-wide">
      <div className="card-head">
        <h2>{t('Schießinfrastruktur')}</h2>
        {editable && <SaveStatus auto={auto} />}
      </div>
      <p className="muted">
        {t(
          'Welche Schießmöglichkeiten stehen dem Verein zur Verfügung? Die Scheibenwahl in Wettbewerben zeigt zuerst passende Scheiben.',
        )}
      </p>
      <fieldset disabled={!editable}>
        <Checkbox
          label={t('Verfügbare Schießmöglichkeiten festlegen')}
          checked={selected !== null}
          onChange={(on) => form.set('shooting_facilities', on ? [] : null)}
          hint={t('Ohne Festlegung wird der vollständige Scheibenkatalog angeboten.')}
        />
        {selected !== null && (
          <>
            <div className="grid-2">
              {labels.map(([key, label]) => (
                <Checkbox
                  key={key}
                  label={label}
                  checked={selected.includes(key)}
                  onChange={(on) =>
                    form.set(
                      'shooting_facilities',
                      on ? [...selected, key] : selected.filter((v) => v !== key),
                    )
                  }
                />
              ))}
            </div>
            {selected.length === 0 && (
              <p className="muted small">
                {t(
                  'Keine eigene Schießinfrastruktur ausgewählt. Für Wettbewerbe auf fremden Anlagen lässt sich der vollständige Katalog einblenden.',
                )}
              </p>
            )}
          </>
        )}
      </fieldset>
    </section>
  )
}
