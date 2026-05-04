export function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`
}

export function formatScore(value: number) {
  return value.toFixed(3)
}

export function formatLatency(value: number) {
  return `${Math.round(value)} ms`
}
