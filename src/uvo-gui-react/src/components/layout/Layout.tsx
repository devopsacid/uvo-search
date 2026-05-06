import { useEffect } from 'react'
import { Outlet, useNavigate, useSearchParams } from 'react-router-dom'
import { Header } from './Header'
import { PinBanner } from './PinBanner'
import { CompanyPinProvider } from '@/context/CompanyPinContext'

function PinIcoRedirect() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  useEffect(() => {
    const pinIco = searchParams.get('pin_ico')
    if (pinIco) {
      navigate(`/firma/${pinIco}`, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // run once on mount only
  return null
}

export function Layout() {
  return (
    <CompanyPinProvider>
      <div className="flex min-h-screen flex-col bg-background">
        <Header />
        <PinBanner />
        <PinIcoRedirect />
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">
          <Outlet />
        </main>
      </div>
    </CompanyPinProvider>
  )
}
