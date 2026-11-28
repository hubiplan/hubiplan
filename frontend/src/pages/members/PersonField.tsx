import { honorsApi } from '../../api/honors.ts'
import type { HonorsPerson } from '../../api/honors.ts'
import { MemberPicker } from '../../components/MemberPicker.tsx'
import { Field } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

/** Mitglied (auch ehemaliges) oder Name als Text. */
export function PersonField({
  label,
  person,
  name,
  onChange,
}: {
  label: string
  person: number | null
  name: string
  onChange: (person: number | null, name: string) => void
}) {
  const org = useActiveOrg()
  if (person !== null) {
    return (
      <div className="field">
        <span>{label}</span>
        <p>
          {name}{' '}
          <button type="button" className="link-button" onClick={() => onChange(null, name)}>
            {t('Verknüpfung lösen')}
          </button>
        </p>
      </div>
    )
  }
  return (
    <div className="grid-2">
      <Field
        label={t('{label} (Name)', { label })}
        value={name}
        hint={t('Für frühere Jahre und Nichtmitglieder.')}
        onChange={(e) => onChange(null, e.target.value)}
      />
      <MemberPicker<HonorsPerson>
        orgId={org.id}
        value={null}
        label={t('oder Mitglied wählen')}
        search={(term) => honorsApi.people(org.id, term)}
        onChange={(m) =>
          m &&
          onChange(
            m.id,
            t('{first_name} {last_name}', {
              first_name: m.first_name,
              last_name: m.last_name,
            }).trim(),
          )
        }
      />
    </div>
  )
}
