import { Outlet } from 'react-router-dom'
import { Header } from './Header'
import { PinBanner } from './PinBanner'
import { CompanyPinProvider } from '@/context/CompanyPinContext'

export function Layout() {
  return (
    <CompanyPinProvider>
      <div className="flex min-h-screen flex-col bg-background">
        <Header />
        <PinBanner />
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">
          <Outlet />
        </main>
      </div>
    </CompanyPinProvider>
  )
}
