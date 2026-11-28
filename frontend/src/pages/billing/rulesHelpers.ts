// Gemeinsame Helfer, Typen und Konstanten von RulesPage.
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { useBillingSettings } from '../../components/masterData.ts'

export function useOrgBillingSettings() {
  const org = useActiveOrg()
  const settings = useBillingSettings(org.id)
  return { org, settings }
}
