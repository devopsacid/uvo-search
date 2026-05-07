import { Link } from 'react-router-dom'
import { cn } from '@/lib/utils'

type EntityType = 'supplier' | 'procurer'

interface EntityLinkProps {
  ico: string
  name: string
  type: EntityType
  className?: string
}

/**
 * Wraps an entity name in a link to its detail page.
 * Use this EVERYWHERE a supplier or procurer name is rendered.
 */
export function EntityLink({ ico, name, type: _type, className }: EntityLinkProps) {
  const to = `/firma/${ico}`
  if (!ico) return <span className={className}>{name || '—'}</span>

  return (
    <Link
      to={to}
      className={cn(
        'text-primary underline-offset-2 hover:underline',
        className,
      )}
    >
      {name || ico}
    </Link>
  )
}
