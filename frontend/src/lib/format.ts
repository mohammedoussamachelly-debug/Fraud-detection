const numberFormatter = new Intl.NumberFormat('en-US')

const dateTimeFormatter = new Intl.DateTimeFormat('en-US', {
  dateStyle: 'medium',
  timeStyle: 'short',
})

const dateFormatter = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium' })

export function formatCurrency(value: number | string): string {
  // Preserve cents on Numeric(18,2) amounts beyond Number.MAX_SAFE_INTEGER.
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(String(value))
  if (!match) return '—'
  const [, sign, integer, fraction = ''] = match
  const cents =
    BigInt(integer) * 100n +
    BigInt((fraction + '00').slice(0, 2)) +
    (Number(fraction[2] ?? 0) >= 5 ? 1n : 0n)
  return `${sign}${numberFormatter.format(cents / 100n)}.${String(cents % 100n).padStart(2, '0')}`
}

export function formatNumber(value: number): string {
  return numberFormatter.format(value)
}

export function formatPercent(value: number, fractionDigits = 1): string {
  return `${(value * 100).toFixed(fractionDigits)}%`
}

export function formatDateTime(value: string | Date): string {
  const date = typeof value === 'string' ? new Date(value) : value
  return dateTimeFormatter.format(date)
}

export function formatDate(value: string | Date): string {
  const date = typeof value === 'string' ? new Date(value) : value
  return dateFormatter.format(date)
}

/** Shortens a UUID to its first 8 characters for compact display, e.g. in a table cell. */
export function shortId(id: string): string {
  return id.slice(0, 8)
}
