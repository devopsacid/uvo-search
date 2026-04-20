/**
 * CytoscapeGraph — lazy-loaded Cytoscape wrapper.
 *
 * Import via React.lazy to keep the initial bundle clean:
 *   const CytoscapeGraph = React.lazy(() => import('./CytoscapeGraph'))
 */
// @ts-expect-error — no @types/react-cytoscapejs package available
import CytoscapeComponent from 'react-cytoscapejs'
import type { ElementDefinition, StylesheetStyle, Core, EventObject } from 'cytoscape'
import type { CytoEdge, CytoNode } from '@/api/types'

const STYLESHEET: StylesheetStyle[] = [
  {
    selector: 'node',
    style: {
      label: 'data(label)',
      'font-size': 11,
      'text-valign': 'bottom',
      'text-halign': 'center',
      'text-margin-y': 4,
      width: 36,
      height: 36,
    },
  },
  {
    selector: 'node[type = "procurer"]',
    style: {
      'background-color': '#2563eb',
      color: '#1e3a8a',
    },
  },
  {
    selector: 'node[type = "supplier"]',
    style: {
      'background-color': '#16a34a',
      color: '#14532d',
    },
  },
  {
    selector: 'edge',
    style: {
      width: 2,
      'line-color': '#94a3b8',
      'target-arrow-shape': 'triangle',
      'target-arrow-color': '#94a3b8',
      'curve-style': 'bezier',
      label: 'data(label)',
      'font-size': 9,
      'text-rotation': 'autorotate',
    },
  },
]

interface CytoscapeGraphProps {
  nodes: CytoNode[]
  edges: CytoEdge[]
  height?: number
  onNodeClick?: (nodeId: string, nodeType: string) => void
}

export default function CytoscapeGraph({
  nodes,
  edges,
  height = 500,
  onNodeClick,
}: CytoscapeGraphProps) {
  const elements: ElementDefinition[] = [
    ...nodes.map((n) => ({ data: n.data })),
    ...edges.map((e) => ({ data: e.data })),
  ]

  return (
    <CytoscapeComponent
      elements={elements}
      stylesheet={STYLESHEET}
      layout={{ name: 'cose', animate: false }}
      style={{ width: '100%', height }}
      cy={(cy: Core) => {
        if (onNodeClick) {
          cy.on('tap', 'node', (evt: EventObject) => {
            const node = evt.target as ReturnType<Core['$']>
            onNodeClick(node.data('id') as string, node.data('type') as string)
          })
        }
      }}
    />
  )
}
