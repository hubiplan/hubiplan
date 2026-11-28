import { StatutePanel } from '../../components/StatutePanel.tsx'
import { Link } from 'react-router-dom'
import { orgApi, PERM } from '../../api/orgs.ts'
import { flatModules, moduleApi } from '../../api/modules.ts'
import type { CatalogModule, Department } from '../../api/orgs.ts'
import { Alert, Checkbox, Field, SaveStatus, SelectField } from '../../components/ui.tsx'
import {
  DATE_PRECISION_OPTIONS,
  DATE_PRECISION_WORD,
  useAutoSave,
  useForm,
  useLoad,
} from '../../components/forms.ts'
import type { DatePrecision } from '../../components/forms.ts'
import { useActiveOrg, useOrg } from '../../org/OrgContext.tsx'
import { useTerms } from '../../org/terms.ts'
import type { DeptTerms } from '../../org/terms.ts'
import { LabelFields } from '../../components/LabelFields.tsx'
import type { Gender } from '../../components/LabelFields.tsx'
import { LogoUpload } from './LogoUpload.tsx'
import { HomepageImage } from '../../components/HomepageImage.tsx'
import { FiscalYearFields, fiscalDescription } from '../../components/FiscalYearFields.tsx'
import { confirmDialog } from '../../components/dialog.ts'
import { Why } from '../../learning/Aids.tsx'
import { t, tn } from '../../i18n/index.ts'
import { ManagerSetup } from './ManagerSetup.tsx'
import { DepartmentRolesPanel } from './DepartmentRolesPanel.tsx'

/** Alle Untereinheiten unterhalb von ``id`` (ohne ``id`` selbst). */
function below(id: number, units: Department[]): Department[] {
  const ids = subtreeIds(units, id)
  return units.filter((u) => u.id !== id && ids.has(u.id))
}

/** Die Untereinheit und alle darunter (dorthin darf sie nicht umgehängt werden). */
function subtreeIds(units: Department[], id: number): Set<number> {
  const ids = new Set([id])
  let grew = true
  while (grew) {
    grew = false
    for (const u of units)
      if (u.parent_unit != null && ids.has(u.parent_unit) && !ids.has(u.id)) {
        ids.add(u.id)
        grew = true
      }
  }
  return ids
}

export function DepartmentCard({
  orgId,
  dep,
  units,
  terms,
  inThis,
  editable,
  catalog,
  onChange,
  onClose,
}: {
  orgId: number
  dep: Department
  units: Department[]
  terms: DeptTerms
  /** „diesem Zug“ / „dieser Abteilung“ */
  inThis: string
  editable: boolean
  catalog: CatalogModule[]
  onChange: () => void
  onClose: () => void
}) {
  const tm = useTerms()
  const { can } = useOrg()
  const editing = editable
  const hasWebsite = useActiveOrg().modules.includes('website')
  const hasBilling = useActiveOrg().modules.includes('billing')
  // Steuerliche Auswertung gibt es nur mit Modul Steuern
  const hasTax = useActiveOrg().modules.includes('tax')
  async function toggleActive(on: boolean) {
    const count = below(dep.id, units).filter((u) => u.is_active).length
    if (!on && count) {
      const ok = await confirmDialog({
        final: false,
        title: t('„{name}“ stilllegen?', { name: dep.name }),
        message: tn(
          'Damit wird auch 1 Untereinheit darunter stillgelegt. Wird sie wieder aktiv, kommt diese mit zurück.',
          'Damit werden auch {n} Untereinheiten darunter stillgelegt. Wird sie wieder aktiv, kommen diese mit zurück.',
          count,
        ),
        confirmLabel: t('Stilllegen'),
      })
      if (!ok) return
    }
    form.set('is_active', on)
  }
  const form = useForm({
    name: dep.name,
    short_name: dep.short_name ?? '',
    founding_year: dep.founding_year == null ? '' : String(dep.founding_year),
    website: dep.website ?? '',
    website_on_site: !!dep.website_on_site,
    is_active: dep.is_active,
    date_precision: dep.date_precision,
    fiscal_start_month: dep.fiscal_start_month,
    fiscal_start_day: dep.fiscal_start_day,
    department_label: dep.department_label ?? t('Gruppe'),
    department_label_plural: dep.department_label_plural ?? t('Gruppen'),
    department_label_gender: (dep.department_label_gender ?? 'f') as Gender,
    department_label_genitive: dep.department_label_genitive ?? '',
    department_label_en: dep.department_label_en ?? '',
    department_label_plural_en: dep.department_label_plural_en ?? '',
    own_workspace: !!dep.own_workspace,
    self_managed: !!dep.self_managed,
    own_website: !!dep.own_website,
    unit_hidden_modules: dep.unit_hidden_modules ?? [],
    fee_exempt: !!dep.fee_exempt,
    tax_independent: !!dep.tax_independent,
    parent_unit: dep.parent_unit ? String(dep.parent_unit) : '',
  })
  const blocked = subtreeIds(units, dep.id)
  const hasChildren = units.some((u) => u.parent_unit === dep.id)

  const auto = useAutoSave(
    form,
    (changes) => {
      const payload: Record<string, unknown> = { ...changes }
      if ('founding_year' in changes)
        payload.founding_year = changes.founding_year ? Number(changes.founding_year) : null
      if ('parent_unit' in changes)
        payload.parent_unit = changes.parent_unit ? Number(changes.parent_unit) : null
      return orgApi.updateDepartment(orgId, dep.id, payload as Partial<Department>)
    },
    { enabled: editable && editing, onSaved: () => onChange() },
  )

  async function finish() {
    if (!(await auto.flush())) return
    onClose()
  }

  return (
    <div className="card card-wide">
      <div className="card-head">
        {dep.logo_url && <img src={dep.logo_url} alt="" className="logo-img logo-upload" />}
        <div>
          <h2>{dep.name}</h2>
          <p className="muted small">
            {dep.short_name && t('Kurzname: {short_name} · ', { short_name: dep.short_name })}
            {dep.founding_year != null &&
              t('gegründet {founding_year} · ', { founding_year: dep.founding_year })}
            {t('Geschäftsjahr')} {fiscalDescription(dep.fiscal_start_month, dep.fiscal_start_day)}
            {dep.date_precision &&
              t(' · Mitgliedschaften {x}', { x: DATE_PRECISION_WORD[dep.date_precision] })}
            {!dep.is_active && t(' · inaktiv')}
          </p>
        </div>
        {/* Felder speichern automatisch; Schließen wartet nur auf die letzte Änderung */}
        <button
          type="button"
          className="button button-ghost push-right"
          onClick={() => (editable ? void finish() : onClose())}
        >
          {t('Schließen')}
        </button>
      </div>
      {dep.is_remote && (
        <Alert kind="info">
          {t(
            'Diese Einheit führt ihre Daten auf einer eigenen HUBIplan-Instanz. Sie ist über den Verbund gekoppelt und pflegt sich dort; hier ist sie nur zu sehen. Die Kopplung steht unter Einstellungen › Verbund.',
          )}
        </Alert>
      )}

      {editing && (
        <form onSubmit={(e) => e.preventDefault()} className="inline-form">
          <SaveStatus auto={auto} />
          <div className="grid-3">
            <Field
              label={t('Vollständiger Name')}
              required
              value={form.values.name}
              error={form.errors.name}
              onChange={(e) => form.set('name', e.target.value)}
            />
            <Field
              label={t('Kurzname (optional)')}
              maxLength={50}
              value={form.values.short_name}
              error={form.errors.short_name}
              onChange={(e) => form.set('short_name', e.target.value)}
            />
            <Field
              label={t('Gründungsjahr (optional)')}
              type="number"
              min={800}
              max={2100}
              value={form.values.founding_year}
              error={form.errors.founding_year}
              onChange={(e) => form.set('founding_year', e.target.value)}
            />
          </div>
          <Field
            label={t('Homepage (optional)')}
            inputMode="url"
            placeholder="https://"
            value={form.values.website}
            error={form.errors.website}
            onChange={(e) => form.set('website', e.target.value)}
          />
          {hasWebsite && (
            <Checkbox
              label={t('Homepage auf der Webseite verlinken')}
              hint={t(
                'Der Link steht auf der Seite von {name} und öffnet sich in einem neuen Tab.',
                { name: dep.name },
              )}
              checked={form.values.website_on_site}
              disabled={!form.values.website.trim()}
              onChange={(on) => form.set('website_on_site', on)}
            />
          )}
          {hasWebsite && dep.website && form.values.website_on_site && (
            <HomepageImage
              orgId={orgId}
              depId={dep.id}
              imageUrl={dep.website_image_url ?? null}
              custom={!!dep.website_image_custom}
              onChange={onChange}
            />
          )}
          <Checkbox
            label={t('{name} ist aktiv', { name: dep.name })}
            hint={
              below(dep.id, units).length
                ? t(
                    'statt Löschen auf inaktiv setzen; legt auch alle Untereinheiten darunter still',
                  )
                : t('statt Löschen auf inaktiv setzen, wenn es Mitglieder gab')
            }
            checked={form.values.is_active}
            onChange={(on) => void toggleActive(on)}
          />
          <SelectField
            label={t('Gehört zu')}
            value={form.values.parent_unit}
            error={form.errors.parent_unit}
            hint={t('Umhängen: Untereinheiten und Mitglieder wandern mit.')}
            onChange={(e) => form.set('parent_unit', e.target.value)}
          >
            <option value="">
              {t('direkt')} {terms.e_zum}
            </option>
            {units
              .filter((u) => u.is_active && !blocked.has(u.id))
              .map((u) => (
                <option key={u.id} value={String(u.id)}>
                  {u.path ?? u.name}
                </option>
              ))}
          </SelectField>
          <FiscalYearFields
            month={form.values.fiscal_start_month}
            day={form.values.fiscal_start_day}
            error={form.errors.fiscal_start_month ?? form.errors.fiscal_start_day}
            onChange={(m, d) => {
              form.set('fiscal_start_month', m)
              form.set('fiscal_start_day', d)
            }}
          />
          <SelectField
            label={t('Genauigkeit für Mitgliedschaften')}
            value={form.values.date_precision}
            error={form.errors.date_precision}
            hint={t('Wie Ein- und Austritt in {inThis} angezeigt werden.', { inThis })}
            onChange={(e) => form.set('date_precision', e.target.value as DatePrecision | '')}
          >
            <option value="">
              {t('wie')} {tm.e_nom}
            </option>
            {DATE_PRECISION_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </SelectField>
          {hasBilling && (
            <>
              <h3>{t('Beitrag')}</h3>
              <Checkbox
                label={t('Mitglieder von {name} sind beitragsfrei', { name: dep.name })}
                hint={t(
                  'Gilt auch für die Einheiten darunter. Der Beitragslauf berechnet für sie 0 € und nennt sie in der Prüfliste. Der Beitrag an den Dachverband bleibt.',
                )}
                checked={form.values.fee_exempt}
                onChange={(on) => form.set('fee_exempt', on)}
              />
            </>
          )}
          <h3>{t('Verwaltung')}</h3>
          <Checkbox
            label={t('{name} verwaltet sich selbst', { name: dep.name })}
            hint={
              form.values.own_workspace
                ? t('Mit eigenem Arbeitsbereich immer an.')
                : t('Rolleninhaber bekommen Zugänge mit Rechten.')
            }
            checked={form.values.self_managed || form.values.own_workspace}
            disabled={form.values.own_workspace}
            onChange={(on) => form.set('self_managed', on)}
          />
          <Why k="unit_self_managed" />
          <p className="muted small">
            {form.values.self_managed || form.values.own_workspace
              ? t(
                  'Die Mitglieder bleiben {e_beim}. Wer in {inThis} eine Rolle mit Rechten hat, arbeitet mit eigenem Zugang.',
                  { e_beim: tm.e_beim, inThis },
                )
              : t(
                  'Die Einheit darüber verwaltet alles. Rollen sind reine Ämter: keine Rechte, keine Zugänge, keine E-Mails.',
                )}
          </p>
          {form.errors.self_managed && <Alert kind="error">{form.errors.self_managed}</Alert>}
          {(form.values.self_managed || form.values.own_workspace) && (
            <>
              <h3>{t('Eigener Arbeitsbereich')}</h3>
              <Checkbox
                label={t('{name} führt eine eigene Kasse und hat eigene Rollen mit Zugängen', {
                  name: dep.name,
                })}
                checked={form.values.own_workspace}
                onChange={(on) => {
                  form.set('own_workspace', on)
                  if (on) form.set('self_managed', true)
                }}
              />
              <p className="muted small">
                {t(
                  'Die Mitglieder bleiben {e_beim}. Der Arbeitsbereich erscheint oben in der Auswahl. Wer hier Rollen verwaltet, richtet dort die Zugänge ein; wer hier die Kasse sieht, sieht dort die Kasse mit (nur lesen).',
                  { e_beim: tm.e_beim },
                )}
              </p>
              {form.values.own_workspace && hasTax && (
                <>
                  <Checkbox
                    label={t('{name} ist steuerlich selbständig (eigener Bescheid)', {
                      name: dep.name,
                    })}
                    checked={form.values.tax_independent}
                    onChange={(on) => form.set('tax_independent', on)}
                  />
                  <p className="muted small">
                    {t(
                      'Meist aus: Dann zählen Einnahmen und Umsätze der Kasse in der steuerlichen Auswertung {e_beim} mit (Freigrenze, Kleinunternehmergrenze). Nur einschalten, wenn das Finanzamt die Einheit als eigenen Verein führt.',
                      { e_beim: tm.e_beim },
                    )}
                  </p>
                </>
              )}
            </>
          )}
          {form.values.own_workspace && (
            <UnitModules
              name={dep.name}
              own={['finance', 'billing', ...(form.values.own_website ? ['website'] : [])]}
              hidden={form.values.unit_hidden_modules}
              onChange={(hidden) => form.set('unit_hidden_modules', hidden)}
            />
          )}
          {hasWebsite && (form.values.own_workspace || form.values.own_website) && (
            <>
              <Checkbox
                label={t('{name} hat eine eigene Webseite', { name: dep.name })}
                checked={form.values.own_website}
                onChange={(on) => form.set('own_website', on)}
              />
              <p className="muted small">
                {t(
                  'Optional. Gepflegt wird sie im Arbeitsbereich unter „Webseite“, mit eigenen Texten, eigener Domain und eigenen Ansprechpartnern. Die Mitglieder und ihre Einwilligungen kommen {e_vom}.',
                  { e_vom: tm.e_vom },
                )}
              </p>
              {form.errors.own_website && <Alert kind="error">{form.errors.own_website}</Alert>}
            </>
          )}
          {/* Ohne Untereinheiten braucht es keine Bezeichnung dafür */}
          {hasChildren && (
            <>
              <h3>{t('Bezeichnung der Untereinheiten')}</h3>
              <p className="muted small">
                {t('So heißen Einheiten, die zu {inThis} gehören (z. B. „Gruppe“ oder „Rotte“).', {
                  inThis,
                })}
              </p>
              <LabelFields
                preview="children"
                testId="unit-child-terms-preview"
                value={{
                  label: form.values.department_label,
                  plural: form.values.department_label_plural,
                  gender: form.values.department_label_gender,
                  genitive: form.values.department_label_genitive,
                  labelEn: form.values.department_label_en,
                  pluralEn: form.values.department_label_plural_en,
                }}
                errors={{
                  label: form.errors.department_label,
                  plural: form.errors.department_label_plural,
                  gender: form.errors.department_label_gender,
                  genitive: form.errors.department_label_genitive,
                }}
                onChange={(v) => {
                  form.set('department_label', v.label)
                  form.set('department_label_plural', v.plural)
                  form.set('department_label_gender', v.gender)
                  form.set('department_label_genitive', v.genitive)
                  form.set('department_label_en', v.labelEn ?? '')
                  form.set('department_label_plural_en', v.pluralEn ?? '')
                }}
              />
            </>
          )}
          <h4>{t('Wappen / Logo')}</h4>
          <LogoUpload
            uploadUrl={orgApi.departmentLogoUrl(orgId, dep.id)}
            logoUrl={dep.logo_url}
            onChange={onChange}
          />
          <h4>{t('Wappen / Logo für den Dunkelmodus')}</h4>
          <p className="muted small">
            {t('Ohne eigenes Logo für den Dunkelmodus gilt das normale Logo.')}
          </p>
          <LogoUpload
            dark
            uploadUrl={orgApi.departmentLogoDarkUrl(orgId, dep.id)}
            logoUrl={dep.logo_dark_url ?? null}
            onChange={onChange}
          />
          {hasWebsite && (
            <p className="muted small" data-testid="unit-gallery-hint">
              {t('Fotos fürs Bilderkarussell gehören nicht hierher:')}{' '}
              <Link to={`/webseite/inhalte?einheit=${dep.id}`}>
                {t('Webseite › Texte › Text für')} {dep.name}
              </Link>
            </p>
          )}
        </form>
      )}

      {editable && can(PERM.rolesManage) && dep.self_managed && (
        <ManagerSetup orgId={orgId} dep={dep} inThis={inThis} onChange={onChange} />
      )}

      {can(PERM.rolesView) && (
        <DepartmentRolesPanel
          orgId={orgId}
          dep={dep}
          inThis={inThis}
          editable={can(PERM.rolesManage)}
          catalog={catalog}
          onChange={onChange}
        />
      )}
      {dep.self_managed ? (
        <p className="muted small">
          {t(
            'Eine Rolle ohne Rechte ist ein reines Amt: Die Inhaber brauchen kein Konto und bekommen keine E-Mail. Rechte wirken nur, wenn der Mitgliederbereich für diese Einheit eingeschaltet ist und der Inhaber ein Konto hat (z. B. über „Leitung besetzen“).',
          )}
        </p>
      ) : (
        <p className="muted small">
          {dep.name}{' '}
          {t(
            'wird von oben verwaltet: Die Rollen sind reine Ämter, ohne Konto und ohne E-Mail. Eigene Zugänge gibt es erst mit „verwaltet sich selbst“ (oben unter Bearbeiten).',
          )}
        </p>
      )}
      <details className="statute-details">
        <summary>{t('Satzung')}</summary>
        <StatutePanel orgId={orgId} departmentId={dep.id} heading="h3" />
      </details>
      <details className="statute-details">
        <summary>{t('Beitragsordnung')}</summary>
        <StatutePanel orgId={orgId} departmentId={dep.id} heading="h3" kind="fee_rules" />
      </details>
      <details className="statute-details">
        <summary>{t('Gründungsurkunde')}</summary>
        <StatutePanel orgId={orgId} departmentId={dep.id} heading="h3" kind="founding_deed" />
      </details>
    </div>
  )
}

/** Rollen der Untereinheit besetzen: ohne Konto, ohne E-Mail (gleiche Ansicht wie Ämter, R3). */
// Module, die eine Untereinheit selbst führt (access/modules.py, UNIT_OWN_MODULES)
const UNIT_OWN_MODULES = ['finance', 'billing', 'website']

/** Module des Vereins, die im Arbeitsbereich auf den eigenen aufbauen (Steuern, Social Media …);
 * der Verein wählt, welche davon die Einheit sieht. */
function UnitModules({
  name,
  own,
  hidden,
  onChange,
}: {
  name: string
  own: string[]
  hidden: string[]
  onChange: (hidden: string[]) => void
}) {
  const clubModules = useActiveOrg().modules
  const directory = useLoad(() => moduleApi.directory(), [])
  const all = flatModules(directory.data)
  const offered = all.filter(
    (m) =>
      clubModules.includes(m.id) &&
      !UNIT_OWN_MODULES.includes(m.id) &&
      m.requires.some((r) => own.includes(r)),
  )
  if (!offered.length) return null
  const visible = offered.map((m) => m.id).filter((id) => !hidden.includes(id))
  function set(id: string, on: boolean) {
    onChange(on ? hidden.filter((x) => x !== id) : [...hidden, id].sort())
  }
  return (
    <>
      <h3>{t('Module für diese Einheit')}</h3>
      <p className="muted small">
        {t(
          'Was {name} im Arbeitsbereich zusätzlich vom Verein nutzt. Ausgeblendete Module erscheinen dort nicht; die Daten bleiben erhalten.',
          { name },
        )}
      </p>
      {offered.map((m) => (
        <Checkbox
          key={m.id}
          label={m.label}
          checked={visible.includes(m.id)}
          onChange={(on) => set(m.id, on)}
        />
      ))}
    </>
  )
}
