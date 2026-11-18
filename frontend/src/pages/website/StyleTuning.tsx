// Webseite › Feinabstimmung (Ralf 10.11.2026, Konzept webseite-baukasten G1; neu gegliedert
// 14.11.2026; übersichtlich nach Bereichen 16.11.2026, Konzept feinabstimmung-uebersichtlich):
// feste Stufen statt CSS. Links eine Leiste mit den Bereichen der Webseite (von oben nach unten),
// rechts die Regler des gewählten Bereichs mit Zwischenüberschriften. Zuerst stehen die
// wichtigsten Regler, der Rest unter „Weitere Einstellungen“. Verstellte Regler sind markiert
// und gezählt; was gerade nicht greift oder das Design festlegt, bleibt ausgegraut sichtbar und
// sagt, warum. Die Suche findet immer alle Regler. Auf dem Handy erst die Liste, dann der Bereich.
// Stufen, Sperren, Vorgaben und Voreinstellungen kommen aus HUBIplan (website/style.py),
// die Darstellungen der Bereiche aus website/variants.py; die Namen stehen hier.
import { useMemo, useState, type ReactNode } from 'react'
import { Link, NavLink } from 'react-router-dom'
import type { HomeSection, LayoutArea, StyleCatalog, StyleValues } from '../../api/website.ts'
import { t, tc } from '../../i18n/index.ts'
import { Sketch } from './AreaLayouts.tsx'
import { styleIcon } from './StyleIcons.tsx'

type Row = {
  key: string
  label: string
  options?: Record<string, string>
  hint?: string
}
/** Regler in einem Abschnitt: ``more`` = unter „Weitere Einstellungen“ */
type Slot = { key: string; more?: boolean }
type Part = { id: string; title: string; slots: Slot[] }
type Area = { id: string; title: string; icon: string; parts: Part[] }

const BASE = '/webseite/feinabstimmung'
const SHOW_ALL = 'hubiplan.feinabstimmung.alle'

const s = (key: string, more = false): Slot => ({ key, more })

/** Hinweis am Regler, wenn die Wahl schwer lesbar ist (UX-Audit WS-15) */
function readabilityWarning(key: string, value: unknown): string | null {
  if (key === 'heading_font' && value === 'fraktur')
    return t(
      'Fraktur ist für viele schwer lesbar. Am besten nur für kurze Überschriften verwenden, nicht für Namen oder Termine.',
    )
  if (key === 'script_greeting' && value === true)
    return t(
      'Schmuckschrift ist schwer lesbar. Die Begrüßung sollte dann kurz sein, längere Texte besser in der normalen Schrift.',
    )
  if (key === 'buttons' && value === 'label')
    return t(
      'Als Etikett stehen Knöpfe in kleinen Großbuchstaben. Das ist schwerer zu lesen; kurze Knopftexte helfen.',
    )
  return null
}
/** Darstellung eines Bereichs (variants.py) als Regler */
const layoutKey = (area: string) => `layout:${area}`

function ROWS(): Row[] {
  return [
    {
      key: 'font',
      label: t('Schriftart'),
      options: {
        system: t('System'),
        modern: t('Modern'),
        festive: t('Festlich'),
        clear: t('Klar'),
        elegant: t('Elegant'),
        readable: t('Gut lesbar'),
      },
      hint: t(
        'Modern: Open Sans und Roboto. Festlich: Open Sans, Überschriften mit Serifen. Klar: Source Sans 3. Elegant: Source Sans 3, Überschriften in Crimson Pro. Gut lesbar: Atkinson Hyperlegible.',
      ),
    },
    {
      key: 'heading_font',
      label: t('Schrift der Überschriften'),
      options: {
        text: t('wie der Text'),
        modern: t('Modern'),
        festive: t('Festlich'),
        clear: t('Klar'),
        elegant: t('Elegant'),
        fraktur: t('Fraktur'),
        strong: t('Kräftig'),
      },
      hint: t('Fraktur: UnifrakturMaguntia. Kräftig: Oswald, schmal und fett.'),
    },
    // #526: Hausschrift aus dem Styleguide, nur lokal installierte Schriften
    {
      key: 'font_family',
      label: t('Eigene Schriftfolge'),
      hint: t(
        'Namen von Schriften, die auf dem Gerät installiert sind, durch Komma getrennt, höchstens sechs. Wer die erste nicht hat, sieht die nächste; am Ende steht immer eine Ersatzschrift (mit „serif“ am Schluss eine mit Serifen). Auf Handys und unter Linux erscheint meist die Ersatzschrift. Geht der Schriftart vor und gilt auch für Überschriften, solange dort nichts anderes gewählt ist.',
      ),
    },
    {
      key: 'heading_font_family',
      label: t('Eigene Schriftfolge der Überschriften'),
      hint: t('Leer: wie oben eingestellt.'),
    },
    {
      key: 'headings',
      label: t('Stil der Überschriften'),
      options: {
        plain: t('schlicht'),
        line: t('mit Linie'),
        short: t('kurze Linie'),
        color: t('in Farbe'),
      },
    },
    {
      key: 'heading_align',
      label: t('Ausrichtung der Überschriften'),
      options: { left: t('links'), center: t('mittig') },
    },
    {
      key: 'heading_size',
      label: t('Größe der Überschriften'),
      options: { normal: t('normal'), large: t('größer') },
    },
    {
      key: 'title_size',
      label: t('Größe des Seitentitels'),
      options: {
        small: t('klein'),
        medium: t('mittel'),
        normal: t('normal'),
        large: t('größer'),
      },
      hint: t(
        'Nur die Überschrift oben auf der Seite; geht vor „Größe der Überschriften“. Klein oder mittel, wenn der Titel größer wirkt als der Name im Kopf.',
      ),
    },
    {
      key: 'leading',
      label: t('Zeilenabstand'),
      options: { tight: t('eng'), normal: t('normal'), airy: t('luftig') },
    },
    { key: 'script_greeting', label: t('Schmuckschrift für die Begrüßung') },
    {
      key: 'size',
      label: t('Schriftgröße'),
      options: { normal: t('normal'), large: t('größer'), xlarge: t('sehr groß') },
    },
    {
      key: 'contrast',
      label: t('Kontrast erhöht'),
      hint: t('Dunklere Schrift und kräftigere Linien, leichter zu lesen.'),
    },
    {
      key: 'dark',
      label: t('Dunkle Darstellung'),
      options: { off: t('aus'), auto: t('nach Gerät') },
      hint: t(
        'Nach Gerät: Wer sein Handy oder seinen Rechner dunkel eingestellt hat, sieht die Webseite dunkel. Kopf, Menü und Fuß behalten ihre Vereinsfarben.',
      ),
    },
    {
      key: 'stripes',
      label: t('Tabellen gestreift'),
      hint: t('Jede zweite Zeile hinterlegt, z. B. bei Ergebnissen und Ämtern.'),
    },
    { key: 'to_top', label: t('Knopf „Nach oben“ auf langen Seiten') },
    {
      key: 'motion',
      label: t('Beim Blättern einblenden'),
      options: { off: t('aus'), subtle: t('dezent') },
      hint: t('Wer am Gerät „weniger Bewegung“ eingestellt hat, sieht es nie.'),
    },
    {
      key: 'width',
      label: tc('Gestaltung', 'Breite'),
      options: { narrow: t('schmal'), normal: t('normal'), wide: t('breit') },
      hint: t('Schmal zeigt die Seite als Kasten auf dem Hintergrund.'),
    },
    {
      key: 'background',
      label: t('Hintergrund'),
      options: { light: t('hell'), tinted: t('getönt'), grey: t('grau') },
    },
    {
      key: 'spacing',
      label: t('Abstände'),
      options: { compact: t('kompakt'), normal: t('normal'), generous: t('großzügig') },
    },
    {
      key: 'corners',
      label: t('Ecken'),
      options: { square: t('eckig'), slight: t('leicht'), round: t('rund') },
    },
    {
      key: 'section_bg',
      label: t('Farbe heller Abschnitte'),
      options: { tinted: t('getönt'), warm: t('warm'), grey: t('grau') },
      hint: t('Farbe der Abschnitte mit hellem Hintergrund auf der Startseite.'),
    },
    {
      key: 'cards',
      label: t('Karten'),
      options: {
        border: t('Rahmen'),
        shadow: t('Schatten'),
        flat: t('flach'),
        accent: t('weiß mit Streifen'),
      },
      hint: t(
        'Weiß mit Streifen: weiße Karten mit feiner Kante, Termine mit Farbstreifen links, Kacheln der Untereinheiten oben.',
      ),
    },
    {
      key: 'images',
      label: t('Bilder'),
      options: { cards: t('wie Karten'), square: t('eckig') },
    },
    {
      key: 'tile_ratio',
      label: t('Bildformat in Kacheln'),
      options: { wide: '3:2', classic: '4:3', square: t('quadratisch') },
    },
    { key: 'image_frame', label: t('Rahmen um Bilder') },
    {
      key: 'buttons',
      label: t('Knöpfe'),
      options: { filled: t('gefüllt'), outline: t('umrandet'), label: t('Etikett') },
    },
    {
      key: 'header_bg',
      label: t('Hintergrund'),
      options: { white: t('weiß'), color: t('farbig'), image: t('Kopfbild') },
    },
    { key: 'logo', label: t('Wappen') },
    {
      key: 'logo_pos',
      label: t('Lage des Wappens'),
      options: { left: t('links'), center: t('mittig'), right: t('rechts') },
    },
    { key: 'name', label: t('Vereinsname') },
    {
      key: 'header_height',
      label: t('Höhe'),
      options: { low: t('niedrig'), medium: t('mittel'), normal: t('normal'), high: t('hoch') },
    },
    {
      key: 'line',
      label: t('Linie unter dem Kopf'),
      options: { none: t('keine'), thin: t('dünn'), strong: t('kräftig') },
    },
    { key: 'sticky', label: t('Oben anheften') },
    {
      key: 'nav',
      label: t('Form des Menüs'),
      options: { bar: t('Leiste'), buttons: t('Knöpfe'), text: t('Text') },
    },
    {
      key: 'nav_active',
      label: t('Aktiver Punkt'),
      options: { underline: t('Linie'), filled: t('hinterlegt') },
    },
    {
      key: 'nav_case',
      label: t('Schreibweise'),
      options: { normal: t('normal'), upper: t('GROSS') },
    },
    {
      key: 'nav_size',
      label: t('Schriftgröße im Menü'),
      options: { normal: t('normal'), large: t('größer') },
    },
    {
      key: 'nav_mobile',
      label: t('Menü auf dem Handy'),
      options: { toggle: t('aufklappbar'), scroll: t('Leiste zum Wischen') },
    },
    {
      key: 'nav_start',
      label: t('„Start“ im Menü'),
      hint: t(
        'Aus: Am Bildschirm führen Wappen, Name oder Kopfbild zur Startseite. Im Handymenü bleibt „Start“.',
      ),
    },
    {
      key: 'search',
      label: t('Lage der Suche'),
      options: { nav: t('im Menü'), header: t('oben rechts'), footer: t('im Fuß') },
    },
    {
      key: 'hero',
      label: t('Höhe'),
      options: { low: t('niedrig'), medium: t('mittel'), normal: t('normal'), high: t('hoch') },
    },
    {
      key: 'hero_width',
      label: tc('Gestaltung', 'Breite'),
      options: {
        content: t('ohne Bühne'),
        stage: t('in Inhaltsbreite'),
        full: t('randlos'),
      },
      hint: t(
        'Das Titelfoto der Startseite steht direkt unter dem Kopf, unten mit einem Verlauf in der Vereinsfarbe. Randlos reicht es über die ganze Breite, in Inhaltsbreite bleibt auf breiten Bildschirmen mehr vom Foto sichtbar. Titelzeilen und Oberzeile darauf stehen am Baustein „Bilderkarussell“ unter Startseite.',
      ),
    },
    {
      key: 'hero_stage_width',
      label: t('Breite der Bühne'),
      options: { content: t('wie der Inhalt'), wider: t('etwas breiter'), wide: t('breit') },
    },
    {
      key: 'hero_side',
      label: t('Fläche neben der Bühne'),
      options: { page: t('Seitenhintergrund'), color: t('dunkle Vereinsfarbe') },
    },
    {
      key: 'hero_shade',
      label: t('Abdunkeln'),
      options: { none: t('nein'), light: t('leicht'), strong: t('kräftig') },
      hint: t('Eine halb durchsichtige Farbe über dem Bild macht Schrift darauf besser lesbar.'),
    },
    {
      key: 'hero_tint',
      label: t('Färbung'),
      options: { dark: t('schwarz'), primary: t('Vereinsfarbe'), accent: t('Zweitfarbe') },
    },
    {
      key: 'hero_focus',
      label: t('Bildausschnitt'),
      options: { top: t('oben'), center: t('Mitte'), bottom: t('unten') },
      hint: t('Welcher Teil sichtbar bleibt, wenn das Bild beschnitten wird.'),
    },
    { key: 'hero_name', label: t('Name auf dem Titelbild') },
    {
      key: 'hero_text',
      label: t('Lage des Namens'),
      options: { top: t('oben'), center: t('mittig'), band: t('unten als Band') },
    },
    {
      key: 'carousel',
      label: t('Blättern'),
      options: {
        off: t('nur von Hand'),
        slow: t('langsam'),
        normal: t('normal'),
        random: t('zufällig'),
      },
      hint: t(
        'Langsam: doppelt so lange je Bild wie beim Karussell eingestellt. Zufällig: bei jedem Aufruf steht ein anderes Bild des Karussells fest als Titelbild.',
      ),
    },
    {
      key: 'carousel_controls',
      label: t('Knöpfe am Karussell'),
      options: { always: t('immer sichtbar'), hover: t('bei Mauszeiger') },
      hint: t(
        'Anhalten, Zurück, Weiter und Zähler. „bei Mauszeiger“: erst wenn die Maus über dem Bild steht oder die Tastatur darauf; auf Handys und Tablets bleiben sie sichtbar.',
      ),
    },
    {
      key: 'sections',
      label: t('Abschnitte trennen'),
      options: { none: t('nicht'), line: t('mit Linie'), alternate: t('abwechselnd getönt') },
    },
    {
      key: 'page_title',
      label: t('Seitentitel'),
      options: { plain: t('schlicht'), band: t('farbiges Band'), image: t('mit Titelbild') },
      hint: t('Mit Titelbild: das Bild der Startseite hinter der Überschrift.'),
    },
    // Webseite #148
    {
      key: 'unit_title',
      label: t('Band der Untereinheiten'),
      options: {
        primary: t('Vereinsfarbe'),
        box: t('Kastenfarbe'),
        light: t('hell'),
        plain: t('schlicht mit Linie'),
      },
      hint: t(
        'Nur auf den Seiten der Untereinheiten und nur bei Überschrift als Band: hell oder schlicht, damit das Band nicht wie ein zweiter Seitenkopf wirkt. Kastenfarbe ist die Farbrolle „Datumsfeld“.',
      ),
    },
    {
      key: 'date',
      label: t('Datum'),
      options: { tile: t('Kachel'), strip: t('Streifen'), card: t('Karten') },
      hint: t(
        'Karten: Die nächsten Termine auf der Startseite und den Seiten der Untereinheiten stehen als Karten nebeneinander mit großem Datum; der nächste Termin in der Vereinsfarbe.',
      ),
    },
    {
      key: 'date_text',
      label: t('Datum daneben'),
      options: {
        weekday: t('Wochentag'),
        short: t('Sa., 14.11.'),
        long: t('Samstag, 14. November'),
      },
    },
    // Webseite #135–#139 (Ralf 16.11.2026)
    {
      key: 'honors_layout',
      label: t('Würdenträger'),
      options: { list: t('Foto und Liste'), band: t('Band und Karten') },
      hint: t(
        'Band und Karten: Die amtierenden Würdenträger stehen groß als Band in der dunklen Vereinsfarbe unter dem Seitentitel, die letzten acht Vorgänger als Karten darunter; die ganze Liste lässt sich aufklappen.',
      ),
    },
    {
      key: 'portrait_placeholder',
      label: t('Personen ohne Foto'),
      options: { initial: t('Anfangsbuchstabe'), none: t('ohne Platzhalter') },
      hint: t(
        'Gilt für Vorstand, Ehrungen und Ansprechpartner der Untereinheiten. Fotos bleiben, wie sie sind.',
      ),
    },
    {
      key: 'person_cards',
      label: t('Karten der Personen'),
      options: { normal: t('schlicht'), label: t('Amt als Etikett') },
      hint: t(
        'Amt als Etikett: Amt klein in Großbuchstaben über dem Namen, Name in der Schrift der Überschriften, „Nachricht schreiben“ als Textlink, Kante oben in der Vereinsfarbe. Ehrenmitglieder stehen im Raster mit drei Spalten.',
      ),
    },
    // Webseite #143 (Ralf 16.11.2026)
    {
      key: 'honorary_layout',
      label: t('Ehrungen'),
      options: { list: t('Liste je Ehrung'), cards: t('eine Karte je Person') },
      hint: t(
        'Eine Karte je Person: Alle Geehrten stehen in einem gemeinsamen Raster wie der Vorstand, oben auf jeder Karte die Ehrung als Etikett. Hat jemand bei der Verleihung einen eigenen Titel (z. B. Ehrenhauptmann), steht dieser Titel auf der Karte.',
      ),
    },
    {
      key: 'timeline_chapter',
      label: t('Epochen der Chronik'),
      options: { plain: t('Zwischentitel'), band: t('als Band'), slim: t('als flaches Band') },
      hint: t(
        'Als Band: jede Epoche randlos in der dunklen Vereinsfarbe mit großem Zeitraum in der Zweitfarbe. Als flaches Band: Zeitraum und Titel in einer Zeile, deutlich niedriger. Bei beiden werden die Sprungmarken oben zu unterstrichenen Links.',
      ),
    },
    {
      key: 'ranking',
      label: t('Ranglisten der Ergebnisse'),
      options: { table: t('Tabelle'), podium: t('Plätze 1 bis 3 als Karten') },
      hint: t(
        'Die ersten drei Plätze jeder Wertung stehen als Karten mit großer Platzziffer über der Tabelle; bei Gleichstand bekommen alle Gleichplatzierten eine Karte.',
      ),
    },
    // Webseite #145 (Ralf 16.11.2026)
    {
      key: 'long_tables',
      label: t('Lange Listen'),
      options: { rows: t('untereinander'), columns: t('zweispaltig') },
      hint: t(
        'Zweispaltig: Listen mit mindestens 20 Zeilen und höchstens zwei Spalten (etwa Könige, Wanderpokale, Sieger je Jahr) stehen am Bildschirm in zwei Spalten nebeneinander, erst links von oben nach unten, dann rechts. Auf dem Handy bleibt es eine Spalte.',
      ),
    },
    {
      key: 'footer',
      label: t('Farbe'),
      options: { dark: t('dunkel'), light: t('hell'), color: t('farbig') },
    },
    {
      key: 'footer_align',
      label: t('Ausrichtung'),
      options: { left: t('links'), center: t('mittig'), right: t('rechts') },
    },
    {
      key: 'footer_layout',
      label: t('Aufbau'),
      options: { simple: t('schlicht'), full: t('mit Wappen und Name') },
      hint: t(
        'Mit Wappen und Name: links das Wappen, daneben Vereinsname, Gründungsjahr und Ort, rechts die Links untereinander und Social Media.',
      ),
    },
    {
      key: 'footer_name',
      label: t('Vereinsname neben dem Wappen'),
      hint: t(
        'Aus, wenn der Name schon im Wappen oder im Kopf steht. Der Hinweis auf den Dachverband rückt dann mittig neben das Wappen.',
      ),
    },
    { key: 'footer_founded', label: t('Gründungsjahr und Ort') },
    {
      key: 'footer_line',
      label: t('Linie über dem Fuß'),
      options: {
        none: t('keine'),
        ornament: t('Zierlinie'),
        accent: t('Zweitfarbe'),
        primary: t('Vereinsfarbe'),
      },
    },
  ]
}

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

/** Regler, die woanders stehen: die Suche verweist dorthin (F3) */
function MOVED(): { key: string; label: string; where: string; to: string }[] {
  return [
    {
      key: 'address',
      label: t('Anrede im Kontaktformular'),
      where: t('Webseite › Übersicht › Anrede'),
      to: '/webseite',
    },
  ]
}

/** Abhängige Regler stehen eingerückt unter dem Regler, von dem sie abhängen */
const DEPENDS: Record<string, string> = {
  logo_pos: 'logo',
  hero_stage_width: 'hero_width',
  hero_side: 'hero_width',
  hero_tint: 'hero_shade',
  hero_text: 'hero_name',
  footer_name: 'footer_layout',
  footer_founded: 'footer_layout',
}

/** Darstellungen der Bereiche (früher eigene Seite „Bereiche“) */
function LAYOUT_LABELS(): Record<string, string> {
  return {
    events: t('Ansicht der Termine'),
    board: t('Ansicht der Pinnwand'),
    units: t('Ansicht der Untereinheiten'),
    gallery: t('Ansicht der Galerie'),
  }
}

/** Namen der Bereiche für das Schild in der Vorschau („Zeigen“) */
export function tuningAreaNames(): Record<string, string> {
  return Object.fromEntries(AREAS().map((a) => [a.id, a.title]))
}

/** Namen der Voreinstellungen (Inhalt aus HUBIplan, style.PRESETS) */
const PRESET_LABELS: () => Record<string, { label: string; hint: string }> = () => ({
  calm: { label: t('Ruhig'), hint: t('Schlicht, viel Weißraum, wenig Farbe') },
  festive: { label: t('Festlich'), hint: t('Serifen, Schmuckschrift, Titelbild in Vereinsfarbe') },
  modern: { label: t('Modern'), hint: t('Runde Ecken, Schatten, Menü als Knöpfe') },
  readable: {
    label: t('Gut lesbar'),
    hint: t('Große Schrift, hoher Kontrast, gestreifte Tabellen'),
  },
})

// Schalter ohne eigene Wahl und ohne Vorgabe aus HUBIplan (ältere Server)
const SWITCH_DEFAULTS: Record<string, boolean> = {
  script_greeting: false,
  image_frame: false,
  logo: true,
  name: true,
  sticky: false,
  hero_name: false,
  contrast: false,
  to_top: false,
  nav_start: true,
  stripes: false,
  footer_name: true,
  footer_founded: true,
}
const SWITCH_BY_DESIGN: Record<string, Record<string, boolean>> = {
  stage: { sticky: true, hero_name: true },
  sidebar: { sticky: true },
}

/** Stelle der Webseite, die die Vorschau nach einer Änderung zeigt (Punkt 5) */
export type PreviewFocus = {
  target?: 'kopf' | 'fuss' | 'inhalt' | 'unterseite' | 'termine'
  device?: 'phone'
}

const INHALT = new Set([
  'cards',
  'images',
  'tile_ratio',
  'image_frame',
  'buttons',
  'headings',
  'heading_align',
])

export function previewFocus(key: string, eventsOn: boolean): PreviewFocus {
  if (key === 'nav_mobile') return { target: 'kopf', device: 'phone' }
  if (key === 'page_title' || key === 'title_size') return { target: 'unterseite' }
  if (key === 'unit_title') return { target: 'unterseite' }
  if (key === 'date' || key === 'date_text') return eventsOn ? { target: 'termine' } : {}
  if (key.startsWith('footer')) return { target: 'fuss' }
  if (key === 'search') return { target: 'kopf' }
  if (key.startsWith('layout:')) return { target: 'inhalt' }
  const area = AREAS().find((a) => a.parts.some((p) => p.slots.some((x) => x.key === key)))
  if (area?.id === 'kopf') return { target: 'kopf' }
  if (INHALT.has(key)) return { target: 'inhalt' }
  return {}
}

function readShowAll(): boolean {
  try {
    return window.localStorage.getItem(SHOW_ALL) === '1'
  } catch {
    return false
  }
}
function writeShowAll(on: boolean) {
  try {
    if (on) window.localStorage.setItem(SHOW_ALL, '1')
    else window.localStorage.removeItem(SHOW_ALL)
  } catch {
    // ohne Speicher gilt die Wahl bis zum Neuladen
  }
}

/** Eigene Schriftfolge (#526): Text mit Komma, übernommen beim Verlassen oder mit Enter. */
function FontStackInput({
  labelledBy,
  value,
  onCommit,
}: {
  labelledBy: string
  value: string
  onCommit: (next: string) => void
}) {
  // Der Aufrufer setzt key={value}: ein neuer Wert von außen beginnt mit frischem Text
  const [text, setText] = useState(value)
  function commit() {
    const next = text
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
      .join(', ')
    if (next !== value) onCommit(next)
    else setText(value)
  }
  return (
    <input
      type="text"
      className="style-fonts"
      aria-labelledby={labelledBy}
      value={text}
      maxLength={300}
      placeholder={t('z. B. Lucida Sans, Segoe UI, Arial')}
      spellCheck={false}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault()
          commit()
        }
      }}
    />
  )
}

/** Grund, warum ein Regler gerade nicht greift, mit Sprung zum Regler oder Link zur Stelle */
type Why = { text: string; jump?: string; link?: { to: string; label: string } }

export function StyleTuning({
  catalog,
  design,
  designLabel,
  value,
  onChange,
  headerImage,
  homeSections,
  blocks,
  onFocus,
  area,
  layoutCatalog,
  layouts,
  onLayouts,
  onUndo,
}: {
  catalog: StyleCatalog
  design: string
  designLabel: string
  value: StyleValues
  onChange: (next: StyleValues) => void
  /** Bildauswahl für „Hintergrund des Kopfes: Kopfbild“ */
  headerImage: ReactNode
  /** Abschnitte der Startseite (Titelbild vorhanden?); fehlt bei älteren Ständen */
  homeSections?: HomeSection[]
  /** Eingeschaltete Bausteine (Suche, Termine) */
  blocks?: Record<string, boolean>
  /** Nach einer Änderung: welche Stelle die Vorschau zeigen soll */
  onFocus?: (focus: PreviewFocus) => void
  /** Gewählter Bereich aus der Adresse (/webseite/feinabstimmung/<bereich>) */
  area?: string
  /** Darstellungen der Bereiche (variants.py); fehlt bei älteren Ständen */
  layoutCatalog?: LayoutArea[]
  layouts?: Record<string, string>
  onLayouts?: (next: Record<string, string>) => void
  /** Rückgängig (Gestaltung), für den Hinweis nach Voreinstellung und Zurücksetzen */
  onUndo?: () => void
}) {
  const areas = useMemo(() => AREAS(), [])
  const rows = useMemo(() => ROWS(), [])
  const moved = MOVED()
  const presets = PRESET_LABELS()
  const layoutLabels = LAYOUT_LABELS()
  const locks = catalog.locks[design] ?? {}
  const layoutValue = layouts ?? {}
  const layoutByArea = Object.fromEntries((layoutCatalog ?? []).map((a) => [a.area, a]))
  // Knöpfe am Karussell ohne Regler: auf der Bühne immer sichtbar, sonst bei Mauszeiger
  const designDefaults = catalog.defaults?.[design]
  const stageWidth =
    'hero_width' in locks ? undefined : (value.hero_width ?? designDefaults?.hero_width)
  const defaults: StyleValues = designDefaults
    ? {
        ...designDefaults,
        carousel_controls: stageWidth === 'stage' || stageWidth === 'full' ? 'always' : 'hover',
      }
    : {}
  const [query, setQuery] = useState('')
  const [showAll, setShowAll] = useState(readShowAll)
  const [openMore, setOpenMore] = useState<Record<string, boolean>>({})
  const [openHint, setOpenHint] = useState<Record<string, boolean>>({})
  const [notice, setNotice] = useState<string | null>(null)

  const rowByKey = useMemo(() => {
    const result: Record<string, Row> = Object.fromEntries(rows.map((r) => [r.key, r]))
    for (const [areaKey, label] of Object.entries(layoutLabels)) {
      result[layoutKey(areaKey)] = { key: layoutKey(areaKey), label }
    }
    return result
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [rows])
  // Bereich und Abschnitt je Regler; Darstellungen ohne festen Platz kommen zu „Bereiche“
  const placed = useMemo(() => {
    const result: { area: Area; part: Part; slot: Slot }[] = []
    const all = areas.map((a) => ({
      ...a,
      parts: a.parts.map((p) => ({ ...p, slots: [...p.slots] })),
    }))
    const known = new Set(all.flatMap((a) => a.parts.flatMap((p) => p.slots.map((x) => x.key))))
    const extra = (layoutCatalog ?? []).filter((l) => !known.has(layoutKey(l.area)))
    if (extra.length > 0) {
      const target = all.find((a) => a.id === 'bereiche')
      target?.parts.push({
        id: 'weitere',
        title: t('Weitere Bereiche'),
        slots: extra.map((l) => s(layoutKey(l.area))),
      })
    }
    for (const a of all)
      for (const p of a.parts) for (const x of p.slots) result.push({ area: a, part: p, slot: x })
    return { areas: all, list: result }
  }, [areas, layoutCatalog])

  /** Gibt es den Regler auf diesem Server? */
  function known(key: string): boolean {
    if (key.startsWith('layout:')) return key.slice(7) in layoutByArea
    return !!catalog.options[key] && key in rowByKey
  }
  function labelOf(key: string): string {
    if (key.startsWith('layout:')) {
      const areaKey = key.slice(7)
      return layoutLabels[areaKey] ?? areaKey
    }
    return rowByKey[key]?.label ?? key
  }

  function switchValue(style: StyleValues, key: string): boolean {
    const own = style[key]
    if (typeof own === 'boolean') return own
    const given = defaults[key]
    if (typeof given === 'boolean') return given
    return SWITCH_BY_DESIGN[design]?.[key] ?? SWITCH_DEFAULTS[key] ?? false
  }
  /** Wirksame Stufe: eigene Wahl, sonst Vorgabe des Designs */
  const effective = (key: string) => value[key] ?? defaults[key]
  /** Selbst verstellt? */
  const own = (key: string) =>
    key.startsWith('layout:') ? key.slice(7) in layoutValue : key in value

  const locked = (key: string, option?: string) => {
    if (!(key in locks)) return false
    const values = locks[key]
    return values === null || (option !== undefined && values.includes(option))
  }
  const wholeLocked = (key: string) =>
    !key.startsWith('layout:') && key in locks && locks[key] === null
  const lockedHint = t('Legt das Design „{design}“ selbst fest.', { design: designLabel })

  const hasHero =
    design === 'stage' ||
    homeSections === undefined ||
    homeSections.some((x) => x.key === 'carousel' && x.on)
  const eventsOn = blocks?.events !== false
  const toStructure = { to: '/webseite/aufbau', label: t('Menü und Seiten') }
  const noHero: Why = {
    text: t('Die Startseite zeigt kein Titelbild (Baustein „Bilderkarussell“).'),
    link: { to: '/webseite/startseite', label: t('Startseite') },
  }

  // U3 (F7): nicht verstecken, sondern sagen, warum es gerade nicht greift
  function why(key: string): Why | null {
    switch (key) {
      case 'logo_pos':
        return switchValue(value, 'logo')
          ? null
          : { text: t('Erst „Wappen“ einschalten.'), jump: 'logo' }
      case 'hero':
      case 'hero_width':
      case 'hero_shade':
      case 'hero_focus':
      case 'hero_name':
        return hasHero ? null : noHero
      case 'hero_tint':
        if (!hasHero) return noHero
        return (effective('hero_shade') ?? 'none') !== 'none'
          ? null
          : { text: t('Erst „Abdunkeln“ wählen.'), jump: 'hero_shade' }
      case 'hero_text':
        if (!hasHero) return noHero
        return design === 'stage' || switchValue(value, 'hero_name')
          ? null
          : { text: t('Erst „Name auf dem Titelbild“ einschalten.'), jump: 'hero_name' }
      case 'hero_side':
      case 'hero_stage_width':
        if (!hasHero) return noHero
        return effective('hero_width') === 'stage'
          ? null
          : { text: t('Nur bei Breite „in Inhaltsbreite“.'), jump: 'hero_width' }
      case 'search':
        return blocks === undefined || blocks.search !== false
          ? null
          : { text: t('Die Suche ist ausgeschaltet.'), link: toStructure }
      case 'date':
      case 'date_text':
        return eventsOn ? null : { text: t('Termine sind ausgeschaltet.'), link: toStructure }
      case 'footer_name':
      case 'footer_founded':
        return effective('footer_layout') === 'full'
          ? null
          : { text: t('Nur beim Aufbau „mit Wappen und Name“.'), jump: 'footer_layout' }
      default:
        if (key.startsWith('layout:') && blocks?.[key.slice(7)] === false)
          return { text: t('Der Bereich ist zurzeit ausgeschaltet.'), link: toStructure }
        return null
    }
  }

  function setKey(key: string, next: string | boolean | null) {
    setNotice(null)
    if (key.startsWith('layout:')) {
      const areaKey = key.slice(7)
      const result = { ...layoutValue }
      // Standard (erste Darstellung) wird nicht gespeichert
      if (next === null || next === layoutByArea[areaKey]?.variants[0]?.key) delete result[areaKey]
      else result[areaKey] = String(next)
      onLayouts?.(result)
      onFocus?.(previewFocus(key, eventsOn))
      return
    }
    const result = { ...value }
    if (next === null) delete result[key]
    else result[key] = next
    // Wappen und Vereinsname nie beide aus: der andere Schalter geht wieder an
    if (next === false && key === 'logo' && switchValue(result, 'name') === false)
      result.name = true
    if (next === false && key === 'name' && switchValue(result, 'logo') === false)
      result.logo = true
    onChange(result)
    onFocus?.(previewFocus(key, eventsOn))
  }

  /** Mehrere Regler auf einmal zurück (Abschnitt, Bereich, alles) */
  function resetKeys(keys: string[], message: string) {
    const styleKeys = keys.filter((k) => !k.startsWith('layout:'))
    const layoutKeys = keys.filter((k) => k.startsWith('layout:')).map((k) => k.slice(7))
    if (styleKeys.some((k) => k in value)) {
      const result = { ...value }
      for (const k of styleKeys) delete result[k]
      onChange(result)
    }
    if (layoutKeys.some((k) => k in layoutValue)) {
      const result = { ...layoutValue }
      for (const k of layoutKeys) delete result[k]
      onLayouts?.(result)
    }
    setNotice(message)
    onFocus?.({})
  }

  function applyPreset(name: string) {
    const preset = catalog.presets?.[name] ?? {}
    const result: StyleValues = { ...value }
    for (const [key, v] of Object.entries(preset)) {
      if (!(key in catalog.options)) continue
      if (typeof v === 'string' && locked(key, v)) continue
      if (locked(key)) continue
      result[key] = v
    }
    if (switchValue(result, 'logo') === false && switchValue(result, 'name') === false)
      result.name = true
    onChange(result)
    onFocus?.({})
    setNotice(t('Voreinstellung „{name}“ übernommen.', { name: presets[name]?.label ?? name }))
  }

  function toggleShowAll(on: boolean) {
    setShowAll(on)
    writeShowAll(on)
  }

  /** Text einer Stufe für Liste und Suche */
  function optionLabel(key: string, option: string | boolean): string {
    if (typeof option === 'boolean') return option ? t('an') : t('aus')
    if (key.startsWith('layout:'))
      return (
        layoutByArea[key.slice(7)]?.variants.find((v) => v.key === option)?.label ?? String(option)
      )
    return rowByKey[key]?.options?.[option] ?? option
  }

  function jumpTo(key: string) {
    setQuery('')
    const where = placed.list.find((x) => x.slot.key === key)
    if (where) setOpenMore((o) => ({ ...o, [`${where.area.id}/${where.part.id}`]: true }))
    window.setTimeout(() => {
      const el = document.getElementById(`style-row-${key}`)
      el?.scrollIntoView?.({ block: 'center' })
      el?.querySelector<HTMLElement>('button:not(.style-info), input, select')?.focus()
    }, 0)
  }

  const changedKeys = placed.list.map((x) => x.slot.key).filter((k) => known(k) && own(k))
  const changed = changedKeys.length
  const countIn = (a: Area) =>
    a.parts.reduce((n, p) => n + p.slots.filter((x) => known(x.key) && own(x.key)).length, 0)
  const current = placed.areas.find((a) => a.id === area)
  const showChanged = area === 'verstellt'
  // Ohne Bereich in der Adresse: am Bildschirm Schnellstart, auf dem Handy die Liste der Bereiche
  const isIndex = !current && !showChanged && area !== 'schnellstart'

  // Suche über Namen, Hinweise, Stufen und Abschnitte (Punkt 8)
  const q = query.trim().toLowerCase()
  function matches(key: string, part: Part, inArea: Area): boolean {
    const row = rowByKey[key]
    const options = key.startsWith('layout:')
      ? (layoutByArea[key.slice(7)]?.variants.map((v) => v.label) ?? [])
      : Object.values(row?.options ?? {})
    return [labelOf(key), row?.hint ?? '', part.title, inArea.title, ...options].some((x) =>
      x.toLowerCase().includes(q),
    )
  }

  // --- Darstellung eines Reglers -------------------------------------------------------------
  function renderControl(key: string, labelId: string): ReactNode {
    if (key.startsWith('layout:')) {
      const areaKey = key.slice(7)
      const variants = layoutByArea[areaKey]?.variants ?? []
      const chosen = layoutValue[areaKey] ?? variants[0]?.key
      return (
        <div
          className={`style-segments style-n${variants.length} style-sketches`}
          role="group"
          aria-labelledby={labelId}
        >
          {variants.map((variant, i) => (
            <button
              key={variant.key}
              type="button"
              aria-pressed={chosen === variant.key}
              className={['has-icon', i === 0 ? 'is-default' : ''].filter(Boolean).join(' ')}
              onClick={() => setKey(key, variant.key)}
            >
              <Sketch id={`${areaKey}:${variant.key}`} />
              <span>{variant.label}</span>
              {i === 0 && <span className="style-default-dot" aria-hidden="true" />}
            </button>
          ))}
        </div>
      )
    }
    const row = rowByKey[key]
    const options = catalog.options[key]
    if (options === 'fonts')
      return (
        <FontStackInput
          key={String(value[key] ?? '')}
          labelledBy={labelId}
          value={typeof value[key] === 'string' ? String(value[key]) : ''}
          onCommit={(next) => setKey(key, next || null)}
        />
      )
    if (options === 'switch')
      return (
        <label className="style-switch">
          <input
            type="checkbox"
            role="switch"
            aria-labelledby={labelId}
            checked={switchValue(value, key)}
            onChange={(e) => setKey(key, e.target.checked)}
          />
          <span aria-hidden="true">{switchValue(value, key) ? t('an') : t('aus')}</span>
          {!own(key) && <small className="muted">{t('wie das Design')}</small>}
        </label>
      )
    if (options.length > 5)
      return (
        <select
          className="style-select"
          aria-labelledby={labelId}
          value={typeof value[key] === 'string' ? String(value[key]) : ''}
          onChange={(e) => setKey(key, e.target.value || null)}
        >
          <option value="">
            {typeof defaults[key] === 'string'
              ? `${t('wie das Design')} (${row.options?.[String(defaults[key])] ?? defaults[key]})`
              : t('wie das Design')}
          </option>
          {options.map((option) => (
            <option key={option} value={option} disabled={locked(key, option)}>
              {row.options?.[option] ?? option}
            </option>
          ))}
        </select>
      )
    return (
      <div
        className={`style-segments style-n${options.length}`}
        role="group"
        aria-labelledby={labelId}
      >
        {options.map((option) => {
          const on = value[key] === option
          const off = locked(key, option)
          const isDefault = defaults[key] === option
          const icon = styleIcon(key, option)
          return (
            <button
              key={option}
              type="button"
              aria-pressed={on}
              disabled={off}
              className={[isDefault ? 'is-default' : '', icon ? 'has-icon' : '']
                .filter(Boolean)
                .join(' ')}
              title={
                off
                  ? lockedHint
                  : isDefault
                    ? t('So zeigt es das Design „{design}“.', { design: designLabel })
                    : undefined
              }
              onClick={() => setKey(key, on ? null : option)}
            >
              {icon}
              <span>{row.options?.[option] ?? option}</span>
              {isDefault && <span className="style-default-dot" aria-hidden="true" />}
            </button>
          )
        })}
      </div>
    )
  }

  function renderRow(key: string, context?: string): ReactNode {
    const row = rowByKey[key]
    const id = `style-${key.replace(':', '-')}`
    const label = labelOf(key)
    const reason = why(key)
    const isLocked = wholeLocked(key)
    const mine = own(key)
    const hint = row?.hint
    const hintOpen = !!openHint[key]
    return (
      <div
        key={key}
        id={`style-row-${key}`}
        className={[
          'style-row',
          DEPENDS[key] ? 'is-dependent' : '',
          mine ? 'is-changed' : '',
          reason || isLocked ? 'is-unavailable' : '',
        ]
          .filter(Boolean)
          .join(' ')}
      >
        <span className="style-label">
          <span className="style-label-line">
            <span id={id}>{label}</span>
            {hint && !reason && !isLocked && (
              <button
                type="button"
                className="style-info"
                aria-expanded={hintOpen}
                aria-label={t('Erklärung zu „{label}“', { label })}
                onClick={() => setOpenHint((o) => ({ ...o, [key]: !hintOpen }))}
              >
                i
              </button>
            )}
          </span>
          {context && <small className="muted">{context}</small>}
          {hint && hintOpen && <small className="muted style-hint">{hint}</small>}
        </span>
        <div className="style-control">
          {isLocked ? (
            <span className="muted small">
              {lockedHint} <Link to="/webseite/gestaltung">{t('Design wechseln')}</Link>
            </span>
          ) : reason ? (
            <span className="muted small">
              {reason.text}{' '}
              {reason.jump && (
                <button type="button" className="link-button" onClick={() => jumpTo(reason.jump!)}>
                  {t('Hin')}
                </button>
              )}
              {reason.link && <Link to={reason.link.to}>{reason.link.label}</Link>}
            </span>
          ) : (
            renderControl(key, id)
          )}
          {mine && (
            <button
              type="button"
              className="style-reset"
              aria-label={t('{label} zurücksetzen', { label })}
              title={t('Zurück auf das Design')}
              onClick={() => setKey(key, null)}
            >
              ↺
            </button>
          )}
        </div>
        {!isLocked && !reason && readabilityWarning(key, effective(key)) && (
          <p className="style-extra style-warn small" role="note">
            {readabilityWarning(key, effective(key))}
          </p>
        )}
        {key === 'header_bg' &&
          !isLocked &&
          (value.header_bg === 'image' || value.header_bg === undefined) && (
            <div className="style-extra">{headerImage}</div>
          )}
      </div>
    )
  }

  function renderPart(inArea: Area, part: Part): ReactNode {
    const id = `${inArea.id}/${part.id}`
    const slots = part.slots.filter((x) => known(x.key))
    const lockedHere = slots.filter((x) => wholeLocked(x.key))
    const usable = slots.filter((x) => !wholeLocked(x.key))
    const basic = usable.filter((x) => !x.more || own(x.key) || showAll)
    const more = usable.filter((x) => !basic.includes(x))
    if (usable.length === 0 && lockedHere.length === 0) return null
    const partChanged = slots.filter((x) => own(x.key)).length
    const moreOpen = !!openMore[id]
    const headingId = `style-part-${inArea.id}-${part.id}`
    return (
      <section key={part.id} className="style-part" aria-labelledby={headingId}>
        <div className="style-part-head">
          <h3 id={headingId}>{part.title}</h3>
          {partChanged > 0 && (
            <button
              type="button"
              className="link-button style-part-reset"
              onClick={() =>
                resetKeys(
                  slots.map((x) => x.key),
                  t('„{part}“ zurückgesetzt.', { part: part.title }),
                )
              }
            >
              ↺ {t('{n} verstellt', { n: partChanged })}
            </button>
          )}
        </div>
        {basic.map((x) => renderRow(x.key))}
        {more.length > 0 && (
          <>
            <button
              type="button"
              className="style-more"
              aria-expanded={moreOpen}
              onClick={() => setOpenMore((o) => ({ ...o, [id]: !moreOpen }))}
            >
              {moreOpen ? '▾' : '▸'} {t('Weitere Einstellungen ({n})', { n: more.length })}
              {!moreOpen && (
                <span className="muted">: {more.map((x) => labelOf(x.key)).join(', ')}</span>
              )}
            </button>
            {moreOpen && more.map((x) => renderRow(x.key))}
          </>
        )}
        {lockedHere.length > 0 && (
          <p className="muted small style-locked">
            {t('Legt das Design „{design}“ selbst fest: {list}.', {
              design: designLabel,
              list: lockedHere.map((x) => labelOf(x.key)).join(', '),
            })}{' '}
            <Link to="/webseite/gestaltung">{t('Design wechseln')}</Link>
          </p>
        )}
      </section>
    )
  }

  // --- Inhalt rechts ---------------------------------------------------------------------------
  function renderSearch(): ReactNode {
    const hits = placed.list.filter((x) => known(x.slot.key) && matches(x.slot.key, x.part, x.area))
    const movedHits = moved.filter((m) => m.label.toLowerCase().includes(q))
    return (
      <div className="style-results">
        {hits.map((x) => renderRow(x.slot.key, `${x.area.title} › ${x.part.title}`))}
        {movedHits.map((m) => (
          <div key={m.key} className="style-row is-unavailable">
            <span className="style-label">{m.label}</span>
            <span className="muted small">
              {t('Steht jetzt unter {where}.', { where: m.where })}{' '}
              <Link to={m.to}>{t('Hin')}</Link>
            </span>
          </div>
        ))}
        {hits.length === 0 && movedHits.length === 0 && (
          <p className="muted">{t('Kein Regler gefunden.')}</p>
        )}
      </div>
    )
  }

  function renderChanged(): ReactNode {
    return (
      <>
        <div className="style-area-head">
          <h2>{t('Verstellte Regler')}</h2>
        </div>
        {changed === 0 ? (
          <p className="muted">{t('Nichts verstellt. Alles zeigt, was das Design vorsieht.')}</p>
        ) : (
          <ul className="style-changed-list" aria-label={t('Verstellte Regler')}>
            {placed.list
              .filter((x) => known(x.slot.key) && own(x.slot.key))
              .map((x) => {
                const key = x.slot.key
                const v = key.startsWith('layout:') ? layoutValue[key.slice(7)] : value[key]
                return (
                  <li key={key} className="style-chip-item">
                    <Link
                      className="style-chip"
                      to={`${BASE}/${x.area.id}`}
                      onClick={() => jumpTo(key)}
                    >
                      {x.area.title} › {labelOf(key)}: <strong>{optionLabel(key, v)}</strong>
                    </Link>
                    <button
                      type="button"
                      className="style-chip-x"
                      aria-label={t('{label} zurücksetzen', { label: labelOf(key) })}
                      onClick={() => setKey(key, null)}
                    >
                      ×
                    </button>
                  </li>
                )
              })}
          </ul>
        )}
      </>
    )
  }

  function renderStart(): ReactNode {
    const presetNames = Object.keys(catalog.presets ?? {}).filter((n) => n in presets)
    return (
      <>
        <div className="style-area-head">
          <h2>{t('Schnellstart')}</h2>
        </div>
        <p className="muted small">
          {t(
            'Ohne eigene Wahl zeigt die Webseite, was das Design „{design}“ vorsieht; diese Stufe ist mit einem Punkt markiert. Links stehen die Bereiche der Webseite von oben nach unten.',
            { design: designLabel },
          )}{' '}
          <Link to="/webseite/gestaltung">{t('Design wechseln')}</Link>
        </p>
        {presetNames.length > 0 && (
          <section className="style-part" aria-labelledby="style-presets-label">
            <div className="style-part-head">
              <h3 id="style-presets-label">{t('Voreinstellungen')}</h3>
            </div>
            <p className="muted small">
              {t('Setzt mehrere Regler auf einmal; danach bleibt alles einzeln änderbar.')}
            </p>
            <div className="style-presets" role="group" aria-labelledby="style-presets-label">
              {presetNames.map((name) => (
                <button
                  key={name}
                  type="button"
                  className="style-preset"
                  onClick={() => applyPreset(name)}
                >
                  <strong>{presets[name].label}</strong>
                  <small className="muted">{presets[name].hint}</small>
                </button>
              ))}
            </div>
          </section>
        )}
        <div className="button-row">
          <button
            type="button"
            className="button button-ghost"
            disabled={changed === 0}
            onClick={() => resetKeys(changedKeys, t('Alles zurückgesetzt.'))}
          >
            {t('Alles zurücksetzen')}
          </button>
          <span className="muted small">
            {changed === 0
              ? t('Alles wie das Design.')
              : t('{n} Regler verstellt.', { n: changed })}
          </span>
        </div>
      </>
    )
  }

  function renderArea(a: Area): ReactNode {
    const n = countIn(a)
    const parts = a.parts.map((p) => renderPart(a, p)).filter(Boolean)
    return (
      <>
        <div className="style-area-head">
          <h2>{a.title}</h2>
          {n > 0 && (
            <button
              type="button"
              className="link-button"
              onClick={() =>
                resetKeys(
                  a.parts.flatMap((p) => p.slots.map((x) => x.key)),
                  t('Bereich „{area}“ zurückgesetzt.', { area: a.title }),
                )
              }
            >
              ↺ {t('Bereich zurücksetzen')}
            </button>
          )}
        </div>
        {parts.length > 0 ? (
          parts
        ) : (
          <p className="muted">{t('Hier gibt es auf diesem Server nichts einzustellen.')}</p>
        )}
      </>
    )
  }

  const navLink = (id: string, label: string, icon: string, count: number) => (
    <li key={id}>
      <NavLink
        to={`${BASE}/${id}`}
        className={({ isActive }) =>
          `style-nav-link${isActive || (id === 'schnellstart' && isIndex) ? ' active' : ''}`
        }
        onClick={() => setQuery('')}
      >
        <span className="style-nav-icon" aria-hidden="true">
          {icon}
        </span>
        <span>{label}</span>
        {count > 0 && (
          <span className="style-nav-count" aria-label={t('{n} verstellt', { n: count })}>
            {count}
          </span>
        )}
      </NavLink>
    </li>
  )

  return (
    <div className="style-tuning" data-index={isIndex ? '' : undefined}>
      <nav className="style-nav" aria-label={t('Bereiche der Feinabstimmung')}>
        <ul>
          {navLink('schnellstart', t('Schnellstart'), '★', 0)}
          {placed.areas.map((a) => navLink(a.id, a.title, a.icon, countIn(a)))}
          {navLink('verstellt', t('Nur Verstelltes'), '●', changed)}
        </ul>
      </nav>
      <div className="style-main">
        <Link className="style-back" to={BASE}>
          ‹ {t('Alle Bereiche')}
        </Link>
        <div className="style-tools">
          <label className="style-search">
            <span className="sr-only">{t('Regler suchen')}</span>
            <input
              type="search"
              placeholder={t('Regler suchen, z. B. Wappen oder Handy')}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <label className="style-switch style-show-all">
            <input
              type="checkbox"
              role="switch"
              checked={showAll}
              onChange={(e) => toggleShowAll(e.target.checked)}
            />
            <span>{t('Alle Regler zeigen')}</span>
          </label>
        </div>
        {notice && (
          <div className="style-notice" role="status">
            <span>{notice}</span>
            {onUndo && (
              <button
                type="button"
                className="link-button"
                onClick={() => {
                  setNotice(null)
                  onUndo()
                }}
              >
                {t('Rückgängig')}
              </button>
            )}
          </div>
        )}
        {q
          ? renderSearch()
          : showChanged
            ? renderChanged()
            : current
              ? renderArea(current)
              : renderStart()}
      </div>
    </div>
  )
}
