// Stammdaten, die viele Seiten zum Auswählen brauchen, über den gemeinsamen Zwischenspeicher
// (components/shared.ts). Der Schlüssel enthält immer die Einheit.
import { billingApi } from '../api/billing.ts'
import { financeApi } from '../api/finance.ts'
import { memberApi } from '../api/members.ts'
import { orgApi } from '../api/orgs.ts'
import { useShared } from './shared.ts'

/** Einstellungen der Kasse (Geschäftsjahr, Steuerbereiche, Schalter). */
export const useFinanceSettings = (org: number) =>
  useShared(`finance.settings:${org}`, () => financeApi.settings(org))

/** Konten der Kasse. */
export const useFinanceAccounts = (org: number) =>
  useShared(`finance.accounts:${org}`, () => financeApi.accounts(org))

/** Kategorien der Kasse. */
export const useFinanceCategories = (org: number) =>
  useShared(`finance.categories:${org}`, () => financeApi.categories(org))

/** Einstellungen der Abrechnung. */
export const useBillingSettings = (org: number) =>
  useShared(`billing.settings:${org}`, () => billingApi.settings(org))

/** Mitgliedsarten. */
export const useMemberTypes = (org: number) =>
  useShared(`members.types:${org}`, () => memberApi.types(org))

/** Untereinheiten zum Auswählen. */
export const useDepartmentChoices = (org: number) =>
  useShared(`orgs.departmentChoices:${org}`, () => orgApi.departmentChoices(org))
