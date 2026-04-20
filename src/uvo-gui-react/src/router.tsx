import { createBrowserRouter } from 'react-router-dom'
import { Layout } from '@/components/layout/Layout'
import { OverviewPage } from '@/pages/OverviewPage'
import { AboutPage } from '@/pages/AboutPage'
import { SearchPage } from '@/pages/SearchPage'
import { SuppliersPage } from '@/pages/SuppliersPage'
import { SupplierDetailPage } from '@/pages/SupplierDetailPage'
import { ProcurersPage } from '@/pages/ProcurersPage'
import { ProcurerDetailPage } from '@/pages/ProcurerDetailPage'

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
    ],
  },
])
