import { createContext, useContext, useState, type ReactNode } from 'react'

interface CompanyPin {
  ico: string | null
  name: string
  type: 'supplier' | 'procurer' | null
}

interface CompanyPinContextValue extends CompanyPin {
  setPin: (ico: string, name: string, type: 'supplier' | 'procurer') => void
  clearPin: () => void
}

const CompanyPinContext = createContext<CompanyPinContextValue | null>(null)

export function CompanyPinProvider({ children }: { children: ReactNode }) {
  const [pin, setPin] = useState<CompanyPin>({ ico: null, name: '', type: null })

  return (
    <CompanyPinContext.Provider
      value={{
        ...pin,
        setPin: (ico, name, type) => setPin({ ico, name, type }),
        clearPin: () => setPin({ ico: null, name: '', type: null }),
      }}
    >
      {children}
    </CompanyPinContext.Provider>
  )
}

export function useCompanyPin() {
  const ctx = useContext(CompanyPinContext)
  if (!ctx) throw new Error('useCompanyPin must be used inside CompanyPinProvider')
  return ctx
}
