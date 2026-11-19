// Suche in der Hilfe: Wörter, die Menschen statt der Begriffe von HUBIplan eintippen.
//
// Jede Zeile ist eine Gruppe gleichbedeutender Wörter (klein geschrieben, als Teilwort
// gesucht). Tippt jemand eines davon, zählt auch ein Treffer mit einem anderen Wort der
// Gruppe. Bewusst kurz: nur Wörter, die sonst nichts finden.
const GROUPS: string[][] = [
  ['homepage', 'website', 'internetseite', 'webseite'],
  ['newsletter', 'rundmail', 'rundbrief', 'serienmail', 'rundschreiben', 'circular'],
  ['serienbrief', 'brief', 'letter'],
  ['benutzer', 'user', 'nutzer', 'login', 'zugang', 'konto', 'account'],
  ['backup', 'datensicherung', 'sicherung', 'sichern', 'datenübernahme', 'data transfer'],
  ['rücklastschrift', 'rückbuchung', 'geplatzt', 'zurückgegeben', 'returned'],
  ['kündigung', 'kündigen', 'austritt', 'austreten', 'cancellation', 'leaving'],
  ['passwort', 'kennwort', 'password'],
  ['spam', 'junk', 'zustellung', 'postausgang', 'outbox'],
  ['vorstandswechsel', 'neuer vorstand', 'amtswechsel', 'vorstand', 'board'],
  ['beitragserhöhung', 'erhöhen', 'beitrag ändern', 'beitragssatz', 'fee rate'],
  ['spendenquittung', 'spendenbescheinigung', 'zuwendungsbestätigung', 'donation receipt'],
  ['abbuchung', 'bankeinzug', 'einzug', 'lastschrift', 'direct debit'],
  ['mahnung', 'zahlungserinnerung', 'mahnen', 'reminder'],
  ['umzug', 'umgezogen', 'adressänderung', 'neue adresse', 'anschrift', 'address'],
  ['verstorben', 'tod', 'todesfall', 'gestorben', 'deceased'],
  ['dsgvo', 'datenschutz', 'auskunft', 'gdpr', 'privacy'],
  ['handy', 'smartphone', 'app'],
  ['excel', 'tabelle', 'export', 'csv'],
  ['2fa', 'zwei-faktor', 'zweifaktor', 'two-factor', 'authenticator'],
  ['protokoll', 'niederschrift', 'minutes'],
  ['abteilung', 'sparte', 'gruppe', 'untereinheit', 'sub-unit'],
  ['rechnung', 'faktura', 'invoice'],
  ['jahreswechsel', 'neues jahr', 'jahresende', 'turn of the year'],
  ['ki', 'chatgpt', 'claude', 'assistent', 'assistant'],
]

const BY_WORD = new Map<string, string[]>()
for (const group of GROUPS) for (const word of group) BY_WORD.set(word, group)

/** Das Wort und, falls bekannt, seine gleichbedeutenden Wörter. */
export function variants(word: string): string[] {
  const w = word.toLocaleLowerCase()
  return BY_WORD.get(w) ?? [w]
}

/** Für Tests: alle Gruppen */
export const SYNONYM_GROUPS = GROUPS
