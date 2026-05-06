import { useNavigate } from 'react-router-dom'
import { useCompanyPin } from '@/context/CompanyPinContext'
import { EntityAutocomplete } from '@/components/search/EntityAutocomplete'
import { cn } from '@/lib/utils'
import sk from '@/i18n/sk'

export function PinpointPage() {
  const { ico, name, type, setPin, clearPin } = useCompanyPin()
  const navigate = useNavigate()

  function handleSelect(selectedIco: string, selectedType: 'supplier' | 'procurer', selectedName: string) {
    setPin(selectedIco, selectedName, selectedType)
  }

  const typeLabel = type === 'supplier' ? sk.search.typeSupplier : sk.search.typeProcurer
  const detailHref = `/firma/${ico}`

  return (
    <div className="mx-auto max-w-xl space-y-8 py-12">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold text-foreground">{sk.pinpoint.title}</h1>
        <p className="text-sm text-muted-foreground">{sk.pinpoint.subtitle}</p>
      </div>

      <EntityAutocomplete
        placeholder={sk.pinpoint.searchPlaceholder}
        className="w-full"
        autoFocus
        onSelect={handleSelect}
      />

      {ico && type ? (
        <div className="rounded-lg border border-border bg-card p-4 space-y-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {sk.pinpoint.currentPin}
          </p>
          <div className="flex items-center gap-2">
            <span
              className={cn(
                'shrink-0 rounded px-1.5 py-0.5 text-xs font-medium uppercase tracking-wide',
                type === 'supplier'
                  ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
                  : 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
              )}
            >
              {typeLabel}
            </span>
            <span className="flex-1 truncate font-medium text-foreground">{name}</span>
            <span className="text-xs text-muted-foreground">{ico}</span>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => navigate('/')}
              className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            >
              {sk.pinpoint.showOverview}
            </button>
            <button
              onClick={() => navigate(detailHref)}
              className="rounded-md border border-border px-3 py-1.5 text-sm font-medium hover:bg-accent"
            >
              {sk.pinpoint.showDetail}
            </button>
            <button
              onClick={clearPin}
              className="ml-auto rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              {sk.pin.clear}
            </button>
          </div>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">{sk.pinpoint.noPin}</p>
      )}
    </div>
  )
}
