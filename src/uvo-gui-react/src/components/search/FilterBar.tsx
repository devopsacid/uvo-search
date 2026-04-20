import { cn } from '@/lib/utils'

interface FilterInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string
}

export function FilterInput({ label, className, ...props }: FilterInputProps) {
  return (
    <label className="block space-y-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <input
        {...props}
        className={cn(
          'w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring',
          className,
        )}
      />
    </label>
  )
}

interface FilterSelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label: string
  options: { value: string; label: string }[]
}

export function FilterSelect({ label, options, className, ...props }: FilterSelectProps) {
  return (
    <label className="block space-y-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <select
        {...props}
        className={cn(
          'w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring',
          className,
        )}
      >
        <option value="">Všetky</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  )
}
