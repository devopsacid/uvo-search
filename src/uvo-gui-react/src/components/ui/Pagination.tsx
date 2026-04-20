import { cn } from '@/lib/utils'

interface PaginationProps {
  page: number
  pageSize: number
  total: number
  onPageChange: (page: number) => void
  className?: string
}

export function Pagination({ page, pageSize, total, onPageChange, className }: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const from = Math.min((page - 1) * pageSize + 1, total)
  const to = Math.min(page * pageSize, total)

  if (totalPages <= 1) return null

  return (
    <div className={cn('flex items-center justify-between gap-4 py-3 text-sm', className)}>
      <span className="text-muted-foreground">
        {from}–{to} z {total}
      </span>
      <div className="flex gap-1">
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          className="rounded px-2 py-1 text-sm text-muted-foreground hover:bg-accent disabled:pointer-events-none disabled:opacity-40"
        >
          ‹ Predchádzajúca
        </button>
        {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
          // Simple windowing: show first, last, and up to 5 around current
          const pageNum = computePageNum(i, page, totalPages)
          if (pageNum === null) {
            return (
              <span key={`ellipsis-${i}`} className="px-2 py-1 text-muted-foreground">
                …
              </span>
            )
          }
          return (
            <button
              key={pageNum}
              onClick={() => onPageChange(pageNum)}
              className={cn(
                'min-w-[2rem] rounded px-2 py-1 text-sm',
                pageNum === page
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-accent',
              )}
            >
              {pageNum}
            </button>
          )
        })}
        <button
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
          className="rounded px-2 py-1 text-sm text-muted-foreground hover:bg-accent disabled:pointer-events-none disabled:opacity-40"
        >
          Ďalšia ›
        </button>
      </div>
    </div>
  )
}

function computePageNum(index: number, current: number, total: number): number | null {
  if (total <= 7) return index + 1

  // Positions: 0=first, 1=ellipsis?, 2..4=window, 5=ellipsis?, 6=last
  if (index === 0) return 1
  if (index === 6) return total

  const windowStart = Math.max(2, Math.min(current - 1, total - 4))
  const windowEnd = windowStart + 2

  if (index === 1) return windowStart > 2 ? null : 2
  if (index === 5) return windowEnd < total - 1 ? null : total - 1

  return windowStart + (index - 2)
}
