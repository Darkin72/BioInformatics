import { useState } from 'react'
import type { FormEvent } from 'react'
import { ErrorState } from '../../components/ErrorState'
import {
  normalizeProteinSequence,
  validateProteinSequence,
} from './proteinValidation'
import { createInferenceRequest } from './submitProteinApi'

interface SubmitProteinPageProps {
  navigate: (path: string) => void
}

export function SubmitProteinPage({ navigate }: SubmitProteinPageProps) {
  const [proteinId, setProteinId] = useState('P12345')
  const [sequence, setSequence] = useState('MENDELACDEFGHIKLMNPQRSTVWY')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)

    const normalizedSequence = normalizeProteinSequence(sequence)
    const sequenceError = validateProteinSequence(normalizedSequence)

    if (!proteinId.trim()) {
      setError('Protein ID is required.')
      return
    }

    if (sequenceError) {
      setError(sequenceError)
      return
    }

    setIsSubmitting(true)

    try {
      const created = await createInferenceRequest({
        protein_id: proteinId.trim(),
        sequence: normalizedSequence,
        source: 'manual_ui',
      })
      navigate(`/requests/${created.request_id}`)
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : 'Unable to create inference request.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="page-stack">
      <div className="section-header">
        <div>
        <h2>Predict protein function</h2>
          <p>Create a new inference request for the streaming pipeline.</p>
        </div>
      </div>

      <form className="form-panel" onSubmit={handleSubmit}>
        <label>
          Protein ID
          <input
            onChange={(event) => setProteinId(event.target.value)}
            placeholder="P12345"
            value={proteinId}
          />
        </label>

        <label>
          Sequence
          <textarea
            onChange={(event) => setSequence(event.target.value)}
            rows={7}
            value={sequence}
          />
        </label>

        {error ? <ErrorState message={error} /> : null}

        <div className="actions-row">
          <button className="primary-button" disabled={isSubmitting} type="submit">
            {isSubmitting ? 'Creating request...' : 'Predict'}
          </button>
        </div>
      </form>
    </section>
  )
}
