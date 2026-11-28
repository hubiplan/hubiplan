// Abschnitt bearbeiten: Texte, Bilder und Gestaltung.
import type { HomeButton, HomeItem, HomeTile } from '../../api/website.ts'
import { TextEditor } from '../../components/texteditor/TextEditor.tsx'
import { Field } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { Why } from '../../learning/Aids.tsx'
import { emptyPicture, emptyTile } from './homeBuilderHelpers.ts'
import { Segments } from './Segments.tsx'
import { TargetField } from './TargetField.tsx'
import { TableField } from './TableField.tsx'

import { ItemList, type SectionContentProps } from './sectionContentShared.tsx'

export function SectionContentText({
  data,
  website,
  section,
  setData,
  imageField,
}: SectionContentProps) {
  const d = section.data ?? {}
  const titleField = (optional = true) => (
    <Field
      label={optional ? t('Überschrift (optional)') : t('Überschrift')}
      value={d.title ?? ''}
      maxLength={150}
      onChange={(e) => setData({ title: e.target.value })}
    />
  )
  switch (section.kind) {
    case 'text':
      return (
        <>
          {titleField()}
          <TextEditor
            label={t('Text')}
            value={d.text ?? ''}
            onChange={(text) => setData({ text })}
          />
        </>
      )
    case 'text_image':
      return (
        <>
          {titleField()}
          <TextEditor
            label={t('Text')}
            value={d.text ?? ''}
            rows={6}
            onChange={(text) => setData({ text })}
          />
          {imageField(t('Bild'), d.image, (image) => setData({ image }))}
          {!d.image && (
            <Field
              label={t('Notiz zum Bildplatz (optional)')}
              hint={t(
                'Noch kein Bild? Die Vorschau zeigt dann einen Platzhalter mit dieser Notiz, etwa „Probenszene, Querformat“. Auf der veröffentlichten Seite erscheint er nicht.',
              )}
              value={d.image_note ?? ''}
              maxLength={120}
              onChange={(e) => setData({ image_note: e.target.value })}
            />
          )}
          <Segments
            label={t('Bild steht')}
            value={d.side ?? 'right'}
            options={[
              ['left', t('links')],
              ['right', t('rechts')],
              ['top', t('über dem Text')],
              ['bottom', t('unter dem Text')],
            ]}
            onChange={(side) => setData({ side })}
          />
          <Segments
            label={t('Bildgröße')}
            value={d.size ?? 'half'}
            options={[
              ['small', t('klein')],
              [
                'half',
                d.side === 'top' || d.side === 'bottom' ? t('ganze Breite') : t('halbe Breite'),
              ],
            ]}
            onChange={(size) => setData({ size })}
          />
        </>
      )
    case 'cover':
      return (
        <>
          {imageField(t('Bild'), d.image, (image) => setData({ image }))}
          <p className="muted small">
            {t(
              'Das Titelbild steht immer ganz oben über der Überschrift, egal an welcher Stelle der Liste.',
            )}
          </p>
        </>
      )
    case 'banner':
      return (
        <>
          {imageField(t('Bild'), d.image, (image) => setData({ image }))}
          <Field
            label={t('Zeile auf dem Bild (optional)')}
            value={d.line ?? ''}
            maxLength={150}
            onChange={(e) => setData({ line: e.target.value })}
          />
          <Segments
            label={t('Höhe')}
            value={d.height ?? 'low'}
            options={[
              ['low', t('niedrig')],
              ['high', t('hoch')],
            ]}
            onChange={(height) => setData({ height })}
          />
        </>
      )
    case 'buttons': {
      const buttons = d.buttons ?? []
      const setButton = (i: number, patch: Partial<HomeButton>) =>
        setData({ buttons: buttons.map((b, j) => (j === i ? { ...b, ...patch } : b)) })
      return (
        <>
          {titleField()}
          {buttons.map((b, i) => (
            <fieldset key={i} className="home-item">
              <legend>{t('Knopf {n}', { n: i + 1 })}</legend>
              <Field
                label={t('Beschriftung')}
                value={b.label}
                maxLength={60}
                onChange={(e) => setButton(i, { label: e.target.value })}
              />
              <TargetField
                data={data}
                website={website}
                value={b.target}
                onChange={(target) => setButton(i, { target })}
              />
              {buttons.length > 1 && (
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() => setData({ buttons: buttons.filter((_, j) => j !== i) })}
                >
                  {t('Knopf entfernen')}
                </button>
              )}
            </fieldset>
          ))}
          {buttons.length < 3 && (
            <div className="button-row">
              <button
                type="button"
                className="button button-ghost"
                onClick={() => setData({ buttons: [...buttons, { label: '', target: null }] })}
              >
                {t('Knopf hinzufügen')}
              </button>
            </div>
          )}
          <Segments
            label={t('Ausrichtung')}
            value={d.align ?? 'left'}
            options={[
              ['left', t('links')],
              ['center', t('mittig')],
              ['right', t('rechts')],
            ]}
            onChange={(align) => setData({ align })}
          />
        </>
      )
    }
    case 'tiles': {
      const tiles = d.tiles ?? []
      const setTile = (i: number, patch: Partial<HomeTile>) =>
        setData({ tiles: tiles.map((k, j) => (j === i ? { ...k, ...patch } : k)) })
      return (
        <>
          {titleField()}
          {tiles.map((k, i) => (
            <fieldset key={i} className="home-item">
              <legend>{t('Kachel {n}', { n: i + 1 })}</legend>
              <Field
                label={t('Titel')}
                value={k.title}
                maxLength={150}
                onChange={(e) => setTile(i, { title: e.target.value })}
              />
              <Field
                label={t('Kurzer Text (optional)')}
                value={k.text}
                maxLength={500}
                onChange={(e) => setTile(i, { text: e.target.value })}
              />
              {imageField(t('Bild (optional)'), k.image, (image) => setTile(i, { image }))}
              <TargetField
                data={data}
                website={website}
                value={k.target}
                onChange={(target) => setTile(i, { target })}
              />
              <Field
                label={t('Knopftext (optional)')}
                hint={t(
                  'Mit Ziel steht unten in der Kachel ein Knopf, z. B. „Kontakt aufnehmen“. Ohne Knopftext wird der Titel zum Link.',
                )}
                value={k.button ?? ''}
                maxLength={60}
                onChange={(e) => setTile(i, { button: e.target.value })}
              />
              {tiles.length > 2 && (
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() => setData({ tiles: tiles.filter((_, j) => j !== i) })}
                >
                  {t('Kachel entfernen')}
                </button>
              )}
            </fieldset>
          ))}
          {tiles.length < 6 && (
            <div className="button-row">
              <button
                type="button"
                className="button button-ghost"
                onClick={() => setData({ tiles: [...tiles, emptyTile()] })}
              >
                {t('Kachel hinzufügen')}
              </button>
            </div>
          )}
          <Segments
            label={t('Spalten')}
            value={d.columns ?? 3}
            options={[
              [2, '2'],
              [3, '3'],
            ]}
            onChange={(columns) => setData({ columns })}
          />
        </>
      )
    }
    case 'quote':
      return (
        <>
          <Field
            label={t('Zitat')}
            value={d.text ?? ''}
            maxLength={1000}
            onChange={(e) => setData({ text: e.target.value })}
          />
          <Field
            label={t('Name (optional)')}
            value={d.name ?? ''}
            maxLength={150}
            onChange={(e) => setData({ name: e.target.value })}
          />
        </>
      )
    case 'divider':
      return (
        <>
          <Segments
            label={t('Art')}
            value={d.style ?? 'line'}
            options={[
              ['line', t('Linie')],
              ['space', t('Abstand')],
            ]}
            onChange={(style) => setData({ style })}
          />
          <Segments
            label={t('Größe')}
            value={d.size === 'large' ? 'large' : 'small'}
            options={[
              ['small', t('klein')],
              ['large', t('groß')],
            ]}
            onChange={(size) => setData({ size })}
          />
        </>
      )
    case 'columns': {
      const items = d.items?.length === 2 ? d.items : [{}, {}]
      const set = (i: number, patch: Partial<HomeItem>) =>
        setData({ items: items.map((x, j) => (j === i ? { ...x, ...patch } : x)) })
      return (
        <>
          {titleField()}
          {[0, 1].map((i) => (
            <fieldset key={i} className="home-item">
              <legend>{i === 0 ? t('Linke Spalte') : t('Rechte Spalte')}</legend>
              <Field
                label={t('Überschrift (optional)')}
                value={items[i].title ?? ''}
                maxLength={150}
                onChange={(e) => set(i, { title: e.target.value })}
              />
              <TextEditor
                label={t('Text')}
                value={items[i].text ?? ''}
                rows={5}
                onChange={(text) => set(i, { text })}
              />
            </fieldset>
          ))}
        </>
      )
    }
    case 'callout':
      return (
        <>
          <Segments
            label={t('Art')}
            value={d.style === 'warning' || d.style === 'success' ? d.style : 'info'}
            options={[
              ['info', t('Info')],
              ['warning', t('Achtung')],
              ['success', t('Erfolg')],
            ]}
            onChange={(style) => setData({ style })}
          />
          {titleField()}
          <TextEditor
            label={t('Text')}
            value={d.text ?? ''}
            rows={4}
            onChange={(text) => setData({ text })}
          />
        </>
      )
    case 'accordion':
      return (
        <>
          {titleField()}
          <ItemList
            items={d.items ?? []}
            min={1}
            max={12}
            legend={(n) => t('Abschnitt {n}', { n })}
            addLabel={t('Abschnitt hinzufügen')}
            removeLabel={t('Abschnitt entfernen')}
            empty={() => ({ title: '', text: '' })}
            onChange={(items) => setData({ items })}
            render={(item, set) => (
              <>
                <Field
                  label={t('Überschrift')}
                  value={item.title ?? ''}
                  maxLength={150}
                  onChange={(e) => set({ title: e.target.value })}
                />
                <TextEditor
                  label={t('Text')}
                  value={item.text ?? ''}
                  rows={5}
                  onChange={(text) => set({ text })}
                />
              </>
            )}
          />
        </>
      )
    case 'images':
      return (
        <>
          {titleField()}
          <ItemList
            items={d.items ?? []}
            min={1}
            max={8}
            legend={(n) => t('Bild {n}', { n })}
            addLabel={t('Bild hinzufügen')}
            removeLabel={t('Bild entfernen')}
            empty={emptyPicture}
            onChange={(items) => setData({ items })}
            render={(item, set) => (
              <>
                {imageField(t('Bild'), item.image, (image) => set({ image }))}
                {!item.image && (
                  <Field
                    label={t('Notiz zum Bildplatz (optional)')}
                    hint={t(
                      'Die Vorschau zeigt einen Platzhalter mit dieser Notiz, bis das Bild da ist.',
                    )}
                    value={item.note ?? ''}
                    maxLength={120}
                    onChange={(e) => set({ note: e.target.value })}
                  />
                )}
                <Field
                  label={t('Bildunterschrift (optional)')}
                  value={item.caption ?? ''}
                  maxLength={250}
                  onChange={(e) => set({ caption: e.target.value })}
                />
              </>
            )}
          />
          {(d.items ?? []).length > 1 ? (
            <Segments
              label={t('Spalten')}
              value={d.columns === 2 || d.columns === 4 ? d.columns : 3}
              options={[
                [2, '2'],
                [3, '3'],
                [4, '4'],
              ]}
              onChange={(columns) => setData({ columns })}
            />
          ) : (
            <p className="muted small">
              {t('Ein einzelnes Bild steht groß über die ganze Breite des Abschnitts.')}
            </p>
          )}
        </>
      )
    case 'video':
      return (
        <>
          <Field
            label={t('Adresse des Videos')}
            type="url"
            value={d.url ?? ''}
            maxLength={500}
            hint={t(
              'Die Webseite bettet das Video nicht ein. Wer auf das Bild klickt, schaut es beim Anbieter an.',
            )}
            onChange={(e) => setData({ url: e.target.value })}
          />
          <Why k="video_link" />
          {titleField()}
          {imageField(t('Vorschaubild (optional)'), d.image, (image) => setData({ image }))}
          <Field
            label={t('Kurzer Text (optional)')}
            value={d.text ?? ''}
            maxLength={500}
            onChange={(e) => setData({ text: e.target.value })}
          />
        </>
      )
    case 'table':
      return <TableField value={d} setData={setData} titleField={titleField()} />
    default:
      return null
  }
}
