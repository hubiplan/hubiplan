import { useState } from 'react'
import type { FormEvent } from 'react'
import { displayName, platformApi } from '../../api/orgs.ts'
import {
  flatModules,
  moduleApi,
  requirementText,
  withoutDependents,
  withRequirements,
} from '../../api/modules.ts'
import type { PlatformOrg } from '../../api/orgs.ts'
import { Alert, Checkbox, Field, LoadError, SelectField } from '../../components/ui.tsx'
import { useForm, useLoad } from '../../components/forms.ts'
import { useOrg } from '../../org/OrgContext.tsx'
import { LabelFields } from '../../components/LabelFields.tsx'
import { buildTerms } from '../../org/terms.ts'
import { t } from '../../i18n/index.ts'
import { EraseCard } from './EraseCard.tsx'
import { ACCESS_LABELS } from './platformHelpers.ts'

// Vorschlag für die Bezeichnung neuer Einheiten, je nachdem, ob sie eigene Mitglieder
// führen (wie im Backend). Jede Einheit kann ihre Bezeichnung frei ändern.
const DEFAULT_LABELS = {
  without: {
    label: 'Dachverband',
    plural: 'Dachverbände',
    gender: 'm',
    genitive: 'Dachverbands',
  },
  members: { label: 'Verein', plural: 'Vereine', gender: 'm', genitive: 'Vereins' },
} as const

function suggestedLabels(keeps: boolean) {
  return DEFAULT_LABELS[keeps ? 'members' : 'without']
}

export function PlatformOrgForm({
  org,
  parents,
  onDone,
  onCancel,
}: {
  org: PlatformOrg | null
  /** Einheiten, unter denen Einheiten mit eigenen Mitgliedern angelegt werden können */
  parents: PlatformOrg[]
  onDone: () => void
  onCancel: () => void
}) {
  const { refresh } = useOrg()
  const initialKeeps = org ? !!org.keeps_members : true
  const form = useForm({
    keeps_members: initialKeeps,
    federation: org?.federation ?? null,
    name: org?.name ?? '',
    short_name: org?.short_name ?? '',
    founding_year: org?.founding_year ? String(org.founding_year) : '',
    street: org?.street ?? '',
    postal_code: org?.postal_code ?? '',
    city: org?.city ?? '',
    country: org?.country ?? 'Deutschland',
    contact_email: org?.contact_email ?? '',
    contact_phone: org?.contact_phone ?? '',
    website: org?.website ?? '',
    label: org?.label ?? suggestedLabels(initialKeeps).label,
    label_plural: org?.label_plural ?? suggestedLabels(initialKeeps).plural,
    label_gender: org?.label_gender ?? suggestedLabels(initialKeeps).gender,
    label_genitive: org?.label_genitive ?? suggestedLabels(initialKeeps).genitive,
    federation_member_access: org?.federation_member_access ?? 'none',
    federation_show_former_memberships: org?.federation_show_former_memberships ?? false,
    released_modules: org?.released_modules ?? org?.enabled_modules ?? ['finance', 'members'],
    modules_pass_down: org?.modules_pass_down ?? false,
    is_active: org?.is_active ?? true,
  })
  // Vorlage beim Anlegen: schlägt Module und die Bezeichnung der Untereinheiten vor
  const templates = useLoad(() => (org ? Promise.resolve([]) : moduleApi.templates()), [org])
  const [template, setTemplate] = useState('')
  const [unitLabels, setUnitLabels] = useState<Partial<PlatformOrg>>({})
  function applyTemplate(id: string) {
    setTemplate(id)
    const tpl = (templates.data ?? []).find((x) => x.id === id)
    if (!tpl) {
      setUnitLabels({})
      return
    }
    form.set('released_modules', tpl.modules)
    if (tpl.org_type === 'federation' && v.keeps_members && v.federation === null) setKeeps(false)
    if (tpl.org_type === 'club' && !v.keeps_members) setKeeps(true)
    setUnitLabels({
      ...(tpl.units
        ? {
            department_label: tpl.units.label,
            department_label_plural: tpl.units.plural,
            department_label_gender: tpl.units.gender,
            department_label_en: tpl.units.label_en,
            department_label_plural_en: tpl.units.plural_en,
          }
        : {}),
      // Reines Kassenbuch: kein Menüpunkt für Untereinheiten (Einstellungen › Bezeichnungen)
      ...(tpl.units_in_menu === false ? { units_in_menu: false } : {}),
    })
  }
  const v = form.values
  const e = form.errors
  const directory = useLoad(() => moduleApi.directory(), [])
  const allModules = flatModules(directory.data)
  const [board, setBoard] = useState('')
  const [boardName, setBoardName] = useState({ first_name: '', last_name: '' })
  const [boardResult, setBoardResult] = useState<string | null>(null)
  const tm = buildTerms(v.label, v.label_plural, v.label_gender, v.label_genitive)
  // Unter einer übergeordneten Einheit führen Einheiten immer eigene Mitglieder
  const underParent = v.federation !== null
  const switchable = org ? !!org.can_switch_members : !underParent
  // Zugriff nach unten: Einheiten, die andere Einheiten mit eigenen Mitgliedern zusammenfassen
  const groupsUnits = org ? org.type === 'federation' : !underParent && !v.keeps_members

  function setKeeps(keeps: boolean) {
    form.set('keeps_members', keeps)
    // Vorschlag für die Bezeichnung mitziehen, solange keine eigene gewählt ist
    const before = suggestedLabels(v.keeps_members)
    if (v.label === before.label && v.label_plural === before.plural) {
      const next = suggestedLabels(keeps)
      form.set('label', next.label)
      form.set('label_plural', next.plural)
      form.set('label_gender', next.gender)
      form.set('label_genitive', next.genitive)
    }
  }

  async function save(ev: FormEvent) {
    ev.preventDefault()
    const { keeps_members, ...rest } = v
    const payload = {
      ...rest,
      ...(org ? {} : unitLabels),
      // Nur senden, was sich ändern lässt
      ...(switchable && (!org || keeps_members !== initialKeeps) ? { keeps_members } : {}),
      founding_year: v.founding_year ? Number(v.founding_year) : null,
    } as Partial<PlatformOrg>
    const ok = await form.submit(() =>
      org ? platformApi.update(org.id, payload) : platformApi.create(payload),
    )
    if (ok) {
      await refresh()
      onDone()
    }
  }

  async function addBoard(ev: FormEvent) {
    ev.preventDefault()
    if (!org) return
    const res = await form.submit(
      () =>
        platformApi.addBoard(org.id, board, {
          first_name: boardName.first_name.trim(),
          last_name: boardName.last_name.trim(),
        }),
      t('Vorstand zugeordnet.'),
    )
    if (res) {
      const r = res as { email: string; invited: boolean; new_account: boolean }
      setBoardResult(
        !r.new_account
          ? t('{email} hat jetzt die Rolle „Vorstand“.', { email: r.email })
          : r.invited
            ? t(
                'Neues Konto {email} angelegt; die Einladung zum Festlegen des Passworts ist per E-Mail unterwegs (gilt 7 Tage).',
                { email: r.email },
              )
            : t(
                'Neues Konto {email} angelegt, aber die Einladung konnte nicht verschickt werden. Die Person kann auf der Anmeldeseite „Passwort vergessen“ wählen.',
                { email: r.email },
              ),
      )
      setBoard('')
      setBoardName({ first_name: '', last_name: '' })
    }
  }

  return (
    <div className="stack">
      <form className="card card-wide" onSubmit={save}>
        <h2>
          {org
            ? t('{Sg} bearbeiten', { Sg: tm.Sg, sg: tm.sg })
            : t('{Sg} anlegen', { Sg: tm.Sg, sg: tm.sg })}
        </h2>
        {!org && (templates.data ?? []).length > 0 && (
          <SelectField
            label={t('Vorlage')}
            hint={t(
              'Schlägt Module und die Bezeichnung der Untereinheiten vor. Danach ist alles frei änderbar.',
            )}
            value={template}
            onChange={(ev) => applyTemplate(ev.target.value)}
          >
            <option value="">{t('– ohne Vorlage –')}</option>
            {(templates.data ?? []).map((x) => (
              <option key={x.id} value={x.id}>
                {x.label}
              </option>
            ))}
          </SelectField>
        )}
        {(!org || org.keeps_members) && (
          <SelectField
            label={t('Übergeordnete Einheit')}
            value={v.federation ?? ''}
            error={e.federation}
            onChange={(ev) => {
              const parent = ev.target.value ? Number(ev.target.value) : null
              form.set('federation', parent)
              if (parent !== null && !v.keeps_members) setKeeps(true)
            }}
          >
            <option value="">{t('– keine (direkt unter der Plattform) –')}</option>
            {parents
              .filter((p) => p.id !== org?.id)
              .map((p) => (
                <option key={p.id} value={p.id}>
                  {displayName(p)}
                </option>
              ))}
          </SelectField>
        )}
        <Checkbox
          label={t('Führt eigene Mitglieder (Mitgliederliste, Mitgliedsarten, Ein- und Austritt)')}
          checked={underParent || v.keeps_members}
          disabled={!switchable}
          onChange={setKeeps}
        />
        {e.keeps_members && <Alert kind="error">{e.keeps_members}</Alert>}
        <p className="small muted">
          {underParent
            ? t('Unter einer übergeordneten Einheit führen Einheiten immer eigene Mitglieder.')
            : org && !switchable
              ? t(
                  'Lässt sich nur ändern, solange die Einheit keine eigenen Mitglieder und keine Untereinheiten hat.',
                )
              : t(
                  'Ohne eigene Mitglieder fasst die Einheit andere Einheiten zusammen, die Mitglieder führen. Umschalten geht, solange die Einheit leer ist.',
                )}
        </p>
        <div className="grid-2">
          <Field
            label={t('Vollständiger Name')}
            required
            value={v.name}
            error={e.name}
            onChange={(ev) => form.set('name', ev.target.value)}
          />
          <Field
            label={t('Kurzname (optional)')}
            maxLength={50}
            value={v.short_name}
            error={e.short_name}
            hint={t('Für Navigation, Listen und Auswahlfelder')}
            onChange={(ev) => form.set('short_name', ev.target.value)}
          />
          <Field
            label={t('Gründungsjahr')}
            type="number"
            required
            value={v.founding_year}
            error={e.founding_year}
            onChange={(ev) => form.set('founding_year', ev.target.value)}
          />
        </div>
        <h3>{t('Bezeichnung')}</h3>
        <LabelFields
          value={{
            label: v.label,
            plural: v.label_plural,
            gender: v.label_gender,
            genitive: v.label_genitive,
          }}
          errors={{
            label: e.label,
            plural: e.label_plural,
            gender: e.label_gender,
            genitive: e.label_genitive,
          }}
          onChange={(l) => {
            form.set('label', l.label)
            form.set('label_plural', l.plural)
            form.set('label_gender', l.gender)
            form.set('label_genitive', l.genitive)
          }}
        />
        <Field
          label={t('Straße und Hausnummer')}
          required
          value={v.street}
          error={e.street}
          onChange={(ev) => form.set('street', ev.target.value)}
        />
        <div className="grid-3">
          <Field
            label={t('PLZ')}
            required
            value={v.postal_code}
            error={e.postal_code}
            onChange={(ev) => form.set('postal_code', ev.target.value)}
          />
          <Field
            label={t('Ort')}
            required
            value={v.city}
            error={e.city}
            onChange={(ev) => form.set('city', ev.target.value)}
          />
          <Field
            label={t('Land')}
            value={v.country}
            error={e.country}
            onChange={(ev) => form.set('country', ev.target.value)}
          />
        </div>
        <div className="grid-3">
          <Field
            label={t('E-Mail')}
            type="email"
            value={v.contact_email}
            error={e.contact_email}
            onChange={(ev) => form.set('contact_email', ev.target.value)}
          />
          <Field
            label={t('Telefon')}
            value={v.contact_phone}
            error={e.contact_phone}
            onChange={(ev) => form.set('contact_phone', ev.target.value)}
          />
          <Field
            label={t('Website')}
            type="url"
            value={v.website}
            error={e.website}
            onChange={(ev) => form.set('website', ev.target.value)}
          />
        </div>

        {groupsUnits && (
          <>
            <h3>
              {t('Freigaben für')} {tm.diese}
            </h3>
            <SelectField
              label={t('Zugriff auf Mitgliedsdaten der Untereinheiten')}
              value={v.federation_member_access}
              error={e.federation_member_access}
              onChange={(ev) =>
                form.set(
                  'federation_member_access',
                  ev.target.value as PlatformOrg['federation_member_access'],
                )
              }
            >
              {Object.entries(ACCESS_LABELS).map(([k, l]) => (
                <option key={k} value={k}>
                  {l}
                </option>
              ))}
            </SelectField>
            <Checkbox
              label={t(
                'Frühere Mitgliedschaften (Einheit, Eintritt, Austritt) für die Untereinheiten sichtbar',
              )}
              checked={v.federation_show_former_memberships}
              onChange={(val) => form.set('federation_show_former_memberships', val)}
            />
            <Checkbox
              label={t('Darf den Einheiten darunter Module freigeben')}
              hint={t(
                'Dann ändert sie die Freigabe für diese Einheiten selbst, ohne die Plattform-Verwaltung.',
              )}
              checked={v.modules_pass_down}
              onChange={(val) => form.set('modules_pass_down', val)}
            />
          </>
        )}

        <h3>{t('Freigegebene Module')}</h3>
        <p className="muted small">
          {t(
            'Neu freigegebene Module werden eingeschaltet. Die Einheit kann freigegebene Module unter Einstellungen › Module selbst aus- und wieder einschalten.',
          )}
        </p>
        {directory.error && <LoadError message={directory.error} onRetry={directory.reload} />}
        {(directory.data ?? []).map((group) => (
          <fieldset key={group.id} className="stack">
            <legend>{group.label}</legend>
            {group.modules.map((m) => {
              const needs = requirementText(m, allModules)
              return (
                <Checkbox
                  key={m.id}
                  label={m.label}
                  hint={
                    needs
                      ? t('{text} (braucht {needs})', { text: m.description, needs })
                      : m.description
                  }
                  checked={v.released_modules.includes(m.id)}
                  onChange={(on) =>
                    form.set(
                      'released_modules',
                      on
                        ? withRequirements([...v.released_modules, m.id], allModules)
                        : withoutDependents(
                            v.released_modules.filter((x) => x !== m.id),
                            allModules,
                          ),
                    )
                  }
                />
              )
            })}
          </fieldset>
        ))}
        {org && (
          <Checkbox
            label={t('{Sg} ist aktiv', { Sg: tm.Sg })}
            checked={v.is_active}
            disabled={!!org.erase_requested_at}
            hint={
              org.erase_requested_at
                ? t('Zum Löschen vorgemerkt. Erst die Vormerkung zurücknehmen.')
                : undefined
            }
            onChange={(val) => form.set('is_active', val)}
          />
        )}

        {form.message && <Alert kind={form.message.kind}>{form.message.text}</Alert>}
        <div className="button-row">
          <button type="submit" className="button button-primary" disabled={form.busy}>
            {t('Speichern')}
          </button>
          <button type="button" className="button button-ghost" onClick={onCancel}>
            {t('Zurück')}
          </button>
        </div>
      </form>

      {org && (
        <EraseCard
          org={org}
          onDone={async () => {
            await refresh()
            onDone()
          }}
        />
      )}

      {org && (
        <form className="card card-wide" onSubmit={addBoard}>
          <h2>{t('Vorstand festlegen')}</h2>
          <p className="muted small">
            {t(
              'Die Person bekommt die Rolle „Vorstand“ mit allen Rechten in {diesem} und kann danach selbst Rollen festlegen und besetzen.',
              { diesem: tm.diesem },
            )}
          </p>
          <div className="grid-2">
            <Field
              label={t('E-Mail-Adresse')}
              type="email"
              required
              value={board}
              hint={t('Gibt es noch kein Konto, wird eines angelegt.')}
              onChange={(ev) => setBoard(ev.target.value)}
            />
            <Field
              label={t('Vorname')}
              value={boardName.first_name}
              hint={t('Nur für ein neues Konto; ein bestehendes behält seinen Namen.')}
              onChange={(ev) => setBoardName((n) => ({ ...n, first_name: ev.target.value }))}
            />
            <Field
              label={t('Nachname')}
              value={boardName.last_name}
              onChange={(ev) => setBoardName((n) => ({ ...n, last_name: ev.target.value }))}
            />
          </div>
          {boardResult && <Alert kind="info">{boardResult}</Alert>}
          <button type="submit" className="button button-primary">
            {t('Zuordnen')}
          </button>
        </form>
      )}
    </div>
  )
}
