import { historyApi } from '../../api/competitionHistory.ts'
import { promptDialog } from '../../components/dialog.ts'
import { useLoad } from '../../components/forms.ts'
import { SelectField } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

/** Einrichten: Reihe zuordnen (Archiv über die Jahre). */
export function SeriesSelect({
  org,
  value,
  disabled,
  onChange,
}: {
  org: number
  value: number | null
  disabled?: boolean
  onChange: (id: number | null) => void
}) {
  const { data, reload } = useLoad(() => historyApi.series.list(org), [org])
  async function create() {
    const name = await promptDialog({
      title: t('Neue Reihe'),
      label: t('Bezeichnung, z. B. „Vereinsmeisterschaft“'),
      confirmLabel: t('Anlegen'),
    })
    if (!name?.trim()) return
    const s = await historyApi.series.create(org, { name: name.trim() })
    reload()
    onChange(s.id)
  }
  return (
    <SelectField
      label={t('Reihe')}
      value={value ?? ''}
      disabled={disabled}
      hint={t('verbindet denselben Wettbewerb über die Jahre (Archiv, Bestenliste)')}
      onChange={(e) => {
        if (e.target.value === 'neu') void create()
        else onChange(e.target.value ? Number(e.target.value) : null)
      }}
    >
      <option value="">{t('keine')}</option>
      {(data ?? []).map((s) => (
        <option key={s.id} value={s.id}>
          {s.name}
        </option>
      ))}
      <option value="neu">{t('Neue Reihe …')}</option>
    </SelectField>
  )
}

// --- Seiten in der Seitenleiste ---
