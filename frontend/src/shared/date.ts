export const APP_TIME_ZONE = 'Asia/Bangkok'

export function formatDateTime(value?: string) {
  if (!value) {
    return '-'
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: APP_TIME_ZONE,
  }).format(new Date(value))
}

export function todayIsoDate() {
  const parts = new Intl.DateTimeFormat('en-CA', {
    day: '2-digit',
    month: '2-digit',
    timeZone: APP_TIME_ZONE,
    year: 'numeric',
  }).formatToParts(new Date())

  const values = Object.fromEntries(
    parts
      .filter((part) => part.type !== 'literal')
      .map((part) => [part.type, part.value]),
  )
  return `${values.year}-${values.month}-${values.day}`
}
