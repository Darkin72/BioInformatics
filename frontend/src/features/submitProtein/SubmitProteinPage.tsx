import { useState } from 'react'
import type { FormEvent } from 'react'
import { ErrorState } from '../../components/ErrorState'
import {
  parseFasta,
  validateProteinSequence,
  type FastaRecord,
} from './proteinValidation'
import { createInferenceRequest } from './submitProteinApi'

interface SubmitProteinPageProps {
  navigate: (path: string) => void
}

export function SubmitProteinPage({ navigate }: SubmitProteinPageProps) {
  const [fastaContent, setFastaContent] = useState('')
  const [model, setModel] = useState<'' | 'ensemble' | 'esm_mlp' | 'protcnn' | 'bilstm'>('')
  const [topK, setTopK] = useState('')
  const [threshold, setThreshold] = useState('')
  const [fastaRecords, setFastaRecords] = useState<FastaRecord[]>([])
  const [selectedFastaIndex, setSelectedFastaIndex] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  function applyFastaRecord(index: number) {
    setSelectedFastaIndex(index)
  }

  async function handleFastaFile(file: File | null) {
    if (!file) {
      return
    }
    setError(null)
    try {
      const content = await file.text()
      const records = parseFasta(content)
      setFastaRecords(records)
      setFastaContent(content)
      applyFastaRecord(0)
    } catch (loadError) {
      setFastaRecords([])
      setError(loadError instanceof Error ? loadError.message : 'Unable to parse FASTA file.')
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)

    let records: FastaRecord[] = []
    try {
      records = parseFasta(fastaContent)
    } catch (parseError) {
      setError(parseError instanceof Error ? parseError.message : 'Invalid FASTA content.')
      return
    }

    const selectedRecord = records[selectedFastaIndex] ?? records[0]
    const sequenceError = validateProteinSequence(selectedRecord.sequence)

    if (!model) {
      setError('Model is required.')
      return
    }

    if (sequenceError) {
      setError(sequenceError)
      return
    }
    const parsedTopK = Number(topK)
    if (!Number.isInteger(parsedTopK) || parsedTopK < 1 || parsedTopK > 500) {
      setError('Top K must be an integer between 1 and 500.')
      return
    }
    const parsedThreshold = threshold.trim() ? Number(threshold) : null
    if (
      parsedThreshold !== null &&
      (!Number.isFinite(parsedThreshold) || parsedThreshold < 0 || parsedThreshold > 1)
    ) {
      setError('Threshold must be empty or a number between 0 and 1.')
      return
    }

    setIsSubmitting(true)

    try {
      const created = await createInferenceRequest({
        protein_id: selectedRecord.id,
        sequence: selectedRecord.sequence,
        source: 'fasta_ui',
        model,
        top_k: parsedTopK,
        threshold: parsedThreshold,
        metadata: {
          fasta_record_count: records.length,
          fasta_selected_index: selectedFastaIndex,
          fasta_description: selectedRecord.description,
        },
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
        <div className="form-row">
          <label>
            Model
            <select
              onChange={(event) =>
                setModel(event.target.value as '' | 'ensemble' | 'esm_mlp' | 'protcnn' | 'bilstm')
              }
              value={model}
            >
              <option value="">Select model</option>
              <option value="ensemble">Ensemble</option>
              <option value="esm_mlp">ESM MLP</option>
              <option value="protcnn">ProtCNN</option>
              <option value="bilstm">BiLSTM</option>
            </select>
          </label>
        </div>

        <div className="form-row">
          <label>
            Top K
            <input
              max={500}
              min={1}
              onChange={(event) => setTopK(event.target.value)}
              placeholder="1-500"
              type="number"
              value={topK}
            />
          </label>

          <label>
            Threshold
            <input
              max={1}
              min={0}
              onChange={(event) => setThreshold(event.target.value)}
              placeholder="0-1"
              step="0.01"
              type="number"
              value={threshold}
            />
          </label>
        </div>

        <label>
          FASTA file
          <input
            accept=".fa,.faa,.fasta,.txt"
            onChange={(event) => void handleFastaFile(event.target.files?.[0] ?? null)}
            type="file"
          />
        </label>

        {fastaRecords.length > 1 ? (
          <label>
            FASTA record
            <select
              onChange={(event) => applyFastaRecord(Number(event.target.value))}
              value={selectedFastaIndex}
            >
              {fastaRecords.map((record, index) => (
                <option key={`${record.id}-${index}`} value={index}>
                  {record.id} ({record.sequence.length} aa)
                </option>
              ))}
            </select>
          </label>
        ) : null}

        <label>
          FASTA content
          <textarea
            onChange={(event) => {
              const nextContent = event.target.value
              setFastaContent(nextContent)
              setSelectedFastaIndex(0)
              try {
                setFastaRecords(nextContent.trim() ? parseFasta(nextContent) : [])
                setError(null)
              } catch {
                setFastaRecords([])
              }
            }}
            placeholder={'>protein_id optional description\nMTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV'}
            rows={9}
            value={fastaContent}
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
