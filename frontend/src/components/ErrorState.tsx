interface ErrorStateProps {
  message: string
}

export function ErrorState({ message }: ErrorStateProps) {
  return <div className="state-box error-state">{message}</div>
}
