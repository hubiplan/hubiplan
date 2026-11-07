// Einstellungen › Module: freigegebene Module ein- und ausschalten (konzepte/module-neustruktur.md, M3)
import { useState } from 'react'
import { moduleApi } from '../../api/modules.ts'
import type { OrgModule, OrgModules } from '../../api/modules.ts'
import { PERM } from '../../api/orgs.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { Alert, Checkbox, LoadError } from '../../components/ui.tsx'
import { useActiveOrg, useOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

export function ModulesPage() {
  const org = useActiveOrg()
  const { refresh } = useOrg()
  const canEdit = org.permissions.includes(PERM.settingsEdit)
  const load = useLoad(() => moduleApi.ofOrg(org.id), [org.id])
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ kind: 'error' | 'success'; text: string } | null>(null)

  if (org.type !== 'club' && org.type !== 'federation')
    return <Alert kind="error">{t('Dafür fehlt dir die Berechtigung.')}</Alert>
  if (load.error) return <LoadError message={load.error} onRetry={load.reload} />
  if (!load.data) return <p className="muted">{t('Lädt …')}</p>
  const all = load.data.groups.flatMap((g) => g.modules)
  const name = (id: string) => all.find((m) => m.id === id)?.label ?? id
  const enabled = all.filter((m) => m.enabled).map((m) => m.id)

  async function toggle(m: OrgModule, on: boolean) {
    const wanted = on ? [...enabled, m.id] : enabled.filter((x) => x !== m.id)
    setMessage(null)
    setBusy(true)
    try {
      const preview = await moduleApi.setOrg(org.id, wanted, true)
      const extraOn = (preview.changes?.on ?? []).filter((x) => x !== m.id)
      const extraOff = (preview.changes?.off ?? []).filter((x) => x !== m.id)
      if (extraOn.length || extraOff.length || !on) {
        const parts = [
          on
            ? t('„{x}“ wird eingeschaltet.', { x: m.label })
            : t(
                '„{x}“ wird ausgeschaltet. Die Daten bleiben erhalten, öffentliche Teile gehen offline.',
                { x: m.label },
              ),
          ...(extraOn.length
            ? [t('Mit eingeschaltet: {x}.', { x: extraOn.map(name).join(', ') })]
            : []),
          ...(extraOff.length
            ? [t('Mit ausgeschaltet: {x}.', { x: extraOff.map(name).join(', ') })]
            : []),
        ]
        if (!(await confirmDialog(parts.join(' ')))) return
      }
      const saved: OrgModules = await moduleApi.setOrg(org.id, wanted)
      load.setData(saved)
      setMessage({ kind: 'success', text: t('Gespeichert.') })
      await refresh()
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card card-wide stack">
      <h2>{t('Module')}</h2>
      <p className="muted small">
        {t(
          'Schaltet ein, was ihr nutzt; ausgeschaltete Module verschwinden aus dem Menü, ihre Daten bleiben erhalten. Welche Module zur Wahl stehen, gibt die Plattform-Verwaltung frei.',
        )}
      </p>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      {load.data.groups.map((group) => (
        <fieldset key={group.id} className="stack">
          <legend>{group.label}</legend>
          {group.modules.map((m) => {
            const needs = [
              ...m.requires.map(name),
              ...(m.requires_any.length ? [m.requires_any.map(name).join(' / ')] : []),
            ]
            const hint = [
              m.description,
              ...(needs.length ? [t('braucht {x}', { x: needs.join(', ') })] : []),
              ...(m.released ? [] : [t('von der Plattform nicht freigegeben')]),
            ].join(' · ')
            return (
              <Checkbox
                key={m.id}
                label={m.label}
                hint={hint}
                checked={m.enabled}
                disabled={!canEdit || (!m.released && !m.enabled)}
                busy={busy}
                onChange={(on) => void toggle(m, on)}
              />
            )
          })}
        </fieldset>
      ))}
    </div>
  )
}
