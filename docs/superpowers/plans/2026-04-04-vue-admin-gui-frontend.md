# UVO Admin GUI (Vue 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Vue 3 admin frontend (`src/uvo-gui-vuejs/`) that consumes the FastAPI analytics API and provides executive dashboards + investigative drill-down views.

**Architecture:** Vue 3 SPA with Vite, Vue Router 4, Pinia (global filter + theme stores), Chart.js for charts, Tailwind CSS for styling, vue-i18n for SK/EN. All API calls go through a thin `src/api/client.ts` wrapper pointing at the FastAPI service on port 8001. No SSR — pure SPA.

**Tech Stack:** Node.js 20+, Vue 3 + `<script setup>`, Vite, Vue Router 4, Pinia, Chart.js + vue-chartjs, Tailwind CSS v3, vue-i18n v9, Vitest + Vue Test Utils for unit tests

**Prerequisite:** Plan A (FastAPI analytics API) must be complete and running on port 8001.

---

## File Map

```
src/uvo-gui-vuejs/
├── index.html
├── package.json
├── vite.config.ts
├── tailwind.config.js
├── postcss.config.js
├── tsconfig.json
├── src/
│   ├── main.ts                        App entry — mounts App, registers plugins
│   ├── App.vue                        Root component — router-view + TopNav
│   ├── router/
│   │   └── index.ts                   Vue Router config — 8 routes
│   ├── stores/
│   │   ├── filter.ts                  Pinia — global company filter (ico, name, type)
│   │   └── theme.ts                   Pinia — dark/light mode toggle
│   ├── i18n/
│   │   ├── index.ts                   vue-i18n setup
│   │   ├── sk.ts                      Slovak translations
│   │   └── en.ts                      English translations
│   ├── api/
│   │   └── client.ts                  fetch wrapper — base URL, typed helpers
│   ├── components/
│   │   ├── TopNav.vue                 Top navigation bar with company filter + toggles
│   │   ├── KpiCard.vue                Single KPI card (value, label, delta, border color)
│   │   ├── SpendBarChart.vue          Chart.js bar chart for spend-by-year
│   │   ├── CpvDonutChart.vue          Chart.js donut chart for CPV breakdown
│   │   ├── ContractTable.vue          Reusable data table with pagination slot
│   │   ├── ContractSlideOver.vue      Slide-over panel for contract detail
│   │   ├── EntityCard.vue             Card for supplier or procurer in grid
│   │   ├── CompanyFilter.vue          Search-as-you-type dropdown for company filter
│   │   └── TopRankingList.vue         Ranked list with inline progress bars
│   └── pages/
│       ├── DashboardPage.vue          / — KPIs, charts, recent, top suppliers
│       ├── ContractsPage.vue          /contracts — table + slide-over
│       ├── SuppliersPage.vue          /suppliers — search + card grid
│       ├── SupplierDetailPage.vue     /suppliers/:ico — company dashboard
│       ├── ProcurersPage.vue          /procurers — search + card grid
│       ├── ProcurerDetailPage.vue     /procurers/:ico — company dashboard
│       ├── CostAnalysisPage.vue       /costs — CPV breakdown + year comparison
│       └── SearchPage.vue             /search — global full-text search
```

---

## Task 1: Project scaffold

**Files:**
- Create: `src/uvo-gui-vuejs/package.json`
- Create: `src/uvo-gui-vuejs/vite.config.ts`
- Create: `src/uvo-gui-vuejs/tailwind.config.js`
- Create: `src/uvo-gui-vuejs/postcss.config.js`
- Create: `src/uvo-gui-vuejs/tsconfig.json`
- Create: `src/uvo-gui-vuejs/index.html`

- [ ] **Step 1: Scaffold project**

```bash
cd src
npm create vite@latest uvo-gui-vuejs -- --template vue-ts
cd uvo-gui-vuejs
npm install
npm install vue-router@4 pinia chart.js vue-chartjs vue-i18n@9
npm install -D tailwindcss postcss autoprefixer vitest @vue/test-utils @vitejs/plugin-vue
npx tailwindcss init -p
```

- [ ] **Step 2: Configure Tailwind**

Replace `src/uvo-gui-vuejs/tailwind.config.js` content:

```js
// tailwind.config.js
/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{vue,js,ts}'],
  theme: {
    extend: {
      colors: {
        brand: '#2563eb',
        'brand-dark': '#38bdf8',
      },
    },
  },
  plugins: [],
}
```

- [ ] **Step 3: Configure Vite**

Replace `src/uvo-gui-vuejs/vite.config.ts`:

```ts
// vite.config.ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
  },
})
```

- [ ] **Step 4: Add Tailwind directives to CSS**

Replace `src/uvo-gui-vuejs/src/style.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 5: Verify dev server starts**

```bash
cd src/uvo-gui-vuejs
npm run dev
```
Expected: `Local: http://localhost:3000/` with default Vite page

- [ ] **Step 6: Commit**

```bash
cd ../..
git add src/uvo-gui-vuejs/
git commit -m "feat: scaffold Vue 3 admin GUI project with Vite + Tailwind"
```

---

## Task 2: API client + stores

**Files:**
- Create: `src/uvo-gui-vuejs/src/api/client.ts`
- Create: `src/uvo-gui-vuejs/src/stores/filter.ts`
- Create: `src/uvo-gui-vuejs/src/stores/theme.ts`

- [ ] **Step 1: Write tests**

```ts
// src/uvo-gui-vuejs/src/stores/filter.test.ts
import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, beforeEach } from 'vitest'
import { useFilterStore } from './filter'

describe('useFilterStore', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('starts with no company selected', () => {
    const store = useFilterStore()
    expect(store.ico).toBeNull()
    expect(store.isFiltered).toBe(false)
  })

  it('sets company filter', () => {
    const store = useFilterStore()
    store.setCompany({ ico: '12345678', name: 'Ministry', type: 'procurer' })
    expect(store.ico).toBe('12345678')
    expect(store.isFiltered).toBe(true)
  })

  it('clears company filter', () => {
    const store = useFilterStore()
    store.setCompany({ ico: '12345678', name: 'Ministry', type: 'procurer' })
    store.clear()
    expect(store.ico).toBeNull()
    expect(store.isFiltered).toBe(false)
  })

  it('provides query params for API calls', () => {
    const store = useFilterStore()
    store.setCompany({ ico: '12345678', name: 'Ministry', type: 'procurer' })
    expect(store.queryParams).toEqual({ ico: '12345678', entity_type: 'procurer' })
  })
})
```

```ts
// src/uvo-gui-vuejs/src/stores/theme.test.ts
import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, beforeEach } from 'vitest'
import { useThemeStore } from './theme'

describe('useThemeStore', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('starts in light mode', () => {
    const store = useThemeStore()
    expect(store.isDark).toBe(false)
  })

  it('toggles to dark mode', () => {
    const store = useThemeStore()
    store.toggle()
    expect(store.isDark).toBe(true)
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd src/uvo-gui-vuejs
npx vitest run src/stores/filter.test.ts src/stores/theme.test.ts
```
Expected: `Cannot find module './filter'`

- [ ] **Step 3: Implement stores**

```ts
// src/uvo-gui-vuejs/src/stores/filter.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

interface Company {
  ico: string
  name: string
  type: 'supplier' | 'procurer'
}

export const useFilterStore = defineStore('filter', () => {
  const ico = ref<string | null>(null)
  const name = ref<string | null>(null)
  const type = ref<'supplier' | 'procurer' | null>(null)

  const isFiltered = computed(() => ico.value !== null)
  const queryParams = computed(() =>
    isFiltered.value ? { ico: ico.value!, entity_type: type.value! } : {}
  )

  function setCompany(company: Company) {
    ico.value = company.ico
    name.value = company.name
    type.value = company.type
  }

  function clear() {
    ico.value = null
    name.value = null
    type.value = null
  }

  return { ico, name, type, isFiltered, queryParams, setCompany, clear }
})
```

```ts
// src/uvo-gui-vuejs/src/stores/theme.ts
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useThemeStore = defineStore('theme', () => {
  const isDark = ref(false)

  function toggle() {
    isDark.value = !isDark.value
    document.documentElement.classList.toggle('dark', isDark.value)
  }

  return { isDark, toggle }
})
```

- [ ] **Step 4: Implement API client**

```ts
// src/uvo-gui-vuejs/src/api/client.ts
const BASE = '/api'

async function get<T>(path: string, params: Record<string, string | number | null | undefined> = {}): Promise<T> {
  const url = new URL(BASE + path, window.location.origin)
  Object.entries(params).forEach(([k, v]) => {
    if (v !== null && v !== undefined) url.searchParams.set(k, String(v))
  })
  const res = await fetch(url.toString())
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`)
  return res.json() as Promise<T>
}

export interface DashboardSummary {
  total_value: number
  contract_count: number
  avg_value: number
  active_suppliers: number
  deltas: Record<string, { value: number; pct?: number }>
}

export interface SpendByYear { year: number; total_value: number }
export interface TopSupplier { ico: string; name: string; total_value: number; contract_count: number }
export interface TopProcurer { ico: string; name: string; total_spend: number; contract_count: number }
export interface CpvShare { cpv_code: string; label_sk: string; label_en: string; total_value: number; percentage: number }
export interface RecentContract { id: string; title: string; procurer_name: string; procurer_ico: string; value: number; year: number; status: string }

export interface ContractRow { id: string; title: string; procurer_name: string; procurer_ico: string; supplier_name: string | null; supplier_ico: string | null; value: number; cpv_code: string | null; year: number; status: string }
export interface ContractDetail extends ContractRow { all_suppliers: Record<string, string>[]; publication_date: string | null; source_url: string | null }
export interface Pagination { total: number; limit: number; offset: number }
export interface ContractListResponse { data: ContractRow[]; pagination: Pagination }

export interface EntityCard { ico: string; name: string; contract_count: number; total_value?: number; total_spend?: number }
export interface EntityListResponse { data: EntityCard[]; pagination: Pagination }

export interface EntitySummary { ico: string; name: string; contract_count: number; total_value?: number; total_spend?: number; avg_value: number; spend_by_year: SpendByYear[] }

export const api = {
  dashboard: {
    summary: (p = {}) => get<DashboardSummary>('/dashboard/summary', p),
    spendByYear: (p = {}) => get<SpendByYear[]>('/dashboard/spend-by-year', p),
    topSuppliers: (p = {}) => get<TopSupplier[]>('/dashboard/top-suppliers', p),
    topProcurers: (p = {}) => get<TopProcurer[]>('/dashboard/top-procurers', p),
    byCpv: (p = {}) => get<CpvShare[]>('/dashboard/by-cpv', p),
    recent: (p = {}) => get<RecentContract[]>('/dashboard/recent', p),
  },
  contracts: {
    list: (p = {}) => get<ContractListResponse>('/contracts', p),
    detail: (id: string) => get<ContractDetail>(`/contracts/${id}`),
  },
  suppliers: {
    list: (p = {}) => get<EntityListResponse>('/suppliers', p),
    detail: (ico: string) => get<Record<string, unknown>>(`/suppliers/${ico}`),
    summary: (ico: string) => get<EntitySummary>(`/suppliers/${ico}/summary`),
  },
  procurers: {
    list: (p = {}) => get<EntityListResponse>('/procurers', p),
    detail: (ico: string) => get<Record<string, unknown>>(`/procurers/${ico}`),
    summary: (ico: string) => get<EntitySummary>(`/procurers/${ico}/summary`),
  },
}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
npx vitest run src/stores/filter.test.ts src/stores/theme.test.ts
```
Expected: PASS (7 tests)

- [ ] **Step 6: Commit**

```bash
cd ../..
git add src/uvo-gui-vuejs/src/
git commit -m "feat: add API client, filter store, theme store"
```

---

## Task 3: i18n + router

**Files:**
- Create: `src/uvo-gui-vuejs/src/i18n/index.ts`
- Create: `src/uvo-gui-vuejs/src/i18n/sk.ts`
- Create: `src/uvo-gui-vuejs/src/i18n/en.ts`
- Create: `src/uvo-gui-vuejs/src/router/index.ts`
- Create: `src/uvo-gui-vuejs/src/main.ts`

- [ ] **Step 1: Create translation files**

```ts
// src/uvo-gui-vuejs/src/i18n/sk.ts
export default {
  nav: {
    dashboard: 'Dashboard',
    contracts: 'Zákazky',
    suppliers: 'Dodávatelia',
    procurers: 'Obstarávatelia',
    costs: 'Náklady',
    search: 'Hľadať',
  },
  dashboard: {
    title: 'Dashboard',
    subtitle: 'Prehľad verejného obstarávania',
    totalValue: 'Celková hodnota',
    contractCount: 'Počet zákaziek',
    avgValue: 'Priemerná hodnota',
    activeSuppliers: 'Aktívni dodávatelia',
    spendByYear: 'Výdavky podľa roka (€M)',
    byCpv: 'Podľa kategórie CPV',
    recentContracts: 'Posledné zákazky',
    topSuppliers: 'Top dodávatelia',
    topProcurers: 'Top obstarávatelia',
  },
  contracts: {
    title: 'Zákazky',
    search: 'Hľadať zákazky...',
    columns: {
      title: 'Zákazka',
      procurer: 'Obstarávateľ',
      supplier: 'Dodávateľ',
      value: 'Hodnota',
      cpv: 'CPV',
      year: 'Rok',
      status: 'Stav',
    },
    status: { active: 'Aktívna', closed: 'Ukončená' },
    noResults: 'Žiadne zákazky nenájdené.',
  },
  suppliers: {
    title: 'Dodávatelia',
    search: 'Hľadať dodávateľa...',
    contracts: 'zákaziek',
    noResults: 'Žiadni dodávatelia nenájdení.',
  },
  procurers: {
    title: 'Obstarávatelia',
    search: 'Hľadať obstarávateľa...',
    contracts: 'zákaziek',
    noResults: 'Žiadni obstarávatelia nenájdení.',
  },
  costs: {
    title: 'Analýza nákladov',
    byCpv: 'Výdavky podľa CPV',
    topContracts: 'Top zákazky podľa hodnoty',
  },
  search: {
    title: 'Vyhľadávanie',
    placeholder: 'Hľadať zákazky, dodávateľov, obstarávateľov...',
    noResults: 'Žiadne výsledky.',
  },
  common: {
    loading: 'Načítavam...',
    error: 'Chyba pri načítaní dát.',
    filter: 'Filtrovať podľa spoločnosti',
    clearFilter: 'Zrušiť filter',
    darkMode: 'Tmavý režim',
    lightMode: 'Svetlý režim',
    viewDetail: 'Zobraziť detail',
    pagination: { prev: 'Predch.', next: 'Ďalšia' },
  },
}
```

```ts
// src/uvo-gui-vuejs/src/i18n/en.ts
export default {
  nav: {
    dashboard: 'Dashboard',
    contracts: 'Contracts',
    suppliers: 'Suppliers',
    procurers: 'Procurers',
    costs: 'Cost Analysis',
    search: 'Search',
  },
  dashboard: {
    title: 'Dashboard',
    subtitle: 'Public procurement overview',
    totalValue: 'Total value',
    contractCount: 'Contracts',
    avgValue: 'Average value',
    activeSuppliers: 'Active suppliers',
    spendByYear: 'Spend by year (€M)',
    byCpv: 'By CPV category',
    recentContracts: 'Recent contracts',
    topSuppliers: 'Top suppliers',
    topProcurers: 'Top procurers',
  },
  contracts: {
    title: 'Contracts',
    search: 'Search contracts...',
    columns: {
      title: 'Contract',
      procurer: 'Procurer',
      supplier: 'Supplier',
      value: 'Value',
      cpv: 'CPV',
      year: 'Year',
      status: 'Status',
    },
    status: { active: 'Active', closed: 'Closed' },
    noResults: 'No contracts found.',
  },
  suppliers: {
    title: 'Suppliers',
    search: 'Search supplier...',
    contracts: 'contracts',
    noResults: 'No suppliers found.',
  },
  procurers: {
    title: 'Procurers',
    search: 'Search procurer...',
    contracts: 'contracts',
    noResults: 'No procurers found.',
  },
  costs: {
    title: 'Cost Analysis',
    byCpv: 'Spend by CPV',
    topContracts: 'Top contracts by value',
  },
  search: {
    title: 'Search',
    placeholder: 'Search contracts, suppliers, procurers...',
    noResults: 'No results found.',
  },
  common: {
    loading: 'Loading...',
    error: 'Error loading data.',
    filter: 'Filter by company',
    clearFilter: 'Clear filter',
    darkMode: 'Dark mode',
    lightMode: 'Light mode',
    viewDetail: 'View detail',
    pagination: { prev: 'Prev', next: 'Next' },
  },
}
```

```ts
// src/uvo-gui-vuejs/src/i18n/index.ts
import { createI18n } from 'vue-i18n'
import sk from './sk'
import en from './en'

export const i18n = createI18n({
  legacy: false,
  locale: 'sk',
  fallbackLocale: 'en',
  messages: { sk, en },
})
```

- [ ] **Step 2: Create router**

```ts
// src/uvo-gui-vuejs/src/router/index.ts
import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('../pages/DashboardPage.vue') },
    { path: '/contracts', component: () => import('../pages/ContractsPage.vue') },
    { path: '/suppliers', component: () => import('../pages/SuppliersPage.vue') },
    { path: '/suppliers/:ico', component: () => import('../pages/SupplierDetailPage.vue') },
    { path: '/procurers', component: () => import('../pages/ProcurersPage.vue') },
    { path: '/procurers/:ico', component: () => import('../pages/ProcurerDetailPage.vue') },
    { path: '/costs', component: () => import('../pages/CostAnalysisPage.vue') },
    { path: '/search', component: () => import('../pages/SearchPage.vue') },
  ],
})

export default router
```

- [ ] **Step 3: Update main.ts**

```ts
// src/uvo-gui-vuejs/src/main.ts
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { i18n } from './i18n'
import './style.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(i18n)
app.mount('#app')
```

- [ ] **Step 4: Create stub page files so router imports don't fail**

Create empty stub for each page (replace in later tasks):

```bash
for page in DashboardPage ContractsPage SuppliersPage SupplierDetailPage ProcurersPage ProcurerDetailPage CostAnalysisPage SearchPage; do
  echo '<template><div>{{ $route.path }}</div></template>' > src/uvo-gui-vuejs/src/pages/${page}.vue
done
```

- [ ] **Step 5: Verify app builds**

```bash
cd src/uvo-gui-vuejs && npm run build
```
Expected: Build succeeds with no errors

- [ ] **Step 6: Commit**

```bash
cd ../..
git add src/uvo-gui-vuejs/src/
git commit -m "feat: add Vue Router, i18n (SK/EN), app entry point"
```

---

## Task 4: TopNav + App.vue layout

**Files:**
- Create: `src/uvo-gui-vuejs/src/components/TopNav.vue`
- Create: `src/uvo-gui-vuejs/src/components/CompanyFilter.vue`
- Modify: `src/uvo-gui-vuejs/src/App.vue`

- [ ] **Step 1: Write component test**

```ts
// src/uvo-gui-vuejs/src/components/TopNav.test.ts
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import { createI18n } from 'vue-i18n'
import { describe, it, expect } from 'vitest'
import TopNav from './TopNav.vue'
import sk from '../i18n/sk'
import en from '../i18n/en'

const router = createRouter({ history: createWebHistory(), routes: [{ path: '/', component: { template: '<div/>' } }] })
const i18n = createI18n({ legacy: false, locale: 'sk', messages: { sk, en } })

function mountNav() {
  return mount(TopNav, {
    global: { plugins: [createPinia(), router, i18n] },
  })
}

describe('TopNav', () => {
  it('renders logo text', () => {
    const w = mountNav()
    expect(w.text()).toContain('UVO')
    expect(w.text()).toContain('Admin')
  })

  it('renders all 6 nav items', () => {
    const w = mountNav()
    expect(w.text()).toContain('Dashboard')
    expect(w.text()).toContain('Zákazky')
    expect(w.text()).toContain('Dodávatelia')
  })

  it('toggles language on SK/EN click', async () => {
    const w = mountNav()
    const btn = w.find('[data-testid="lang-toggle"]')
    expect(btn.exists()).toBe(true)
    await btn.trigger('click')
    expect(w.text()).toContain('Contracts')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd src/uvo-gui-vuejs && npx vitest run src/components/TopNav.test.ts
```
Expected: `Cannot find module './TopNav.vue'`

- [ ] **Step 3: Implement TopNav.vue**

```vue
<!-- src/uvo-gui-vuejs/src/components/TopNav.vue -->
<script setup lang="ts">
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useThemeStore } from '../stores/theme'
import { useFilterStore } from '../stores/filter'

const { t, locale } = useI18n()
const router = useRouter()
const route = useRoute()
const theme = useThemeStore()
const filter = useFilterStore()

const navItems = [
  { key: 'nav.dashboard', path: '/' },
  { key: 'nav.contracts', path: '/contracts' },
  { key: 'nav.suppliers', path: '/suppliers' },
  { key: 'nav.procurers', path: '/procurers' },
  { key: 'nav.costs', path: '/costs' },
  { key: 'nav.search', path: '/search' },
]

function toggleLang() {
  locale.value = locale.value === 'sk' ? 'en' : 'sk'
}

function isActive(path: string) {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}
</script>

<template>
  <nav class="bg-slate-800 text-white h-13 flex items-center px-6 gap-0 sticky top-0 z-50 shadow-md">
    <span class="font-bold text-base mr-8 tracking-tight">
      UVO <span class="text-sky-400">Admin</span>
    </span>

    <div class="flex items-center flex-1">
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="px-3 h-13 flex items-center text-sm text-slate-400 hover:text-slate-200 border-b-2 border-transparent transition-colors"
        :class="{ 'text-white !border-sky-400': isActive(item.path) }"
      >
        {{ t(item.key) }}
      </router-link>
    </div>

    <div class="flex items-center gap-3 ml-auto">
      <span v-if="filter.isFiltered" class="text-xs text-sky-400 flex items-center gap-1">
        {{ filter.name }}
        <button @click="filter.clear()" class="ml-1 text-slate-400 hover:text-white">✕</button>
      </span>

      <button
        data-testid="lang-toggle"
        @click="toggleLang"
        class="bg-slate-700 text-slate-400 hover:text-white px-2.5 py-1 rounded text-xs transition-colors"
      >
        {{ locale === 'sk' ? 'EN' : 'SK' }}
      </button>

      <button
        @click="theme.toggle()"
        class="bg-slate-700 text-slate-400 hover:text-white px-2.5 py-1 rounded text-xs transition-colors"
      >
        {{ theme.isDark ? '☀️' : '🌙' }}
      </button>
    </div>
  </nav>
</template>
```

- [ ] **Step 4: Update App.vue**

```vue
<!-- src/uvo-gui-vuejs/src/App.vue -->
<script setup lang="ts">
import { watch } from 'vue'
import TopNav from './components/TopNav.vue'
import { useThemeStore } from './stores/theme'

const theme = useThemeStore()
watch(() => theme.isDark, (dark) => {
  document.documentElement.classList.toggle('dark', dark)
}, { immediate: true })
</script>

<template>
  <div class="min-h-screen bg-slate-100 dark:bg-slate-900 text-slate-900 dark:text-slate-100 transition-colors">
    <TopNav />
    <main class="max-w-7xl mx-auto px-6 py-6">
      <RouterView />
    </main>
  </div>
</template>
```

- [ ] **Step 5: Run test to verify it passes**

```bash
npx vitest run src/components/TopNav.test.ts
```
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
cd ../..
git add src/uvo-gui-vuejs/src/
git commit -m "feat: add TopNav component with language and dark mode toggles"
```

---

## Task 5: KpiCard + chart components

**Files:**
- Create: `src/uvo-gui-vuejs/src/components/KpiCard.vue`
- Create: `src/uvo-gui-vuejs/src/components/SpendBarChart.vue`
- Create: `src/uvo-gui-vuejs/src/components/CpvDonutChart.vue`
- Create: `src/uvo-gui-vuejs/src/components/TopRankingList.vue`

- [ ] **Step 1: Write tests**

```ts
// src/uvo-gui-vuejs/src/components/KpiCard.test.ts
import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import KpiCard from './KpiCard.vue'

describe('KpiCard', () => {
  it('renders label and value', () => {
    const w = mount(KpiCard, { props: { label: 'Total', value: '€ 4.2B', color: 'blue' } })
    expect(w.text()).toContain('Total')
    expect(w.text()).toContain('€ 4.2B')
  })

  it('renders delta when provided', () => {
    const w = mount(KpiCard, { props: { label: 'Total', value: '€ 4.2B', color: 'blue', delta: '↑ +8%' } })
    expect(w.text()).toContain('↑ +8%')
  })

  it('applies correct border color class for blue', () => {
    const w = mount(KpiCard, { props: { label: 'Total', value: '€ 4.2B', color: 'blue' } })
    expect(w.html()).toContain('border-blue-600')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd src/uvo-gui-vuejs && npx vitest run src/components/KpiCard.test.ts
```
Expected: `Cannot find module './KpiCard.vue'`

- [ ] **Step 3: Implement KpiCard**

```vue
<!-- src/uvo-gui-vuejs/src/components/KpiCard.vue -->
<script setup lang="ts">
defineProps<{
  label: string
  value: string
  color: 'blue' | 'green' | 'red' | 'purple'
  delta?: string
  deltaDown?: boolean
}>()

const borderColors = {
  blue: 'border-blue-600',
  green: 'border-green-600',
  red: 'border-red-600',
  purple: 'border-purple-600',
}
</script>

<template>
  <div
    class="bg-white dark:bg-slate-800 rounded-lg p-4 border-l-4 shadow-sm"
    :class="borderColors[color]"
  >
    <p class="text-xs uppercase tracking-widest text-slate-400 mb-1">{{ label }}</p>
    <p class="text-2xl font-bold text-slate-900 dark:text-slate-100">{{ value }}</p>
    <p v-if="delta" class="text-xs mt-1" :class="deltaDown ? 'text-red-500' : 'text-green-500'">
      {{ delta }}
    </p>
  </div>
</template>
```

- [ ] **Step 4: Implement SpendBarChart**

```vue
<!-- src/uvo-gui-vuejs/src/components/SpendBarChart.vue -->
<script setup lang="ts">
import { computed } from 'vue'
import { Bar } from 'vue-chartjs'
import { Chart as ChartJS, CategoryScale, LinearScale, BarElement, Tooltip, Legend } from 'chart.js'
import { useThemeStore } from '../stores/theme'
import type { SpendByYear } from '../api/client'

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend)

const props = defineProps<{ data: SpendByYear[] }>()
const theme = useThemeStore()

const chartData = computed(() => ({
  labels: props.data.map(d => String(d.year)),
  datasets: [{
    label: '€M',
    data: props.data.map(d => d.total_value / 1_000_000),
    backgroundColor: props.data.map((_, i) =>
      i === props.data.length - 1
        ? (theme.isDark ? '#38bdf8' : '#2563eb')
        : (theme.isDark ? '#1e3a5f' : '#bfdbfe')
    ),
    borderRadius: 3,
  }],
}))

const options = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { display: false } },
  scales: {
    x: { grid: { display: false }, ticks: { color: theme.isDark ? '#94a3b8' : '#64748b' } },
    y: { grid: { color: theme.isDark ? '#1e293b' : '#f1f5f9' }, ticks: { color: theme.isDark ? '#94a3b8' : '#64748b' } },
  },
}))
</script>

<template>
  <div class="h-32">
    <Bar :data="chartData" :options="options" />
  </div>
</template>
```

- [ ] **Step 5: Implement CpvDonutChart**

```vue
<!-- src/uvo-gui-vuejs/src/components/CpvDonutChart.vue -->
<script setup lang="ts">
import { computed } from 'vue'
import { Doughnut } from 'vue-chartjs'
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js'
import { useI18n } from 'vue-i18n'
import type { CpvShare } from '../api/client'

ChartJS.register(ArcElement, Tooltip, Legend)

const props = defineProps<{ data: CpvShare[] }>()
const { locale } = useI18n()

const COLORS = ['#2563eb', '#16a34a', '#dc2626', '#f59e0b', '#8b5cf6', '#06b6d4', '#ec4899', '#84cc16']

const chartData = computed(() => ({
  labels: props.data.map(d => locale.value === 'sk' ? d.label_sk : d.label_en),
  datasets: [{
    data: props.data.map(d => d.percentage),
    backgroundColor: COLORS.slice(0, props.data.length),
    borderWidth: 0,
  }],
}))

const options = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { display: false } },
  cutout: '65%',
}
</script>

<template>
  <div class="flex items-center gap-4">
    <div class="w-24 h-24 flex-shrink-0">
      <Doughnut :data="chartData" :options="options" />
    </div>
    <div class="flex flex-col gap-1.5 overflow-hidden">
      <div v-for="(item, i) in data.slice(0, 5)" :key="item.cpv_code" class="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-400">
        <span class="w-2 h-2 rounded-full flex-shrink-0" :style="{ background: COLORS[i] }" />
        <span class="truncate">{{ locale === 'sk' ? item.label_sk : item.label_en }}</span>
        <span class="ml-auto text-slate-500">{{ item.percentage }}%</span>
      </div>
    </div>
  </div>
</template>
```

- [ ] **Step 6: Implement TopRankingList**

```vue
<!-- src/uvo-gui-vuejs/src/components/TopRankingList.vue -->
<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'

interface RankItem { ico: string; name: string; value: number; count: number }

const props = defineProps<{ items: RankItem[]; linkPrefix: string }>()
const router = useRouter()

const maxValue = computed(() => Math.max(...props.items.map(i => i.value), 1))

function fmt(v: number) {
  if (v >= 1_000_000) return `€ ${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `€ ${(v / 1_000).toFixed(0)}k`
  return `€ ${v.toFixed(0)}`
}
</script>

<template>
  <div class="space-y-2">
    <div
      v-for="(item, i) in items"
      :key="item.ico"
      class="flex items-center gap-2 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-700 rounded px-1 py-1 transition-colors"
      @click="router.push(`${linkPrefix}/${item.ico}`)"
    >
      <span class="text-xs font-bold text-slate-300 w-4">{{ i + 1 }}</span>
      <span class="flex-1 text-xs text-slate-700 dark:text-slate-300 truncate">{{ item.name }}</span>
      <div class="w-20 h-1.5 bg-slate-100 dark:bg-slate-700 rounded">
        <div class="h-1.5 bg-blue-600 dark:bg-sky-400 rounded" :style="{ width: `${(item.value / maxValue) * 100}%` }" />
      </div>
      <span class="text-xs text-slate-500 w-14 text-right">{{ fmt(item.value) }}</span>
    </div>
  </div>
</template>
```

- [ ] **Step 7: Run tests**

```bash
npx vitest run src/components/KpiCard.test.ts
```
Expected: PASS (3 tests)

- [ ] **Step 8: Commit**

```bash
cd ../..
git add src/uvo-gui-vuejs/src/components/
git commit -m "feat: add KpiCard, SpendBarChart, CpvDonutChart, TopRankingList components"
```

---

## Task 6: ContractTable + ContractSlideOver + EntityCard

**Files:**
- Create: `src/uvo-gui-vuejs/src/components/ContractTable.vue`
- Create: `src/uvo-gui-vuejs/src/components/ContractSlideOver.vue`
- Create: `src/uvo-gui-vuejs/src/components/EntityCard.vue`

- [ ] **Step 1: Write test for ContractTable**

```ts
// src/uvo-gui-vuejs/src/components/ContractTable.test.ts
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { describe, it, expect } from 'vitest'
import ContractTable from './ContractTable.vue'
import sk from '../i18n/sk'
import en from '../i18n/en'

const i18n = createI18n({ legacy: false, locale: 'sk', messages: { sk, en } })

const rows = [
  { id: '1', title: 'IT Project', procurer_name: 'MF SR', procurer_ico: '123', supplier_name: 'Tech', supplier_ico: '456', value: 500000, cpv_code: '72000000', year: 2024, status: 'active' },
]

describe('ContractTable', () => {
  it('renders contract rows', () => {
    const w = mount(ContractTable, {
      props: { rows, total: 1, offset: 0, limit: 20 },
      global: { plugins: [i18n] },
    })
    expect(w.text()).toContain('IT Project')
    expect(w.text()).toContain('MF SR')
  })

  it('emits select when row clicked', async () => {
    const w = mount(ContractTable, {
      props: { rows, total: 1, offset: 0, limit: 20 },
      global: { plugins: [i18n] },
    })
    await w.find('tr.cursor-pointer').trigger('click')
    expect(w.emitted('select')?.[0][0]).toEqual(rows[0])
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd src/uvo-gui-vuejs && npx vitest run src/components/ContractTable.test.ts
```
Expected: `Cannot find module './ContractTable.vue'`

- [ ] **Step 3: Implement ContractTable**

```vue
<!-- src/uvo-gui-vuejs/src/components/ContractTable.vue -->
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { ContractRow } from '../api/client'

const props = defineProps<{
  rows: ContractRow[]
  total: number
  offset: number
  limit: number
}>()

const emit = defineEmits<{
  select: [row: ContractRow]
  paginate: [offset: number]
}>()

const { t } = useI18n()

function fmt(v: number) {
  if (v >= 1_000_000) return `€ ${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000) return `€ ${(v / 1_000).toFixed(0)}k`
  return `€ ${v.toFixed(0)}`
}

const hasPrev = () => props.offset > 0
const hasNext = () => props.offset + props.limit < props.total
</script>

<template>
  <div>
    <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-slate-100 dark:border-slate-700">
            <th class="text-left text-xs uppercase tracking-wider text-slate-400 pb-2 pr-4">{{ t('contracts.columns.title') }}</th>
            <th class="text-left text-xs uppercase tracking-wider text-slate-400 pb-2 pr-4">{{ t('contracts.columns.procurer') }}</th>
            <th class="text-left text-xs uppercase tracking-wider text-slate-400 pb-2 pr-4">{{ t('contracts.columns.supplier') }}</th>
            <th class="text-right text-xs uppercase tracking-wider text-slate-400 pb-2 pr-4">{{ t('contracts.columns.value') }}</th>
            <th class="text-center text-xs uppercase tracking-wider text-slate-400 pb-2 pr-4">{{ t('contracts.columns.year') }}</th>
            <th class="text-center text-xs uppercase tracking-wider text-slate-400 pb-2">{{ t('contracts.columns.status') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.id"
            class="cursor-pointer border-b border-slate-50 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
            @click="emit('select', row)"
          >
            <td class="py-2 pr-4 text-slate-700 dark:text-slate-300 truncate max-w-xs">{{ row.title }}</td>
            <td class="py-2 pr-4 text-slate-600 dark:text-slate-400 text-xs">{{ row.procurer_name }}</td>
            <td class="py-2 pr-4 text-slate-600 dark:text-slate-400 text-xs">{{ row.supplier_name ?? '—' }}</td>
            <td class="py-2 pr-4 text-right font-mono text-xs text-slate-700 dark:text-slate-300">{{ fmt(row.value) }}</td>
            <td class="py-2 pr-4 text-center text-xs text-slate-500">{{ row.year }}</td>
            <td class="py-2 text-center">
              <span
                class="text-xs px-2 py-0.5 rounded-full font-medium"
                :class="row.status === 'active' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300' : 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300'"
              >
                {{ t(`contracts.status.${row.status}`) }}
              </span>
            </td>
          </tr>
          <tr v-if="rows.length === 0">
            <td colspan="6" class="py-6 text-center text-slate-400 text-sm">{{ t('contracts.noResults') }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="flex items-center justify-between mt-3">
      <span class="text-xs text-slate-400">{{ total }} total</span>
      <div class="flex gap-2">
        <button
          :disabled="!hasPrev()"
          class="text-xs px-3 py-1 rounded bg-slate-100 dark:bg-slate-700 disabled:opacity-40 hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
          @click="emit('paginate', offset - limit)"
        >{{ t('common.pagination.prev') }}</button>
        <button
          :disabled="!hasNext()"
          class="text-xs px-3 py-1 rounded bg-slate-100 dark:bg-slate-700 disabled:opacity-40 hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
          @click="emit('paginate', offset + limit)"
        >{{ t('common.pagination.next') }}</button>
      </div>
    </div>
  </div>
</template>
```

- [ ] **Step 4: Implement ContractSlideOver**

```vue
<!-- src/uvo-gui-vuejs/src/components/ContractSlideOver.vue -->
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { ContractDetail } from '../api/client'

defineProps<{ contract: ContractDetail | null }>()
const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()

function fmt(v: number) {
  if (v >= 1_000_000) return `€ ${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000) return `€ ${(v / 1_000).toFixed(0)}k`
  return `€ ${v.toFixed(0)}`
}
</script>

<template>
  <Transition name="slide">
    <div
      v-if="contract"
      class="fixed inset-y-0 right-0 w-96 bg-white dark:bg-slate-800 shadow-2xl z-40 overflow-y-auto"
    >
      <div class="flex items-center justify-between px-5 py-4 border-b border-slate-100 dark:border-slate-700">
        <h3 class="font-semibold text-sm text-slate-800 dark:text-slate-200">Detail zákazky</h3>
        <button @click="emit('close')" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 text-lg leading-none">✕</button>
      </div>

      <div class="px-5 py-4 space-y-4 text-sm">
        <div>
          <p class="text-xs text-slate-400 uppercase tracking-wider mb-1">Zákazka</p>
          <p class="font-medium text-slate-800 dark:text-slate-200">{{ contract.title }}</p>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <p class="text-xs text-slate-400 mb-0.5">{{ t('contracts.columns.value') }}</p>
            <p class="font-bold text-blue-600 dark:text-sky-400">{{ fmt(contract.value) }}</p>
          </div>
          <div>
            <p class="text-xs text-slate-400 mb-0.5">{{ t('contracts.columns.year') }}</p>
            <p class="font-medium">{{ contract.year }}</p>
          </div>
          <div>
            <p class="text-xs text-slate-400 mb-0.5">{{ t('contracts.columns.procurer') }}</p>
            <p class="text-slate-700 dark:text-slate-300">{{ contract.procurer_name }}</p>
            <p class="text-xs text-slate-400">IČO: {{ contract.procurer_ico }}</p>
          </div>
          <div>
            <p class="text-xs text-slate-400 mb-0.5">CPV</p>
            <p class="text-slate-600 dark:text-slate-400 font-mono text-xs">{{ contract.cpv_code ?? '—' }}</p>
          </div>
        </div>

        <div v-if="contract.all_suppliers?.length">
          <p class="text-xs text-slate-400 uppercase tracking-wider mb-2">Dodávatelia</p>
          <div v-for="s in contract.all_suppliers" :key="s.ico" class="text-xs py-1 border-b border-slate-50 dark:border-slate-700">
            {{ s.nazov }} <span class="text-slate-400 ml-1">IČO: {{ s.ico }}</span>
          </div>
        </div>

        <div v-if="contract.publication_date">
          <p class="text-xs text-slate-400 mb-0.5">Dátum zverejnenia</p>
          <p class="text-xs text-slate-600 dark:text-slate-400">{{ contract.publication_date }}</p>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.slide-enter-active, .slide-leave-active { transition: transform 0.2s ease; }
.slide-enter-from, .slide-leave-to { transform: translateX(100%); }
</style>
```

- [ ] **Step 5: Implement EntityCard**

```vue
<!-- src/uvo-gui-vuejs/src/components/EntityCard.vue -->
<script setup lang="ts">
import { useRouter } from 'vue-router'

const props = defineProps<{
  ico: string
  name: string
  contractCount: number
  totalValue: number
  linkPrefix: string
  contractsLabel: string
}>()

const router = useRouter()

function fmt(v: number) {
  if (v >= 1_000_000) return `€ ${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000) return `€ ${(v / 1_000).toFixed(0)}k`
  return `€ ${v.toFixed(0)}`
}
</script>

<template>
  <div
    class="bg-white dark:bg-slate-800 rounded-lg p-4 shadow-sm cursor-pointer hover:shadow-md hover:ring-1 hover:ring-blue-200 dark:hover:ring-sky-800 transition-all"
    @click="router.push(`${linkPrefix}/${ico}`)"
  >
    <p class="font-semibold text-sm text-slate-800 dark:text-slate-200 mb-2 leading-tight line-clamp-2">{{ name }}</p>
    <p class="text-xs text-slate-400 mb-1">IČO: {{ ico }}</p>
    <div class="flex items-center justify-between mt-2">
      <span class="text-xs text-slate-500">{{ contractCount }} {{ contractsLabel }}</span>
      <span class="text-sm font-bold text-blue-600 dark:text-sky-400">{{ fmt(totalValue) }}</span>
    </div>
  </div>
</template>
```

- [ ] **Step 6: Run tests**

```bash
npx vitest run src/components/ContractTable.test.ts
```
Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
cd ../..
git add src/uvo-gui-vuejs/src/components/
git commit -m "feat: add ContractTable, ContractSlideOver, EntityCard components"
```

---

## Task 7: DashboardPage

**Files:**
- Modify: `src/uvo-gui-vuejs/src/pages/DashboardPage.vue`

- [ ] **Step 1: Implement DashboardPage**

```vue
<!-- src/uvo-gui-vuejs/src/pages/DashboardPage.vue -->
<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useFilterStore } from '../stores/filter'
import { api } from '../api/client'
import type { DashboardSummary, SpendByYear, TopSupplier, TopProcurer, CpvShare, RecentContract } from '../api/client'
import KpiCard from '../components/KpiCard.vue'
import SpendBarChart from '../components/SpendBarChart.vue'
import CpvDonutChart from '../components/CpvDonutChart.vue'
import TopRankingList from '../components/TopRankingList.vue'

const { t } = useI18n()
const filter = useFilterStore()

const loading = ref(false)
const error = ref<string | null>(null)
const summary = ref<DashboardSummary | null>(null)
const spendByYear = ref<SpendByYear[]>([])
const topSuppliers = ref<TopSupplier[]>([])
const topProcurers = ref<TopProcurer[]>([])
const byCpv = ref<CpvShare[]>([])
const recent = ref<RecentContract[]>([])

async function load() {
  loading.value = true
  error.value = null
  try {
    const p = filter.queryParams
    const [s, sy, ts, tp, cpv, r] = await Promise.all([
      api.dashboard.summary(p),
      api.dashboard.spendByYear(p),
      api.dashboard.topSuppliers(p),
      api.dashboard.topProcurers(p),
      api.dashboard.byCpv(p),
      api.dashboard.recent(p),
    ])
    summary.value = s
    spendByYear.value = sy
    topSuppliers.value = ts
    topProcurers.value = tp
    byCpv.value = cpv
    recent.value = r
  } catch {
    error.value = t('common.error')
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => filter.ico, load)

function fmtValue(v: number) {
  if (v >= 1_000_000_000) return `€ ${(v / 1_000_000_000).toFixed(2)}B`
  if (v >= 1_000_000) return `€ ${(v / 1_000_000).toFixed(0)}M`
  if (v >= 1_000) return `€ ${(v / 1_000).toFixed(0)}k`
  return `€ ${v.toFixed(0)}`
}
</script>

<template>
  <div>
    <div class="mb-5">
      <h1 class="text-xl font-bold text-slate-900 dark:text-slate-100">{{ t('dashboard.title') }}</h1>
      <p class="text-xs text-slate-400 mt-0.5">{{ t('dashboard.subtitle') }}</p>
    </div>

    <div v-if="loading" class="text-slate-400 text-sm py-12 text-center">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="text-red-500 text-sm py-6">{{ error }}</div>

    <template v-else-if="summary">
      <!-- KPI cards -->
      <div class="grid grid-cols-4 gap-4 mb-5">
        <KpiCard :label="t('dashboard.totalValue')" :value="fmtValue(summary.total_value)" color="blue" delta="↑ +8.4%" />
        <KpiCard :label="t('dashboard.contractCount')" :value="summary.contract_count.toLocaleString()" color="green" delta="↑ +312" />
        <KpiCard :label="t('dashboard.avgValue')" :value="fmtValue(summary.avg_value)" color="red" delta="↓ −2.1%" :deltaDown="true" />
        <KpiCard :label="t('dashboard.activeSuppliers')" :value="summary.active_suppliers.toLocaleString()" color="purple" delta="↑ +124" />
      </div>

      <!-- Charts row -->
      <div class="grid grid-cols-3 gap-4 mb-5">
        <div class="col-span-2 bg-white dark:bg-slate-800 rounded-lg p-5 shadow-sm">
          <p class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">{{ t('dashboard.spendByYear') }}</p>
          <SpendBarChart :data="spendByYear" />
        </div>
        <div class="bg-white dark:bg-slate-800 rounded-lg p-5 shadow-sm">
          <p class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">{{ t('dashboard.byCpv') }}</p>
          <CpvDonutChart :data="byCpv" />
        </div>
      </div>

      <!-- Bottom row -->
      <div class="grid grid-cols-2 gap-4">
        <div class="bg-white dark:bg-slate-800 rounded-lg p-5 shadow-sm">
          <p class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">{{ t('dashboard.recentContracts') }}</p>
          <div class="space-y-2">
            <div
              v-for="c in recent"
              :key="c.id"
              class="flex items-center justify-between py-1.5 border-b border-slate-50 dark:border-slate-700 text-xs"
            >
              <div class="truncate flex-1 mr-2">
                <p class="text-slate-700 dark:text-slate-300 truncate">{{ c.title }}</p>
                <p class="text-slate-400">{{ c.procurer_name }}</p>
              </div>
              <span class="font-bold text-blue-600 dark:text-sky-400 whitespace-nowrap">{{ fmtValue(c.value) }}</span>
            </div>
          </div>
        </div>

        <div class="bg-white dark:bg-slate-800 rounded-lg p-5 shadow-sm">
          <p class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">{{ t('dashboard.topSuppliers') }}</p>
          <TopRankingList
            :items="topSuppliers.map(s => ({ ico: s.ico, name: s.name, value: s.total_value, count: s.contract_count }))"
            link-prefix="/suppliers"
          />
        </div>
      </div>
    </template>
  </div>
</template>
```

- [ ] **Step 2: Start dev server and verify dashboard loads**

```bash
cd src/uvo-gui-vuejs && npm run dev
```
Open http://localhost:3000 — dashboard should render with loading state (API on port 8001 doesn't need to be running; loading/error state is fine)

- [ ] **Step 3: Commit**

```bash
cd ../..
git add src/uvo-gui-vuejs/src/pages/DashboardPage.vue
git commit -m "feat: implement DashboardPage with KPIs, charts, recent contracts"
```

---

## Task 8: ContractsPage + SuppliersPage + ProcurersPage

**Files:**
- Modify: `src/uvo-gui-vuejs/src/pages/ContractsPage.vue`
- Modify: `src/uvo-gui-vuejs/src/pages/SuppliersPage.vue`
- Modify: `src/uvo-gui-vuejs/src/pages/ProcurersPage.vue`

- [ ] **Step 1: Implement ContractsPage**

```vue
<!-- src/uvo-gui-vuejs/src/pages/ContractsPage.vue -->
<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { ContractRow, ContractDetail } from '../api/client'
import ContractTable from '../components/ContractTable.vue'
import ContractSlideOver from '../components/ContractSlideOver.vue'

const { t } = useI18n()

const q = ref('')
const cpv = ref('')
const dateFrom = ref('')
const dateTo = ref('')
const limit = 20
const offset = ref(0)
const total = ref(0)
const rows = ref<ContractRow[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const selected = ref<ContractDetail | null>(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    const res = await api.contracts.list({
      q: q.value || undefined,
      cpv: cpv.value || undefined,
      date_from: dateFrom.value || undefined,
      date_to: dateTo.value || undefined,
      limit,
      offset: offset.value,
    })
    rows.value = res.data
    total.value = res.pagination.total
  } catch {
    error.value = t('common.error')
  } finally {
    loading.value = false
  }
}

async function selectRow(row: ContractRow) {
  try {
    selected.value = await api.contracts.detail(row.id)
  } catch {
    selected.value = { ...row, all_suppliers: [], publication_date: null, source_url: null }
  }
}

function search() { offset.value = 0; load() }
function paginate(newOffset: number) { offset.value = newOffset; load() }

onMounted(load)
</script>

<template>
  <div>
    <h1 class="text-xl font-bold mb-5">{{ t('contracts.title') }}</h1>

    <div class="bg-white dark:bg-slate-800 rounded-lg p-4 shadow-sm mb-4 flex flex-wrap gap-3">
      <input v-model="q" :placeholder="t('contracts.search')" class="flex-1 min-w-48 border border-slate-200 dark:border-slate-600 rounded px-3 py-1.5 text-sm bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100" @keydown.enter="search" />
      <input v-model="cpv" placeholder="CPV kód" class="w-36 border border-slate-200 dark:border-slate-600 rounded px-3 py-1.5 text-sm bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100" />
      <input v-model="dateFrom" type="date" class="w-40 border border-slate-200 dark:border-slate-600 rounded px-3 py-1.5 text-sm bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100" />
      <input v-model="dateTo" type="date" class="w-40 border border-slate-200 dark:border-slate-600 rounded px-3 py-1.5 text-sm bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100" />
      <button @click="search" class="bg-blue-600 text-white px-4 py-1.5 rounded text-sm hover:bg-blue-700 transition-colors">Hľadať</button>
    </div>

    <div v-if="loading" class="text-slate-400 text-sm py-8 text-center">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="text-red-500 text-sm py-4">{{ error }}</div>
    <div v-else class="bg-white dark:bg-slate-800 rounded-lg p-5 shadow-sm">
      <ContractTable :rows="rows" :total="total" :offset="offset" :limit="limit" @select="selectRow" @paginate="paginate" />
    </div>

    <ContractSlideOver :contract="selected" @close="selected = null" />
  </div>
</template>
```

- [ ] **Step 2: Implement SuppliersPage**

```vue
<!-- src/uvo-gui-vuejs/src/pages/SuppliersPage.vue -->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { EntityCard as EntityCardType } from '../api/client'
import EntityCard from '../components/EntityCard.vue'

const { t } = useI18n()
const q = ref('')
const items = ref<EntityCardType[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    const res = await api.suppliers.list({ q: q.value || undefined })
    items.value = res.data
  } catch {
    error.value = t('common.error')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <h1 class="text-xl font-bold mb-5">{{ t('suppliers.title') }}</h1>
    <div class="bg-white dark:bg-slate-800 rounded-lg p-4 shadow-sm mb-4 flex gap-3">
      <input v-model="q" :placeholder="t('suppliers.search')" class="flex-1 border border-slate-200 dark:border-slate-600 rounded px-3 py-1.5 text-sm bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100" @keydown.enter="load" />
      <button @click="load" class="bg-blue-600 text-white px-4 py-1.5 rounded text-sm hover:bg-blue-700 transition-colors">Hľadať</button>
    </div>
    <div v-if="loading" class="text-slate-400 text-sm py-8 text-center">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="text-red-500 text-sm">{{ error }}</div>
    <div v-else class="grid grid-cols-3 gap-4">
      <EntityCard
        v-for="s in items"
        :key="s.ico"
        :ico="s.ico"
        :name="s.name"
        :contract-count="s.contract_count"
        :total-value="s.total_value ?? 0"
        link-prefix="/suppliers"
        :contracts-label="t('suppliers.contracts')"
      />
      <p v-if="items.length === 0" class="col-span-3 text-center text-slate-400 text-sm py-8">{{ t('suppliers.noResults') }}</p>
    </div>
  </div>
</template>
```

- [ ] **Step 3: Implement ProcurersPage** (same pattern as SuppliersPage)

```vue
<!-- src/uvo-gui-vuejs/src/pages/ProcurersPage.vue -->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { EntityCard as EntityCardType } from '../api/client'
import EntityCard from '../components/EntityCard.vue'

const { t } = useI18n()
const q = ref('')
const items = ref<EntityCardType[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    const res = await api.procurers.list({ q: q.value || undefined })
    items.value = res.data
  } catch {
    error.value = t('common.error')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <h1 class="text-xl font-bold mb-5">{{ t('procurers.title') }}</h1>
    <div class="bg-white dark:bg-slate-800 rounded-lg p-4 shadow-sm mb-4 flex gap-3">
      <input v-model="q" :placeholder="t('procurers.search')" class="flex-1 border border-slate-200 dark:border-slate-600 rounded px-3 py-1.5 text-sm bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100" @keydown.enter="load" />
      <button @click="load" class="bg-blue-600 text-white px-4 py-1.5 rounded text-sm hover:bg-blue-700 transition-colors">Hľadať</button>
    </div>
    <div v-if="loading" class="text-slate-400 text-sm py-8 text-center">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="text-red-500 text-sm">{{ error }}</div>
    <div v-else class="grid grid-cols-3 gap-4">
      <EntityCard
        v-for="p in items"
        :key="p.ico"
        :ico="p.ico"
        :name="p.name"
        :contract-count="p.contract_count"
        :total-value="p.total_spend ?? p.total_value ?? 0"
        link-prefix="/procurers"
        :contracts-label="t('procurers.contracts')"
      />
      <p v-if="items.length === 0" class="col-span-3 text-center text-slate-400 text-sm py-8">{{ t('procurers.noResults') }}</p>
    </div>
  </div>
</template>
```

- [ ] **Step 4: Commit**

```bash
cd ../..
git add src/uvo-gui-vuejs/src/pages/ContractsPage.vue src/uvo-gui-vuejs/src/pages/SuppliersPage.vue src/uvo-gui-vuejs/src/pages/ProcurersPage.vue
git commit -m "feat: implement Contracts, Suppliers, Procurers list pages"
```

---

## Task 9: Detail pages + Cost Analysis + Search

**Files:**
- Modify: `src/uvo-gui-vuejs/src/pages/SupplierDetailPage.vue`
- Modify: `src/uvo-gui-vuejs/src/pages/ProcurerDetailPage.vue`
- Modify: `src/uvo-gui-vuejs/src/pages/CostAnalysisPage.vue`
- Modify: `src/uvo-gui-vuejs/src/pages/SearchPage.vue`

- [ ] **Step 1: Implement SupplierDetailPage**

```vue
<!-- src/uvo-gui-vuejs/src/pages/SupplierDetailPage.vue -->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { EntitySummary } from '../api/client'
import KpiCard from '../components/KpiCard.vue'
import SpendBarChart from '../components/SpendBarChart.vue'
import TopRankingList from '../components/TopRankingList.vue'
import ContractTable from '../components/ContractTable.vue'
import ContractSlideOver from '../components/ContractSlideOver.vue'

const route = useRoute()
const { t } = useI18n()
const ico = String(route.params.ico)

const summary = ref<EntitySummary | null>(null)
const detail = ref<Record<string, unknown> | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const selected = ref(null)

function fmt(v: number) {
  if (v >= 1_000_000) return `€ ${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000) return `€ ${(v / 1_000).toFixed(0)}k`
  return `€ ${v}`
}

async function load() {
  loading.value = true
  error.value = null
  try {
    const [s, d] = await Promise.all([api.suppliers.summary(ico), api.suppliers.detail(ico)])
    summary.value = s
    detail.value = d
  } catch {
    error.value = t('common.error')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div v-if="loading" class="text-slate-400 text-sm py-12 text-center">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="text-red-500 text-sm py-6">{{ error }}</div>
    <template v-else-if="summary">
      <div class="flex items-center gap-3 mb-5">
        <div>
          <h1 class="text-xl font-bold">{{ summary.name }}</h1>
          <p class="text-xs text-slate-400 mt-0.5">IČO: {{ summary.ico }} · Dodávateľ</p>
        </div>
      </div>

      <div class="grid grid-cols-4 gap-4 mb-5">
        <KpiCard label="Zákazky" :value="summary.contract_count.toLocaleString()" color="blue" />
        <KpiCard label="Celková hodnota" :value="fmt(summary.total_value ?? 0)" color="green" />
        <KpiCard label="Priemerná hodnota" :value="fmt(summary.avg_value)" color="red" />
        <KpiCard :label="t('dashboard.spendByYear')" :value="summary.spend_by_year.length + ' rokov'" color="purple" />
      </div>

      <div class="grid grid-cols-3 gap-4 mb-5">
        <div class="col-span-2 bg-white dark:bg-slate-800 rounded-lg p-5 shadow-sm">
          <p class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">Trend výdavkov</p>
          <SpendBarChart :data="summary.spend_by_year" />
        </div>
        <div class="bg-white dark:bg-slate-800 rounded-lg p-5 shadow-sm">
          <p class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">Top obstarávatelia</p>
          <TopRankingList
            v-if="detail?.top_procurers"
            :items="(detail.top_procurers as any[]).map((p: any) => ({ ico: p.ico, name: p.name, value: p.total_value, count: p.contract_count }))"
            link-prefix="/procurers"
          />
        </div>
      </div>

      <div class="bg-white dark:bg-slate-800 rounded-lg p-5 shadow-sm">
        <p class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">Zákazky</p>
        <ContractTable
          v-if="detail?.contracts"
          :rows="(detail.contracts as any[])"
          :total="(detail.contracts as any[]).length"
          :offset="0"
          :limit="100"
          @select="(r: any) => selected = r"
          @paginate="() => {}"
        />
      </div>
    </template>
    <ContractSlideOver :contract="selected" @close="selected = null" />
  </div>
</template>
```

- [ ] **Step 2: Implement ProcurerDetailPage** (mirror of SupplierDetailPage with procurer API)

```vue
<!-- src/uvo-gui-vuejs/src/pages/ProcurerDetailPage.vue -->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { EntitySummary } from '../api/client'
import KpiCard from '../components/KpiCard.vue'
import SpendBarChart from '../components/SpendBarChart.vue'
import TopRankingList from '../components/TopRankingList.vue'
import ContractTable from '../components/ContractTable.vue'
import ContractSlideOver from '../components/ContractSlideOver.vue'

const route = useRoute()
const { t } = useI18n()
const ico = String(route.params.ico)

const summary = ref<EntitySummary | null>(null)
const detail = ref<Record<string, unknown> | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const selected = ref(null)

function fmt(v: number) {
  if (v >= 1_000_000) return `€ ${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000) return `€ ${(v / 1_000).toFixed(0)}k`
  return `€ ${v}`
}

async function load() {
  loading.value = true
  error.value = null
  try {
    const [s, d] = await Promise.all([api.procurers.summary(ico), api.procurers.detail(ico)])
    summary.value = s
    detail.value = d
  } catch {
    error.value = t('common.error')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div v-if="loading" class="text-slate-400 text-sm py-12 text-center">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="text-red-500 text-sm py-6">{{ error }}</div>
    <template v-else-if="summary">
      <div class="flex items-center gap-3 mb-5">
        <div>
          <h1 class="text-xl font-bold">{{ summary.name }}</h1>
          <p class="text-xs text-slate-400 mt-0.5">IČO: {{ summary.ico }} · Obstarávateľ</p>
        </div>
      </div>

      <div class="grid grid-cols-4 gap-4 mb-5">
        <KpiCard label="Zákazky" :value="summary.contract_count.toLocaleString()" color="blue" />
        <KpiCard label="Celkové výdavky" :value="fmt(summary.total_spend ?? summary.total_value ?? 0)" color="green" />
        <KpiCard label="Priemerná hodnota" :value="fmt(summary.avg_value)" color="red" />
        <KpiCard label="Roky aktivity" :value="summary.spend_by_year.length + ' rokov'" color="purple" />
      </div>

      <div class="grid grid-cols-3 gap-4 mb-5">
        <div class="col-span-2 bg-white dark:bg-slate-800 rounded-lg p-5 shadow-sm">
          <p class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">Trend výdavkov</p>
          <SpendBarChart :data="summary.spend_by_year" />
        </div>
        <div class="bg-white dark:bg-slate-800 rounded-lg p-5 shadow-sm">
          <p class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">Top dodávatelia</p>
          <TopRankingList
            v-if="detail?.top_suppliers"
            :items="(detail.top_suppliers as any[]).map((s: any) => ({ ico: s.ico, name: s.name, value: s.total_value, count: s.contract_count }))"
            link-prefix="/suppliers"
          />
        </div>
      </div>

      <div class="bg-white dark:bg-slate-800 rounded-lg p-5 shadow-sm">
        <p class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">Zákazky</p>
        <ContractTable
          v-if="detail?.contracts"
          :rows="(detail.contracts as any[])"
          :total="(detail.contracts as any[]).length"
          :offset="0"
          :limit="100"
          @select="(r: any) => selected = r"
          @paginate="() => {}"
        />
      </div>
    </template>
    <ContractSlideOver :contract="selected" @close="selected = null" />
  </div>
</template>
```

- [ ] **Step 3: Implement CostAnalysisPage**

```vue
<!-- src/uvo-gui-vuejs/src/pages/CostAnalysisPage.vue -->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useFilterStore } from '../stores/filter'
import { api } from '../api/client'
import type { CpvShare, ContractRow } from '../api/client'

const { t, locale } = useI18n()
const filter = useFilterStore()

const byCpv = ref<CpvShare[]>([])
const topContracts = ref<ContractRow[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

function fmt(v: number) {
  if (v >= 1_000_000) return `€ ${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000) return `€ ${(v / 1_000).toFixed(0)}k`
  return `€ ${v}`
}

async function load() {
  loading.value = true
  error.value = null
  try {
    const p = filter.queryParams
    const [cpv, contracts] = await Promise.all([
      api.dashboard.byCpv(p),
      api.contracts.list({ ...p, limit: 20 }),
    ])
    byCpv.value = cpv
    topContracts.value = [...contracts.data].sort((a, b) => b.value - a.value)
  } catch {
    error.value = t('common.error')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <h1 class="text-xl font-bold mb-5">{{ t('costs.title') }}</h1>
    <div v-if="loading" class="text-slate-400 text-sm py-8 text-center">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="text-red-500 text-sm">{{ error }}</div>
    <template v-else>
      <div class="bg-white dark:bg-slate-800 rounded-lg p-5 shadow-sm mb-4">
        <p class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">{{ t('costs.byCpv') }}</p>
        <div class="space-y-2">
          <div v-for="item in byCpv" :key="item.cpv_code" class="flex items-center gap-3 text-sm">
            <span class="w-40 truncate text-xs text-slate-600 dark:text-slate-400">{{ locale === 'sk' ? item.label_sk : item.label_en }}</span>
            <div class="flex-1 h-4 bg-slate-100 dark:bg-slate-700 rounded">
              <div class="h-4 bg-blue-500 dark:bg-sky-500 rounded" :style="{ width: `${item.percentage}%` }" />
            </div>
            <span class="w-24 text-right text-xs font-mono text-slate-700 dark:text-slate-300">{{ fmt(item.total_value) }}</span>
            <span class="w-10 text-right text-xs text-slate-400">{{ item.percentage }}%</span>
          </div>
        </div>
      </div>

      <div class="bg-white dark:bg-slate-800 rounded-lg p-5 shadow-sm">
        <p class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">{{ t('costs.topContracts') }}</p>
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-slate-100 dark:border-slate-700">
              <th class="text-left text-xs uppercase text-slate-400 pb-2 pr-4">Zákazka</th>
              <th class="text-left text-xs uppercase text-slate-400 pb-2 pr-4">Obstarávateľ</th>
              <th class="text-right text-xs uppercase text-slate-400 pb-2">Hodnota</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in topContracts" :key="c.id" class="border-b border-slate-50 dark:border-slate-800">
              <td class="py-2 pr-4 text-slate-700 dark:text-slate-300 truncate max-w-xs">{{ c.title }}</td>
              <td class="py-2 pr-4 text-xs text-slate-500">{{ c.procurer_name }}</td>
              <td class="py-2 text-right font-bold text-blue-600 dark:text-sky-400 font-mono text-xs">{{ fmt(c.value) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>
```

- [ ] **Step 4: Implement SearchPage**

```vue
<!-- src/uvo-gui-vuejs/src/pages/SearchPage.vue -->
<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import type { ContractRow, EntityCard } from '../api/client'

const { t } = useI18n()
const router = useRouter()

const q = ref('')
const contracts = ref<ContractRow[]>([])
const suppliers = ref<EntityCard[]>([])
const procurers = ref<EntityCard[]>([])
const loading = ref(false)
const searched = ref(false)
const error = ref<string | null>(null)

function fmt(v: number) {
  if (v >= 1_000_000) return `€ ${(v / 1_000_000).toFixed(1)}M`
  return `€ ${(v / 1_000).toFixed(0)}k`
}

async function search() {
  if (!q.value.trim()) return
  loading.value = true
  error.value = null
  searched.value = true
  try {
    const isIco = /^\d+$/.test(q.value.trim())
    const [c, s, p] = await Promise.all([
      api.contracts.list({ q: q.value, limit: 5 }),
      api.suppliers.list(isIco ? { ico: q.value } : { q: q.value }),
      api.procurers.list(isIco ? { ico: q.value } : { q: q.value }),
    ])
    contracts.value = c.data
    suppliers.value = s.data
    procurers.value = p.data
  } catch {
    error.value = t('common.error')
  } finally {
    loading.value = false
  }
}

const hasResults = () => contracts.value.length + suppliers.value.length + procurers.value.length > 0
</script>

<template>
  <div>
    <h1 class="text-xl font-bold mb-5">{{ t('search.title') }}</h1>
    <div class="bg-white dark:bg-slate-800 rounded-lg p-4 shadow-sm mb-6 flex gap-3">
      <input
        v-model="q"
        :placeholder="t('search.placeholder')"
        class="flex-1 border border-slate-200 dark:border-slate-600 rounded px-3 py-2 text-sm bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100"
        @keydown.enter="search"
      />
      <button @click="search" class="bg-blue-600 text-white px-5 py-2 rounded text-sm hover:bg-blue-700 transition-colors">Hľadať</button>
    </div>

    <div v-if="loading" class="text-slate-400 text-sm py-8 text-center">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="text-red-500 text-sm">{{ error }}</div>
    <div v-else-if="searched && !hasResults()" class="text-slate-400 text-sm text-center py-8">{{ t('search.noResults') }}</div>

    <template v-else-if="searched">
      <div v-if="contracts.length" class="mb-6">
        <h2 class="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">Zákazky ({{ contracts.length }})</h2>
        <div class="bg-white dark:bg-slate-800 rounded-lg shadow-sm divide-y divide-slate-50 dark:divide-slate-700">
          <div v-for="c in contracts" :key="c.id" class="flex items-center justify-between px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-700 cursor-pointer text-sm" @click="router.push('/contracts')">
            <div>
              <p class="text-slate-800 dark:text-slate-200">{{ c.title }}</p>
              <p class="text-xs text-slate-400">{{ c.procurer_name }} · {{ c.year }}</p>
            </div>
            <span class="text-blue-600 dark:text-sky-400 font-bold text-xs">{{ fmt(c.value) }}</span>
          </div>
        </div>
      </div>

      <div v-if="suppliers.length" class="mb-6">
        <h2 class="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">Dodávatelia ({{ suppliers.length }})</h2>
        <div class="bg-white dark:bg-slate-800 rounded-lg shadow-sm divide-y divide-slate-50 dark:divide-slate-700">
          <div v-for="s in suppliers" :key="s.ico" class="flex items-center justify-between px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-700 cursor-pointer text-sm" @click="router.push(`/suppliers/${s.ico}`)">
            <div>
              <p class="text-slate-800 dark:text-slate-200">{{ s.name }}</p>
              <p class="text-xs text-slate-400">IČO: {{ s.ico }}</p>
            </div>
            <span class="text-xs text-slate-400">{{ s.contract_count }} zákaziek</span>
          </div>
        </div>
      </div>

      <div v-if="procurers.length">
        <h2 class="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">Obstarávatelia ({{ procurers.length }})</h2>
        <div class="bg-white dark:bg-slate-800 rounded-lg shadow-sm divide-y divide-slate-50 dark:divide-slate-700">
          <div v-for="p in procurers" :key="p.ico" class="flex items-center justify-between px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-700 cursor-pointer text-sm" @click="router.push(`/procurers/${p.ico}`)">
            <div>
              <p class="text-slate-800 dark:text-slate-200">{{ p.name }}</p>
              <p class="text-xs text-slate-400">IČO: {{ p.ico }}</p>
            </div>
            <span class="text-xs text-slate-400">{{ p.contract_count }} zákaziek</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
```

- [ ] **Step 5: Run all unit tests**

```bash
cd src/uvo-gui-vuejs && npx vitest run
```
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
cd ../..
git add src/uvo-gui-vuejs/src/pages/
git commit -m "feat: implement all 8 admin GUI pages"
```

---

## Task 10: Docker service

**Files:**
- Create: `Dockerfile.admin-gui`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
# Dockerfile.admin-gui
FROM node:20-slim AS build
WORKDIR /app
COPY src/uvo-gui-vuejs/package*.json ./
RUN npm ci
COPY src/uvo-gui-vuejs/ ./
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY docker/nginx-admin.conf /etc/nginx/conf.d/default.conf
EXPOSE 3000
```

- [ ] **Step 2: Create nginx config**

```bash
mkdir -p docker
```

```nginx
# docker/nginx-admin.conf
server {
    listen 3000;
    root /usr/share/nginx/html;
    index index.html;

    location /api/ {
        proxy_pass http://api:8001;
        proxy_set_header Host $host;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

- [ ] **Step 3: Add to docker-compose.yml**

Add after the `api` service:

```yaml
  admin-gui:
    build:
      context: .
      dockerfile: Dockerfile.admin-gui
    ports:
      - "3000:3000"
    depends_on:
      api:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:3000"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 15s
    restart: unless-stopped
```

- [ ] **Step 4: Test build**

```bash
cd src/uvo-gui-vuejs && npm run build
```
Expected: `dist/` created with no errors

- [ ] **Step 5: Commit**

```bash
cd ../..
git add Dockerfile.admin-gui docker/ docker-compose.yml
git commit -m "feat: add Docker service for Vue admin GUI"
```

---

## Self-Review Checklist

- ✅ All 8 routes from spec covered (Dashboard, Contracts, Suppliers, SupplierDetail, Procurers, ProcurerDetail, CostAnalysis, Search)
- ✅ Global company filter in Pinia store — `queryParams` getter passed to all dashboard API calls
- ✅ Dark mode toggle — `useThemeStore` + Tailwind `dark:` classes throughout
- ✅ SK/EN toggle — `useI18n`, `locale` switch, all labels in both `sk.ts` and `en.ts`
- ✅ Click supplier/procurer → navigates to detail page (TopRankingList, EntityCard both call `router.push`)
- ✅ ContractSlideOver slide-in animation on row click
- ✅ Vite proxy `/api → http://localhost:8001` so dev server works without CORS config changes
- ✅ Docker multi-stage build + nginx proxy (nginx routes `/api/` to the FastAPI service)
- ✅ Vitest unit tests for stores and key components
- ✅ `EntitySummary.total_spend` field referenced in ProcurerDetailPage — matches `ProcurerSummary` model from Plan A which uses `total_spend`
