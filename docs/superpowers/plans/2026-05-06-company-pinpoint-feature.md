# Company Pinpoint Feature — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent company "pinpoint" selector that filters all four main tabs — Prehlad, Vyhladavanie, Dodavatelia, Obstaravatelia — to a single company's perspective. User can pick any supplier or procurer from an autocomplete, see a thin persistent banner across all tabs, and clear it at any time.

**Tech Stack:** React 18, TypeScript, TanStack Query v5, react-router-dom v6, Tailwind CSS, existing `EntityAutocomplete` + `useSupplier`/`useProcurer` hooks.

---

## Background: Current State

- `OverviewPage` calls all dashboard hooks without any `ico`/`entityType` arguments.
- `useDashboardSummary`, `useSpendByYear` already accept `ico?` + `entityType?` but are never used with them.
- `useRecent` does not accept `ico`/`entityType` even though the backend supports it.
- `useTopSuppliers`, `useTopProcurers` return global rankings only — when a company is pinned these charts are replaced by entity-specific partner data from `useSupplier`/`useSupplierSummary` hooks (no backend changes needed).
- `EntityAutocomplete` is production-ready: debounced fuzzy search, keyboard nav, `onSelect(ico, type)` callback.
- No global state mechanism exists — each page is isolated. A React context is the right fit (in-memory, persists across tab navigation, no URL noise).

---

## Design Summary

### Pin state
`CompanyPinContext` (`src/context/CompanyPinContext.tsx`) wraps the app. State:
```ts
{ ico: string | null; name: string; type: 'supplier' | 'procurer' | null }
```
Methods: `setPin(ico, name, type)` / `clearPin()`.

### Thin PinBanner
A 36px strip rendered in `Layout.tsx` between `<Header>` and `<main>`, visible only when pin is set:
```
[Dod.] MICROCOMP - Computersystém s r. o.   ×
```
Clicking the name navigates to the entity detail page. The `×` calls `clearPin()`.

### Per-tab behavior when pinned

| Tab | Pin = Supplier | Pin = Procurer |
|-----|---------------|----------------|
| **Prehlad** | All KPIs/charts filtered to supplier; top bar charts replaced by supplier's top procurers | All KPIs/charts filtered to procurer; top bar charts replaced by procurer's top suppliers |
| **Vyhladavanie** | `supplier_ico` URL param pre-set; locked chip in filter bar | `procurer_ico` URL param pre-set; locked chip in filter bar |
| **Dodavatelia** | Redirects to `/suppliers/:ico` detail page | Shows normal supplier list (pin is procurer, different entity) |
| **Obstaravatelia** | Shows normal procurer list (pin is supplier) | Redirects to `/procurers/:ico` detail page |

---

## File Map

| File | Action | What changes |
|------|--------|--------------|
| `src/uvo-gui-react/src/context/CompanyPinContext.tsx` | **Create** | Context + `useCompanyPin()` hook |
| `src/uvo-gui-react/src/components/layout/PinBanner.tsx` | **Create** | Thin strip component |
| `src/uvo-gui-react/src/components/layout/Layout.tsx` | **Modify** | Wrap in `CompanyPinProvider`, add `<PinBanner>` |
| `src/uvo-gui-react/src/api/queries/dashboard.ts` | **Modify** | Extend `useRecent` + cache keys with `ico`/`entityType` |
| `src/uvo-gui-react/src/pages/OverviewPage.tsx` | **Modify** | Add pin picker, pass pin to hooks, swap top-N charts when pinned |
| `src/uvo-gui-react/src/pages/SearchPage.tsx` | **Modify** | Sync pin → URL param on mount/change; locked chip |
| `src/uvo-gui-react/src/pages/SuppliersPage.tsx` | **Modify** | Redirect to `/suppliers/:ico` when `pin.type === 'supplier'` |
| `src/uvo-gui-react/src/pages/ProcurersPage.tsx` | **Modify** | Redirect to `/procurers/:ico` when `pin.type === 'procurer'` |
| `src/uvo-gui-react/src/i18n/sk.ts` | **Modify** | Add `pin.*` strings |

---

## Task 1: CompanyPinContext + PinBanner + Layout wiring

**Files:**
- Create: `src/uvo-gui-react/src/context/CompanyPinContext.tsx`
- Create: `src/uvo-gui-react/src/components/layout/PinBanner.tsx`
- Modify: `src/uvo-gui-react/src/components/layout/Layout.tsx`

- [ ] **Step 1: Create `CompanyPinContext.tsx`**

```tsx
// src/uvo-gui-react/src/context/CompanyPinContext.tsx
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
```

- [ ] **Step 2: Create `PinBanner.tsx`**

```tsx
// src/uvo-gui-react/src/components/layout/PinBanner.tsx
import { useNavigate } from 'react-router-dom'
import { useCompanyPin } from '@/context/CompanyPinContext'
import { cn } from '@/lib/utils'
import sk from '@/i18n/sk'

export function PinBanner() {
  const { ico, name, type, clearPin } = useCompanyPin()
  const navigate = useNavigate()

  if (!ico || !type) return null

  const typeLabel = type === 'supplier' ? sk.search.typeSupplier : sk.search.typeProcurer
  const href = type === 'supplier' ? `/suppliers/${ico}` : `/procurers/${ico}`

  return (
    <div className="flex items-center gap-2 border-b border-border bg-accent/60 px-4 py-1.5 text-xs">
      <span
        className={cn(
          'shrink-0 rounded px-1.5 py-0.5 font-medium uppercase tracking-wide',
          type === 'supplier'
            ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
            : 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
        )}
      >
        {typeLabel}
      </span>
      <button
        onClick={() => navigate(href)}
        className="flex-1 truncate text-left font-medium text-foreground hover:underline"
      >
        {name}
      </button>
      <span className="text-muted-foreground">{ico}</span>
      <button
        onClick={clearPin}
        aria-label={sk.pin.clear}
        className="ml-2 rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"
      >
        ×
      </button>
    </div>
  )
}
```

- [ ] **Step 3: Update `Layout.tsx`**

```tsx
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
```

- [ ] **Step 4: Add `pin` strings to `sk.ts`**

In `src/uvo-gui-react/src/i18n/sk.ts`, add a `pin` section:

```ts
pin: {
  placeholder: 'Vyhladat firmu...',
  clear: 'Zrusit vybranú firmu',
  viewingAs: 'Zobrazene ako',
},
```

- [ ] **Step 5: Verify the banner appears/disappears**

Start dev server (`cd src/uvo-gui-react && npm run dev`). Manually call `setPin` from browser console via React DevTools, confirm banner renders. Confirm `clearPin()` hides it.

---

## Task 2: Extend `useRecent` hook with `ico` / `entityType`

**Files:**
- Modify: `src/uvo-gui-react/src/api/queries/dashboard.ts`

The backend `/api/dashboard/recent` already accepts `ico` and `entity_type` params. Only the frontend hook needs updating.

- [ ] **Step 1: Update `dashboardKeys.recent` cache key**

```ts
recent: (limit?: number, ico?: string, entityType?: string) =>
  [...dashboardKeys.all, 'recent', limit, ico, entityType] as const,
```

- [ ] **Step 2: Update `useRecent` signature**

```ts
export function useRecent(limit = 10, ico?: string, entityType?: string) {
  return useQuery({
    queryKey: dashboardKeys.recent(limit, ico, entityType),
    queryFn: () => {
      const params = new URLSearchParams({ limit: String(limit) })
      if (ico) params.set('ico', ico)
      if (entityType) params.set('entity_type', entityType)
      return apiClient.get<RecentContract[]>(`/dashboard/recent?${params.toString()}`)
    },
    staleTime: 60 * 1000,
  })
}
```

- [ ] **Step 3: Verify existing callers still compile**

`OverviewPage` calls `useRecent(8)` — the new optional params don't break it. Run `npm run build` (or `tsc --noEmit`) inside `src/uvo-gui-react`.

---

## Task 3: OverviewPage — pin picker + full filter wiring

**Files:**
- Modify: `src/uvo-gui-react/src/pages/OverviewPage.tsx`

This task uses `useCompanyPin()`, passes pin to hooks, and conditionally swaps the top-N bar charts.

- [ ] **Step 1: Add pin picker in page header**

Import `EntityAutocomplete` and `useCompanyPin`. Replace the page `<h1>` block:

```tsx
const { ico, name, type, setPin, clearPin } = useCompanyPin()

// In JSX, below <h1>:
<div className="flex items-center gap-3">
  <EntityAutocomplete
    placeholder={sk.pin.placeholder}
    className="w-72"
    onSelect={(selectedIco, selectedType) => {
      // name is not available from EntityAutocomplete callback — wire it via a wrapper
      // (see Step 2 for the approach using a local state)
    }}
  />
</div>
```

`EntityAutocomplete.onSelect` only provides `ico` and `type`, not `name`. Two options:
- **Preferred:** extend `EntityAutocomplete` interface to pass `name` in the callback: change `onSelect?: (ico: string, type, name: string) => void` in `EntityAutocomplete.tsx`. The hit object already has `hit.name`. Add it to the existing `commit()` call.

Updated `EntityAutocomplete.tsx` callback interface:
```ts
onSelect?: (ico: string, type: 'supplier' | 'procurer', name: string) => void
```

In `commit()`:
```ts
onSelect(hit.ico, hit.type as 'supplier' | 'procurer', hit.name)
```

Existing callers (`SearchPage`) don't use the third arg — no breakage.

- [ ] **Step 2: Pass pin to filtering hooks**

```tsx
const { data: summary, ... } = useDashboardSummary(ico ?? undefined, type ?? undefined)
const { data: spendByYear, ... } = useSpendByYear(ico ?? undefined, type ?? undefined)
const { data: recent, ... } = useRecent(8, ico ?? undefined, type ?? undefined)
```

Global top-N hooks stay as-is when pin is `null`. When pin is active, they are **not called** (the charts are replaced — see Step 3).

- [ ] **Step 3: Conditionally swap top-N charts**

When `ico` is set, the global top-10 charts don't make sense. Replace them with entity-specific partner charts using existing detail hooks.

```tsx
// At hook level (always call both, enable conditionally):
const { data: supplierDetail } = useSupplier(ico ?? '')
const { data: procurerDetail } = useProcurer(ico ?? '')

// In JSX for top charts section:
{ico ? (
  // Pinned view: show entity's top partners
  <div className="grid gap-6 md:grid-cols-2">
    <SectionCard>
      <SectionTitle>
        {type === 'supplier' ? sk.overview.sectionTopProcurers : sk.overview.sectionTopSuppliers}
      </SectionTitle>
      {/* BarChart using supplierDetail?.top_procurers or procurerDetail?.top_suppliers */}
      <PartnerBarChart
        data={type === 'supplier' ? supplierDetail?.top_procurers : procurerDetail?.top_suppliers}
        valueKey={type === 'supplier' ? 'total_spend' : 'total_value'}
      />
    </SectionCard>
  </div>
) : (
  // Global view: existing two-column grid
  <div className="grid gap-6 md:grid-cols-2">
    {/* ... existing top suppliers + top procurers code ... */}
  </div>
)}
```

`PartnerBarChart` is a thin local helper (20 lines) reusing the same `BarChart` markup already in the file — not a new abstraction.

> **Note:** Check what field names `SupplierDetail.top_procurers` / `ProcurerDetail.top_suppliers` actually use by reading `src/uvo-gui-react/src/api/types.ts` before coding — the value key may differ (`total_spend` vs `total_value`).

- [ ] **Step 4: Run tests**

```bash
cd src/uvo-gui-react && npm test -- --testPathPattern=OverviewPage 2>&1
```

---

## Task 4: SearchPage — sync pin to URL filter

**Files:**
- Modify: `src/uvo-gui-react/src/pages/SearchPage.tsx`

When a company is pinned, the search page should pre-filter to that company's contracts. The pin is the "main point of view" — it's a locked filter that is set by the banner, not by the search page's own filter controls.

- [ ] **Step 1: Add pin sync effect**

```tsx
const { ico, type } = useCompanyPin()

// Sync pin → URL param on mount and when pin changes.
// Only if pin is set and not already matching current URL param.
useEffect(() => {
  if (!ico || !type) return
  const paramKey = type === 'supplier' ? 'supplier_ico' : 'procurer_ico'
  const current = searchParams.get(paramKey)
  if (current !== ico) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set(paramKey, ico)
      // Clear the other entity param if set
      next.delete(type === 'supplier' ? 'procurer_ico' : 'supplier_ico')
      next.delete('page')
      return next
    }, { replace: true })
  }
}, [ico, type]) // eslint-disable-line react-hooks/exhaustive-deps
```

When pin is cleared (`ico` becomes null), remove the param:

```tsx
useEffect(() => {
  if (ico) return
  // Only remove if we previously set a pinned param
  // (don't nuke manually-typed params on first render)
  // Use a ref to track whether pin was previously active
}, [ico])
```

Simpler approach: track `prevIco` with a ref; when it transitions from truthy to null, clear the param.

- [ ] **Step 2: Show locked pin chip in filter area**

Add a read-only chip above or beside the existing `EntityAutocomplete` filter in SearchPage:

```tsx
{ico && (
  <div className="flex items-center gap-1 rounded-md bg-accent px-2 py-1 text-xs">
    <span className="text-muted-foreground">{sk.pin.viewingAs}:</span>
    <span className="font-medium">{name}</span>
    <span className="text-muted-foreground">{sk.common.lockedByPin}</span>
  </div>
)}
```

The chip is informational only — clearing the pin happens via the PinBanner `×`, not from here.

- [ ] **Step 3: Add `common.lockedByPin` i18n string**

```ts
common: {
  // ... existing
  lockedByPin: '(nastavené cez pinpoint)',
}
```

---

## Task 5: Dodavatelia + Obstaravatelia — redirect on matching pin type

**Files:**
- Modify: `src/uvo-gui-react/src/pages/SuppliersPage.tsx`
- Modify: `src/uvo-gui-react/src/pages/ProcurersPage.tsx`

When the pin matches the page's entity type, skip the list and go straight to the detail page.

- [ ] **Step 1: SuppliersPage redirect**

At the top of `SuppliersPage` component (after hooks):

```tsx
const { ico, type } = useCompanyPin()
const navigate = useNavigate()

useEffect(() => {
  if (ico && type === 'supplier') {
    navigate(`/suppliers/${ico}`, { replace: true })
  }
}, [ico, type, navigate])
```

- [ ] **Step 2: ProcurersPage redirect**

Same pattern:

```tsx
const { ico, type } = useCompanyPin()
const navigate = useNavigate()

useEffect(() => {
  if (ico && type === 'procurer') {
    navigate(`/procurers/${ico}`, { replace: true })
  }
}, [ico, type, navigate])
```

- [ ] **Step 3: Verify back-navigation works**

With pin active, navigate to Dodavatelia → should land on supplier detail. Clicking "← Back" on the detail page should go to `/suppliers` list (which will redirect again — this is correct UX; to browse the full list, clear the pin first). Confirm this loop doesn't cause issues.

If the redirect loop is annoying (user can't view the list while pinned), consider adding a "Zobraziť všetkých dodávateľov" link on the detail page that calls `clearPin()` first. This is a UX polish item and can be deferred.

---

## Task 6: EntityAutocomplete — add `name` to `onSelect` callback

**Files:**
- Modify: `src/uvo-gui-react/src/components/search/EntityAutocomplete.tsx`

Required by Task 3 so OverviewPage can call `setPin(ico, name, type)`.

- [ ] **Step 1: Update interface**

```ts
interface EntityAutocompleteProps {
  placeholder?: string
  className?: string
  onSelect?: (ico: string, type: 'supplier' | 'procurer', name: string) => void
}
```

- [ ] **Step 2: Pass name in `commit()`**

```ts
onSelect(hit.ico, hit.type as 'supplier' | 'procurer', hit.name)
```

- [ ] **Step 3: Confirm SearchPage still compiles**

`SearchPage` uses `onSelect={(ico, type) => ...}` — TypeScript ignores extra args, no change needed there.

---

## Verification

After all tasks:

1. **All dashboard tests pass:**
   ```bash
   cd src/uvo-gui-react && npm test 2>&1
   ```

2. **Manual smoke test (dev server):**
   - Start dev server: `npm run dev`
   - On Prehlad, type "MICROCOMP" in picker → select it → banner appears, KPIs change, top chart shows MICROCOMP's top procurers
   - Navigate to Vyhladavanie → contracts pre-filtered to MICROCOMP, locked chip visible
   - Navigate to Dodavatelia → redirected to MICROCOMP detail page
   - Click `×` in banner → pin cleared, Dodavatelia shows full list, Vyhladavanie clears the filter
   - Repeat with a procurer (e.g. "Ministerstvo")

3. **TypeScript clean build:**
   ```bash
   cd src/uvo-gui-react && npx tsc --noEmit 2>&1
   ```

---

## Out of Scope (v1)

- **URL-persistent pin** (bookmarkable `?pin_ico=...&pin_type=...`): adds complexity to every route; in-memory is sufficient for a dashboard session.
- **Cross-type partner lists**: e.g., on Obstaravatelia when pinned as supplier, showing that supplier's procurement partners. Requires a new API aggregation; deferred.
- **Pin history / recent pins**: dropdown of last N pinned companies.
- **Mobile UX**: PinBanner at 36px is fine on desktop; may need adjustment for narrow viewports.
