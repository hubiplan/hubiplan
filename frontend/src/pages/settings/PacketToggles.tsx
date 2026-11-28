import type { Levels, PacketChoice } from '../../api/peering.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { Why } from '../../learning/Aids.tsx'
import { t } from '../../i18n/index.ts'

export function PacketToggles({
  choices,
  levels,
  onChange,
  disabled,
}: {
  choices: PacketChoice[]
  levels: Levels
  onChange: (l: Levels) => void
  disabled?: boolean
}) {
  return (
    <fieldset className="fieldset">
      <legend>{t('Diese Einheit gibt frei')}</legend>
      {choices.map((c) => (
        <label key={c.key} className="field">
          <span>
            {c.label}
            {c.personal && (
              <span className="muted small">
                {' '}
                {t('· Personenbezug:')} {c.personal}
              </span>
            )}
          </span>
          <select
            value={levels[c.key] ?? ''}
            disabled={disabled}
            onChange={(e) => {
              const value = e.target.value
              void (async () => {
                if (c.key === 'members' && value === 'b' && !(await confirmNamed())) return
                const next = { ...levels }
                if (value) next[c.key] = value
                else delete next[c.key]
                onChange(next)
              })()
            }}
          >
            <option value="">{t('aus')}</option>
            {c.levels.map((l) => (
              <option key={l.value} value={l.value}>
                {l.label}
              </option>
            ))}
          </select>
        </label>
      ))}
      {choices.some((c) => c.key === 'members') && <Why k="peering_named" />}
    </fieldset>
  )
}

/** Prüfliste vor der namentlichen Meldung (Konzept 6.1). */
function confirmNamed(): Promise<boolean> {
  return confirmDialog({
    final: false,
    message:
      t('Namentliche Meldung: Name, Vorname, Geburtsdatum, Verbandsnummer, Mitgliedsart und ') +
      t('Zeiträume gehen an die Einheit darüber (nie Anschrift, Kontakt, Bankdaten, Fotos). ') +
      t('Bitte vorher prüfen: Steht die Meldepflicht in der Satzung? Nennen die ') +
      t('Datenschutzhinweise die Einheit darüber als Empfänger?'),
    confirmLabel: t('Geprüft, namentlich melden'),
  })
}
