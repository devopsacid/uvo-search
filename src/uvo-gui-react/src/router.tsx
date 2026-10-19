import { lazy } from 'react'
import {
  createBrowserRouter,
  Navigate,
  useLocation,
  useParams,
  type RouteObject,
} from 'react-router-dom'
import { Layout } from '@/components/layout/Layout'

// Route components are split into per-page chunks. Layout wraps <Outlet/> in a
// shared <Suspense>, and CompanyPage does the same for its tab outlet.
const AnalyticsLayout = lazy(() =>
  import('@/components/analytics/AnalyticsLayout').then((m) => ({ default: m.AnalyticsLayout })),
)
const OverviewPage = lazy(() =>
  import('@/pages/analytics/OverviewPage').then((m) => ({ default: m.OverviewPage })),
)
const ConcentrationPage = lazy(() =>
  import('@/pages/analytics/ConcentrationPage').then((m) => ({ default: m.ConcentrationPage })),
)
const CpvPage = lazy(() => import('@/pages/analytics/CpvPage').then((m) => ({ default: m.CpvPage })))
const CoveragePage = lazy(() =>
  import('@/pages/analytics/CoveragePage').then((m) => ({ default: m.CoveragePage })),
)
const AboutPage = lazy(() =>
  import('@/pages/AboutPage').then((m) => ({ default: m.AboutPage })),
)
const ContractsPage = lazy(() =>
  import('@/pages/ContractsPage').then((m) => ({ default: m.ContractsPage })),
)
const SearchPage = lazy(() =>
  import('@/pages/SearchPage').then((m) => ({ default: m.SearchPage })),
)
const GraphPage = lazy(() =>
  import('@/pages/GraphPage').then((m) => ({ default: m.GraphPage })),
)
const IngestionPage = lazy(() =>
  import('@/pages/IngestionPage').then((m) => ({ default: m.IngestionPage })),
)
const CompanyPage = lazy(() =>
  import('@/pages/CompanyPage').then((m) => ({ default: m.CompanyPage })),
)
const CompaniesPage = lazy(() =>
  import('@/pages/CompaniesPage').then((m) => ({ default: m.CompaniesPage })),
)
const CompanyOverviewTab = lazy(() =>
  import('@/pages/company/CompanyOverviewTab').then((m) => ({ default: m.CompanyOverviewTab })),
)
const CompanyContractsTab = lazy(() =>
  import('@/pages/company/CompanyContractsTab').then((m) => ({ default: m.CompanyContractsTab })),
)
const CompanyNetworkTab = lazy(() =>
  import('@/pages/company/CompanyNetworkTab').then((m) => ({ default: m.CompanyNetworkTab })),
)
const CompanyPartnersTab = lazy(() =>
  import('@/pages/company/CompanyPartnersTab').then((m) => ({ default: m.CompanyPartnersTab })),
)
const CompanyCpvTab = lazy(() =>
  import('@/pages/company/CompanyCpvTab').then((m) => ({ default: m.CompanyCpvTab })),
)

/**
 * Redirect that keeps `?query` and `#hash`. Plain `<Navigate to="/x">` drops both,
 * which would break bookmarked filter URLs from before the English route rename.
 */
export function RedirectPreservingQuery({ to }: { to: string }) {
  const { search, hash } = useLocation()
  return <Navigate to={{ pathname: to, search, hash }} replace />
}

/** Same, for routes with an `:ico` param. `to` may contain `:ico`. */
export function RedirectWithIco({ to }: { to: string }) {
  const { ico = '' } = useParams()
  return <RedirectPreservingQuery to={to.replace(':ico', encodeURIComponent(ico))} />
}

/** Legacy `/suppliers/:ico` and `/procurers/:ico` land on the company workspace. */
function CompanyRedirect() {
  return <RedirectWithIco to="/company/:ico" />
}

/** Permanent redirects from former paths (Slovak SPA routes, pre-2026 legacy routes). Exported for tests. */
export const legacyRedirects: RouteObject[] = [
  { path: 'analytika', element: <RedirectPreservingQuery to="/analytics/overview" /> },
  { path: 'analytika/prehlad', element: <RedirectPreservingQuery to="/analytics/overview" /> },
  { path: 'analytika/koncentracia', element: <RedirectPreservingQuery to="/analytics/concentration" /> },
  { path: 'analytika/cpv', element: <RedirectPreservingQuery to="/analytics/cpv" /> },
  { path: 'analytika/pokrytie', element: <RedirectPreservingQuery to="/analytics/coverage" /> },
  { path: 'firma/:ico', element: <RedirectWithIco to="/company/:ico/overview" /> },
  { path: 'firma/:ico/prehlad', element: <RedirectWithIco to="/company/:ico/overview" /> },
  { path: 'firma/:ico/zakazky', element: <RedirectWithIco to="/company/:ico/contracts" /> },
  { path: 'firma/:ico/siet', element: <RedirectWithIco to="/company/:ico/network" /> },
  { path: 'firma/:ico/partneri', element: <RedirectWithIco to="/company/:ico/partners" /> },
  { path: 'firma/:ico/cpv', element: <RedirectWithIco to="/company/:ico/cpv" /> },
  { path: 'firmy', element: <RedirectPreservingQuery to="/companies" /> },
  { path: 'zakazky', element: <RedirectPreservingQuery to="/contracts" /> },
  { path: 'hladaj', element: <RedirectPreservingQuery to="/search" /> },

  // Older legacy redirects
  { path: 'suppliers', element: <RedirectPreservingQuery to="/companies" /> },
  { path: 'suppliers/:ico', element: <CompanyRedirect /> },
  { path: 'procurers', element: <RedirectPreservingQuery to="/companies" /> },
  { path: 'procurers/:ico', element: <CompanyRedirect /> },
  { path: 'pinpoint', element: <RedirectPreservingQuery to="/companies" /> },
  { path: 'cpv-trends', element: <RedirectPreservingQuery to="/analytics/cpv" /> },
]

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <RedirectPreservingQuery to="/analytics/overview" /> },

      // Analytics dashboards (replace the old overview and CPV trends pages)
      {
        path: 'analytics',
        element: <AnalyticsLayout />,
        children: [
          { index: true, element: <RedirectPreservingQuery to="/analytics/overview" /> },
          { path: 'overview', element: <OverviewPage /> },
          { path: 'concentration', element: <ConcentrationPage /> },
          { path: 'cpv', element: <CpvPage /> },
          { path: 'coverage', element: <CoveragePage /> },
        ],
      },
      { path: 'about', element: <AboutPage /> },

      // Company workspace
      {
        path: 'company/:ico',
        element: <CompanyPage />,
        children: [
          { index: true, element: <RedirectWithIco to="/company/:ico/overview" /> },
          { path: 'overview', element: <CompanyOverviewTab /> },
          { path: 'contracts', element: <CompanyContractsTab /> },
          { path: 'network', element: <CompanyNetworkTab /> },
          { path: 'partners', element: <CompanyPartnersTab /> },
          { path: 'cpv', element: <CompanyCpvTab /> },
        ],
      },

      { path: 'companies', element: <CompaniesPage /> },
      { path: 'contracts', element: <ContractsPage /> },
      { path: 'search', element: <SearchPage /> },

      ...legacyRedirects,

      // Unchanged routes
      { path: 'graph', element: <GraphPage /> },
      { path: 'ingestion', element: <IngestionPage /> },
    ],
  },
])
