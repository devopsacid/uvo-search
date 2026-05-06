import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'

interface CompanyPin {
  ico: string | null
  name: string | null
  type: 'supplier' | 'procurer' | null
}

interface CompanyPinContextValue extends CompanyPin {
  setPin: (ico: string, name: string, type: 'supplier' | 'procurer') => void
  clearPin: () => void
}

const CompanyPinContext = createContext<CompanyPinContextValue | null>(null)

const STORAGE_KEY = 'uvo_pin'

function readStorage(): CompanyPin {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ico: null, name: null, type: null }
    return JSON.parse(raw) as CompanyPin
  } catch {
    return { ico: null, name: null, type: null }
  }
}

function writeStorage(pin: CompanyPin) {
  if (pin.ico) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(pin))
  } else {
    localStorage.removeItem(STORAGE_KEY)
  }
}

export function CompanyPinProvider({ children }: { children: ReactNode }) {
  const [searchParams] = useSearchParams()

  const [pin, setPinState] = useState<CompanyPin>(() => {
    // URL params take priority — enables shared links to seed the pin
    const urlIco = searchParams.get('pin_ico')
    const urlType = searchParams.get('pin_type') as 'supplier' | 'procurer' | null
    const urlName = searchParams.get('pin_name') ?? null
    if (urlIco && (urlType === 'supplier' || urlType === 'procurer')) {
      const fromUrl = { ico: urlIco, name: urlName, type: urlType }
      writeStorage(fromUrl)
      return fromUrl
    }
    return readStorage()
  })

  const setPin = useCallback((ico: string, name: string, type: 'supplier' | 'procurer') => {
    const next: CompanyPin = { ico, name, type }
    writeStorage(next)
    setPinState(next)
  }, [])

  const clearPin = useCallback(() => {
    writeStorage({ ico: null, name: null, type: null })
    setPinState({ ico: null, name: null, type: null })
  }, [])

  return (
    <CompanyPinContext.Provider value={{ ...pin, setPin, clearPin }}>
      {children}
    </CompanyPinContext.Provider>
  )
}

export function useCompanyPin() {
  const ctx = useContext(CompanyPinContext)
  if (!ctx) throw new Error('useCompanyPin must be used inside CompanyPinProvider')
  return ctx
}
