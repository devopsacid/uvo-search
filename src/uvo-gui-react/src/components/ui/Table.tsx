import { cn } from '@/lib/utils'

interface TableProps {
  className?: string
  children: React.ReactNode
}

export function Table({ className, children }: TableProps) {
  return (
    <div className="w-full overflow-auto">
      <table className={cn('w-full caption-bottom text-sm', className)}>{children}</table>
    </div>
  )
}

export function TableHeader({ children }: { children: React.ReactNode }) {
  return <thead className="border-b border-border">{children}</thead>
}

export function TableBody({ children }: { children: React.ReactNode }) {
  return <tbody>{children}</tbody>
}

export function TableRow({
  children,
  onClick,
  selected,
  className,
}: {
  children: React.ReactNode
  onClick?: () => void
  selected?: boolean
  className?: string
}) {
  return (
    <tr
      onClick={onClick}
      className={cn(
        'border-b border-border transition-colors',
        onClick && 'cursor-pointer hover:bg-accent/50',
        selected && 'bg-accent',
        className,
      )}
    >
      {children}
    </tr>
  )
}

export function TableHead({
  children,
  className,
}: {
  children?: React.ReactNode
  className?: string
}) {
  return (
    <th
      className={cn(
        'h-10 px-3 text-left align-middle text-xs font-medium uppercase tracking-wide text-muted-foreground',
        className,
      )}
    >
      {children}
    </th>
  )
}

export function TableCell({
  children,
  className,
}: {
  children?: React.ReactNode
  className?: string
}) {
  return (
    <td className={cn('px-3 py-2.5 align-middle text-foreground', className)}>{children}</td>
  )
}
