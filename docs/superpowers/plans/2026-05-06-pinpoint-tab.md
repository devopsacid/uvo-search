# Pinpoint Tab — Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the awkward EntityAutocomplete embedded in the Overview page header with a dedicated `/pinpoint` nav tab. The tab is a full-page company picker — prominent search box, current-pin preview, quick actions. Selecting a company sets the pin and redirects to Overview.

**Why the current UX is broken:** The autocomplete is a 288px input beside `<h1>` — easy to miss, competing with the global `/` shortcut that also exists in `SearchPage`, and gives no feedback about the currently pinned company unless the banner is already showing.

---

## Design

### Route & nav

New nav item **Pinpoint** → `/pinpoint`, inserted between _Obstaravatelia_ and _Graf_.

### PinpointPage layout

```
┌─────────────────────────────────────────────────────────┐
│  [h1] Sledovanie firmy                                  │
│  [p]  Vyhľadajte dodávateľa alebo obstarávateľa …      │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  🔍  Zadajte názov alebo IČO firmy …            │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ── Ak je pin aktívny ─────────────────────────────    │
│  ┌─────────────────────────────────────────────────┐   │
│  │  [Dod.]  MICROCOMP s.r.o.          IČO 12345   │   │
│  │  [Zobraziť prehľad]  [Zobraziť detail]  [Zrušiť]│  │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

- `EntityAutocomplete` with `onSelect` wired → calls `setPin()` then `navigate('/')`.
- Active-pin card: type badge, name, ICO, three action buttons.
- No pin active: only the search input + instructional copy.

### OverviewPage cleanup

Remove the `EntityAutocomplete` picker from the Overview page header row. The `<h1>` stands alone. Pin selection now lives exclusively on `/pinpoint`. The PinBanner is the only in-page reminder.

### PinBanner — "Zmeniť" link

Add a small secondary link `Zmeniť` after the company name that navigates to `/pinpoint`. Lets users swap company without hunting for the tab.

---

## File map

| File | Action | What changes |
|------|--------|--------------|
| `src/uvo-gui-react/src/pages/PinpointPage.tsx` | **Create** | New dedicated picker page |
| `src/uvo-gui-react/src/router.tsx` | **Modify** | Add `/pinpoint` route |
| `src/uvo-gui-react/src/components/layout/Header.tsx` | **Modify** | Add Pinpoint nav item |
| `src/uvo-gui-react/src/components/layout/PinBanner.tsx` | **Modify** | Add "Zmeniť" link to `/pinpoint` |
| `src/uvo-gui-react/src/pages/OverviewPage.tsx` | **Modify** | Remove EntityAutocomplete + unused `setPin` import |
| `src/uvo-gui-react/src/i18n/sk.ts` | **Modify** | Add `nav.pinpoint` + `pinpoint.*` strings |

---

## Task 1 — i18n strings

**File:** `src/uvo-gui-react/src/i18n/sk.ts`

- [ ] Add `nav.pinpoint`:
  ```ts
  pinpoint: 'Pinpoint',
  ```
  (between `procurers` and `graph` in the `nav` object)

- [ ] Add top-level `pinpoint` section:
  ```ts
  pinpoint: {
    title: 'Sledovanie firmy',
    subtitle: 'Vyberte dodávateľa alebo obstarávateľa. Všetky karty sa prefiltrujú na vybranú firmu.',
    searchPlaceholder: 'Zadajte názov alebo IČO firmy …',
    currentPin: 'Aktuálna firma',
    showOverview: 'Zobraziť prehľad',
    showDetail: 'Zobraziť detail',
    change: 'Zmeniť',
    noPin: 'Žiadna firma nie je vybraná.',
  },
  ```

---

## Task 2 — PinpointPage

**File:** `src/uvo-gui-react/src/pages/PinpointPage.tsx` (create)

- [ ] **Step 1: scaffold page**

```tsx
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
    navigate('/')
  }

  const typeLabel = type === 'supplier' ? sk.search.typeSupplier : sk.search.typeProcurer
  const detailHref = type === 'supplier' ? `/suppliers/${ico}` : `/procurers/${ico}`

  return (
    <div className="mx-auto max-w-xl space-y-8 py-12">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold text-foreground">{sk.pinpoint.title}</h1>
        <p className="text-sm text-muted-foreground">{sk.pinpoint.subtitle}</p>
      </div>

      <EntityAutocomplete
        placeholder={sk.pinpoint.searchPlaceholder}
        className="w-full"
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
```

---

## Task 3 — Router

**File:** `src/uvo-gui-react/src/router.tsx`

- [ ] Import `PinpointPage`
- [ ] Add route: `{ path: 'pinpoint', element: <PinpointPage /> }`
  (between `procurers/:ico` and `graph`)

---

## Task 4 — Header nav

**File:** `src/uvo-gui-react/src/components/layout/Header.tsx`

- [ ] Add nav item between `procurers` and `graph`:
  ```ts
  { to: '/pinpoint', label: sk.nav.pinpoint, end: false },
  ```

---

## Task 5 — PinBanner "Zmeniť" link

**File:** `src/uvo-gui-react/src/components/layout/PinBanner.tsx`

- [ ] Add a `Zmeniť` button after the company name button, before the ICO span:
  ```tsx
  <button
    onClick={() => navigate('/pinpoint')}
    className="shrink-0 text-xs text-muted-foreground underline-offset-2 hover:underline"
  >
    {sk.pinpoint.change}
  </button>
  ```

---

## Task 6 — OverviewPage cleanup

**File:** `src/uvo-gui-react/src/pages/OverviewPage.tsx`

- [ ] Remove `import { EntityAutocomplete }` line
- [ ] Change `const { ico, name, type, setPin } = useCompanyPin()` → `const { ico, name, type } = useCompanyPin()` (drop `setPin`)
- [ ] Remove the `<EntityAutocomplete … onSelect={…} />` JSX block and the wrapping `<div className="flex flex-wrap …">` if it only holds the h1 + autocomplete (simplify to plain `<h1>`)

---

## Verification

```bash
cd src/uvo-gui-react
npx tsc --noEmit          # no errors
npm test -- --run         # 87+ tests pass
```

Manual smoke:
1. Nav shows **Pinpoint** tab between Obstaravatelia and Graf
2. Click Pinpoint → centered search input, "Žiadna firma nie je vybraná."
3. Type "MICROCOMP" → dropdown → select → pin set → redirected to Overview showing filtered data + banner
4. Banner shows **Zmeniť** link → returns to `/pinpoint` showing the active-pin card
5. "Zobraziť prehľad" → Overview, "Zobraziť detail" → supplier detail page, "Zrušiť pin" → clears pin, card disappears
6. Refresh any page → pin restored from localStorage
7. Overview URL shows `?pin_ico=…` in address bar
