// Gemeinsame Helfer, Typen und Konstanten von InvoicesPage.

/** Mitglieder als Rechnungsempfänger gibt es nur mit dem Modul (Dachverbände führen sie anders). */
export function hasMembersModule(org: { type: string; modules: string[] }): boolean {
  return org.type !== 'club' || org.modules.includes('members')
}
