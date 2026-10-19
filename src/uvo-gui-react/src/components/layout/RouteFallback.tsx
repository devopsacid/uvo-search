import sk from '@/i18n/sk'

export function RouteFallback() {
  return (
    <div role="status" className="p-8 text-muted-foreground">
      {sk.common.loadingPage}
    </div>
  )
}
