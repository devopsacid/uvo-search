# Pinpoint extension — Graf + Trendy CPV — Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the company pinpoint to two tabs that currently ignore the pin: **Graf** (`/graph`) and **Trendy CPV** (`/cpv-trends`). When a supplier or procurer is pinned, Graf's ego-network mode should auto-load the pinned ICO, and Trendy CPV's chart should show the pinned company's CPV breakdown instead of global totals. CPV-network mode in Graf is unrelated and stays unchanged.

**Tech stack:** React 18, TypeScript, TanStack Query v5, react-router-dom v6, Tailwind. Reuses existing `useCompanyPin()` from `@/context/CompanyPinContext`, `useEgoGraph` and `useCpvShare` query hooks, and the i18n keys at `@/i18n/sk`.

---

## Background: current state

- **`pages/GraphPage.tsx`** — two modes via `?mode=ego|cpv`. Ego mode reads `?ico=...&hops=...` from the URL; CPV mode reads `?cpv=...&year=...`. The ICO field is a manual `<input type="text">` (no autocomplete). No awareness of `useCompanyPin()`.
- **`pages/CpvTrendsPage.tsx`** — calls `useCpvShare(yearFrom, yearTo)`. No awareness of pin.
- **CpvTrendsPage is not yet wired into `router.tsx` or `Header.tsx`.** The file exists but has no route. This is a precondition for this work — the tab must be reachable before pin-filtering it has any user-visible effect.
- **Backend `/dashboard/by-cpv`** already accepts `ico` and `entity_type` query params via `_ico_filter()` in `src/uvo_api/routers/dashboard.py:70`. The dashboard hook `useCpvShare` does **not** currently pass them. **No backend change required** — only frontend hook + page wiring.
- **Backend `/graph/ego/{ico}`** already takes ICO in the path; no change needed there either.

---

## Design summary

### Graf — ego mode auto-populate

When pin is active **and** mode is `ego`:
- Seed `icoInput` from `pin.ico` on mount (and when pin changes), if the URL doesn't already have an `ico` param.
- Auto-trigger the search by writing the ICO into the URL (`setSearchParams`) so `useEgoGraph` fires immediately. User does not have to click "Zobrazit".
- The ICO `<input>` stays editable — user can override and press the search button. **Rationale:** the field is the only way to compare ego networks of unpinned ICOs without losing the pin context, and matches the Search-page pattern where pinned filters are visible but the user can still add ad-hoc filters.
- Show a small "locked" chip next to the ICO field when `icoInput === pin.ico` to communicate that the value came from the pin (mirrors `SearchPage`'s locked chip). When the user edits the ICO away from `pin.ico`, the chip disappears.

When pin is cleared while on `/graph?mode=ego` with `?ico=<pinned>`:
- Don't auto-clear the URL `ico` param. Once a graph is loaded, removing the pin should not blow away the visualisation. (Mirrors SearchPage's intentional decision: pin-driven URL params are seeded, not enforced.)

CPV mode is untouched.

### Trendy CPV — pin-filtered totals

When pin is active:
- `useCpvShare(yearFrom, yearTo, ico, entityType)` — extend the hook signature.
- The chart shows the pinned company's CPV mix for the year range. Page title gets a subtitle "pre <name>" (or a small "Zobrazené ako: <name>" chip identical to SearchPage's).
- Year-range filter remains user-controllable.

When pin is cleared:
- Hook reverts to global totals automatically (TanStack Query refetches with new key).

### Router + nav prerequisite

`/cpv-trends` route + Header nav item must be wired before this feature has user-visible effect. This is **Task 0** below.

---

## File map

| File | Action | What changes |
|------|--------|--------------|
| `src/uvo-gui-react/src/router.tsx` | **Modify** | Add `/cpv-trends` route |
| `src/uvo-gui-react/src/components/layout/Header.tsx` | **Modify** | Add `nav.cpvTrends` link |
| `src/uvo-gui-react/src/api/queries/dashboard.ts` | **Modify** | Extend `useCpvShare` + cache key with `ico`/`entityType` |
| `src/uvo-gui-react/src/pages/CpvTrendsPage.tsx` | **Modify** | Read pin, pass to hook, show locked chip |
| `src/uvo-gui-react/src/pages/GraphPage.tsx` | **Modify** | Auto-seed ICO from pin in ego mode, show locked chip |
| `src/uvo-gui-react/src/i18n/sk.ts` | **Modify** | Add `cpvTrends.subtitlePinned`, `graph.lockedFromPin` strings |

**No backend changes.**

---

## Task 0 — Wire up the Trendy CPV tab (prerequisite)

**Files:**
- Modify: `src/uvo-gui-react/src/router.tsx`
- Modify: `src/uvo-gui-react/src/components/layout/Header.tsx`

The page exists at `pages/CpvTrendsPage.tsx` but is not reachable. Without this task the rest of the Trendy-CPV work has no visible effect.

- [ ] **Step 1: Add route**

In `router.tsx`, add the import and a route entry between `pinpoint` and `graph`:

```tsx
import { CpvTrendsPage } from '@/pages/CpvTrendsPage'
// ...
{ path: 'cpv-trends', element: <CpvTrendsPage /> },
```

- [ ] **Step 2: Add nav item**

In `Header.tsx`, insert a nav item using the existing `sk.nav.cpvTrends` key (already defined in `i18n/sk.ts`). Place it after `graph` (or wherever fits the existing order — match the order of `nav.*` keys as the convention).

- [ ] **Step 3: Smoke check**

Start dev server; click the new tab; confirm the page renders with the year-range filter and existing global CPV bars. No pin behavior yet — that's Task 2.

---

## Task 1 — GraphPage ego-mode auto-populate

**Files:**
- Modify: `src/uvo-gui-react/src/pages/GraphPage.tsx`
- Modify: `src/uvo-gui-react/src/i18n/sk.ts` (add one string)

This task makes the Graf ego mode auto-load the pinned ICO. Independent of Task 2 — can run in parallel.

- [ ] **Step 1: Add i18n key**

In `sk.ts` under the `graph` section:

```ts
lockedFromPin: '(z pinpointu)',
```

- [ ] **Step 2: Read pin in GraphPage**

At the top of the component (after the existing `useState`/`useSearchParams` block):

```tsx
import { useCompanyPin } from '@/context/CompanyPinContext'
// ...
const { ico: pinIco, type: pinType, name: pinName } = useCompanyPin()
```

- [ ] **Step 3: Seed URL `ico` from pin on mount + when pin changes**

Add an effect that fires only in ego mode and only when there's no `ico` already in the URL (so we don't clobber a user who navigated explicitly to `/graph?ico=...`):

```tsx
useEffect(() => {
  if (mode !== 'ego') return
  if (!pinIco || !pinType) return
  if (searchParams.get('ico')) return // user already targeted an ICO

  setIcoInput(pinIco)
  setSearchParams((prev) => {
    const next = new URLSearchParams(prev)
    next.set('mode', 'ego')
    next.set('ico', pinIco)
    if (!next.get('hops')) next.set('hops', String(hopsInput))
    return next
  }, { replace: true })
}, [mode, pinIco, pinType]) // eslint-disable-line react-hooks/exhaustive-deps
```

This both populates the input and triggers `useEgoGraph` via the URL change (the existing `activeIco = searchParams.get('ico')` pattern).

- [ ] **Step 4: Update input to track pin changes when not user-edited**

If the user has not typed into `icoInput`, switching the pin to a different company should re-seed. The simplest correct approach: when `pinIco` changes and `icoInput === ''` or `icoInput === previousPinIco`, update both `icoInput` and the URL. Use a ref to track previous pin:

```tsx
const prevPinIcoRef = useRef<string | null>(null)
useEffect(() => {
  if (mode !== 'ego' || !pinIco) {
    prevPinIcoRef.current = pinIco
    return
  }
  const prev = prevPinIcoRef.current
  // Only re-seed if the user hadn't manually edited away from the previous pin
  if (icoInput === '' || icoInput === prev) {
    setIcoInput(pinIco)
    setSearchParams((p) => {
      const next = new URLSearchParams(p)
      next.set('mode', 'ego')
      next.set('ico', pinIco)
      return next
    }, { replace: true })
  }
  prevPinIcoRef.current = pinIco
}, [pinIco]) // eslint-disable-line react-hooks/exhaustive-deps
```

Alternatively keep this simpler: drop the ref, only seed once on mount (Step 3), and accept that switching pins while on /graph requires the user to click search. Discuss with the user before implementing the more complex variant. Prefer the simple variant for v1.

- [ ] **Step 5: Show "locked from pin" chip beside the ICO field**

Inside the existing ego-mode controls block, beside the `<input>`:

```tsx
{pinIco && icoInput === pinIco && (
  <span className="self-end pb-1 text-xs text-muted-foreground">
    {sk.graph.lockedFromPin} {pinName ? `· ${pinName}` : ''}
  </span>
)}
```

The chip auto-disappears when the user edits the ICO field.

- [ ] **Step 6: Verify CPV mode is untouched**

Manually switch to `?mode=cpv` with a pin active — the CPV input should remain blank, no auto-populate, no chip. Confirm by reading the resulting `searchParams` after page load: only `mode=cpv` should be set (plus any existing `cpv`/`year` from the URL).

- [ ] **Step 7: Run tests**

```bash
cd src/uvo-gui-react && npm test -- GraphPage 2>&1 || true
```

If no GraphPage tests exist yet, add a minimal one in `src/test/` that:
1. Renders `<GraphPage />` inside the test wrapper with no pin → no auto-populate.
2. Sets a pin via `localStorage` before render → ICO field shows the pinned ICO and `useEgoGraph` is called.
3. Pin is cleared, navigate to `/graph` fresh → input is empty.

---

## Task 2 — Extend `useCpvShare` with `ico` / `entityType`

**Files:**
- Modify: `src/uvo-gui-react/src/api/queries/dashboard.ts`

Sequential prerequisite for Task 3. Independent of Task 1.

- [ ] **Step 1: Update cache key**

```ts
cpvShare: (yearFrom?: number, yearTo?: number, ico?: string, entityType?: string) =>
  [...dashboardKeys.all, 'cpvShare', yearFrom, yearTo, ico, entityType] as const,
```

- [ ] **Step 2: Update hook signature**

```ts
export function useCpvShare(
  yearFrom?: number,
  yearTo?: number,
  ico?: string,
  entityType?: string,
) {
  return useQuery({
    queryKey: dashboardKeys.cpvShare(yearFrom, yearTo, ico, entityType),
    queryFn: () => {
      const params = new URLSearchParams()
      if (yearFrom != null) params.set('year_from', String(yearFrom))
      if (yearTo != null) params.set('year_to', String(yearTo))
      if (ico) params.set('ico', ico)
      if (entityType) params.set('entity_type', entityType)
      const qs = params.toString()
      return apiClient.get<CpvShare[]>(`/dashboard/by-cpv${qs ? `?${qs}` : ''}`)
    },
    staleTime: 5 * 60 * 1000,
  })
}
```

- [ ] **Step 3: Verify no existing caller breaks**

Only `CpvTrendsPage` calls `useCpvShare`. The new params are optional. Run `npx tsc --noEmit` in `src/uvo-gui-react`.

---

## Task 3 — CpvTrendsPage uses pin

**Files:**
- Modify: `src/uvo-gui-react/src/pages/CpvTrendsPage.tsx`
- Modify: `src/uvo-gui-react/src/i18n/sk.ts` (one string)

Depends on Task 2.

- [ ] **Step 1: Add i18n string**

Under `cpvTrends`:

```ts
subtitlePinned: 'CPV rozpis pre vybranú firmu',
```

- [ ] **Step 2: Read pin in CpvTrendsPage**

```tsx
import { useCompanyPin } from '@/context/CompanyPinContext'
// ...
const { ico, type, name } = useCompanyPin()
```

- [ ] **Step 3: Pass pin to hook**

```tsx
const { data, isLoading } = useCpvShare(
  yearFrom,
  yearTo,
  ico ?? undefined,
  type ?? undefined,
)
```

- [ ] **Step 4: Show locked chip below the title**

Mirror SearchPage's chip placement:

```tsx
{ico && (
  <div className="flex items-center gap-1 rounded-md bg-accent px-2 py-1 text-xs">
    <span className="text-muted-foreground">{sk.pin.viewingAs}:</span>
    <span className="font-medium">{name ?? ''}</span>
    <span className="text-muted-foreground">{sk.common.lockedByPin}</span>
  </div>
)}
```

Place it directly below the `<h1>` and above the year-range filter row.

- [ ] **Step 5: Verify drill-through still makes sense**

`handleCpvClick` navigates to `/search?cpv=...`. With a pin active, SearchPage's existing pin-sync effect adds `supplier_ico` or `procurer_ico` automatically — so the drill-through correctly lands on the pinned company's contracts in that CPV. **No code change needed; document this as expected behavior in the verification step.**

- [ ] **Step 6: Test**

Add or extend a test in `src/test/` that:
1. Renders `<CpvTrendsPage />` with no pin → mock fetch is called with `/dashboard/by-cpv?year_from=...&year_to=...` (no ico/entity_type).
2. Renders with a pin set in localStorage → mock fetch URL includes `&ico=<pinIco>&entity_type=supplier`.
3. Pin chip text is visible when pin is active.

---

## Verification

- [ ] **TypeScript clean:**
  ```bash
  cd src/uvo-gui-react && npx tsc --noEmit
  ```

- [ ] **All tests pass:**
  ```bash
  cd src/uvo-gui-react && npm test -- --run
  ```

- [ ] **Manual smoke (`npm run dev`):**
  1. Open `/pinpoint`, pin a known supplier (e.g. MICROCOMP).
  2. Click **Graf** in nav. Mode defaults to `ego`. The ICO field is pre-filled with MICROCOMP's ICO; "(z pinpointu) · MICROCOMP" chip appears beside it; the network loads automatically.
  3. Edit the ICO field manually → chip disappears. Click "Zobrazit" → loads the new graph.
  4. Switch to CPV mode → CPV field is empty, no chip, no auto-load. Confirmed unchanged.
  5. Click **Trendy CPV** in nav. Below the title see "Zobrazené ako: MICROCOMP (nastavené cez pinpoint)". The bar list shows MICROCOMP's CPV mix, not global. Network tab confirms `&ico=...&entity_type=supplier` in the request.
  6. Change year range → still pinned, refetch with new range.
  7. Click a CPV row → routed to `/search?cpv=...`; SearchPage's existing pin sync should also add `supplier_ico`. Confirm filtered list.
  8. Clear pin via the banner `×` → both pages revert: Graf keeps the loaded graph (no auto-clear, by design); Trendy CPV refetches global totals and chip disappears.
  9. Pin a procurer instead → repeat steps 2 and 5; chips and request params reflect `entity_type=procurer`.

---

## Parallelism

- **Task 0** must complete first (the Trendy-CPV route is currently absent — without it, Tasks 2+3 have no user-visible effect, and tests that mount the page through the router would fail).
- **Task 1** (GraphPage) is fully independent — can run in parallel with Tasks 0/2/3.
- **Task 2** (hook signature) must precede **Task 3** (page wiring) — sequential within the CpvTrends thread.
- After Task 0, two parallel threads:
  - Thread A: Task 1 (GraphPage)
  - Thread B: Task 2 → Task 3 (CpvTrends)

Suggested allocation: one developer agent per thread.

---

## Backend dependencies

**None.** Both required backend params already exist:

- `GET /dashboard/by-cpv` accepts `ico` + `entity_type` (`src/uvo_api/routers/dashboard.py:220`).
- `GET /graph/ego/{ico}` takes ICO in the path; nothing to add.

---

## Edge cases / gotchas

1. **GraphPage stores ICO as a separate `useState` AND a URL param.** The existing pattern keeps `icoInput` (form-state, free typing) decoupled from `activeIco = searchParams.get('ico')` (committed query). The auto-seed effect must update **both** — only writing to `searchParams` would leave the input visually empty until the user opens the form.

2. **Don't clobber explicit URL ICOs.** If a user lands on `/graph?ico=12345` with a different pin active, respect the URL — it's the explicit signal. The Step 3 effect only seeds when `searchParams.get('ico')` is empty.

3. **Pin in `localStorage` + URL race.** `CompanyPinContext` reads URL params (`pin_ico`, `pin_type`) on mount and falls back to localStorage. A direct hit on `/graph?pin_ico=X&pin_type=supplier` should set the pin **before** GraphPage's auto-seed effect fires. React's commit ordering inside the same provider tree guarantees this; verify with the smoke test step 9.

4. **CpvTrendsPage drill-through composes with SearchPage's pin sync.** `handleCpvClick` navigates with only `?cpv=...`. SearchPage then runs its existing pin → URL effect and adds `supplier_ico`. No conflict, but this two-stage param assembly is non-obvious — call it out in a code comment in Step 5 of Task 3.

5. **CpvTrendsPage is not currently reachable.** Without Task 0, none of this work is testable end-to-end. The prerequisite is real, not cosmetic — it must land in the same change set or as a strict precondition.

6. **`pin.name` can be null.** When seeded via URL without `pin_name`, the chip text falls back to empty. Use `pinName ?? ''` (matches PinBanner's existing handling).

7. **GraphPage CPV mode must remain untouched.** The auto-seed effect must guard on `mode !== 'ego'`. The smoke test step 4 verifies this; do not skip it.

8. **TanStack Query cache key must include `ico`/`entityType` for `useCpvShare`.** Forgetting this would cause stale global data to be served when the pin toggles. Step 1 of Task 2 is load-bearing.

---

## Out of scope

- **Auto-load of Graf when pin is set elsewhere and user has never visited /graph** — covered, but no preloading. The graph is only fetched when the user actually navigates to /graph.
- **CPV-network mode pin awareness** — explicitly out of scope per the brief; the CPV-network input is a CPV code, not a company.
- **Per-year CPV breakdown** — current `/by-cpv` returns aggregated totals, not a year-stacked series. Out of scope.
- **Locking the ICO input read-only when pinned** — rejected: keeping it editable allows ad-hoc comparisons without breaking the pin context.
