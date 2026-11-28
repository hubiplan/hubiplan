// Gemeinsame Helfer, Typen und Konstanten von StyleTuning.
import { t } from '../../i18n/index.ts'

/** Regler in einem Abschnitt: ``more`` = unter „Weitere Einstellungen“ */
export type Slot = { key: string; more?: boolean }
export type Part = { id: string; title: string; slots: Slot[] }
export type Area = { id: string; title: string; icon: string; parts: Part[] }

export const s = (key: string, more = false): Slot => ({ key, more })

/** Darstellung eines Bereichs (variants.py) als Regler */
export const layoutKey = (area: string) => `layout:${area}`

/** Bereiche der Feinabstimmung, in der Reihenfolge der Webseite (F1, Ralf 16.11.2026) */
export function AREAS(): Area[] {
  return [
    {
      id: 'grundstil',
      title: t('Grundstil'),
      icon: '▦',
      parts: [
        {
          id: 'seite',
          title: t('Seite'),
          slots: [s('width'), s('background'), s('corners'), s('spacing', true)],
        },
        { id: 'karten', title: t('Karten und Knöpfe'), slots: [s('cards'), s('buttons')] },
        {
          id: 'bilder',
          title: t('Bilder'),
          slots: [s('images', true), s('image_frame', true), s('tile_ratio', true)],
        },
      ],
    },
    {
      id: 'schrift',
      title: t('Schrift'),
      icon: 'Aa',
      parts: [
        { id: 'schriftart', title: t('Schriftart'), slots: [s('font'), s('heading_font')] },
        {
          id: 'ueberschriften',
          title: t('Überschriften'),
          slots: [s('headings'), s('heading_align', true), s('heading_size', true)],
        },
        {
          id: 'text',
          title: t('Text'),
          slots: [s('leading', true), s('script_greeting', true)],
        },
        {
          id: 'profi',
          title: t('Für Fortgeschrittene'),
          slots: [s('font_family', true), s('heading_font_family', true)],
        },
      ],
    },
    {
      id: 'lesbarkeit',
      title: t('Lesbarkeit'),
      icon: '◐',
      parts: [
        {
          id: 'lesen',
          title: t('Lesen'),
          slots: [
            s('size'),
            s('contrast'),
            s('dark'),
            s('stripes', true),
            s('to_top', true),
            s('motion', true),
          ],
        },
      ],
    },
    {
      id: 'kopf',
      title: t('Kopf und Menü'),
      icon: '▔',
      parts: [
        {
          id: 'kopf',
          title: t('Kopf'),
          slots: [
            s('header_bg'),
            s('logo'),
            s('logo_pos'),
            s('header_height'),
            s('name', true),
            s('line', true),
            s('sticky', true),
          ],
        },
        {
          id: 'menue',
          title: t('Menü'),
          slots: [
            s('nav'),
            s('nav_active'),
            s('nav_case', true),
            s('nav_size', true),
            s('nav_start', true),
            s('search', true),
          ],
        },
        { id: 'handy', title: t('Auf dem Handy'), slots: [s('nav_mobile')] },
      ],
    },
    {
      id: 'startseite',
      title: t('Titelbild und Startseite'),
      icon: '▣',
      parts: [
        {
          id: 'titelbild',
          title: t('Titelbild'),
          slots: [
            s('hero'),
            s('hero_width'),
            s('hero_stage_width'),
            s('hero_side'),
            s('hero_focus', true),
          ],
        },
        { id: 'abdunkeln', title: t('Bild abdunkeln'), slots: [s('hero_shade'), s('hero_tint')] },
        {
          id: 'name',
          title: t('Name auf dem Titelbild'),
          slots: [s('hero_name'), s('hero_text')],
        },
        {
          id: 'karussell',
          title: t('Karussell'),
          slots: [s('carousel'), s('carousel_controls', true)],
        },
        {
          id: 'abschnitte',
          title: t('Abschnitte'),
          slots: [s('sections'), s('section_bg', true)],
        },
      ],
    },
    {
      id: 'unterseiten',
      title: t('Unterseiten'),
      icon: '▤',
      parts: [
        { id: 'seitentitel', title: t('Seitentitel'), slots: [s('page_title'), s('title_size')] },
        { id: 'einheiten', title: t('Untereinheiten'), slots: [s('unit_title')] },
      ],
    },
    {
      id: 'bereiche',
      title: t('Bereiche der Webseite'),
      icon: '☷',
      parts: [
        {
          id: 'termine',
          title: t('Termine'),
          slots: [s(layoutKey('events')), s('date'), s('date_text', true)],
        },
        { id: 'pinnwand', title: t('Pinnwand'), slots: [s(layoutKey('board'))] },
        { id: 'einheiten', title: t('Untereinheiten'), slots: [s(layoutKey('units'))] },
        { id: 'galerie', title: t('Galerie'), slots: [s(layoutKey('gallery'))] },
        {
          id: 'personen',
          title: t('Personen und Ehrungen'),
          slots: [
            s('honors_layout'),
            s('honorary_layout'),
            s('person_cards', true),
            s('portrait_placeholder', true),
          ],
        },
        { id: 'chronik', title: t('Chronik'), slots: [s('timeline_chapter')] },
        { id: 'kontakt', title: t('Kontakt'), slots: [s('contact_details')] },
        {
          id: 'ergebnisse',
          title: t('Ergebnisse'),
          slots: [s('ranking'), s('long_tables', true)],
        },
      ],
    },
    {
      id: 'fuss',
      title: t('Fuß'),
      icon: '▁',
      parts: [
        {
          id: 'fuss',
          title: t('Fuß'),
          slots: [
            s('footer'),
            s('footer_layout'),
            s('footer_name'),
            s('footer_founded'),
            s('footer_align', true),
            s('footer_line', true),
          ],
        },
      ],
    },
  ]
}

/** Namen der Bereiche für das Schild in der Vorschau („Zeigen“) */
export function tuningAreaNames(): Record<string, string> {
  return Object.fromEntries(AREAS().map((a) => [a.id, a.title]))
}

/** Stelle der Webseite, die die Vorschau nach einer Änderung zeigt (Punkt 5) */
export type PreviewFocus = {
  target?: 'kopf' | 'fuss' | 'inhalt' | 'unterseite' | 'termine'
  device?: 'phone'
}
