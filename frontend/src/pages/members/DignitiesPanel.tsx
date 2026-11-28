import { sendingVersion } from '../../api/client.ts'
import { EditAt, editKey } from '../../components/EditInPlace.tsx'
import { EmptyList } from '../../components/EmptyList.tsx'
import { useState } from 'react'
import { honorsApi } from '../../api/honors.ts'
import type { Dignity } from '../../api/honors.ts'
import { orgApi, PERM } from '../../api/orgs.ts'
import { DataTable } from '../../components/DataTable.tsx'
import type { Column } from '../../components/DataTable.tsx'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useAutoSave, useForm, useLoad } from '../../components/forms.ts'
import { DeleteIcon, EditIcon, IconButton } from '../../components/icons.tsx'
import {
  Alert,
  Checkbox,
  Field,
  LoadError,
  SaveStatus,
  SelectField,
  Loading,
} from '../../components/ui.tsx'
import { SortableList, SortHint } from '../../components/Sortable.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { HowTo, Why } from '../../learning/Aids.tsx'
import { t } from '../../i18n/index.ts'

export function DignitiesPanel() {
  const org = useActiveOrg()
  const canEdit = org.permissions.includes(PERM.membersEdit)
  const { data, error, reload } = useLoad(() => honorsApi.dignities(org.id), [org.id])
  // Untereinheiten (Züge) gibt es nur bei Vereinen; die oberste Einheit mit eigenen
  // Mitgliedern hat keine, dort würde die Abfrage scheitern
  const club = org.type === 'club'
  const units = useLoad(
    () => (club ? orgApi.departmentChoices(org.id) : Promise.resolve([])),
    [org.id, club],
  )
  const [editing, setEditing] = useState<Dignity | 'new' | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [sorting, setSorting] = useState(false)

  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading />

  // Je Einheit eine Liste: erst die eigenen Würden, dann die der Untereinheiten
  const groups = [...new Set(data.map((d) => d.unit))].map((unit) => ({
    unit,
    name: data.find((d) => d.unit === unit)?.unit_name ?? org.name,
    items: data.filter((d) => d.unit === unit),
  }))
  groups.sort((a, b) => (a.unit === null ? -1 : b.unit === null ? 1 : 0))

  async function remove(d: Dignity) {
    setMessage(null)
    const ok = await confirmDialog({
      final: true,
      title: t('Würde löschen?'),
      message:
        d.reign_count > 0
          ? t(
              '„{name}“ wird mit allen {reign_count} Regentschaften gelöscht, samt Begleitpersonen und Fotos. Das lässt sich nicht rückgängig machen.',
              { name: d.name, reign_count: d.reign_count },
            )
          : t('„{name}“ wird gelöscht.', { name: d.name }),
      confirmLabel: t('Löschen'),
    })
    if (!ok) return
    try {
      await sendingVersion(d.version, () =>
        honorsApi.deleteDignity(org.id, d.id, d.reign_count > 0),
      )
      await reload()
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }

  const columns: Column<Dignity>[] = [
    { key: 'name', label: t('Würde'), value: (d) => d.name },
    {
      key: 'unit',
      label: t('Gehört zu'),
      value: (d) => d.unit_name ?? org.name,
      filter: true,
    },
    {
      key: 'public',
      label: t('Webseite'),
      value: (d) => (d.is_public ? t('öffentlich') : t('nicht öffentlich')),
      optional: true,
    },
    {
      key: 'status',
      label: t('Status'),
      value: (d) => (d.is_archived ? t('nicht mehr verwendet') : 'aktiv'),
      filter: { initial: 'aktiv' },
    },
    { key: 'count', label: t('Regentschaften'), value: (d) => d.reign_count, numeric: true },
  ]

  return (
    <div className="card card-wide">
      <div className="card-head">
        <h2>{t('Würden')}</h2>
        {canEdit && editing === null && (
          <div className="button-row push-right">
            {groups.some((g) => g.items.length > 1) && (
              <button
                type="button"
                className="button button-ghost"
                aria-pressed={sorting}
                onClick={() => setSorting((x) => !x)}
              >
                {sorting ? t('Schließen') : t('Reihenfolge ändern')}
              </button>
            )}
            {!sorting && (
              <button
                type="button"
                className="button button-ghost"
                onClick={() => setEditing('new')}
              >
                {t('Neue Würde')}
              </button>
            )}
          </div>
        )}
      </div>
      <p className="muted small">
        {t(
          'Welche Würden es gibt, legt ihr selbst fest, z. B. König, Prinz, Schülerprinz oder Kaiser. Würden einer Untereinheit (z. B. Zugkönig) erscheinen auf deren Seite. Eine Würde trägt jemand für eine Zeit, meist ein Jahr, danach folgt der Nächste. Dauerhafte Auszeichnungen wie Ehrenmitglied sind dagegen Ehrungen (Mitglieder › Einrichtung › Ehrungen).',
        )}
      </p>
      {editing !== null && units.error && (
        <LoadError
          message={t(
            'Die Untereinheiten konnten nicht geladen werden; die Zuordnung zu einer Untereinheit ist deshalb gerade nicht wählbar. {error}',
            { error: units.error },
          )}
          onRetry={() => void units.reload()}
        />
      )}
      {editing !== null && (
        <EditAt at={editing === 'new' ? null : editKey('dignity', editing.id)}>
          <DignityForm
            key={editing === 'new' ? 'new' : editing.id}
            dignity={editing === 'new' ? null : editing}
            units={units.data ?? []}
            onDone={async () => {
              setEditing(null)
              await reload()
            }}
            onCancel={() => setEditing(null)}
          />
        </EditAt>
      )}
      {message && <Alert kind="error">{message}</Alert>}
      {sorting ? (
        <>
          <SortHint website={org.modules.includes('website')} />
          {groups.map((g) => (
            <div key={g.unit ?? 0}>
              {groups.length > 1 && <h3>{g.name}</h3>}
              <SortableList
                ariaLabel={t('Reihenfolge der Würden: {name}', { name: g.name })}
                items={g.items}
                id={(d) => d.id}
                label={(d) => d.name}
                render={(d) => (
                  <span className={d.is_archived ? 'muted' : undefined}>
                    {d.name}
                    {d.is_archived && t(' (nicht mehr verwendet)')}
                  </span>
                )}
                onReorder={(ids) =>
                  honorsApi.reorderDignities(org.id, g.unit, ids).then(() => reload())
                }
              />
            </div>
          ))}
        </>
      ) : (
        <DataTable
          label={t('Würden')}
          slot="dignity"
          rows={data}
          rowKey={(d) => d.id}
          columns={columns}
          emptyText={t('Noch keine Würden angelegt.')}
          empty={
            editing === null ? (
              <EmptyList
                title={t('Noch keine Würden angelegt.')}
                canAdd={canEdit}
                action={{ label: t('Neue Würde'), onClick: () => setEditing('new') }}
              >
                {t(
                  'Welche Würden es gibt, etwa Königin, Prinz oder Vereinsmeister, legt ihr selbst fest; danach tragt ihr die Regentschaften ein.',
                )}
              </EmptyList>
            ) : undefined
          }
          rowClassName={(d) => (d.is_archived ? 'inactive' : undefined)}
          actions={
            canEdit
              ? (d) => (
                  <>
                    <IconButton
                      label={t('{name} bearbeiten', { name: d.name })}
                      icon={<EditIcon />}
                      onClick={() => setEditing(d)}
                    />
                    <IconButton
                      label={t('{name} löschen', { name: d.name })}
                      icon={<DeleteIcon />}
                      danger
                      onClick={() => void remove(d)}
                    />
                  </>
                )
              : undefined
          }
        />
      )}
    </div>
  )
}

function DignityForm({
  dignity,
  units,
  onDone,
  onCancel,
}: {
  dignity: Dignity | null
  units: { id: number; name: string }[]
  onDone: () => void
  onCancel: () => void
}) {
  const org = useActiveOrg()
  const form = useForm({
    name: dignity?.name ?? '',
    unit: dignity?.unit ?? null,
    is_public: dignity?.is_public ?? true,
    is_archived: dignity?.is_archived ?? false,
    numbered: dignity?.numbered ?? false,
    count_each_reign: dignity?.count_each_reign ?? false,
    share_down: dignity?.share_down ?? false,
    name_plural: dignity?.name_plural ?? '',
    // Webseite #149: leer = Adresse aus der Mehrzahl
    web_slug: dignity && dignity.web_slug_auto === false ? (dignity.web_slug ?? '') : '',
  })
  const { values: v, set, errors } = form
  // Bestehende Würden speichern automatisch, neue erst mit „Anlegen“
  const auto = useAutoSave(
    form,
    (changes) => honorsApi.updateDignity(org.id, dignity!.id, changes),
    { enabled: dignity !== null, version: dignity?.version },
  )
  return (
    <form
      className="subcard"
      onSubmit={(e) => {
        e.preventDefault()
        if (dignity) {
          void auto.flush().then((ok) => {
            if (ok) onDone()
          })
          return
        }
        void form.submit(async () => {
          await honorsApi.createDignity(org.id, v)
          onDone()
        })
      }}
    >
      {dignity && <SaveStatus auto={auto} />}
      <div className="grid-2">
        <Field
          label={t('Bezeichnung')}
          value={v.name}
          required
          error={errors.name}
          onChange={(e) => set('name', e.target.value)}
        />
        <Field
          label={t('Mehrzahl (für Überschrift und Menü der Webseite)')}
          value={v.name_plural}
          placeholder={dignity?.plural || undefined}
          error={errors.name_plural}
          onChange={(e) => set('name_plural', e.target.value)}
        />
        <Field
          label={t('Adresse auf der Webseite')}
          value={v.web_slug}
          placeholder={dignity?.web_slug || undefined}
          error={errors.web_slug}
          hint={t(
            'Leer: aus der Mehrzahl, z. B. /wuerden/hubertuskoenige/. Frühere Adressen leiten weiter.',
          )}
          onChange={(e) => set('web_slug', e.target.value)}
        />
        <SelectField
          label={t('Gehört zu')}
          value={v.unit === null ? '' : String(v.unit)}
          error={errors.unit}
          onChange={(e) => set('unit', e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">{org.name}</option>
          {units.map((u) => (
            <option key={u.id} value={u.id}>
              {u.name}
            </option>
          ))}
        </SelectField>
      </div>
      <Checkbox
        label={t('In der Chronik auf der Webseite zeigen')}
        checked={v.is_public}
        onChange={(on) => set('is_public', on)}
      />
      <Why k="chronicle_public" />
      <Checkbox
        label={t('An Untereinheiten weitergeben')}
        hint={t(
          'Vereine bzw. Züge darunter sehen die Träger, die aus ihnen kamen (Feld „Aus“), und können sie auf ihrer Webseite zeigen.',
        )}
        checked={v.share_down}
        onChange={(on) => set('share_down', on)}
      />
      <Checkbox
        label={t(
          'Ordnungszahl je Vorname (der erste Michael ist „Michael I.“, der zweite „Michael II.“)',
        )}
        checked={v.numbered}
        onChange={(on) => set('numbered', on)}
      />
      {v.numbered && <HowTo k="how_regnal_number" />}
      {v.numbered && (
        <Checkbox
          label={t(
            'Bei mehrfacher Würde neu zählen (zweimal Otto Muster: Otto I. und Otto II.; sonst behält er seine Zahl)',
          )}
          checked={v.count_each_reign}
          onChange={(on) => set('count_each_reign', on)}
        />
      )}
      {dignity && (
        <Checkbox
          label={t('Nicht mehr verwendet (bisherige Regentschaften bleiben)')}
          checked={v.is_archived}
          onChange={(on) => set('is_archived', on)}
        />
      )}
      {form.message && <Alert kind={form.message.kind}>{form.message.text}</Alert>}
      <div className="button-row">
        <button
          type="submit"
          className={dignity ? 'button button-ghost' : 'button button-primary'}
          disabled={form.busy}
        >
          {dignity ? t('Schließen') : t('Anlegen')}
        </button>
        {!dignity && (
          <button type="button" className="button" onClick={onCancel}>
            {t('Abbrechen')}
          </button>
        )}
      </div>
    </form>
  )
}

// --- Import ---
