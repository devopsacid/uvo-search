import { Suspense } from 'react'
import { createBrowserRouter, Navigate, useParams } from 'react-router-dom'
import { Layout } from '@/components/layout/Layout'
import { OverviewPage } from '@/pages/OverviewPage'
import { AboutPage } from '@/pages/AboutPage'
import { ZakazkyPage } from '@/pages/ZakazkyPage'
import { HladajPage } from '@/pages/HladajPage'
import { GraphPage } from '@/pages/GraphPage'
import { IngestionPage } from '@/pages/IngestionPage'
import { CpvTrendsPage } from '@/pages/CpvTrendsPage'
import { FirmaPage } from '@/pages/FirmaPage'
import { FirmaPrehladTab } from '@/pages/firma/FirmaPrehladTab'
import { FirmaZakazkyTab } from '@/pages/firma/FirmaZakazkyTab'
import { FirmaSietTab } from '@/pages/firma/FirmaSietTab'
import { FirmaPartneriTab } from '@/pages/firma/FirmaPartneriTab'
import { FirmaCpvTab } from '@/pages/firma/FirmaCpvTab'
import { FirmyPage } from '@/pages/FirmyPage'

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

      // Firma workspace
      {
        path: 'firma/:ico',
        element: <FirmaPage />,
        children: [
          { index: true, element: <Navigate to="prehlad" replace /> },
          { path: 'prehlad', element: <FirmaPrehladTab /> },
          { path: 'zakazky', element: <FirmaZakazkyTab /> },
          {
            path: 'siet',
            element: (
              <Suspense fallback={<div className="p-8 text-muted-foreground">Načítavam…</div>}>
                <FirmaSietTab />
              </Suspense>
            ),
          },
          { path: 'partneri', element: <FirmaPartneriTab /> },
          { path: 'cpv', element: <FirmaCpvTab /> },
        ],
      },

      // Other new routes
      { path: 'firmy', element: <FirmyPage /> },
      { path: 'zakazky', element: <ZakazkyPage /> },
      { path: 'hladaj', element: <HladajPage /> },

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
