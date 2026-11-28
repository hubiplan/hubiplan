import { useCallback, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../../api/client.ts'
import { helperApi } from '../../api/helpers.ts'
import type { PickedMember } from '../../api/members.ts'
import { MemberPicker } from '../../components/MemberPicker.tsx'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage } from '../../components/forms.ts'
import { t } from '../../i18n/index.ts'
import './helpers.css'

export function AssignForm({
  base,
  orgId,
  label,
  assign,
  membersOnly = false,
  onDone,
}: {
  base: string
  orgId: number
  label: string
  assign: (data: object) => Promise<unknown>
  membersOnly?: boolean
  onDone: (changed: boolean) => Promise<void>
}) {
  const [external, setExternal] = useState(false)
  const [member, setMember] = useState<PickedMember | null>(null)
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const search = useCallback((term: string) => helperApi.members(base, term), [base])
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const data = external ? { name, phone } : { membership: member?.id }
    setBusy(true)
    setError('')
    try {
      try {
        await assign(data)
      } catch (err) {
        const body = err instanceof ApiError ? (err.body as { warnings?: string[] }) : null
        if (!body?.warnings?.length) throw err
        const yes = await confirmDialog({
          title: t('Trotzdem einteilen?'),
          message: errorMessage(err),
          confirmLabel: t('Trotzdem einteilen'),
          danger: false,
        })
        if (!yes) return
        await assign({ ...data, force: true })
      }
      await onDone(true)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <form
      className="assign-form stack"
      aria-label={t('Einteilen: {shift}', { shift: label })}
      onSubmit={submit}
    >
      {!membersOnly && (
        <div className="segmented" role="group" aria-label={t('Wer?')}>
          <button
            type="button"
            className={`button button-ghost${!external ? ' is-active' : ''}`}
            aria-pressed={!external}
            onClick={() => setExternal(false)}
          >
            {t('Mitglied')}
          </button>
          <button
            type="button"
            className={`button button-ghost${external ? ' is-active' : ''}`}
            aria-pressed={external}
            onClick={() => setExternal(true)}
          >
            {t('Externe Person')}
          </button>
        </div>
      )}
      {external ? (
        <>
          <label className="field">
            <span>{t('Name')}</span>
            <input
              value={name}
              maxLength={200}
              required
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="field">
            <span>{t('Telefon')}</span>
            <input
              type="tel"
              value={phone}
              maxLength={50}
              onChange={(e) => setPhone(e.target.value)}
            />
          </label>
        </>
      ) : (
        <MemberPicker
          orgId={orgId}
          value={member}
          onChange={setMember}
          label={t('Mitglied')}
          search={search}
        />
      )}
      {error && <p role="alert">{error}</p>}
      <div className="button-row">
        <button type="button" className="button button-ghost" onClick={() => onDone(false)}>
          {t('Abbrechen')}
        </button>
        <button
          className="button button-primary"
          disabled={busy || (external ? !name.trim() : !member)}
        >
          {t('Einteilen')}
        </button>
      </div>
    </form>
  )
}
