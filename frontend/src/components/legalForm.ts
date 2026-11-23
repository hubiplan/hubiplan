const NBSP = '\u00a0'
// Rechtsform am Ende des Namens (e. V., e.V., gGmbH, GmbH, UG, eG, AG …)
const LEGAL_FORM =
  /\s+((?:e\.?\s?V|r\.\s?V|e\.\s?G|eG|g?GmbH|g?UG|AG|KG|mbH)\.?(?:\s?\(haftungsbeschränkt\))?)$/i

/**
 * Hält die Rechtsform beim Umbruch am letzten Wort fest, damit „e. V.“ nie allein in einer
 * Zeile steht (Ralf 23.11.2026, Anmeldeseite „Schützenkapelle Neuss-Furth / e.V.“).
 */
export function keepLegalForm(name: string): string {
  return name.replace(LEGAL_FORM, (_, form: string) => NBSP + form.replace(/\s/g, NBSP))
}
