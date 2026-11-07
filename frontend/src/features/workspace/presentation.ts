export const panel = 'min-w-0 rounded-control border border-border bg-surface p-4'
export const readable = (value: string) =>
  value.includes('DEMO:') ? value.split(':').slice(2).join(':') : value.replace(/_/g, ' ')
export const percentage = (value: number) =>
  value > 0 && value < 0.0001 ? '<0.01%' : `${(value * 100).toFixed(2)}%`
