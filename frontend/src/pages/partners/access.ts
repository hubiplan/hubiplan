// Wer sieht und pflegt Geschäftspartner? Eigenes Recht oder Kasse/Beiträge, weil Rechnungen
// und der Rechnungseingang die Liste brauchen (konzepte/geschaeftspartner.md, GP-3).
import { PERM } from '../../api/orgs.ts'
import type { PartnerKind, PartnerRole } from '../../api/partners.ts'
import { t } from '../../i18n/index.ts'

export function partnerAccess(permissions: string[]) {
  const has = (p: string) => permissions.includes(p)
  return {
    view: has(PERM.partnersView) || has(PERM.financeView) || has(PERM.billingView),
    edit: has(PERM.partnersEdit) || has(PERM.financeEdit) || has(PERM.billingEdit),
    /** Ganze Liste: Excel, Serienbrief und Verteiler nur mit dem Recht „Geschäftspartner“ */
    list: has(PERM.partnersView) || has(PERM.partnersEdit),
    /** Bank, Standardkategorie, Zahlungsziel, Künstlerkennzeichen */
    money: has(PERM.financeView) || has(PERM.billingView),
    moneyEdit: has(PERM.financeEdit) || has(PERM.billingEdit),
  }
}

export function kindLabel(kind: PartnerKind): string {
  return {
    company: t('Firma'),
    authority: t('Behörde/Amt'),
    association: t('Verein/Verband'),
    person: t('Privatperson'),
    other: t('Sonstiges'),
  }[kind]
}

export function roleLabel(role: PartnerRole): string {
  return {
    supplier: t('Lieferant'),
    service: t('Dienstleister'),
    customer: t('Kunde/Auftraggeber'),
    sponsor: t('Sponsor'),
    donor: t('Spender'),
    venue: t('Vermieter/Veranstaltungsort'),
    artist: t('Künstler/Musiker'),
    authority: t('Behörde'),
    press: t('Presse'),
    insurance: t('Versicherung'),
    bank: t('Bank'),
  }[role]
}
