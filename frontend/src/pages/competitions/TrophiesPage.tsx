import { useState } from 'react'
import type { FormEvent } from 'react'
import { historyApi, type Trophy } from '../../api/competitionHistory.ts'
import { PERM } from '../../api/orgs.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert, Checkbox, Field, LoadError } from '../../components/ui.tsx'
import { t, tn } from '../../i18n/index.ts'
import { PageHeader } from '../../components/PageHeader.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { ManualGrant } from './ManualGrant.tsx'

export function TrophiesPage() {
  const org = useActiveOrg()
  const canManage = org.permissions.includes(PERM.competitionsManage)
  const { data, error, reload } = useLoad(() => historyApi.trophies.list(org.id), [org.id])
  const [name, setName] = useState('')
  const [message, setMessage] = useState<string | null>(null)

  async function add(e: FormEvent) {
    e.preventDefault()
    try {
      await historyApi.trophies.create(org.id, { name })
      setName('')
      reload()
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }

  async function update(tr: Trophy, changes: Partial<Trophy>) {
    try {
      await historyApi.trophies.update(org.id, tr.id, changes)
      reload()
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }

  async function remove(tr: Trophy) {
    const ok = await confirmDialog({
      final: true,
      title: t('Wanderpokal löschen'),
      message: t('„{name}“ löschen? Die Inhaber bleiben als Titel erhalten.', { name: tr.name }),
      confirmLabel: t('Löschen'),
    })
    if (!ok) return
    await historyApi.trophies.remove(org.id, tr.id)
    reload()
  }

  return (
    <section>
      <PageHeader name={t('Wanderpokale')} />
      <p className="muted">
        {t(
          'Ein Wanderpokal wechselt seine Inhaber. Ihr verknüpft ihn beim Wettbewerb unter „Einrichten“ › Auszeichnungen mit einem Platz; frühere Inhaber tragt ihr hier nach.',
        )}
      </p>
      {error && <LoadError message={error} onRetry={reload} />}
      {message && <Alert kind="error">{message}</Alert>}
      {data?.map((tr) => (
        <div key={tr.id} className="card card-wide">
          <div className="card-head">
            <h2>{tr.name}</h2>
            {canManage && (
              <button
                type="button"
                className="button button-ghost push-right"
                onClick={() => void remove(tr)}
              >
                {t('Löschen')}
              </button>
            )}
          </div>
          {canManage && (
            <div className="grid-3">
              <Field
                label={t('In den Besitz nach Siegen in Folge')}
                type="number"
                min={1}
                max={20}
                defaultValue={tr.keep_after ?? ''}
                hint={t('leer: bleibt immer ein Wanderpokal')}
                onBlur={(e) => {
                  const n = e.target.value ? Number(e.target.value) : null
                  if (n !== tr.keep_after) void update(tr, { keep_after: n })
                }}
              />
              <Checkbox
                label={t('Inhaber auf der Webseite')}
                checked={tr.on_website}
                onChange={(on) => void update(tr, { on_website: on })}
              />
              <Checkbox
                label={t('nicht mehr vergeben')}
                checked={tr.is_archived}
                onChange={(on) => void update(tr, { is_archived: on })}
              />
            </div>
          )}
          {tr.holders.length === 0 ? (
            <p className="muted">{t('Noch keine Inhaber.')}</p>
          ) : (
            <ul className="plain-list">
              {tr.holders.map((h) => (
                <li key={h.id}>
                  {h.year}: <strong>{h.name}</strong>
                  {h.streak > 1 &&
                    t(' · {x}', { x: tn('{n}. Sieg in Folge', '{n}. Sieg in Folge', h.streak) })}
                  {h.kept && t(' · {x}', { x: t('in den Besitz übergegangen') })}
                </li>
              ))}
            </ul>
          )}
          {canManage && (
            <ManualGrant
              org={org.id}
              defaults={{ trophy: tr.id }}
              onSaved={reload}
              label={t('Früheren Inhaber nachtragen')}
            />
          )}
        </div>
      ))}
      {canManage && (
        <form onSubmit={add} className="card">
          <Field
            label={t('Neuer Wanderpokal')}
            placeholder={t('z. B. Zugpokal')}
            value={name}
            required
            onChange={(e) => setName(e.target.value)}
          />
          <div className="button-row">
            <button type="submit" className="button">
              {t('Anlegen')}
            </button>
          </div>
        </form>
      )}
    </section>
  )
}
