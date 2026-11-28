import { useState } from 'react'
import type { FormEvent } from 'react'
import { historyApi, type Award } from '../../api/competitionHistory.ts'
import type { CompetitionDetail } from '../../api/competitions.ts'
import { honorsApi } from '../../api/honors.ts'
import { PERM } from '../../api/orgs.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert, Field, LoadError, SelectField } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'

function places(a: { place_from: number; place_to: number }): string {
  return a.place_from === a.place_to
    ? t('Platz {n}', { n: a.place_from })
    : t('Platz {a} bis {b}', { a: a.place_from, b: a.place_to })
}

function awardText(a: Award): string {
  return [
    a.title,
    a.item,
    a.dignity_name && t('Würde: {name}', { name: a.dignity_name }),
    a.trophy_name && t('Wanderpokal: {name}', { name: a.trophy_name }),
  ]
    .filter(Boolean)
    .join(' · ')
}

/** Einrichten: Auszeichnungen je Wertung (Plätze) oder je Pfand. */
export function AwardsCard({ org, comp }: { org: number; comp: CompetitionDetail }) {
  const active = useActiveOrg()
  const { data, error, reload } = useLoad(
    () => historyApi.awards.list(org, comp.id),
    [org, comp.id],
  )
  const extras = useLoad(
    () => Promise.all([honorsApi.dignities(org).catch(() => []), historyApi.trophies.list(org)]),
    [org],
  )
  const bird = comp.form === 'vogel'
  const targets = bird
    ? comp.prizes.map((p) => ({ value: `p${p.id}`, label: p.name }))
    : comp.scorings.map((s) => ({ value: `s${s.id}`, label: s.name }))
  const empty = {
    target: targets[0]?.value ?? '',
    place_from: '1',
    place_to: '1',
    title: '',
    item: '',
    dignity: '',
    trophy: '',
  }
  const [v, setV] = useState(empty)
  const [message, setMessage] = useState<string | null>(null)
  const canManage = comp.can_manage
  const canHonors = active.permissions.includes(PERM.membersView)

  async function add(e: FormEvent) {
    e.preventDefault()
    setMessage(null)
    try {
      await historyApi.awards.create(org, comp.id, {
        scoring: v.target.startsWith('s') ? Number(v.target.slice(1)) : null,
        prize: v.target.startsWith('p') ? Number(v.target.slice(1)) : null,
        place_from: Number(v.place_from) || 1,
        place_to: Number(v.place_to) || Number(v.place_from) || 1,
        title: v.title,
        item: v.item,
        dignity: v.dignity ? Number(v.dignity) : null,
        trophy: v.trophy ? Number(v.trophy) : null,
      })
      setV({ ...empty, target: v.target })
      reload()
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }

  async function remove(a: Award) {
    try {
      await historyApi.awards.remove(org, comp.id, a.id)
      reload()
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }

  const name = (a: Award) =>
    a.prize
      ? comp.prizes.find((p) => p.id === a.prize)?.name
      : comp.scorings.find((s) => s.id === a.scoring)?.name
  const [dignities, trophies] = extras.data ?? [[], []]

  return (
    <div className="card card-wide">
      <h2>{t('Auszeichnungen')}</h2>
      <p className="muted">
        {bird
          ? t('Was es für ein Pfand gibt, z. B. Titel „Schützenkönig“ mit der Würde König.')
          : t(
              'Was es für welche Plätze gibt: Titel (z. B. „Vereinsmeister“, das Jahr kommt dazu), Preis, Würde oder Wanderpokal.',
            )}{' '}
        {t(
          'Vergeben wird, sobald der Wettbewerb endgültig ist; eine Würde erst, wenn ihr den Vorschlag bestätigt.',
        )}
      </p>
      {error && <LoadError message={error} onRetry={reload} />}
      {data && data.length > 0 && (
        <ul className="plain-list">
          {data.map((a) => (
            <li key={a.id}>
              <strong>{name(a)}</strong>
              {!a.prize && t(' · {x}', { x: places(a) })}: {awardText(a)}
              {canManage && (
                <button
                  type="button"
                  className="button button-ghost button-small"
                  onClick={() => void remove(a)}
                >
                  {t('Entfernen')}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {data && data.length === 0 && <p className="muted">{t('Noch keine Auszeichnungen.')}</p>}
      {canManage && targets.length > 0 && (
        <form onSubmit={add}>
          <div className="grid-3">
            <SelectField
              label={bird ? t('Pfand') : t('Wertung')}
              value={v.target}
              onChange={(e) => setV({ ...v, target: e.target.value })}
            >
              {targets.map((x) => (
                <option key={x.value} value={x.value}>
                  {x.label}
                </option>
              ))}
            </SelectField>
            {!bird && (
              <>
                <Field
                  label={t('ab Platz')}
                  type="number"
                  min={1}
                  value={v.place_from}
                  onChange={(e) => setV({ ...v, place_from: e.target.value })}
                />
                <Field
                  label={t('bis Platz')}
                  type="number"
                  min={1}
                  value={v.place_to}
                  onChange={(e) => setV({ ...v, place_to: e.target.value })}
                />
              </>
            )}
            <Field
              label={t('Titel')}
              placeholder={t('z. B. Vereinsmeister')}
              value={v.title}
              onChange={(e) => setV({ ...v, title: e.target.value })}
            />
            <Field
              label={t('Preis')}
              placeholder={t('z. B. Pokal, Medaille')}
              value={v.item}
              onChange={(e) => setV({ ...v, item: e.target.value })}
            />
            {canHonors && (
              <SelectField
                label={t('Würde vorschlagen')}
                value={v.dignity}
                onChange={(e) => setV({ ...v, dignity: e.target.value })}
              >
                <option value="">{t('keine')}</option>
                {dignities
                  .filter((d) => !d.is_archived)
                  .map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.unit_name
                        ? t('{name} ({unit_name})', { name: d.name, unit_name: d.unit_name })
                        : d.name}
                    </option>
                  ))}
              </SelectField>
            )}
            <SelectField
              label={t('Wanderpokal')}
              term="challenge_cup"
              value={v.trophy}
              hint={t('Wanderpokale legt ihr unter Wettbewerbe › Wanderpokale an')}
              onChange={(e) => setV({ ...v, trophy: e.target.value })}
            >
              <option value="">{t('keiner')}</option>
              {trophies
                .filter((x) => !x.is_archived)
                .map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.name}
                  </option>
                ))}
            </SelectField>
          </div>
          {message && <Alert kind="error">{message}</Alert>}
          <div className="button-row">
            <button type="submit" className="button">
              {t('Auszeichnung hinzufügen')}
            </button>
          </div>
        </form>
      )}
    </div>
  )
}
