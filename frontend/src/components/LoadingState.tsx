interface LoadingStateProps {
  message?: string
}

export function LoadingState({ message = 'Loading data...' }: LoadingStateProps) {
  return <div className="state-box">{message}</div>
}
