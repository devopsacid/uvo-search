import { createBrowserRouter, Navigate, useParams } from 'react-router-dom'
import { Layout } from '@/components/layout/Layout'
import { OverviewPage } from '@/pages/OverviewPage'
import { AboutPage } from '@/pages/AboutPage'
import { SearchPage } from '@/pages/SearchPage'
import { GraphPage } from '@/pages/GraphPage'
import { IngestionPage } from '@/pages/IngestionPage'
import { CpvTrendsPage } from '@/pages/CpvTrendsPage'

function ComingSoon() {
  return <div className="p-8 text-muted-foreground">Stránka sa pripravuje…</div>
}

function SupplierRedirect() {
  const { ico } = useParams()
  return <Navigate to={`/firma/${ico}`} replace />
}

function ProcurerRedirect() {
  const { ico } = useParams()
  return <Navigate to={`/firma/${ico}`} replace />
}

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <OverviewPage /> },
      { path: 'about', element: <AboutPage /> },

      // New routes
      { path: 'firma/:ico', element: <ComingSoon /> },
      { path: 'firma/:ico/prehlad', element: <ComingSoon /> },
      { path: 'firma/:ico/zakazky', element: <ComingSoon /> },
      { path: 'firma/:ico/siet', element: <ComingSoon /> },
      { path: 'firma/:ico/partneri', element: <ComingSoon /> },
      { path: 'firma/:ico/cpv', element: <ComingSoon /> },
      { path: 'firmy', element: <ComingSoon /> },
      { path: 'zakazky', element: <SearchPage /> },
      { path: 'hladaj', element: <ComingSoon /> },

      // Redirects — old paths → new paths
      { path: 'suppliers', element: <Navigate to="/firmy" replace /> },
      { path: 'suppliers/:ico', element: <SupplierRedirect /> },
      { path: 'procurers', element: <Navigate to="/firmy" replace /> },
      { path: 'procurers/:ico', element: <ProcurerRedirect /> },
      { path: 'pinpoint', element: <Navigate to="/firmy" replace /> },
      { path: 'search', element: <Navigate to="/zakazky" replace /> },

      // Unchanged routes
      { path: 'cpv-trends', element: <CpvTrendsPage /> },
      { path: 'graph', element: <GraphPage /> },
      { path: 'ingestion', element: <IngestionPage /> },
    ],
  },
])
