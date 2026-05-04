const AMINO_ACID_PATTERN = /^[ACDEFGHIKLMNPQRSTVWY]+$/

export function validateProteinSequence(sequence: string) {
  const normalized = sequence.replace(/\s+/g, '').toUpperCase()

  if (!normalized) {
    return 'Sequence is required.'
  }

  if (!AMINO_ACID_PATTERN.test(normalized)) {
    return 'Sequence can only contain standard amino acid symbols: ACDEFGHIKLMNPQRSTVWY.'
  }

  if (normalized.length < 10) {
    return 'Sequence is too short for a useful inference request.'
  }

  if (normalized.length > 10000) {
    return 'Sequence is too long for the current UI limit.'
  }

  return null
}

export function normalizeProteinSequence(sequence: string) {
  return sequence.replace(/\s+/g, '').toUpperCase()
}
