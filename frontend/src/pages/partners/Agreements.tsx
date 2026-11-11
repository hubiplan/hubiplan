// Vereinbarungen an der Partnerakte (Konzept geschaeftspartner.md, P4): Sponsoring mit
// Zeitraum, Leistung, Gegenleistung, steuerlicher Einordnung, Erinnerung und Dankesbrief.
import { useState } from 'react'
import { saveBlob } from '../../api/client.ts'
import {
  AGREEMENT_BENEFITS,
  AGREEMENT_KINDS,
  AGREEMENT_TAX_KINDS,
  partnerApi,
} from '../../api/partners.ts'
import type {
  AgreementBenefit,
  AgreementInput,
  AgreementKind,
  AgreementTaxKind,
  BusinessPartner,
  PartnerAgreement,
} from '../../api/partners.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert, Checkbox, Field, SelectField } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { formatDay, formatEuro } from '../../i18n/format.ts'
import { TextArea } from '../settings/TextArea.tsx'

function agreementKindLabel(kind: AgreementKind): string {
  return {
    sponsoring: t('Sponsoring'),
    framework: t('Rahmenvereinbarung'),
    contract: t('Vertrag'),
    other: t('Sonstige Vereinbarung'),
  }[kind]
}

function taxKindLabel(kind: AgreementTaxKind): string {
  return {
    mention: t('Nur Nennung (ohne Werbung)'),
    advertising: t('Aktive Werbung'),
    none: t('Keine Einnahme'),
  }[kind]
}

function benefitLabel(benefit: AgreementBenefit): string {
  return {
    website: t('Logo auf der Webseite'),
    banner: t('Bande oder Banner'),
    publication: t('Festschrift oder Programmheft'),
    clothing: t('Trikot oder Kleidung'),
    event: t('Nennung bei Veranstaltungen'),
    other: t('Sonstiges'),
  }[benefit]
}

const emptyAgreement = (): AgreementInput => ({
  kind: 'sponsoring',
  title: '',
  start: new Date().toISOString().slice(0, 10),
  end: null,
  amount: null,
  in_kind: '',
  benefits: [],
  benefits_text: '',
  tax_kind: 'mention',
  notice_days: null,
  auto_renew: false,
  remind_days: 60,
  notes: '',
})

function period(a: PartnerAgreement): string {
  return a.end
    ? t('{start} bis {end}', { start: formatDay(a.start), end: formatDay(a.end) })
    : t('ab {start}', { start: formatDay(a.start) })
}

export function Agreements({ partner, canEdit }: { partner: BusinessPartner; canEdit: boolean }) {
  const org = useActiveOrg()
  const loaded = useLoad(() => partnerApi.agreements(org.id, partner.id), [org.id, partner.id])
  const [items, setItems] = useState<PartnerAgreement[] | null>(null)
  const [editing, setEditing] = useState<number | 'new' | null>(null)
  const [draft, setDraft] = useState<AgreementInput>(emptyAgreement())
  const [thanks, setThanks] = useState<{ id: number; text: string } | null>(null)
  const [error, setError] = useState('')
  const list = items ?? loaded.data ?? []
  if (loaded.error) return <Alert kind="error">{loaded.error}</Alert>

  const save = async () => {
    setError('')
    try {
      const saved = await partnerApi.saveAgreement(
        org.id,
        partner.id,
        draft,
        editing === 'new' ? undefined : (editing ?? undefined),
      )
      setItems([saved, ...list.filter((a) => a.id !== saved.id)])
      setEditing(null)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const letter = async () => {
    if (!thanks) return
    setError('')
    try {
      const blob = await partnerApi.thanks(org.id, partner.id, thanks.id, thanks.text)
      saveBlob(blob, `${t('Dankesbrief')}-${partner.number || partner.id}.pdf`)
      const today = new Date().toISOString().slice(0, 10)
      setItems(list.map((a) => (a.id === thanks.id ? { ...a, thanked_at: today } : a)))
      setThanks(null)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const toggleBenefit = (b: AgreementBenefit, on: boolean) => {
    const set = new Set(draft.benefits ?? [])
    if (on) set.add(b)
    else set.delete(b)
    setDraft({ ...draft, benefits: AGREEMENT_BENEFITS.filter((x) => set.has(x)) })
  }

  return (
    <section className="subcard stack">
      <h4>{t('Vereinbarungen')}</h4>
      {list.length === 0 && (
        <p className="muted small">
          {t('Noch keine Vereinbarungen, etwa für Sponsoring oder eine Bandenwerbung.')}
        </p>
      )}
      <ul className="item-list">
        {list.map((a) => (
          <li key={a.id} className="item-row">
            <div className="item-row-info">
              <strong>{a.title}</strong>
              <span className="muted small"> · {agreementKindLabel(a.kind)}</span>
              <div className="muted small">
                {[
                  period(a),
                  a.amount ? formatEuro(Number(a.amount)) : '',
                  a.in_kind,
                  taxKindLabel(a.tax_kind),
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </div>
              {a.benefits.length > 0 && (
                <div className="muted small">
                  {t('Gegenleistung: {list}', {
                    list: [...a.benefits.map(benefitLabel), a.benefits_text]
                      .filter(Boolean)
                      .join(', '),
                  })}
                </div>
              )}
              <div className="muted small">
                {[
                  a.notice_by ? t('kündigen bis {date}', { date: formatDay(a.notice_by) }) : '',
                  a.auto_renew ? t('verlängert sich automatisch') : '',
                  a.reminder_due
                    ? t('Erinnerung am {date}', { date: formatDay(a.reminder_due) })
                    : '',
                  a.thanked_at ? t('Dankesbrief am {date}', { date: formatDay(a.thanked_at) }) : '',
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </div>
            </div>
            {canEdit && (
              <div className="button-row">
                <button
                  type="button"
                  className="button"
                  onClick={() => {
                    setDraft({
                      kind: a.kind,
                      title: a.title,
                      start: a.start,
                      end: a.end,
                      amount: a.amount,
                      in_kind: a.in_kind,
                      benefits: a.benefits,
                      benefits_text: a.benefits_text,
                      tax_kind: a.tax_kind,
                      category: a.category,
                      notice_days: a.notice_days,
                      auto_renew: a.auto_renew,
                      remind_days: a.remind_days,
                      notes: a.notes,
                    })
                    setEditing(a.id)
                  }}
                >
                  {t('Bearbeiten')}
                </button>
                <button
                  type="button"
                  className="button"
                  onClick={() => setThanks({ id: a.id, text: '' })}
                >
                  {t('Dankesbrief')}
                </button>
                <button
                  type="button"
                  className="button button-danger"
                  onClick={async () => {
                    if (!(await confirmDialog(t('Vereinbarung entfernen?')))) return
                    try {
                      await partnerApi.removeAgreement(org.id, partner.id, a.id)
                      setItems(list.filter((x) => x.id !== a.id))
                    } catch (err) {
                      setError(errorMessage(err))
                    }
                  }}
                >
                  {t('Entfernen')}
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
      {thanks && (
        <div className="stack">
          <TextArea
            label={t('Eigener Text für den Dankesbrief')}
            value={thanks.text}
            onChange={(text) => setThanks({ ...thanks, text })}
          />
          <p className="muted small">
            {t(
              'Leer lassen für den Vorschlag mit Betrag und Sachleistung. Der Brief kommt auf euren Briefbogen.',
            )}
          </p>
          <div className="button-row">
            <button type="button" className="button button-primary" onClick={() => void letter()}>
              {t('Dankesbrief erstellen')}
            </button>
            <button type="button" className="button" onClick={() => setThanks(null)}>
              {t('Abbrechen')}
            </button>
          </div>
        </div>
      )}
      {editing !== null && (
        <div className="stack">
          <div className="form-grid">
            <SelectField
              label={t('Art')}
              value={draft.kind}
              onChange={(e) => setDraft({ ...draft, kind: e.target.value as AgreementKind })}
            >
              {AGREEMENT_KINDS.map((k) => (
                <option key={k} value={k}>
                  {agreementKindLabel(k)}
                </option>
              ))}
            </SelectField>
            <Field
              label={t('Bezeichnung')}
              required
              value={draft.title ?? ''}
              onChange={(e) => setDraft({ ...draft, title: e.target.value })}
            />
            <Field
              label={t('Beginn')}
              type="date"
              required
              value={draft.start ?? ''}
              onChange={(e) => setDraft({ ...draft, start: e.target.value })}
            />
            <Field
              label={t('Ende')}
              type="date"
              value={draft.end ?? ''}
              onChange={(e) => setDraft({ ...draft, end: e.target.value || null })}
            />
            <Field
              label={t('Betrag in Euro')}
              type="number"
              min={0}
              step="0.01"
              value={draft.amount ?? ''}
              onChange={(e) => setDraft({ ...draft, amount: e.target.value || null })}
            />
            <Field
              label={t('Sachleistung')}
              value={draft.in_kind ?? ''}
              onChange={(e) => setDraft({ ...draft, in_kind: e.target.value })}
            />
            <SelectField
              label={t('Steuerlich')}
              hint={t('Aktive Werbung gehört zum wirtschaftlichen Geschäftsbetrieb.')}
              value={draft.tax_kind}
              onChange={(e) => setDraft({ ...draft, tax_kind: e.target.value as AgreementTaxKind })}
            >
              {AGREEMENT_TAX_KINDS.map((k) => (
                <option key={k} value={k}>
                  {taxKindLabel(k)}
                </option>
              ))}
            </SelectField>
            <Field
              label={t('Kündigungsfrist in Tagen')}
              type="number"
              min={0}
              max={730}
              value={draft.notice_days ?? ''}
              onChange={(e) =>
                setDraft({ ...draft, notice_days: e.target.value ? Number(e.target.value) : null })
              }
            />
            <Field
              label={t('Erinnerung (Tage vor Ende bzw. Kündigungsfrist)')}
              type="number"
              min={0}
              max={365}
              value={draft.remind_days ?? 60}
              onChange={(e) => setDraft({ ...draft, remind_days: Number(e.target.value) || 0 })}
            />
          </div>
          <Checkbox
            label={t('Verlängert sich automatisch, wenn niemand kündigt')}
            checked={!!draft.auto_renew}
            onChange={(auto_renew) => setDraft({ ...draft, auto_renew })}
          />
          <fieldset className="subcard">
            <legend>{t('Gegenleistung')}</legend>
            <div className="grid-3">
              {AGREEMENT_BENEFITS.map((b) => (
                <Checkbox
                  key={b}
                  label={benefitLabel(b)}
                  checked={(draft.benefits ?? []).includes(b)}
                  onChange={(on) => toggleBenefit(b, on)}
                />
              ))}
            </div>
            <Field
              label={t('Gegenleistung genauer')}
              value={draft.benefits_text ?? ''}
              onChange={(e) => setDraft({ ...draft, benefits_text: e.target.value })}
            />
          </fieldset>
          <TextArea
            label={t('Notizen')}
            value={draft.notes ?? ''}
            onChange={(notes) => setDraft({ ...draft, notes })}
          />
          {draft.end && (
            <p className="muted small">
              {t('Mit dem Modul Aufgaben erinnert dich HUBIplan rechtzeitig an die Verlängerung.')}
            </p>
          )}
          <div className="button-row">
            <button
              type="button"
              className="button button-primary"
              disabled={!draft.title?.trim() || !draft.start}
              onClick={() => void save()}
            >
              {t('Vereinbarung speichern')}
            </button>
            <button type="button" className="button" onClick={() => setEditing(null)}>
              {t('Abbrechen')}
            </button>
          </div>
        </div>
      )}
      {error && <Alert kind="error">{error}</Alert>}
      {canEdit && editing === null && (
        <button
          type="button"
          className="button"
          onClick={() => {
            setDraft(emptyAgreement())
            setEditing('new')
          }}
        >
          {t('Vereinbarung hinzufügen')}
        </button>
      )}
    </section>
  )
}
