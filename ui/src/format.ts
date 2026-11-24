const whole = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 })
const fine = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 })
const finer = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 })

/** A credit amount: whole from 100, one decimal from 10, two below. A real turn can cost under a tenth of a credit. */
export function credits(value: number): string {
  if (!Number.isFinite(value)) return '-'
  const size = Math.abs(value)
  return size >= 100 ? whole.format(value) : size >= 10 ? fine.format(value) : finer.format(value)
}

/** A time the reader can place: "08:14" today, "Nov 23, 08:14" otherwise. */
export function when(iso: string): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  const sameDay = date.toDateString() === new Date().toDateString()
  return date.toLocaleString(undefined, sameDay ? { hour: '2-digit', minute: '2-digit' } : { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`
}
