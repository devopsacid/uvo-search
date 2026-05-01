import { createBrowserRouter } from 'react-router-dom'
import { Layout } from '@/components/layout/Layout'
import { OverviewPage } from '@/pages/OverviewPage'
import { AboutPage } from '@/pages/AboutPage'
import { SearchPage } from '@/pages/SearchPage'
import { SuppliersPage } from '@/pages/SuppliersPage'
import { SupplierDetailPage } from '@/pages/SupplierDetailPage'
import { ProcurersPage } from '@/pages/ProcurersPage'
import { ProcurerDetailPage } from '@/pages/ProcurerDetailPage'
import { GraphPage } from '@/pages/GraphPage'
import { IngestionPage } from '@/pages/IngestionPage'
import { AnalyticsIndexPage } from '@/pages/analytics/AnalyticsIndexPage'
import { ProcurerAnalyticsPage } from '@/pages/analytics/ProcurerAnalyticsPage'
import { SupplierAnalyticsPage } from '@/pages/analytics/SupplierAnalyticsPage'
import { ExecutiveSummaryPage } from '@/pages/analytics/ExecutiveSummaryPage'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <OverviewPage /> },
      { path: 'about', element: <AboutPage /> },
      { path: 'search', element: <SearchPage /> },
      { path: 'suppliers', element: <SuppliersPage /> },
      { path: 'suppliers/:ico', element: <SupplierDetailPage /> },
      { path: 'procurers', element: <ProcurersPage /> },
      { path: 'procurers/:ico', element: <ProcurerDetailPage /> },
      { path: 'graph', element: <GraphPage /> },
      { path: 'ingestion', element: <IngestionPage /> },
      { path: 'analytics', element: <AnalyticsIndexPage /> },
      { path: 'analytics/procurer/:ico', element: <ProcurerAnalyticsPage /> },
      { path: 'analytics/supplier/:ico', element: <SupplierAnalyticsPage /> },
      { path: 'analytics/executive/:ico', element: <ExecutiveSummaryPage /> },
    ],
  },
])
