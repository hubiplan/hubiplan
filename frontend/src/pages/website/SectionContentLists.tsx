// Abschnitt bearbeiten: Listen und Angaben des Vereins.
import { formatDateTime } from '../../components/forms.ts'
import { TextEditor } from '../../components/texteditor/TextEditor.tsx'
import { Checkbox, Field, SelectField } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import {
  emptyFact,
  emptyHours,
  emptyPartner,
  emptyProgram,
  emptyStation,
} from './homeBuilderHelpers.ts'
import { Segments } from './Segments.tsx'
import { ContactsField } from './ContactsField.tsx'

import { ItemList, PartnerImport, type SectionContentProps } from './sectionContentShared.tsx'

export function SectionContentLists({ data, section, setData, imageField }: SectionContentProps) {
  const d = section.data ?? {}
  const choices = data.home_choices
  const titleField = (optional = true) => (
    <Field
      label={optional ? t('Überschrift (optional)') : t('Überschrift')}
      value={d.title ?? ''}
      maxLength={150}
      onChange={(e) => setData({ title: e.target.value })}
    />
  )
  switch (section.kind) {
    case 'contacts':
      return <ContactsField data={data} value={d} setData={setData} titleField={titleField()} />
    case 'faq':
      return (
        <>
          {titleField()}
          <ItemList
            items={d.items ?? []}
            min={1}
            max={12}
            legend={(n) => t('Frage {n}', { n })}
            addLabel={t('Frage hinzufügen')}
            removeLabel={t('Frage entfernen')}
            empty={() => ({ question: '', answer: '' })}
            onChange={(items) => setData({ items })}
            render={(item, set) => (
              <>
                <Field
                  label={t('Frage')}
                  value={item.question ?? ''}
                  maxLength={150}
                  onChange={(e) => set({ question: e.target.value })}
                />
                <TextEditor
                  label={t('Antwort')}
                  value={item.answer ?? ''}
                  rows={4}
                  onChange={(answer) => set({ answer })}
                />
              </>
            )}
          />
        </>
      )
    case 'partners':
      return (
        <>
          {titleField()}
          <ItemList
            items={d.items ?? []}
            min={1}
            max={12}
            legend={(n) => t('Partner {n}', { n })}
            addLabel={t('Partner hinzufügen')}
            removeLabel={t('Partner entfernen')}
            empty={emptyPartner}
            onChange={(items) => setData({ items })}
            render={(item, set) => (
              <>
                <Field
                  label={t('Name')}
                  value={item.name ?? ''}
                  maxLength={120}
                  onChange={(e) => set({ name: e.target.value })}
                />
                {imageField(t('Logo (optional)'), item.image, (image) => set({ image }))}
                <Field
                  label={t('Link (optional)')}
                  type="url"
                  placeholder="https://"
                  value={item.url ?? ''}
                  maxLength={500}
                  onChange={(e) => set({ url: e.target.value })}
                />
              </>
            )}
          />
          <PartnerImport items={d.items ?? []} onChange={(items) => setData({ items })} />
        </>
      )
    case 'directions':
      return (
        <>
          <SelectField
            label={t('Ort')}
            value={d.place ?? ''}
            hint={t('Orte pflegst du unter Einstellungen › Orte.')}
            onChange={(e) => setData({ place: e.target.value ? Number(e.target.value) : null })}
          >
            <option value="">{t('Bitte wählen')}</option>
            {(choices?.places ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </SelectField>
          {titleField()}
          <Field
            label={t('Hinweis zur Anfahrt (optional)')}
            value={d.text ?? ''}
            maxLength={1000}
            onChange={(e) => setData({ text: e.target.value })}
          />
        </>
      )
    case 'facts':
      return (
        <>
          {titleField()}
          <ItemList
            items={d.items ?? []}
            min={2}
            max={6}
            legend={(n) => t('Zahl {n}', { n })}
            addLabel={t('Zahl hinzufügen')}
            removeLabel={t('Zahl entfernen')}
            empty={emptyFact}
            onChange={(items) => setData({ items })}
            render={(item, set) => (
              <>
                <Field
                  label={t('Zahl')}
                  value={item.value ?? ''}
                  maxLength={20}
                  hint={t('z. B. 1920 oder 350+')}
                  onChange={(e) => set({ value: e.target.value })}
                />
                <Field
                  label={t('Text')}
                  value={item.label ?? ''}
                  maxLength={60}
                  onChange={(e) => set({ label: e.target.value })}
                />
              </>
            )}
          />
        </>
      )
    case 'countdown': {
      const mode = d.mode === 'date' ? 'date' : 'event'
      const after = d.after === 'text' ? 'text' : 'hide'
      return (
        <>
          {titleField()}
          <Segments
            label={t('Zählt herunter bis')}
            value={mode}
            options={[
              ['event', t('Termin')],
              ['date', t('Datum und Uhrzeit')],
            ]}
            onChange={(next) => setData({ mode: next })}
          />
          {mode === 'event' ? (
            <SelectField
              label={t('Termin')}
              value={d.event ?? ''}
              hint={t('Nur öffentliche Termine. Gezählt wird bis zum Beginn.')}
              onChange={(e) => setData({ event: e.target.value ? Number(e.target.value) : null })}
            >
              <option value="">{t('Bitte wählen')}</option>
              {(choices?.events ?? []).map((e) => (
                <option key={e.id} value={e.id}>
                  {e.title} ({formatDateTime(e.starts_at)})
                </option>
              ))}
            </SelectField>
          ) : (
            <Field
              label={t('Datum und Uhrzeit')}
              type="datetime-local"
              value={d.at ?? ''}
              onChange={(e) => setData({ at: e.target.value })}
            />
          )}
          <Field
            label={t('Text unter dem Zähler (optional)')}
            value={d.text ?? ''}
            maxLength={500}
            onChange={(e) => setData({ text: e.target.value })}
          />
          <Segments
            label={t('Nach Ablauf')}
            value={after}
            options={[
              ['hide', t('ausblenden')],
              ['text', t('Text zeigen')],
            ]}
            onChange={(next) => setData({ after: next })}
          />
          {after === 'text' && (
            <Field
              label={t('Text nach Ablauf')}
              value={d.after_text ?? ''}
              maxLength={500}
              hint={t('z. B. „Das Sommerfest hat begonnen!“')}
              onChange={(e) => setData({ after_text: e.target.value })}
            />
          )}
        </>
      )
    }
    case 'join':
      return (
        <>
          {titleField()}
          <TextEditor
            label={t('Text')}
            value={d.text ?? ''}
            rows={4}
            onChange={(text) => setData({ text })}
          />
          <Field
            label={t('Beschriftung des Knopfs (optional)')}
            value={d.label ?? ''}
            maxLength={60}
            placeholder={t('Jetzt Mitglied werden')}
            hint={t(
              'Der Knopf führt zur Seite „Mitglied werden“. Der Abschnitt erscheint nur, wenn der Online-Antrag eingeschaltet ist.',
            )}
            onChange={(e) => setData({ label: e.target.value })}
          />
        </>
      )
    case 'donation':
      return (
        <>
          {titleField()}
          <TextEditor
            label={t('Text')}
            value={d.text ?? ''}
            rows={4}
            onChange={(text) => setData({ text })}
          />
          <Field
            label={t('Kontoinhaber')}
            value={d.holder ?? ''}
            maxLength={120}
            onChange={(e) => setData({ holder: e.target.value })}
          />
          <Field
            label={t('IBAN')}
            value={d.iban ?? ''}
            maxLength={42}
            onChange={(e) => setData({ iban: e.target.value })}
          />
          <Field
            label={t('BIC (optional)')}
            value={d.bic ?? ''}
            maxLength={11}
            onChange={(e) => setData({ bic: e.target.value })}
          />
          <Field
            label={t('Verwendungszweck')}
            value={d.purpose ?? ''}
            maxLength={120}
            onChange={(e) => setData({ purpose: e.target.value })}
          />
          <Field
            label={t('Spendenziel in Euro (optional)')}
            type="number"
            min={0}
            step={1}
            value={d.goal ?? ''}
            hint={t('Mit Ziel zeigt die Webseite einen Fortschrittsbalken.')}
            onChange={(e) => setData({ goal: e.target.value ? Number(e.target.value) : null })}
          />
          {d.goal ? (
            <Field
              label={t('Bisher gesammelt in Euro')}
              type="number"
              min={0}
              step={1}
              value={d.raised ?? ''}
              onChange={(e) => setData({ raised: e.target.value ? Number(e.target.value) : null })}
            />
          ) : null}
          <Field
            label={t('Link zu einer Spendenseite (optional)')}
            type="url"
            placeholder="https://"
            value={d.url ?? ''}
            maxLength={500}
            onChange={(e) => setData({ url: e.target.value })}
          />
          {d.url ? (
            <Field
              label={t('Beschriftung des Knopfs (optional)')}
              value={d.label ?? ''}
              maxLength={60}
              placeholder={t('Jetzt spenden')}
              onChange={(e) => setData({ label: e.target.value })}
            />
          ) : null}
        </>
      )
    case 'hours':
      return (
        <>
          {titleField()}
          <ItemList
            items={d.items ?? []}
            min={1}
            max={14}
            legend={(n) => t('Zeile {n}', { n })}
            addLabel={t('Zeile hinzufügen')}
            removeLabel={t('Zeile entfernen')}
            empty={emptyHours}
            onChange={(items) => setData({ items })}
            render={(item, set) => (
              <>
                <Field
                  label={t('Tag')}
                  value={item.day ?? ''}
                  maxLength={60}
                  hint={t('z. B. Dienstag oder Mo–Fr')}
                  onChange={(e) => set({ day: e.target.value })}
                />
                <Field
                  label={t('Uhrzeit')}
                  value={item.time ?? ''}
                  maxLength={60}
                  hint={t('z. B. 19:00–22:00 Uhr')}
                  onChange={(e) => set({ time: e.target.value })}
                />
                <Field
                  label={t('Hinweis (optional)')}
                  value={item.note ?? ''}
                  maxLength={120}
                  onChange={(e) => set({ note: e.target.value })}
                />
              </>
            )}
          />
          <Field
            label={t('Text darunter (optional)')}
            value={d.text ?? ''}
            maxLength={500}
            onChange={(e) => setData({ text: e.target.value })}
          />
        </>
      )
    case 'timeline':
      return (
        <>
          {titleField()}
          <ItemList
            items={d.items ?? []}
            min={1}
            max={12}
            legend={(n) => t('Station {n}', { n })}
            addLabel={t('Station hinzufügen')}
            removeLabel={t('Station entfernen')}
            empty={emptyStation}
            onChange={(items) => setData({ items })}
            render={(item, set) => (
              <>
                <Field
                  label={t('Zeitangabe')}
                  value={item.when ?? ''}
                  maxLength={60}
                  hint={t('z. B. 1920, Frühjahr 2026 oder 14:00 Uhr')}
                  onChange={(e) => set({ when: e.target.value })}
                />
                <Field
                  label={t('Titel')}
                  value={item.title ?? ''}
                  maxLength={150}
                  onChange={(e) => set({ title: e.target.value })}
                />
                <Field
                  label={t('Text (optional)')}
                  value={item.text ?? ''}
                  maxLength={500}
                  onChange={(e) => set({ text: e.target.value })}
                />
              </>
            )}
          />
        </>
      )
    case 'program':
      return (
        <>
          {titleField()}
          <ItemList
            items={d.items ?? []}
            min={1}
            max={40}
            legend={(n) => t('Programmpunkt {n}', { n })}
            addLabel={t('Programmpunkt hinzufügen')}
            removeLabel={t('Programmpunkt entfernen')}
            empty={() => ({ ...emptyProgram(), day: d.items?.at(-1)?.day ?? '' })}
            onChange={(items) => setData({ items })}
            render={(item, set) => (
              <>
                <Field
                  label={t('Tag')}
                  value={item.day ?? ''}
                  maxLength={60}
                  hint={t('Gleiche Tage hintereinander erscheinen unter einer Überschrift.')}
                  onChange={(e) => set({ day: e.target.value })}
                />
                <Field
                  label={t('Uhrzeit (optional)')}
                  value={item.time ?? ''}
                  maxLength={20}
                  onChange={(e) => set({ time: e.target.value })}
                />
                <Field
                  label={t('Programmpunkt')}
                  value={item.text ?? ''}
                  maxLength={500}
                  onChange={(e) => set({ text: e.target.value })}
                />
              </>
            )}
          />
          <Field
            label={t('Text darunter (optional)')}
            value={d.text ?? ''}
            maxLength={500}
            onChange={(e) => setData({ text: e.target.value })}
          />
        </>
      )
    case 'downloads': {
      const chosen = d.documents ?? []
      const docs = choices?.documents ?? []
      return (
        <>
          {titleField()}
          <p className="muted small">
            {t('Bis zu zehn veröffentlichte Dokumente aus Webseite › Dokumente.')}
          </p>
          {docs.length === 0 && (
            <p className="muted">{t('Noch keine Dokumente veröffentlicht.')}</p>
          )}
          {docs.map((doc) => (
            <Checkbox
              key={doc.id}
              label={doc.title}
              checked={chosen.includes(doc.id)}
              disabled={!chosen.includes(doc.id) && chosen.length >= 10}
              onChange={(on) =>
                setData({
                  documents: on ? [...chosen, doc.id] : chosen.filter((x) => x !== doc.id),
                })
              }
            />
          ))}
        </>
      )
    }
    case 'app':
      return (
        <>
          {titleField()}
          <TextEditor
            label={t('Text')}
            value={d.text ?? ''}
            rows={4}
            onChange={(text) => setData({ text })}
          />
          <Checkbox
            label={t('QR-Code zur Anmeldung zeigen')}
            checked={d.qr !== false}
            onChange={(qr) => setData({ qr })}
          />
          <Checkbox
            label={t('Link zur App bei Google Play zeigen')}
            checked={d.store !== false}
            onChange={(store) => setData({ store })}
          />
        </>
      )
    default:
      return null
  }
}
