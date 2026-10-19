import { lazy } from 'react'
import { createBrowserRouter, Navigate, useParams } from 'react-router-dom'
import { Layout } from '@/components/layout/Layout'

// Route components are split into per-page chunks. Layout wraps <Outlet/> in a
// shared <Suspense>, and FirmaPage does the same for its tab outlet.
const AnalyticsLayout = lazy(() =>
  import('@/components/analytics/AnalyticsLayout').then((m) => ({ default: m.AnalyticsLayout })),
)
const PrehladPage = lazy(() =>
  import('@/pages/analytics/PrehladPage').then((m) => ({ default: m.PrehladPage })),
)
const KoncentraciaPage = lazy(() =>
  import('@/pages/analytics/KoncentraciaPage').then((m) => ({ default: m.KoncentraciaPage })),
)
const CpvPage = lazy(() => import('@/pages/analytics/CpvPage').then((m) => ({ default: m.CpvPage })))
const PokrytiePage = lazy(() =>
  import('@/pages/analytics/PokrytiePage').then((m) => ({ default: m.PokrytiePage })),
)
const AboutPage = lazy(() =>
  import('@/pages/AboutPage').then((m) => ({ default: m.AboutPage })),
)
const ZakazkyPage = lazy(() =>
  import('@/pages/ZakazkyPage').then((m) => ({ default: m.ZakazkyPage })),
)
const HladajPage = lazy(() =>
  import('@/pages/HladajPage').then((m) => ({ default: m.HladajPage })),
)
const GraphPage = lazy(() =>
  import('@/pages/GraphPage').then((m) => ({ default: m.GraphPage })),
)
const IngestionPage = lazy(() =>
  import('@/pages/IngestionPage').then((m) => ({ default: m.IngestionPage })),
)
const FirmaPage = lazy(() =>
  import('@/pages/FirmaPage').then((m) => ({ default: m.FirmaPage })),
)
const FirmyPage = lazy(() =>
  import('@/pages/FirmyPage').then((m) => ({ default: m.FirmyPage })),
)
const FirmaPrehladTab = lazy(() =>
  import('@/pages/firma/FirmaPrehladTab').then((m) => ({ default: m.FirmaPrehladTab })),
)
const FirmaZakazkyTab = lazy(() =>
  import('@/pages/firma/FirmaZakazkyTab').then((m) => ({ default: m.FirmaZakazkyTab })),
)
const FirmaSietTab = lazy(() =>
  import('@/pages/firma/FirmaSietTab').then((m) => ({ default: m.FirmaSietTab })),
)
const FirmaPartneriTab = lazy(() =>
  import('@/pages/firma/FirmaPartneriTab').then((m) => ({ default: m.FirmaPartneriTab })),
)
const FirmaCpvTab = lazy(() =>
  import('@/pages/firma/FirmaCpvTab').then((m) => ({ default: m.FirmaCpvTab })),
)

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
      { index: true, element: <Navigate to="/analytika/prehlad" replace /> },

      // Analytics dashboards (replace the old overview and CPV trends pages)
      {
        path: 'analytika',
        element: <AnalyticsLayout />,
        children: [
          { index: true, element: <Navigate to="prehlad" replace /> },
          { path: 'prehlad', element: <PrehladPage /> },
          { path: 'koncentracia', element: <KoncentraciaPage /> },
          { path: 'cpv', element: <CpvPage /> },
          { path: 'pokrytie', element: <PokrytiePage /> },
        ],
      },
      { path: 'about', element: <AboutPage /> },

      // Firma workspace
      {
        path: 'firma/:ico',
        element: <FirmaPage />,
        children: [
          { index: true, element: <Navigate to="prehlad" replace /> },
          { path: 'prehlad', element: <FirmaPrehladTab /> },
          { path: 'zakazky', element: <FirmaZakazkyTab /> },
          { path: 'siet', element: <FirmaSietTab /> },
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
      { path: 'cpv-trends', element: <Navigate to="/analytika/cpv" replace /> },
      { path: 'graph', element: <GraphPage /> },
      { path: 'ingestion', element: <IngestionPage /> },
    ],
  },
])
