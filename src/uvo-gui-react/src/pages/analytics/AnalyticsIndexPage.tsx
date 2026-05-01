import { useNavigate } from 'react-router-dom'
import { EntityAutocomplete } from '@/components/search/EntityAutocomplete'
import sk from '@/i18n/sk'

export function AnalyticsIndexPage() {
  const navigate = useNavigate()

  function handleSelect(ico: string, type: 'supplier' | 'procurer') {
    navigate(
      type === 'procurer'
        ? `/analytics/executive/${ico}?entity_type=procurer`
        : `/analytics/executive/${ico}?entity_type=supplier`,
    )
  }

  return (
    <div className="mx-auto max-w-lg py-20 text-center space-y-6">
      <h1 className="text-xl font-semibold text-foreground">{sk.analytics.executive.title}</h1>
      <p className="text-sm text-muted-foreground">{sk.analytics.common.noDataHint}</p>
      <EntityAutocomplete
        placeholder={sk.search.autocompletePlaceholder}
        onSelect={handleSelect}
      />
    </div>
  )
}
