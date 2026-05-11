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

export interface FastaRecord {
  id: string
  description: string
  sequence: string
}

export function parseFasta(content: string): FastaRecord[] {
  if (!content.trim()) {
    throw new Error('FASTA content is required.')
  }
  if (!content.trimStart().startsWith('>')) {
    throw new Error('FASTA content must start with a header line beginning with ">".')
  }

  const records: FastaRecord[] = []
  let currentHeader = ''
  let sequenceLines: string[] = []

  function pushCurrent() {
    if (!currentHeader) {
      return
    }
    const [id = '', ...descriptionParts] = currentHeader.trim().split(/\s+/)
    const sequence = normalizeProteinSequence(sequenceLines.join(''))
    if (!id) {
      throw new Error('Each FASTA header must include a protein ID after ">".')
    }
    if (!sequenceLines.length) {
      throw new Error(`FASTA record ${id} must include sequence lines after the header.`)
    }
    records.push({
      id,
      description: descriptionParts.join(' '),
      sequence,
    })
  }

  content.split(/\r?\n/).forEach((line) => {
    const trimmed = line.trim()
    if (!trimmed) {
      return
    }
    if (trimmed.startsWith('>')) {
      pushCurrent()
      currentHeader = trimmed.slice(1)
      sequenceLines = []
      return
    }
    if (!currentHeader) {
      throw new Error('Sequence lines must appear after a FASTA header line.')
    }
    sequenceLines.push(trimmed)
  })
  pushCurrent()

  if (!records.length) {
    throw new Error('FASTA file must contain at least one header line starting with ">".')
  }
  const invalidRecord = records.find((record) => !record.id || validateProteinSequence(record.sequence))
  if (invalidRecord) {
    throw new Error(
      invalidRecord.id
        ? `FASTA record ${invalidRecord.id} has an invalid protein sequence.`
        : 'FASTA record is missing an ID in the header line.',
    )
  }

  return records
}
