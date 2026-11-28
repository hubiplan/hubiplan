import { PALETTE_ROLES } from '../../api/orgs.ts'
import type { PaletteRole, PaletteRoles } from '../../api/orgs.ts'
import { Checkbox } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { roleLabel } from './appearanceHelpers.ts'

/** Wofür eine Farbe da ist: Rollen zum Ankreuzen, jede Rolle hat höchstens eine Farbe */
export function ColorRoles({
  label,
  slot,
  roles,
  onToggle,
}: {
  label: string
  slot: number
  roles: PaletteRoles
  onToggle: (slot: number, role: PaletteRole, on: boolean) => void
}) {
  return (
    <div className="color-roles" role="group" aria-label={label}>
      <span className="muted small">{t('Verwendet für')}</span>
      {PALETTE_ROLES.map((role) => (
        <Checkbox
          key={role}
          label={roleLabel(role)}
          checked={roles[role] === slot}
          onChange={(on) => onToggle(slot, role, on)}
        />
      ))}
    </div>
  )
}
