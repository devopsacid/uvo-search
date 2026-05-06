import React, { Suspense } from 'react'
import { useEgoGraph } from '@/api/queries/graph'
import { Skeleton } from '@/components/ui/Skeleton'
import sk from '@/i18n/sk'

const CytoscapeGraph = React.lazy(() => import('./CytoscapeGraph'))

export interface EgoNetworkProps {
  ico: string
  hops?: number
  height?: string
  onNodeClick?: (ico: string) => void
}

export function EgoNetwork({ ico, hops = 2, height = '500px', onNodeClick }: EgoNetworkProps) {
  const query = useEgoGraph(ico, hops)
  const nodes = query.data?.nodes ?? []
  const edges = query.data?.edges ?? []

  function handleNodeClick(nodeId: string, nodeType: string) {
    if (onNodeClick && (nodeType === 'procurer' || nodeType === 'supplier')) {
      onNodeClick(nodeId)
    }
  }

  if (query.isLoading) {
    return (
      <div className="flex items-center justify-center rounded-lg border border-border bg-card p-12">
        <Skeleton className="h-6 w-40" />
      </div>
    )
  }

  if (query.isError) {
    return (
      <div className="rounded-lg border border-border bg-card p-8 text-center">
        <p className="text-sm text-muted-foreground">{sk.common.error}</p>
      </div>
    )
  }

  if (nodes.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card p-8 text-center">
        <p className="text-sm font-medium text-foreground">{sk.firma.sietNoData}</p>
        <p className="mt-1 text-xs text-muted-foreground">{sk.firma.sietNoDataHint}</p>
      </div>
    )
  }

  const heightPx = parseInt(height, 10) || 500

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <Suspense
        fallback={
          <div className="flex items-center justify-center p-12">
            <Skeleton className="h-6 w-40" />
          </div>
        }
      >
        <CytoscapeGraph
          nodes={nodes}
          edges={edges}
          height={heightPx}
          onNodeClick={handleNodeClick}
        />
      </Suspense>
    </div>
  )
}
