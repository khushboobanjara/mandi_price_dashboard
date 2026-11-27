export default function ErrorBox({ message, onRetry }) {
  if (!message) return null;
  return (
    <div className="error" role="alert">
      <span>⚠ {message}</span>
      {onRetry && <button className="btn small" onClick={onRetry}>Retry</button>}
    </div>
  );
}
