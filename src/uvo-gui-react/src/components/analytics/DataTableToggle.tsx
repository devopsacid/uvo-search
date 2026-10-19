import { Link } from 'react-router-dom'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { cn } from '@/lib/utils'
import sk from '@/i18n/sk'

interface DataTableToggleProps {
  showTable: boolean
  onToggle: () => void
  /** Id of the region the button controls. */
  controls?: string
}

/** The guaranteed accessible path to a chart's numbers: swaps the graphic for a real table. */
export function DataTableToggle({ showTable, onToggle, controls }: DataTableToggleProps) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={showTable}
      aria-controls={controls}
      className={cn(
        'rounded-md border border-border px-2.5 py-1 text-xs text-foreground hover:bg-accent',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        showTable && 'bg-accent',
      )}
    >
      {showTable ? sk.analytics.charts.showChart : sk.analytics.charts.showTable}
    </button>
  )
}

export interface DataColumn<T> {
  header: string
  /** Rendered cell content. */
  cell: (row: T) => React.ReactNode
  align?: 'left' | 'right'
}

interface SimpleDataTableProps<T> {
  caption: string
  columns: DataColumn<T>[]
  rows: T[]
  rowKey: (row: T) => string
}

/** Plain semantic table used for chart table views and the dashboard detail tables. */
export function SimpleDataTable<T>({ caption, columns, rows, rowKey }: SimpleDataTableProps<T>) {
  return (
    <Table>
      <caption className="sr-only">{caption}</caption>
      <TableHeader>
        <tr>
          {columns.map((c) => (
            <TableHead key={c.header} className={c.align === 'right' ? 'text-right' : undefined}>
              {c.header}
            </TableHead>
          ))}
        </tr>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={rowKey(row)}>
            {columns.map((c) => (
              <TableCell key={c.header} className={c.align === 'right' ? 'text-right tabular-nums' : undefined}>
                {c.cell(row)}
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

export function TableLink({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <Link to={to} className="text-primary underline-offset-2 hover:underline">
      {children}
    </Link>
  )
}
