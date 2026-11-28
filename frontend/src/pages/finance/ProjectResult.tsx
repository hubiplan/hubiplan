import { euro } from '../../api/finance.ts'

export function ProjectResult({ value }: { value: string }) {
  const n = Number(value)
  return <span className={n < 0 ? 'amount-out' : n > 0 ? 'amount-in' : ''}>{euro(value)}</span>
}
