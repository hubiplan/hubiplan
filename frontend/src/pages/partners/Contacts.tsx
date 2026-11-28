import { EditAt, EditSlot, editKey } from '../../components/EditInPlace.tsx'
import { useState } from 'react'
import { partnerApi } from '../../api/partners.ts'
import type { BusinessPartner, ContactInput, PartnerContact } from '../../api/partners.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage } from '../../components/forms.ts'
import { Alert, Checkbox, Field } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

const emptyContact = (): ContactInput => ({
  last_name: '',
  first_name: '',
  function: '',
  email: '',
  phone: '',
  is_primary: false,
  receives_invoices: false,
  receives_mail: true,
  notes: '',
})

export function Contacts({ partner, canEdit }: { partner: BusinessPartner; canEdit: boolean }) {
  const org = useActiveOrg()
  const [items, setItems] = useState<PartnerContact[]>(partner.contacts)
  const [editing, setEditing] = useState<number | 'new' | null>(null)
  const [draft, setDraft] = useState<ContactInput>(emptyContact())
  const [error, setError] = useState('')
  const save = async () => {
    setError('')
    try {
      const saved = await partnerApi.saveContact(
        org.id,
        partner.id,
        draft,
        editing === 'new' ? undefined : (editing ?? undefined),
      )
      const rest = items
        .filter((c) => c.id !== saved.id)
        .map((c) => (saved.is_primary ? { ...c, is_primary: false } : c))
      setItems(saved.is_primary ? [saved, ...rest] : [...rest, saved])
      setEditing(null)
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  return (
    <section className="subcard stack">
      <h4>{t('Ansprechpartner')}</h4>
      {items.length === 0 && <p className="muted small">{t('Noch keine Ansprechpartner.')}</p>}
      <ul className="item-list">
        {items.map((c) => (
          <li key={c.id} className="item-row">
            <div className="item-row-info">
              <strong>{`${c.first_name} ${c.last_name}`.trim()}</strong>
              {c.function && <span className="muted small"> · {c.function}</span>}
              {c.is_primary && <span className="muted small"> · {t('Hauptansprechpartner')}</span>}
              <div className="muted small">
                {[c.email, c.phone, c.receives_invoices ? t('erhält Rechnungen') : '']
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
                    setDraft({ ...c })
                    setEditing(c.id)
                  }}
                >
                  {t('Bearbeiten')}
                </button>
                <button
                  type="button"
                  className="button button-danger"
                  onClick={async () => {
                    if (
                      !(await confirmDialog({
                        final: true,
                        message: t('Ansprechpartner entfernen?'),
                        confirmLabel: t('Entfernen'),
                      }))
                    )
                      return
                    try {
                      await partnerApi.removeContact(org.id, partner.id, c.id)
                      setItems(items.filter((x) => x.id !== c.id))
                    } catch (err) {
                      setError(errorMessage(err))
                    }
                  }}
                >
                  {t('Entfernen')}
                </button>
              </div>
            )}
            <EditSlot id={editKey('partner-contact', c.id)} />
          </li>
        ))}
      </ul>
      {editing !== null && (
        <EditAt at={editing === 'new' ? null : editKey('partner-contact', editing)}>
          <div className="stack">
            <div className="form-grid">
              <Field
                label={t('Vorname')}
                value={draft.first_name ?? ''}
                onChange={(e) => setDraft({ ...draft, first_name: e.target.value })}
              />
              <Field
                label={t('Name')}
                required
                value={draft.last_name ?? ''}
                onChange={(e) => setDraft({ ...draft, last_name: e.target.value })}
              />
              <Field
                label={t('Funktion')}
                value={draft.function ?? ''}
                onChange={(e) => setDraft({ ...draft, function: e.target.value })}
              />
              <Field
                label={t('E-Mail')}
                type="email"
                value={draft.email ?? ''}
                onChange={(e) => setDraft({ ...draft, email: e.target.value })}
              />
              <Field
                label={t('Telefon')}
                type="tel"
                value={draft.phone ?? ''}
                onChange={(e) => setDraft({ ...draft, phone: e.target.value })}
              />
              <Field
                label={t('Notiz')}
                value={draft.notes ?? ''}
                onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
              />
            </div>
            <Checkbox
              label={t('Hauptansprechpartner')}
              checked={!!draft.is_primary}
              onChange={(is_primary) => setDraft({ ...draft, is_primary })}
            />
            <Checkbox
              label={t('erhält Rechnungen')}
              checked={!!draft.receives_invoices}
              onChange={(receives_invoices) => setDraft({ ...draft, receives_invoices })}
            />
            <Checkbox
              label={t('erhält Post')}
              checked={!!draft.receives_mail}
              onChange={(receives_mail) => setDraft({ ...draft, receives_mail })}
            />
            <div className="button-row">
              <button
                type="button"
                className="button button-primary"
                disabled={!draft.last_name?.trim()}
                onClick={() => void save()}
              >
                {t('Ansprechpartner speichern')}
              </button>
              <button type="button" className="button" onClick={() => setEditing(null)}>
                {t('Abbrechen')}
              </button>
            </div>
          </div>
        </EditAt>
      )}
      {error && <Alert kind="error">{error}</Alert>}
      {canEdit && editing === null && (
        <button
          type="button"
          className="button"
          onClick={() => {
            setDraft(emptyContact())
            setEditing('new')
          }}
        >
          {t('Ansprechpartner hinzufügen')}
        </button>
      )}
    </section>
  )
}
