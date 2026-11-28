// Katalog der Feinabstimmung: jeder Stilregler mit Bereich, Beschriftung, Abhängigkeiten und
// Vorgaben. Die Seite dazu ist StyleTuning.tsx.
import { t, tc } from '../../i18n/index.ts'
import { AREAS, type PreviewFocus } from './styleTuningHelpers.ts'

export type Row = {
  key: string
  label: string
  options?: Record<string, string>
  hint?: string
}
export const BASE = '/webseite/feinabstimmung'
export function ROWS(): Row[] {
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
      key: 'contact_details',
      label: t('Kontaktangaben neben dem Formular'),
      hint: t(
        'Neben dem Kontaktformular stehen Anschrift, Telefon und E-Mail aus den Vereinsdaten. Ausgeschaltet zeigt die Seite nur das Formular.',
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

/** Regler, die woanders stehen: die Suche verweist dorthin (F3) */
export function MOVED(): { key: string; label: string; where: string; to: string }[] {
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
export const DEPENDS: Record<string, string> = {
  logo_pos: 'logo',
  hero_stage_width: 'hero_width',
  hero_side: 'hero_width',
  hero_tint: 'hero_shade',
  hero_text: 'hero_name',
  footer_name: 'footer_layout',
  footer_founded: 'footer_layout',
}

/** Darstellungen der Bereiche (früher eigene Seite „Bereiche“) */
export function LAYOUT_LABELS(): Record<string, string> {
  return {
    events: t('Ansicht der Termine'),
    board: t('Ansicht der Pinnwand'),
    units: t('Ansicht der Untereinheiten'),
    gallery: t('Ansicht der Galerie'),
  }
}

/** Namen der Voreinstellungen (Inhalt aus HUBIplan, style.PRESETS) */
export const PRESET_LABELS: () => Record<string, { label: string; hint: string }> = () => ({
  calm: { label: t('Ruhig'), hint: t('Schlicht, viel Weißraum, wenig Farbe') },
  festive: { label: t('Festlich'), hint: t('Serifen, Schmuckschrift, Titelbild in Vereinsfarbe') },
  modern: { label: t('Modern'), hint: t('Runde Ecken, Schatten, Menü als Knöpfe') },
  readable: {
    label: t('Gut lesbar'),
    hint: t('Große Schrift, hoher Kontrast, gestreifte Tabellen'),
  },
})

// Schalter ohne eigene Wahl und ohne Vorgabe aus HUBIplan (ältere Server)
export const SWITCH_DEFAULTS: Record<string, boolean> = {
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
export const SWITCH_BY_DESIGN: Record<string, Record<string, boolean>> = {
  stage: { sticky: true, hero_name: true },
  sidebar: { sticky: true },
}

export const INHALT = new Set([
  'cards',
  'images',
  'tile_ratio',
  'image_frame',
  'buttons',
  'headings',
  'heading_align',
])

/** Welche Stelle die Vorschau nach einer Änderung am Regler zeigt */
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
