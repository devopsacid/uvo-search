import { cn } from '@/lib/utils'

interface SidebarProps {
  children: React.ReactNode
  className?: string
}

/**
 * Sticky left-column filter shell. Used by SearchPage and directory pages.
 */
export function Sidebar({ children, className }: SidebarProps) {
  return (
    <aside
      className={cn(
        'sticky top-4 h-fit w-64 shrink-0 rounded-lg border border-border bg-card p-4',
        className,
      )}
    >
      {children}
    </aside>
  )
}

export function SidebarSection({
  title,
  children,
}: {
  title?: string
  children: React.ReactNode
}) {
  return (
    <div className="space-y-2">
      {title && <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</p>}
      {children}
    </div>
  )
}
