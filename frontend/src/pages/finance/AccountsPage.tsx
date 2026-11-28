import { EditAt, EditSlot, editKey } from '../../components/EditInPlace.tsx'
import { Fragment, useState } from 'react'
import type { FormEvent } from 'react'
import { euro, financeApi, parseAmount } from '../../api/finance.ts'
import type { Account, FinanceSettings } from '../../api/finance.ts'
import { PERM } from '../../api/orgs.ts'
import { errorMessage, formatDate, useAutoSave, useForm } from '../../components/forms.ts'
import { Alert, Checkbox, Field, SaveStatus, SelectField, Loading } from '../../components/ui.tsx'
import { useActiveOrg, useOrg } from '../../org/OrgContext.tsx'
import { confirmDialog } from '../../components/dialog.ts'
import { Term, Why } from '../../learning/Aids.tsx'
import { t } from '../../i18n/index.ts'
import { EmptyList } from '../../components/EmptyList.tsx'
import { useFinanceAccounts, useFinanceSettings } from '../../components/masterData.ts'

/** Aktuelles Jahr, beim Öffnen eines Formulars ermittelt (nicht beim Laden der Seite). */
function thisYear() {
  return new Date().getFullYear()
}

const KIND_LABEL = { bank: t('Bankkonto'), cash: t('Barkasse'), savings: t('Sparkonto') }

export function AccountsPage() {
  const org = useActiveOrg()
  const { refresh } = useOrg()
  const canEdit = org.permissions.includes(PERM.financeEdit)
  const [switchError, setSwitchError] = useState<string | null>(null)
  const settings = useFinanceSettings(org.id)
  const datevOn = !!settings.data?.datev_enabled
  const { data, error, reload } = useFinanceAccounts(org.id)
  const [editing, setEditing] = useState<Account | 'new' | null>(null)

  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading />

  return (
    <div className="card card-wide">
      <div className="card-head">
        <h2>{t('Bankkonten und Kassen')}</h2>
        {canEdit && editing === null && (
          <button
            type="button"
            className="button button-ghost push-right"
            onClick={() => setEditing('new')}
          >
            {t('Neues Konto')}
          </button>
        )}
      </div>
      <p className="muted small">
        {t(
          'Bankkonten, Barkassen und Sparkonten – von jeder Art beliebig viele. Der Anfangsbestand gilt zum Stichtag; Buchungen davor sind nicht möglich.',
        )}
      </p>
      {editing !== null && (
        <EditAt at={editing === 'new' ? null : editKey('account', editing.id)}>
          <AccountForm
            // Je Objekt ein eigenes Formular: Werte und Autospeichern wechseln nie das Ziel
            key={editing === 'new' ? 'new' : editing.id}
            orgId={org.id}
            account={editing === 'new' ? null : editing}
            datev={datevOn}
            onDone={async () => {
              setEditing(null)
              await reload()
            }}
            onCancel={() => setEditing(null)}
          />
        </EditAt>
      )}
      {data.length === 0 ? (
        editing === null && (
          <EmptyList
            title={t('Noch keine Konten.')}
            canAdd={canEdit}
            action={{ label: t('Neues Konto'), onClick: () => setEditing('new') }}
          >
            {t('Lege zuerst das Bankkonto und die Barkasse an; darauf wird gebucht.')}
          </EmptyList>
        )
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t('Konto')}</th>
              <th>
                <Term k="opening_balance_term">{t('Anfangsbestand')}</Term>
              </th>
              <th className="num">{t('Bestand heute')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.map((a) => (
              <Fragment key={a.id}>
                <tr key={a.id} className={a.is_active ? undefined : 'muted'}>
                  <td>
                    <strong>{a.name}</strong>
                    <div className="muted small">
                      {a.kind_label}
                      {a.iban && t(' · {x}', { x: a.iban.replace(/(.{4})/g, '$1 ').trim() })}
                      {!a.is_active && t(' · inaktiv')}
                    </div>
                  </td>
                  <td>
                    {euro(a.opening_balance)}
                    <div className="muted small">
                      {t('zum')} {formatDate(a.opening_date)}
                    </div>
                  </td>
                  <td className="num">
                    <strong>{euro(a.balance)}</strong>
                    {a.planned_balance !== null && (
                      <div className="muted small">
                        {t('mit vorgemerkten Buchungen')} {euro(a.planned_balance)}
                      </div>
                    )}
                  </td>
                  <td className="actions">
                    {canEdit && (
                      <button type="button" className="link-button" onClick={() => setEditing(a)}>
                        {t('Bearbeiten')}
                      </button>
                    )}
                  </td>
                </tr>
                <EditSlot id={editKey('account', a.id)} colSpan={4} />
              </Fragment>
            ))}
          </tbody>
        </table>
      )}
      {canEdit && (
        <>
          <Checkbox
            label={t('Zählprotokoll und Kassenbericht für Veranstaltungen nutzen')}
            checked={!!org.cash_counts_enabled}
            onChange={(on) =>
              void (async () => {
                setSwitchError(null)
                try {
                  await financeApi.updateSettings(org.id, { cash_counts_enabled: on })
                  await refresh()
                } catch (err) {
                  setSwitchError(errorMessage(err))
                }
              })()
            }
          />
          <p className="muted small">
            {t(
              'Zählprotokoll: Bargeld nach Scheinen und Münzen zählen und mit dem Kassenbuch vergleichen. Kassenbericht: Tageseinnahme einer offenen Kasse, etwa beim Getränkeverkauf am Fest, aus Anfangs- und Endbestand ermitteln und buchen.',
            )}
          </p>
          {org.modules.includes('tax') && (
            <>
              <Checkbox
                label={t('Rücklagen führen')}
                checked={!!org.reserves_enabled}
                onChange={(on) =>
                  void (async () => {
                    setSwitchError(null)
                    try {
                      await financeApi.updateSettings(org.id, { reserves_enabled: on })
                      await refresh()
                    } catch (err) {
                      setSwitchError(errorMessage(err))
                    }
                  })()
                }
              />
              <p className="muted small">
                {t(
                  'Rücklagen nach § 62 AO binden einen Teil der Mittel für einen Zweck, etwa die nächste Veranstaltung oder eine größere Anschaffung. Es wird kein Geld bewegt.',
                )}
              </p>
            </>
          )}
          {switchError && <Alert kind="error">{switchError}</Alert>}
          {settings.data && (
            <DatevSettings
              orgId={org.id}
              settings={settings.data}
              onChange={(next) => settings.setData(next)}
            />
          )}
        </>
      )}
    </div>
  )
}

function AccountForm({
  orgId,
  account,
  datev,
  onDone,
  onCancel,
}: {
  orgId: number
  account: Account | null
  /** DATEV-Export eingeschaltet: Feld für das Finanzkonto zeigen */
  datev: boolean
  onDone: () => void
  onCancel: () => void
}) {
  const form = useForm({
    name: account?.name ?? '',
    kind: account?.kind ?? 'bank',
    iban: account?.iban ?? '',
    bic: account?.bic ?? '',
    bank_name: account?.bank_name ?? '',
    opening_balance: account ? account.opening_balance.replace('.', ',') : '0,00',
    opening_date: account?.opening_date ?? `${thisYear()}-01-01`,
    is_active: account?.is_active ?? true,
    datev_account: account?.datev_account ?? '',
  })
  const { values: v, errors, set } = form

  // Bestehende Konten speichern automatisch, neue erst mit „Anlegen“
  const auto = useAutoSave(
    form,
    (changes) =>
      financeApi.updateAccount(orgId, account!.id, {
        ...changes,
        ...('opening_balance' in changes
          ? { opening_balance: parseAmount(changes.opening_balance ?? '') || '0' }
          : {}),
      }),
    { enabled: account !== null },
  )

  async function save(e: FormEvent) {
    e.preventDefault()
    if (account) {
      if (!(await auto.flush())) return
      onDone()
      return
    }
    const payload = { ...v, opening_balance: parseAmount(v.opening_balance) || '0' }
    const ok = await form.submit(() => financeApi.createAccount(orgId, payload))
    if (ok) onDone()
  }

  async function remove() {
    if (
      !account ||
      !(await confirmDialog({
        final: true,
        title: t('Konto „{name}“ löschen?', { name: account.name }),
        confirmLabel: t('Löschen'),
      }))
    )
      return
    const ok = await form.submit(() => financeApi.deleteAccount(orgId, account.id))
    if (ok !== undefined) onDone()
  }

  return (
    <form className="subcard" onSubmit={save}>
      <h3>{account ? t('Konto „{name}“', { name: account.name }) : t('Neues Konto')}</h3>
      {account && <SaveStatus auto={auto} />}
      <div className="grid-3">
        <Field
          label={t('Name')}
          required
          value={v.name}
          error={errors.name}
          onChange={(e) => set('name', e.target.value)}
        />
        <SelectField
          label={t('Art')}
          value={v.kind}
          onChange={(e) => set('kind', e.target.value as Account['kind'])}
        >
          {Object.entries(KIND_LABEL).map(([k, label]) => (
            <option key={k} value={k}>
              {label}
            </option>
          ))}
        </SelectField>
        <Field
          label={t('Bank')}
          value={v.bank_name}
          error={errors.bank_name}
          onChange={(e) => set('bank_name', e.target.value)}
        />
      </div>
      {v.kind !== 'cash' && (
        <div className="grid-2">
          <Field
            label="IBAN"
            value={v.iban}
            error={errors.iban}
            onChange={(e) => set('iban', e.target.value)}
          />
          <Field
            label="BIC"
            value={v.bic}
            error={errors.bic}
            onChange={(e) => set('bic', e.target.value)}
          />
        </div>
      )}
      <div className="grid-3">
        <Field
          label={t('Anfangsbestand (€)')}
          inputMode="decimal"
          value={v.opening_balance}
          error={errors.opening_balance}
          onChange={(e) => set('opening_balance', e.target.value)}
        />
        <Field
          label={t('zum Stichtag')}
          type="date"
          required
          value={v.opening_date}
          error={errors.opening_date}
          onChange={(e) => set('opening_date', e.target.value)}
        />
        {datev && (
          <Field
            label={t('DATEV-Konto')}
            inputMode="numeric"
            placeholder={v.kind === 'cash' ? t('z. B. 1000') : t('z. B. 1200')}
            value={v.datev_account}
            error={errors.datev_account}
            onChange={(e) => set('datev_account', e.target.value)}
          />
        )}
      </div>
      <Why k="opening_balance" />
      <div className="grid-3">
        {account && (
          <div className="field">
            <span>&nbsp;</span>
            <Checkbox
              label={t('aktiv')}
              checked={v.is_active}
              onChange={(val) => set('is_active', val)}
            />
          </div>
        )}
      </div>
      {form.message?.kind === 'error' && <Alert kind="error">{form.message.text}</Alert>}
      <div className="button-row">
        <button
          type="submit"
          className={account ? 'button button-ghost' : 'button button-primary'}
          disabled={form.busy}
        >
          {account ? t('Schließen') : t('Anlegen')}
        </button>
        {!account && (
          <button type="button" className="button button-ghost" onClick={onCancel}>
            {t('Abbrechen')}
          </button>
        )}
        {account && (
          <button type="button" className="button button-danger push-right" onClick={remove}>
            {t('Löschen')}
          </button>
        )}
      </div>
    </form>
  )
}

/** DATEV-Export für die Steuerberatung: ein/aus und Stammdaten des Mandanten. */
function DatevSettings({
  orgId,
  settings,
  onChange,
}: {
  orgId: number
  settings: FinanceSettings
  onChange: (next: FinanceSettings) => void
}) {
  const [error, setError] = useState<string | null>(null)
  async function save(data: Partial<FinanceSettings>) {
    setError(null)
    try {
      onChange(await financeApi.updateSettings(orgId, data))
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  const blur =
    (field: 'datev_consultant' | 'datev_client' | 'datev_chart' | 'datev_account_length') =>
    (e: { target: { value: string } }) => {
      const value = e.target.value.trim()
      if (value !== String(settings[field] ?? ''))
        void save({ [field]: field === 'datev_account_length' ? Number(value) : value })
    }
  return (
    <>
      <Checkbox
        label={t('DATEV-Export für die Steuerberatung nutzen')}
        checked={!!settings.datev_enabled}
        onChange={(on) => void save({ datev_enabled: on })}
      />
      {settings.datev_enabled && (
        <>
          <div className="grid-4">
            <Field
              label={t('Beraternummer')}
              inputMode="numeric"
              defaultValue={settings.datev_consultant ?? ''}
              onBlur={blur('datev_consultant')}
            />
            <Field
              label={t('Mandantennummer')}
              inputMode="numeric"
              defaultValue={settings.datev_client ?? ''}
              onBlur={blur('datev_client')}
            />
            <Field
              label={t('Sachkontenlänge')}
              type="number"
              min={4}
              max={8}
              defaultValue={settings.datev_account_length ?? 4}
              onBlur={blur('datev_account_length')}
            />
            <Field
              label={t('Kontenrahmen')}
              placeholder={t('z. B. SKR 49')}
              defaultValue={settings.datev_chart ?? ''}
              onBlur={blur('datev_chart')}
            />
          </div>
          <p className="muted small">
            {t(
              'Die Angaben bekommt ihr von eurer Steuerberatung. Tragt bei jedem Konto das DATEV-Finanzkonto (z. B. 1200 Bank, 1000 Kasse) und unter Kategorien das Sachkonto ein. Den Buchungsstapel gibt es dann unter Finanzen › Jahresabschluss.',
            )}
          </p>
          <Why k="datev_accounts" />
        </>
      )}
      {error && <Alert kind="error">{error}</Alert>}
    </>
  )
}
