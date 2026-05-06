import React, { Suspense, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useEgoGraph, useCpvGraph } from '@/api/queries/graph'
import { Skeleton } from '@/components/ui/Skeleton'
import sk from '@/i18n/sk'

const CytoscapeGraph = React.lazy(() => import('../components/graph/CytoscapeGraph'))

type Mode = 'ego' | 'cpv'

const CURRENT_YEAR = new Date().getFullYear()

export function GraphPage() {
  const [searchParams, setSearchParams] = useSearchParams()

  const mode: Mode = (searchParams.get('mode') as Mode) === 'cpv' ? 'cpv' : 'ego'

  const [icoInput, setIcoInput] = useState(searchParams.get('ico') ?? '')
  const [hopsInput, setHopsInput] = useState(Number(searchParams.get('hops') ?? 2))
  const [cpvInput, setCpvInput] = useState(searchParams.get('cpv') ?? '')
  const [yearInput, setYearInput] = useState(Number(searchParams.get('year') ?? CURRENT_YEAR))

  const activeIco = searchParams.get('ico') ?? ''
  const activeHops = Number(searchParams.get('hops') ?? 2)
  const activeCpv = searchParams.get('cpv') ?? ''
  const activeYear = Number(searchParams.get('year') ?? CURRENT_YEAR)

  const egoQuery = useEgoGraph(activeIco, activeHops)
  const cpvQuery = useCpvGraph(activeCpv, activeYear)

  const query = mode === 'ego' ? egoQuery : cpvQuery
  const graphData = query.data

  function setMode(m: Mode) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set('mode', m)
      return next
    })
  }

  function handleSearch() {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set('mode', mode)
      if (mode === 'ego') {
        next.set('ico', icoInput)
        next.set('hops', String(hopsInput))
        next.delete('cpv')
        next.delete('year')
      } else {
        next.set('cpv', cpvInput)
        next.set('year', String(yearInput))
        next.delete('ico')
        next.delete('hops')
      }
      return next
    })
  }

  function handleNodeClick(nodeId: string, nodeType: string) {
    if (nodeType === 'procurer' || nodeType === 'supplier') {
      const path = nodeType === 'procurer' ? '/procurers' : '/suppliers'
      window.open(`${path}/${nodeId}`, '_blank')
    }
  }

  const isLoading = query.isLoading
  const nodes = graphData?.nodes ?? []
  const edges = graphData?.edges ?? []
  const isEmpty = !isLoading && !query.isError && nodes.length === 0 && (activeIco || activeCpv)

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-foreground">{sk.graph.title}</h1>

      {/* Mode tabs */}
      <div className="flex gap-2">
        <button
          onClick={() => setMode('ego')}
          className={
            mode === 'ego'
              ? 'rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground'
              : 'rounded-md border border-border px-4 py-1.5 text-sm text-muted-foreground hover:bg-accent'
          }
        >
          {sk.graph.egoMode}
        </button>
        <button
          onClick={() => setMode('cpv')}
          className={
            mode === 'cpv'
              ? 'rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground'
              : 'rounded-md border border-border px-4 py-1.5 text-sm text-muted-foreground hover:bg-accent'
          }
        >
          {sk.graph.cpvMode}
        </button>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-end gap-4 rounded-lg border border-border bg-card p-4">
        {mode === 'ego' ? (
          <>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted-foreground">{sk.graph.icoLabel}</label>
              <input
                type="text"
                value={icoInput}
                onChange={(e) => setIcoInput(e.target.value)}
                placeholder={sk.graph.icoPlaceholder}
                className="w-40 rounded border border-border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted-foreground">
                {sk.graph.hopsLabel}: {hopsInput}
              </label>
              <input
                type="range"
                min={1}
                max={3}
                value={hopsInput}
                onChange={(e) => setHopsInput(Number(e.target.value))}
                className="w-24"
              />
            </div>
          </>
        ) : (
          <>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted-foreground">{sk.graph.cpvLabel}</label>
              <input
                type="text"
                value={cpvInput}
                onChange={(e) => setCpvInput(e.target.value)}
                placeholder={sk.graph.cpvPlaceholder}
                className="w-40 rounded border border-border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted-foreground">{sk.graph.yearLabel}</label>
              <input
                type="number"
                value={yearInput}
                onChange={(e) => setYearInput(Number(e.target.value))}
                min={2010}
                max={CURRENT_YEAR}
                className="w-24 rounded border border-border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
          </>
        )}
        <button
          onClick={handleSearch}
          className="rounded bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          {sk.graph.search}
        </button>
      </div>

      {/* Legend */}
      {nodes.length > 0 && (
        <div className="flex gap-4 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <span className="inline-block h-3 w-3 rounded-full bg-[#2563eb]" />
            {sk.graph.nodesProcurer}
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-3 w-3 rounded-full bg-[#16a34a]" />
            {sk.graph.nodesSupplier}
          </span>
        </div>
      )}

      {/* Graph area */}
      {isLoading ? (
        <div className="flex items-center justify-center rounded-lg border border-border bg-card p-12">
          <Skeleton className="h-6 w-40" />
        </div>
      ) : isEmpty ? (
        <div className="rounded-lg border border-border bg-card p-8 text-center">
          <p className="text-sm font-medium text-foreground">{sk.graph.noData}</p>
          <p className="mt-1 text-xs text-muted-foreground">{sk.graph.noDataHint}</p>
        </div>
      ) : nodes.length > 0 ? (
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
              height={520}
              onNodeClick={handleNodeClick}
            />
          </Suspense>
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-border bg-card p-12 text-center">
          <p className="text-sm text-muted-foreground">
            {mode === 'ego' ? sk.graph.icoPlaceholder : sk.graph.cpvPlaceholder}
          </p>
        </div>
      )}
    </div>
  )
}
