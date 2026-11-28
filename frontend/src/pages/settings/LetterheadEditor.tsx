import { useState } from 'react'
import { Link } from 'react-router-dom'
import { FONTS, WEB_FONTS } from '../../api/letterhead.ts'
import type { LetterheadFields, LetterheadState } from '../../api/letterhead.ts'
import { useAutoSave, useForm } from '../../components/forms.ts'
import { Alert, Checkbox, Field, SaveStatus, SelectField } from '../../components/ui.tsx'
import { TextArea } from './TextArea.tsx'
import { LogoUpload } from './LogoUpload.tsx'
import { t } from '../../i18n/index.ts'
import { Why } from '../../learning/Aids.tsx'
import { LetterPreview } from './LetterPreview.tsx'

const FIELDS: (keyof LetterheadFields)[] = [
  'mode',
  'form',
  'logo_position',
  'tagline',
  'font',
  'salutation',
  'closing',
  'show_bank',
  'account',
  'show_email',
  'show_phone',
  'show_website',
  'show_board',
  'show_register',
  'show_social',
  'heading_font',
  'font_fallback',
  'heading_font_fallback',
  'show_name',
  'head_name',
  'head_name_small',
  'logo_size',
  'line_color',
  'head_line',
  'footer_line',
  'title_color',
  'table_line_color',
  'table_stripe',
]

function slotName(slot: number): string {
  if (slot === 0) return t('Hauptfarbe')
  if (slot === 1) return t('Zweitfarbe')
  return t('Farbe {n}', { n: slot + 1 })
}

/** Auswahl aus der Palette der Einheit, mit Kontrast auf Weiß. */
function slotOptions(palette: LetterheadState['palette'] | undefined) {
  return (palette ?? []).map((p) => (
    <option key={p.slot} value={String(p.slot)}>
      {slotName(p.slot)} ({p.color},{' '}
      {t('Kontrast {x}:1', { x: p.contrast.toFixed(1).replace('.', ',') })})
    </option>
  ))
}

function pick(state: LetterheadState): LetterheadFields {
  return Object.fromEntries(
    FIELDS.map((k) => [k, state.letterhead[k]]),
  ) as unknown as LetterheadFields
}

export function LetterheadEditor({
  state,
  editable,
  save,
  preview,
  logoUploadUrl,
  reload,
}: {
  state: LetterheadState
  editable: boolean
  save: (changes: Partial<LetterheadFields>) => Promise<LetterheadState>
  preview: () => Promise<Blob>
  logoUploadUrl: string
  reload: () => Promise<LetterheadState>
}) {
  const [current, setCurrent] = useState(state)
  const form = useForm(pick(state))
  const { values: v, set, errors } = form
  const auto = useAutoSave(form, (changes) => save(changes), {
    enabled: editable,
    onSaved: (saved) => setCurrent(saved as LetterheadState),
  })
  const isUnit = state.organization.type === 'unit'
  const inherits = isUnit && (!current.may_have_own || v.mode === 'inherit')

  return (
    <form className="card card-wide" onSubmit={(e) => e.preventDefault()}>
      {editable && <SaveStatus auto={auto} />}
      <h2>
        {t('Briefbogen')} {state.organization.name}
      </h2>
      <p className="muted small">
        {t('Vorstandsmitglieder erzeugen daraus unter')}{' '}
        <Link to="/briefvorlage">{t('Briefvorlage erstellen')}</Link>{' '}
        {t(
          'ihre eigene Word-Vorlage mit Funktion und Kontaktweg. Gespeichert werden die erzeugten Dateien nicht.',
        )}
      </p>
      {isUnit && (
        <SelectField
          label={t('Briefbogen')}
          value={current.may_have_own ? v.mode : 'inherit'}
          disabled={!editable || !current.may_have_own}
          error={errors.mode}
          hint={
            current.may_have_own
              ? undefined
              : t('Einen eigenen Briefbogen gibt es nur mit eigenem Arbeitsbereich.')
          }
          onChange={(e) => set('mode', e.target.value as LetterheadFields['mode'])}
        >
          <option value="inherit">
            {t('wie')} {current.owner.is_self ? t('darüber') : current.owner.name}
            {t(', mit eigenem Namen als Zusatzzeile')}
          </option>
          <option value="own">{t('eigener Briefbogen')}</option>
        </SelectField>
      )}
      {inherits ? (
        <p className="muted">
          {t(
            'Es gilt der Briefbogen von {name}. Der Name {name2}  erscheint im Kopf als Zusatzzeile; Logo/Wappen ist das eigene, falls hinterlegt.',
            { name: current.owner.name, name2: state.organization.name },
          )}
        </p>
      ) : (
        <fieldset disabled={!editable}>
          <div className="grid-2">
            <SelectField
              label={t('Aufbau')}
              value={v.form}
              onChange={(e) => set('form', e.target.value as LetterheadFields['form'])}
            >
              <option value="b">{t('DIN 5008 Form B (Anschriftfeld 45 mm von oben)')}</option>
              <option value="a">{t('DIN 5008 Form A (Anschriftfeld 27 mm von oben)')}</option>
            </SelectField>
            <SelectField
              label={t('Logo/Wappen')}
              value={v.logo_position}
              onChange={(e) =>
                set('logo_position', e.target.value as LetterheadFields['logo_position'])
              }
            >
              <option value="right">{t('rechts im Kopf')}</option>
              <option value="left">{t('links im Kopf')}</option>
              <option value="none">{t('ohne Logo/Wappen')}</option>
            </SelectField>
            <Field
              label={t('Zusatzzeile im Kopf')}
              value={v.tagline}
              error={errors.tagline}
              placeholder={t('z. B. gegründet 1920')}
              onChange={(e) => set('tagline', e.target.value)}
            />
            <SelectField
              label={t('Schrift für den Text')}
              value={v.font}
              hint={t(
                'Office-Schriften sind überall vorhanden. Schriften der Webseite stehen im PDF eingebettet, in Word mit Ersatzschrift.',
              )}
              onChange={(e) => set('font', e.target.value)}
            >
              <optgroup label={t('Office-Schriften')}>
                {FONTS.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </optgroup>
              <optgroup label={t('Schriften der Webseite')}>
                {WEB_FONTS.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </optgroup>
            </SelectField>
            <SelectField
              label={t('Schrift für Name, Titel und Betreff')}
              value={v.heading_font}
              onChange={(e) => set('heading_font', e.target.value)}
            >
              <option value="">{t('wie der Text')}</option>
              <optgroup label={t('Office-Schriften')}>
                {FONTS.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </optgroup>
              <optgroup label={t('Schriften der Webseite')}>
                {WEB_FONTS.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </optgroup>
            </SelectField>
            {WEB_FONTS.includes(v.font) && (
              <SelectField
                label={t('Ersatzschrift in Word (Text)')}
                value={v.font_fallback}
                hint={t('Gilt, wenn {f} auf dem Rechner nicht installiert ist.', { f: v.font })}
                onChange={(e) => set('font_fallback', e.target.value)}
              >
                {FONTS.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </SelectField>
            )}
            {WEB_FONTS.includes(v.heading_font) && (
              <SelectField
                label={t('Ersatzschrift in Word (Überschriften)')}
                value={v.heading_font_fallback}
                hint={t('Gilt, wenn {f} auf dem Rechner nicht installiert ist.', {
                  f: v.heading_font,
                })}
                onChange={(e) => set('heading_font_fallback', e.target.value)}
              >
                {FONTS.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </SelectField>
            )}
            <Field
              label={t('Anrede')}
              value={v.salutation}
              error={errors.salutation}
              onChange={(e) => set('salutation', e.target.value)}
            />
            <Field
              label={t('Grußformel')}
              value={v.closing}
              error={errors.closing}
              onChange={(e) => set('closing', e.target.value)}
            />
          </div>
          <h3>{t('Kopf, Linien und Farben')}</h3>
          <div className="grid-2">
            <SelectField
              label={t('Größe von Logo/Wappen')}
              value={v.logo_size}
              disabled={v.logo_position === 'none'}
              onChange={(e) => set('logo_size', e.target.value as LetterheadFields['logo_size'])}
            >
              <option value="small">{t('klein')}</option>
              <option value="medium">{t('mittel')}</option>
              <option value="large">{t('groß')}</option>
            </SelectField>
            <SelectField
              label={t('Linienfarbe')}
              value={v.line_color}
              hint={t('Linie unter dem Kopf, über der Fußzeile und auf Folgeseiten.')}
              onChange={(e) => set('line_color', e.target.value as LetterheadFields['line_color'])}
            >
              {slotOptions(current.palette)}
            </SelectField>
            <SelectField
              label={t('Farbe von Titel und Betreff')}
              value={v.title_color}
              hint={t('z. B. „Rechnung“, „Stornorechnung“ und der Betreff der Word-Vorlage.')}
              onChange={(e) =>
                set('title_color', e.target.value as LetterheadFields['title_color'])
              }
            >
              <option value="black">{t('Schwarz')}</option>
              <option value="primary">{t('Hauptfarbe')}</option>
            </SelectField>
            <SelectField
              label={t('Linien in Tabellen')}
              value={v.table_line_color}
              hint={t('Kopf- und Summenlinie in Rechnungen und Quittungen.')}
              onChange={(e) =>
                set('table_line_color', e.target.value as LetterheadFields['table_line_color'])
              }
            >
              {slotOptions(current.palette)}
            </SelectField>
            <SelectField
              label={t('Streifen in Tabellen')}
              value={v.table_stripe}
              onChange={(e) =>
                set('table_stripe', e.target.value as LetterheadFields['table_stripe'])
              }
            >
              <option value="grey">{t('hellgrau')}</option>
              <option value="none">{t('keine Streifen')}</option>
              {(current.palette ?? []).map((p) => (
                <option key={p.slot} value={String(p.slot)}>
                  {t('{name}, hell', { name: slotName(p.slot) })}
                </option>
              ))}
            </SelectField>
          </div>
          <Checkbox
            label={t('Name als Text neben dem Logo')}
            hint={t(
              'Ausschalten, wenn das Logo den Namen schon enthält. Ohne Logo steht der Name immer da.',
            )}
            checked={v.show_name}
            onChange={(val) => set('show_name', val)}
          />
          {v.show_name && (
            <>
              <TextArea
                label={t('Name im Briefkopf')}
                value={v.head_name}
                error={errors.head_name}
                rows={2}
                hint={t(
                  'Höchstens zwei Zeilen, umbrochen wie hier eingegeben. Leer: der Name der Einheit; ein langer Name wird dann verkleinert und ausgewogen auf zwei Zeilen verteilt. Folgeseiten und Rücksendeangabe zeigen immer den vollen Namen.',
                )}
                onChange={(val) => set('head_name', val)}
              />
              {v.head_name.trim().includes('\n') && (
                <Checkbox
                  label={t('Zweite Zeile kleiner')}
                  checked={v.head_name_small}
                  onChange={(val) => set('head_name_small', val)}
                />
              )}
            </>
          )}
          {v.logo_position !== 'none' && (
            <>
              <h3>{t('Logo für den Briefbogen')}</h3>
              <p className="muted small">
                {t(
                  'Ohne eigenes Logo gilt das Logo aus dem Erscheinungsbild. Ein eigenes passt z. B., wenn Briefe eine querformatige Wort-Bild-Marke statt des Wappens zeigen sollen. Es gilt nur für Word-Vorlage und PDF-Briefe.',
                )}
              </p>
              {editable ? (
                <LogoUpload
                  uploadUrl={logoUploadUrl}
                  logoUrl={current.logo_url ?? null}
                  onChange={async () => setCurrent(await reload())}
                />
              ) : current.logo_url ? (
                <img
                  src={current.logo_url}
                  alt={t('Logo für den Briefbogen')}
                  className="logo-preview"
                />
              ) : (
                <p className="muted">{t('wie im Erscheinungsbild')}</p>
              )}
            </>
          )}
          <Checkbox
            label={t('Linie unter dem Kopf')}
            checked={v.head_line}
            onChange={(val) => set('head_line', val)}
          />
          <Checkbox
            label={t('Linie über der Fußzeile')}
            checked={v.footer_line}
            onChange={(val) => set('footer_line', val)}
          />
          <h3>{t('Fußzeile')}</h3>
          <Checkbox
            label={t('Bankverbindung')}
            checked={v.show_bank}
            onChange={(val) => set('show_bank', val)}
          />
          {v.show_bank && (
            <SelectField
              label={t('Bankkonto')}
              value={v.account ?? ''}
              error={errors.account}
              hint={
                current.accounts.length === 0
                  ? t(
                      'Es gibt noch kein aktives Bankkonto mit IBAN (Finanzen › Einrichtung › Konten).',
                    )
                  : undefined
              }
              onChange={(e) => set('account', e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">{t('erstes aktives Bankkonto')}</option>
              {current.accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} ({a.iban})
                </option>
              ))}
            </SelectField>
          )}
          <Checkbox
            label={t('Telefon der Einheit')}
            checked={v.show_phone}
            onChange={(val) => set('show_phone', val)}
          />
          <Checkbox
            label={t('E-Mail der Einheit')}
            checked={v.show_email}
            onChange={(val) => set('show_email', val)}
          />
          <Checkbox
            label={t('Webseite')}
            checked={v.show_website}
            onChange={(val) => set('show_website', val)}
          />
          <Checkbox
            label={t('Social-Media-Kanäle (Einstellungen › Organisation)')}
            checked={v.show_social}
            onChange={(val) => set('show_social', val)}
          />
          <Checkbox
            label={t('Vorstand: Vertretungsberechtigte und Rollen mit „auf dem Briefbogen nennen“')}
            checked={v.show_board}
            onChange={(val) => set('show_board', val)}
          />
          {v.show_board && (
            <p className="muted small">
              {current.board.length > 0
                ? t('Heute: {x}.', {
                    x: current.board
                      .map((b) => (b.role ? `${b.name} (${b.role})` : b.name))
                      .join(', '),
                  })
                : t('Heute steht dort niemand.')}{' '}
              {t('Welche Rollen erscheinen, legst du unter')}{' '}
              <Link to="/einstellungen/rollen">{t('Rollen und Rechte')}</Link>{' '}
              {t('fest; private Kontaktdaten anderer erscheinen nie.')}
            </p>
          )}
          <Checkbox
            label={t('Registerangaben und USt-IdNr. aus dem Impressum')}
            checked={v.show_register}
            onChange={(val) => set('show_register', val)}
          />
          <Why k="letterhead_register" />
        </fieldset>
      )}
      {current.hints.length > 0 && (
        <Alert kind="info" as="div">
          <ul className="plain-list">
            {current.hints.map((h) => (
              <li key={h}>{h}</li>
            ))}
          </ul>
        </Alert>
      )}
      <h3>{t('Vorschau')}</h3>
      {/* Vorschau zeigt den gespeicherten Stand; offene Änderungen kenntlich machen (NAF-01) */}
      {editable && auto.state !== 'saved' && auto.state !== 'idle' && (
        <p className="small" role="status">
          {auto.state === 'error'
            ? t('Vorschau veraltet: Die letzten Änderungen sind noch nicht gespeichert.')
            : t('Änderungen werden gespeichert, danach erneuert sich die Vorschau.')}
        </p>
      )}
      <LetterPreview load={preview} version={current.letterhead.updated_at} />
    </form>
  )
}
