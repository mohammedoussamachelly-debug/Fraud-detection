export function EvidenceViewer({ payload }: { payload: Record<string, unknown> }) {
  return (
    <details className="mt-3 rounded-control border border-border bg-background p-3">
      <summary className="cursor-pointer text-xs font-medium">Inspect evidence payload</summary>
      <pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap break-all font-mono text-xs leading-relaxed">
        {JSON.stringify(payload, null, 2)}
      </pre>
    </details>
  )
}
