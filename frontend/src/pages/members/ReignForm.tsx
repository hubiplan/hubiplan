import { useEffect, useRef, useState } from 'react'
import { honorsApi } from '../../api/honors.ts'
import type { Companion, Dignity, Origin, Reign, ReignInput } from '../../api/honors.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useAutoSave, useForm } from '../../components/forms.ts'
import { Alert, Field, SaveStatus, SelectField } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { useImageCrop } from '../../components/ImageCrop.tsx'
import { RightsHint } from '../../components/RightsHint.tsx'
import { t, tn } from '../../i18n/index.ts'
import { PersonField } from './PersonField.tsx'

/** Aktuelles Jahr, beim Öffnen eines Formulars ermittelt (nicht beim Laden der Seite). */
function thisYear() {
  return new Date().getFullYear()
}

/** Woher der Würdenträger kam: Auswahl einer Einheit darunter oder frei als Text. */
function OriginField({
  origins,
  origin,
  name,
  onChange,
}: {
  origins: Origin[]
  origin: number | null
  name: string
  onChange: (origin: number | null, name: string) => void
}) {
  const [free, setFree] = useState(origin === null && name !== '')
  const value = origin !== null ? String(origin) : free ? 'frei' : ''
  return (
    <div className="grid-2">
      <SelectField
        label={t('Aus (Herkunft des Würdenträgers)')}
        value={value}
        hint={t('Einheiten darunter sehen bei weitergegebenen Würden nur ihre eigenen Träger.')}
        onChange={(e) => {
          const v = e.target.value
          setFree(v === 'frei')
          if (v === 'frei' || v === '') onChange(null, v === 'frei' ? name : '')
          else onChange(Number(v), '')
        }}
      >
        <option value="">{t('keine Angabe')}</option>
        {origins.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
        <option value="frei">{t('andere (frei eingeben)')}</option>
      </SelectField>
      {free && (
        <Field
          label={t('Aus (frei)')}
          value={name}
          placeholder={t('z. B. ein aufgelöster Zug')}
          onChange={(e) => onChange(null, e.target.value)}
        />
      )}
    </div>
  )
}

export function ReignForm({
  reign,
  dignities,
  origins,
  onDone,
  onCancel,
}: {
  reign: Reign | null
  dignities: Dignity[]
  origins: Origin[]
  onDone: () => void
  onCancel: () => void
}) {
  const org = useActiveOrg()
  const form = useForm<ReignInput>({
    dignity: reign?.dignity ?? dignities.find((d) => !d.is_archived)?.id ?? dignities[0].id,
    // Bestehende Werte unverändert übernehmen: ein Zeitraum bleibt Zeitraum (UI-Audit NMF-02)
    year: reign ? reign.year : thisYear(),
    end_year: reign?.end_year ?? null,
    ordinal: reign?.ordinal ?? null,
    valid_from: reign?.valid_from ?? null,
    valid_until: reign?.valid_until ?? null,
    person: reign?.person ?? null,
    name: reign?.display_name ?? '',
    note: reign?.note ?? '',
    // Neu: leer lassen, damit der Server die Untereinheit des Mitglieds vorbelegt
    ...(reign ? { origin: reign.origin, origin_name: reign.origin_name } : {}),
    companions: (reign?.companions ?? []).map((c) => ({
      label: c.label,
      person: c.person,
      name: c.display_name ?? c.name,
    })),
  })
  const { values: v, set, errors } = form
  const [period, setPeriod] = useState(!!reign && !reign.year && !!reign.valid_from)
  // Neue Regentschaft: Foto erst mit „Anlegen“ übernehmen, „Abbrechen“ verwirft es (UI-Audit NMF-03).
  // Bestehende Regentschaft: Foto wird wie alle Felder sofort gespeichert.
  const [photo, setPhoto] = useState(reign?.photo ?? null)
  const [photoBusy, setPhotoBusy] = useState(false)
  const [photoError, setPhotoError] = useState<string | null>(null)
  const [photoFile, setPhotoFile] = useState<File | null>(null)
  const [photoConsent, setPhotoConsent] = useState(!!reign?.photo?.consent)
  const [preview, setPreview] = useState<string | null>(null)
  const previewRef = useRef<string | null>(null)
  const shownPhoto = reign ? (photo?.small_url ?? null) : preview
  const crop = useImageCrop({ title: t('Fotoausschnitt festlegen') })

  // Bestehende Regentschaften speichern automatisch, neue erst mit „Anlegen“
  const auto = useAutoSave(
    form,
    (_changes, values) => honorsApi.updateReign(org.id, reign!.id, values),
    { enabled: reign !== null },
  )

  async function changePhoto(file: File | null) {
    if (!reign) {
      choosePhoto(file)
      return
    }
    if (
      file === null &&
      !(await confirmDialog({
        final: true,
        title: t('Foto entfernen?'),
        message: t('Das Foto wird aus der Chronik gelöscht.'),
        confirmLabel: t('Entfernen'),
      }))
    )
      return
    setPhotoBusy(true)
    setPhotoError(null)
    try {
      if (file) setPhoto(await honorsApi.uploadPhoto(org.id, reign.id, file, photoConsent))
      else {
        await honorsApi.deletePhoto(org.id, reign.id)
        setPhoto(null)
      }
    } catch (err) {
      setPhotoError(t('Das Foto wurde nicht gespeichert: {x}', { x: errorMessage(err) }))
    } finally {
      setPhotoBusy(false)
    }
  }

  function choosePhoto(file: File | null) {
    if (previewRef.current) URL.revokeObjectURL(previewRef.current)
    previewRef.current = file ? URL.createObjectURL(file) : null
    setPreview(previewRef.current)
    setPhotoFile(file)
  }

  useEffect(
    () => () => {
      if (previewRef.current) URL.revokeObjectURL(previewRef.current)
    },
    [],
  )

  // Frühere Text-Einträge derselben Person mitverknüpfen? (Datenaudit 08.11. FD-06)
  async function offerLink(oldName: string, person: number) {
    try {
      const { found } = await honorsApi.linkReignName(org.id, { name: oldName, person })
      const others = found - (reign && reign.person === null ? 1 : 0)
      if (others <= 0) return
      if (
        await confirmDialog({
          title: t('Frühere Einträge mitverknüpfen?'),
          message: tn(
            'Es gibt {n} weiteren Eintrag mit dem Namen „{name}“ ohne Mitglied. Soll er ebenfalls mit diesem Mitglied verknüpft werden? Das ist wichtig für die richtige Ordnungszahl.',
            'Es gibt {n} weitere Einträge mit dem Namen „{name}“ ohne Mitglied. Sollen sie ebenfalls mit diesem Mitglied verknüpft werden? Das ist wichtig für die richtige Ordnungszahl.',
            others,
            { name: oldName },
          ),
          confirmLabel: t('Mitverknüpfen'),
          cancelLabel: t('Nur diesen Eintrag'),
          danger: false,
        })
      )
        await honorsApi.linkReignName(org.id, { name: oldName, person, confirm: true })
    } catch {
      // Die Rückfrage ist eine Hilfe; ohne sie bleibt die Verknüpfung dieses Eintrags
    }
  }

  function setCompanion(index: number, patch: Partial<Companion>) {
    set(
      'companions',
      v.companions.map((c, i) => (i === index ? { ...c, ...patch } : c)),
    )
  }

  function choosePeriod(on: boolean) {
    setPeriod(on)
    // Widersprechende Angaben bewusst leeren: entweder Jahr oder Zeitraum
    if (on) form.setValues({ ...v, year: null, end_year: null })
    else form.setValues({ ...v, year: v.year ?? thisYear(), valid_from: null, valid_until: null })
  }

  async function create() {
    const saved = await honorsApi.createReign(org.id, v)
    try {
      if (photoFile) await honorsApi.uploadPhoto(org.id, saved.id, photoFile, photoConsent)
    } catch (err) {
      throw new Error(
        t('Die Regentschaft ist angelegt, das Foto aber nicht: {x}', { x: errorMessage(err) }),
      )
    }
    onDone()
  }

  return (
    <form
      className="subcard"
      onSubmit={(e) => {
        e.preventDefault()
        if (reign) {
          void auto.flush().then((ok) => {
            if (ok && !photoBusy) onDone()
          })
          return
        }
        void form.submit(create)
      }}
    >
      <h3>{reign ? t('Regentschaft bearbeiten') : t('Neue Regentschaft')}</h3>
      {reign && <SaveStatus auto={auto} />}
      <div className="grid-2">
        <SelectField
          label={t('Würde')}
          value={String(v.dignity)}
          error={errors.dignity}
          onChange={(e) => set('dignity', Number(e.target.value))}
        >
          {dignities.map((d) => (
            <option key={d.id} value={d.id}>
              {d.unit_name
                ? t('{name} ({unit_name})', { name: d.name, unit_name: d.unit_name })
                : d.name}
              {d.is_archived ? t(' (nicht mehr verwendet)') : ''}
            </option>
          ))}
        </SelectField>
        <fieldset className="field">
          <legend>{t('Angabe')}</legend>
          <label className="checkbox">
            <input type="radio" checked={!period} onChange={() => choosePeriod(false)} />{' '}
            {t('Jahr oder Jahre')}
          </label>
          <label className="checkbox">
            <input type="radio" checked={period} onChange={() => choosePeriod(true)} />{' '}
            {t('Zeitraum mit Datum')}
          </label>
        </fieldset>
      </div>
      {period ? (
        <div className="grid-2">
          <Field
            label={t('Zeitraum der Regentschaft: von')}
            type="date"
            value={v.valid_from ?? ''}
            error={errors.valid_from ?? errors.year}
            onChange={(e) => set('valid_from', e.target.value || null)}
          />
          <Field
            label={t('Bis (leer = noch im Amt)')}
            type="date"
            value={v.valid_until ?? ''}
            error={errors.valid_until}
            onChange={(e) => set('valid_until', e.target.value || null)}
          />
        </div>
      ) : (
        <div className="grid-2">
          <Field
            label={v.end_year ? t('Startjahr') : t('Jahr')}
            type="number"
            min={1000}
            max={2999}
            value={v.year ?? ''}
            error={errors.year}
            onChange={(e) => set('year', e.target.value ? Number(e.target.value) : null)}
          />
          <Field
            label={t('Endjahr (leer = nur ein Jahr)')}
            type="number"
            min={1000}
            max={2999}
            value={v.end_year ?? ''}
            error={errors.end_year}
            onChange={(e) => set('end_year', e.target.value ? Number(e.target.value) : null)}
          />
        </div>
      )}
      <PersonField
        label={t('Würdenträger')}
        person={v.person}
        name={v.name}
        onChange={(person, name) => {
          const oldName = v.name.trim()
          form.setValues({ ...v, person, name })
          if (person !== null && v.person === null && oldName) void offerLink(oldName, person)
        }}
      />
      {errors.name && <Alert kind="error">{errors.name}</Alert>}
      {errors.person && <Alert kind="error">{errors.person}</Alert>}
      <OriginField
        origins={origins}
        origin={v.origin ?? null}
        name={v.origin_name ?? ''}
        onChange={(origin, origin_name) => form.setValues({ ...v, origin, origin_name })}
      />
      {errors.origin && <Alert kind="error">{errors.origin}</Alert>}
      {dignities.find((d) => d.id === v.dignity)?.numbered && (
        <Field
          label={t('Ordnungszahl (leer = automatisch je Vorname)')}
          type="number"
          min={1}
          max={3999}
          value={v.ordinal ?? ''}
          placeholder={reign?.ordinal ? undefined : reign?.ordinal_text || undefined}
          error={errors.ordinal}
          onChange={(e) => set('ordinal', e.target.value ? Number(e.target.value) : null)}
        />
      )}
      <h4>{t('Begleitpersonen')}</h4>
      {v.companions.map((c, i) => (
        <div key={i} className="subcard">
          <div className="grid-2">
            <Field
              label={t('Funktion')}
              value={c.label}
              placeholder={t('z. B. Königin, Minister')}
              onChange={(e) => setCompanion(i, { label: e.target.value })}
            />
            <button
              type="button"
              className="link-button"
              onClick={() =>
                set(
                  'companions',
                  v.companions.filter((_, j) => j !== i),
                )
              }
            >
              {t('Begleitperson entfernen')}
            </button>
          </div>
          <PersonField
            label={t('Begleitperson')}
            person={c.person}
            name={c.name}
            onChange={(person, name) => setCompanion(i, { person, name })}
          />
        </div>
      ))}
      {errors.companions && <Alert kind="error">{errors.companions}</Alert>}
      <button
        type="button"
        className="button button-ghost"
        onClick={() => set('companions', [...v.companions, { label: '', person: null, name: '' }])}
      >
        {t('Begleitperson hinzufügen')}
      </button>
      <Field
        label={t('Bemerkung')}
        value={v.note}
        placeholder={t('z. B. Jubiläumskönig')}
        onChange={(e) => set('note', e.target.value)}
      />
      <div className="field">
        <span>{t('Foto (z. B. Königspaar)')}</span>
        {shownPhoto && <img src={shownPhoto} alt="" width={200} />}
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          aria-label={t('Foto auswählen')}
          disabled={photoBusy}
          onChange={(e) => {
            const file = e.target.files?.[0] ?? null
            e.target.value = ''
            if (file)
              void crop.pick(file).then((cropped) => {
                if (cropped) void changePhoto(cropped)
              })
          }}
        />
        {crop.dialog}
        <RightsHint />
        {shownPhoto && (
          <button
            type="button"
            className="link-button"
            disabled={photoBusy}
            onClick={() => void changePhoto(null)}
          >
            {t('Foto entfernen')}
          </button>
        )}
        {shownPhoto && (
          <label className="checkbox">
            <input
              type="checkbox"
              checked={photoConsent}
              disabled={photoBusy}
              onChange={(e) => {
                const on = e.target.checked
                setPhotoConsent(on)
                if (reign && photo)
                  void honorsApi
                    .setPhotoConsent(org.id, reign.id, on)
                    .then(setPhoto)
                    .catch((err) => setPhotoError(errorMessage(err)))
              }}
            />{' '}
            {t('Einwilligung der nur mit Namen Abgebildeten liegt vor')}
          </label>
        )}
        {photoBusy && <p className="muted small">{t('Foto wird gespeichert …')}</p>}
        {photoError && <Alert kind="error">{photoError}</Alert>}
        <small className="muted">
          {reign
            ? t('Wird sofort übernommen, verkleinert und ohne Metadaten gespeichert.')
            : t('Wird mit „Anlegen“ übernommen, verkleinert und ohne Metadaten gespeichert.')}{' '}
          {t(
            'Auf der Webseite erscheint es nur, wenn alle verknüpften Mitglieder in Fotos eingewilligt haben und für nur mit Namen Abgebildete die Einwilligung bestätigt ist.',
          )}
        </small>
      </div>
      {form.message && <Alert kind={form.message.kind}>{form.message.text}</Alert>}
      <div className="button-row">
        <button
          type="submit"
          className={reign ? 'button button-ghost' : 'button button-primary'}
          disabled={form.busy || photoBusy}
        >
          {reign ? t('Schließen') : t('Anlegen')}
        </button>
        {!reign && (
          <button type="button" className="button" onClick={onCancel}>
            {t('Abbrechen')}
          </button>
        )}
      </div>
    </form>
  )
}

// --- Würden ---
