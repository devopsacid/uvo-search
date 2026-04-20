import sk from '@/i18n/sk'

export function AboutPage() {
  return (
    <div className="max-w-2xl">
      <h1 className="mb-4 text-xl font-semibold text-foreground">{sk.about.title}</h1>
      <p className="text-muted-foreground">{sk.about.description}</p>
      <dl className="mt-6 space-y-4">
        <div>
          <dt className="text-sm font-medium text-foreground">{sk.about.dataSource}</dt>
          <dd className="mt-1 text-sm text-muted-foreground">{sk.about.dataSourceText}</dd>
        </div>
      </dl>
    </div>
  )
}
