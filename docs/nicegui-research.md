# NiceGUI Research for UVO Search Application

**Date:** 2026-04-03
**Status:** Research complete
**Context:** Evaluating NiceGUI as frontend framework for Slovak government procurement search app

---

## Research Summary

NiceGUI is a strong candidate for the UVO Search GUI. It is a mature Python-first web UI framework (v3.9.0, ~15.3k GitHub stars) built on FastAPI + Vue.js/Quasar + Tailwind CSS. It provides built-in AG Grid, server-side pagination via `ui.table`, date pickers, dialogs, cards, tabs, and async support -- all critical for a procurement search application. Its native FastAPI foundation makes it particularly well-suited for co-hosting with an MCP server.

**Verdict: NiceGUI is the recommended framework for this project**, replacing the earlier Reflex recommendation. NiceGUI is more mature (v3.9 vs Reflex 0.7), has a larger community (15.3k vs ~6k stars), and its FastAPI-native architecture maps directly to the MCP server integration pattern.

---

## 1. NiceGUI Capabilities for Procurement Search

### Table / Data Grid Components

NiceGUI provides **two** table components:

#### `ui.table` (Quasar QTable wrapper)
- Built-in pagination, sorting, filtering
- **Server-side pagination** via the `request` event -- only fetches the current page from backend
- Slot system for custom cell rendering (action buttons, links, badges)
- Column configuration with sortable/filterable flags
- Best for: dynamic server-side data with pagination (our primary use case)

#### `ui.aggrid` (AG Grid wrapper)
- Full AG Grid Community Edition features
- Client-side filtering (agTextColumnFilter, agNumberColumnFilter)
- Column resizing, pinning, grouping
- Direct Pandas/Polars DataFrame integration
- HTML cell rendering, custom formatters
- Caveat: server-side pagination is not natively supported (community discussion #5385); all data must be loaded client-side
- Best for: smaller datasets that fit in memory, complex grid interactions

**Recommendation for UVO Search:** Use `ui.table` for the main search results (server-side pagination with the MCP/API backend). Use `ui.aggrid` for detail views where the full dataset is small (e.g., list of contracts within a single procurement).

### Search / Filter Input Components

- `ui.input` -- text input with placeholder, validation, debounce via `on('keydown.enter', ...)`
- `ui.select` -- dropdown with search/filter, multiple selection (good for CPV code selection)
- `ui.number` -- numeric input with min/max/step
- `ui.checkbox`, `ui.switch` -- boolean filters
- `ui.chip` -- tag-style elements for active filter display
- All inputs support two-way binding via `.bind_value()`

### Date Range Pickers

- `ui.date` -- calendar date picker (Quasar QDate)
- `ui.date_input` -- text input with calendar popup
- **No built-in date range picker** -- but easily composed with two `ui.date_input` components for "from" and "to"
- Supports date format customization and validation

### Pagination

- `ui.table` has **built-in pagination** with configurable `rows_per_page`
- Server-side pagination via `pagination={'rowsNumber': total}` + `on('request', handler)`
- `ui.pagination` -- standalone pagination control if building custom layouts

### Responsive / Mobile Layout

- Built on **Tailwind CSS 4** (since v3.0) -- full responsive utility classes
- Quasar's responsive grid system available
- `ui.row()`, `ui.column()`, `ui.grid()` layout containers
- Classes like `w-full`, `max-w-screen-lg`, `mx-auto` work directly
- `ui.drawer` for mobile-friendly sidebar navigation
- Responsive breakpoints via Tailwind (`sm:`, `md:`, `lg:`)

### Tabs, Cards, Dialogs

- `ui.tabs` + `ui.tab` + `ui.tab_panels` -- tabbed navigation within a page
- `ui.card` -- material design card container with header, content, actions sections
- `ui.dialog` -- modal dialog, supports awaitable pattern for confirm/cancel flows
- `ui.expansion` -- collapsible/accordion sections
- `ui.stepper` -- step-by-step wizard flow
- `ui.menu` -- context menus and dropdown menus
- `ui.notification` -- toast notifications

---

## 2. Async Backend Integration

### Calling Async Functions

NiceGUI runs on FastAPI/uvicorn (async event loop). All event handlers can be `async`:

```python
from nicegui import ui
import httpx

async def search_procurements(query: str):
    """Call MCP server or REST API asynchronously."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            'http://localhost:8000/mcp',
            params={'query': query}
        )
        return response.json()

async def on_search_click():
    results = await search_procurements(search_input.value)
    table.rows = results['data']
    table.update()

search_input = ui.input('Search procurements')
ui.button('Search', on_click=on_search_click)
table = ui.table(columns=[...], rows=[])
```

### Loading States

Pattern 1 -- Spinner with visibility binding:

```python
from nicegui import ui

loading = False

spinner = ui.spinner('dots', size='lg')
spinner.bind_visibility_from(globals(), 'loading')

async def on_search():
    global loading
    loading = True
    try:
        results = await fetch_data()
        table.rows = results
        table.update()
    finally:
        loading = False

ui.button('Search', on_click=on_search)
```

Pattern 2 -- Inline spinner management:

```python
async def on_search():
    spinner = ui.spinner('dots', size='lg')
    try:
        results = await fetch_data()
        update_table(results)
    finally:
        spinner.delete()
```

Pattern 3 -- Notification-based feedback:

```python
async def on_search():
    ui.notification('Searching...', type='ongoing', timeout=None, 
                    close_button=False, spinner=True)
    results = await fetch_data()
    ui.notification.clear()
    ui.notification(f'Found {len(results)} results', type='positive')
```

### State Management Patterns

NiceGUI provides a multi-level storage system:

| Storage Scope | Persistence | Shared Across Tabs | Use Case |
|---------------|-------------|-------------------|----------|
| `app.storage.browser` | Browser localStorage | Yes | Theme preferences |
| `app.storage.user` | Server-side, per user cookie | Yes | User settings, saved searches |
| `app.storage.tab` | Server-side, per tab | No | Current search state |
| `app.storage.client` | Server-side, per connection | No | Temporary UI state |
| `app.storage.general` | Server-side, global | N/A | App-wide config, cache |

The `@ui.refreshable` decorator enables reactive UI updates:

```python
from nicegui import ui, app

@ui.refreshable
def results_view():
    """Re-renders when results_view.refresh() is called."""
    state = app.storage.tab
    if state.get('loading'):
        ui.spinner('dots', size='lg')
        return
    
    rows = state.get('results', [])
    if not rows:
        ui.label('No results. Try a different search.').classes('text-gray-500')
        return
    
    ui.table(
        columns=columns,
        rows=rows,
        pagination={'rowsPerPage': 20, 'rowsNumber': state.get('total', 0)},
    ).on('request', handle_pagination)

async def do_search():
    app.storage.tab['loading'] = True
    results_view.refresh()
    
    data = await call_mcp_tool('search_completed_procurements', {
        'query': app.storage.tab.get('query', ''),
        'limit': 20,
        'offset': 0,
    })
    
    app.storage.tab['results'] = data['data']
    app.storage.tab['total'] = data['summary']['total_records']
    app.storage.tab['loading'] = False
    results_view.refresh()
```

---

## 3. NiceGUI + FastAPI Integration

### Architecture: NiceGUI IS FastAPI

NiceGUI's `app` object is a FastAPI application. There are two integration patterns:

#### Pattern A: NiceGUI as primary app (recommended for UVO Search)

```python
from nicegui import app, ui

# Add custom API routes directly to the NiceGUI app
@app.get('/api/health')
async def health():
    return {'status': 'ok'}

@app.get('/api/v1/search')
async def api_search(query: str, limit: int = 20):
    """REST API endpoint alongside the GUI."""
    results = await search_backend(query, limit)
    return results

# GUI pages
@ui.page('/')
def index():
    ui.label('UVO Search')
    # ... search UI

@ui.page('/detail/{procurement_id}')
def detail(procurement_id: str):
    ui.label(f'Procurement {procurement_id}')
    # ... detail UI

ui.run(
    title='UVO Search',
    storage_secret='your-secret-here',
    host='0.0.0.0',
    port=8080,
)
```

#### Pattern B: Mount NiceGUI on existing FastAPI app

```python
import uvicorn
from fastapi import FastAPI
from nicegui import app as nicegui_app, ui

fastapi_app = FastAPI()

# REST/MCP endpoints on the main FastAPI app
@fastapi_app.get('/')
def api_root():
    return {'message': 'UVO Search API', 'gui': '/gui'}

@fastapi_app.get('/api/v1/search')
async def api_search(query: str):
    return await search_backend(query)

# NiceGUI pages
@ui.page('/')
def gui_index():
    ui.label('UVO Search GUI')

# Mount NiceGUI under /gui path
ui.run_with(
    fastapi_app,
    mount_path='/gui',
    storage_secret='your-secret-here',
)

if __name__ == '__main__':
    uvicorn.run('main:fastapi_app', host='0.0.0.0', port=8080, reload=True)
```

### Can We Co-host MCP Server + NiceGUI?

**Yes, with Pattern B.** The MCP server (using FastMCP's streamable-http transport) exposes endpoints on the FastAPI app. NiceGUI mounts under a separate path. Architecture:

```
                    ┌─────────────────────────────────────┐
                    │         FastAPI Application          │
                    │                                      │
                    │  /mcp/*  ──► MCP Server (FastMCP)    │
                    │  /api/*  ──► REST API endpoints      │
                    │  /gui/*  ──► NiceGUI (ui.run_with)   │
                    │                                      │
                    └─────────────────────────────────────┘
```

However, for simplicity and separation of concerns, you may prefer:

```
┌─────────────────┐         ┌─────────────────┐
│  NiceGUI App    │  HTTP   │  MCP Server     │
│  (port 8080)    │ ──────► │  (port 8000)    │
│  + REST API     │         │  FastMCP +      │
│                 │         │  streamable-http│
└─────────────────┘         └─────────────────┘
```

**Recommendation:** Start with separate processes (simpler debugging, independent scaling). If deployment complexity becomes an issue, consolidate into a single FastAPI app using Pattern B.

---

## 4. Production Deployment

### Docker Deployment

Official Docker image: `zauberzeug/nicegui`

```dockerfile
FROM zauberzeug/nicegui:3.9

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8080
CMD ["python", "main.py"]
```

Or build from scratch:

```dockerfile
FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir nicegui httpx mcp[cli]

COPY . .

EXPOSE 8080
CMD ["python", "main.py"]
```

Docker Compose for full stack:

```yaml
version: '3.8'
services:
  mcp-server:
    build: ./mcp-server
    ports:
      - "8000:8000"
    environment:
      - UVOSTAT_API_TOKEN=${UVOSTAT_API_TOKEN}
    
  gui:
    build: ./gui
    ports:
      - "8080:8080"
    environment:
      - MCP_SERVER_URL=http://mcp-server:8000/mcp
      - STORAGE_SECRET=${STORAGE_SECRET}
    depends_on:
      - mcp-server
```

### Multi-User Support / Session Handling

- NiceGUI creates **per-user server-side sessions** identified by browser cookies
- `app.storage.user` persists across tabs and server restarts (stored as JSON files by default)
- Each browser connection gets its own UI instance -- no shared state between users by default
- `app.storage.general` is shared across all users (useful for caches)

### Scaling

- NiceGUI runs a **single uvicorn worker** (due to WebSocket requirements)
- For horizontal scaling: run multiple instances behind **nginx with sticky sessions** (ip_hash)
- Shared state across instances requires external storage (Redis)
- For the expected scale of a Slovak procurement search app (dozens to low hundreds of concurrent users), a single instance is likely sufficient

```nginx
upstream nicegui {
    ip_hash;
    server gui1:8080;
    server gui2:8080;
}
```

### Performance Considerations

- NiceGUI maintains a WebSocket connection per client -- memory usage scales with concurrent users
- Each user session holds its UI state server-side -- expect ~1-5 MB per active session
- AG Grid with large datasets (10k+ rows) should use pagination, not load everything client-side
- Server-side pagination with `ui.table` is the correct pattern for our procurement search
- Static assets (Tailwind, Quasar, AG Grid JS) are served from NiceGUI's bundled files -- consider CDN for production

---

## 5. Code Examples

### Example 1: Searchable Data Table with Server-Side Pagination

```python
from nicegui import ui, app
import httpx

API_BASE = 'http://localhost:8000'

columns = [
    {'name': 'id', 'label': 'ID', 'field': 'id', 'sortable': True, 'align': 'left'},
    {'name': 'title', 'label': 'Názov', 'field': 'nazov', 'sortable': True, 'align': 'left'},
    {'name': 'procurer', 'label': 'Obstarávateľ', 'field': 'obstaravatel', 'align': 'left'},
    {'name': 'value', 'label': 'Hodnota (EUR)', 'field': 'hodnota', 'sortable': True, 'align': 'right'},
    {'name': 'date', 'label': 'Dátum', 'field': 'datum_zverejnenia', 'sortable': True, 'align': 'left'},
    {'name': 'cpv', 'label': 'CPV kód', 'field': 'cpv_kod', 'align': 'left'},
]

async def fetch_procurements(query: str, date_from: str, date_to: str,
                              limit: int = 20, offset: int = 0) -> dict:
    """Fetch procurement data from MCP server or REST API."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        params = {'limit': limit, 'offset': offset}
        if query:
            params['q'] = query
        if date_from:
            params['datum_zverejnenia_od'] = date_from
        if date_to:
            params['datum_zverejnenia_do'] = date_to
        
        resp = await client.get(f'{API_BASE}/api/ukoncene_obstaravania', params=params)
        resp.raise_for_status()
        return resp.json()


@ui.page('/')
async def search_page():
    ui.label('UVO Search').classes('text-3xl font-bold mb-4')
    ui.label('Vyhľadávanie v slovenských verejných obstarávaniach').classes('text-gray-500 mb-6')
    
    # --- Filter controls ---
    with ui.card().classes('w-full mb-4'):
        with ui.row().classes('w-full items-end gap-4 flex-wrap'):
            query_input = ui.input(
                'Hľadať', placeholder='Názov, obstarávateľ, CPV kód...'
            ).classes('flex-grow min-w-[200px]')
            
            date_from = ui.date_input(
                'Dátum od', value=''
            ).classes('min-w-[150px]')
            
            date_to = ui.date_input(
                'Dátum do', value=''
            ).classes('min-w-[150px]')
            
            search_btn = ui.button('Hľadať', icon='search')
    
    # --- Results area ---
    results_container = ui.column().classes('w-full')
    
    async def do_search(page: int = 1, rows_per_page: int = 20):
        results_container.clear()
        with results_container:
            spinner = ui.spinner('dots', size='xl').classes('mx-auto my-8')
        
        try:
            offset = (page - 1) * rows_per_page
            data = await fetch_procurements(
                query=query_input.value or '',
                date_from=date_from.value or '',
                date_to=date_to.value or '',
                limit=rows_per_page,
                offset=offset,
            )
            
            results_container.clear()
            with results_container:
                total = data.get('summary', {}).get('total_records', 0)
                ui.label(f'Nájdených: {total} záznamov').classes('text-sm text-gray-600 mb-2')
                
                table = ui.table(
                    columns=columns,
                    rows=data.get('data', []),
                    row_key='id',
                    pagination={
                        'rowsPerPage': rows_per_page,
                        'page': page,
                        'rowsNumber': total,
                    },
                ).classes('w-full')
                
                # Server-side pagination handler
                async def handle_request(e):
                    p = e.args['pagination']
                    await do_search(
                        page=p['page'],
                        rows_per_page=p['rowsPerPage'],
                    )
                
                table.on('request', handle_request)
                
                # Row click opens detail dialog
                async def on_row_click(e):
                    row = e.args['row']
                    await show_detail_dialog(row)
                
                table.on('rowClick', on_row_click)
        
        except Exception as e:
            results_container.clear()
            with results_container:
                ui.notification(f'Chyba: {e}', type='negative')
                ui.label(f'Nepodarilo sa načítať dáta: {e}').classes('text-red-500')
    
    search_btn.on_click(lambda: do_search())
    query_input.on('keydown.enter', lambda: do_search())
    
    # Initial load
    await do_search()


async def show_detail_dialog(row: dict):
    """Show procurement detail in a modal dialog."""
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl'):
        ui.label(row.get('nazov', 'Detail')).classes('text-xl font-bold')
        ui.separator()
        
        with ui.grid(columns=2).classes('w-full gap-2'):
            ui.label('Obstarávateľ:').classes('font-semibold')
            ui.label(row.get('obstaravatel', '-'))
            
            ui.label('Hodnota:').classes('font-semibold')
            ui.label(f"{row.get('hodnota', '-')} EUR")
            
            ui.label('Dátum zverejnenia:').classes('font-semibold')
            ui.label(row.get('datum_zverejnenia', '-'))
            
            ui.label('CPV kód:').classes('font-semibold')
            ui.label(row.get('cpv_kod', '-'))
        
        ui.separator()
        
        if row.get('dodavatelia'):
            ui.label('Dodávatelia').classes('font-semibold mt-2')
            for supplier in row['dodavatelia']:
                with ui.card().classes('w-full'):
                    ui.label(supplier.get('nazov', '-'))
                    ui.label(f"IČO: {supplier.get('ico', '-')}").classes('text-sm text-gray-500')
        
        with ui.row().classes('w-full justify-end mt-4'):
            ui.button('Zavrieť', on_click=dialog.close)
    
    dialog.open()


ui.run(title='UVO Search', storage_secret='change-me', host='0.0.0.0', port=8080)
```

### Example 2: Async Data Fetching with Loading Indicators

```python
from nicegui import ui
import asyncio

class SearchState:
    """Manages search state for a single user session."""
    
    def __init__(self):
        self.query = ''
        self.results = []
        self.total = 0
        self.loading = False
        self.error = None
        self.page = 1
        self.per_page = 20
    
    async def search(self, query: str):
        self.query = query
        self.page = 1
        self.loading = True
        self.error = None
        self.results_ui.refresh()
        
        try:
            data = await fetch_procurements(
                query=query,
                limit=self.per_page,
                offset=0,
            )
            self.results = data.get('data', [])
            self.total = data.get('summary', {}).get('total_records', 0)
        except Exception as e:
            self.error = str(e)
            self.results = []
        finally:
            self.loading = False
            self.results_ui.refresh()
    
    @ui.refreshable
    def results_ui(self):
        if self.loading:
            with ui.column().classes('w-full items-center py-8'):
                ui.spinner('dots', size='xl', color='primary')
                ui.label('Načítavam...').classes('text-gray-500 mt-2')
            return
        
        if self.error:
            ui.label(f'Chyba: {self.error}').classes('text-red-500')
            return
        
        if not self.results:
            with ui.column().classes('w-full items-center py-8'):
                ui.icon('search_off', size='xl').classes('text-gray-300')
                ui.label('Žiadne výsledky').classes('text-gray-500')
            return
        
        ui.label(f'{self.total} výsledkov').classes('text-sm text-gray-600')
        for item in self.results:
            with ui.card().classes('w-full cursor-pointer hover:shadow-lg transition-shadow'):
                ui.label(item['nazov']).classes('font-semibold')
                with ui.row().classes('gap-4 text-sm text-gray-600'):
                    ui.label(item.get('obstaravatel', ''))
                    ui.label(f"{item.get('hodnota', '?')} EUR")
                    ui.label(item.get('datum_zverejnenia', ''))


@ui.page('/')
def index():
    state = SearchState()
    
    with ui.row().classes('w-full items-center gap-2'):
        inp = ui.input('Hľadať').classes('flex-grow')
        ui.button('Hľadať', on_click=lambda: state.search(inp.value))
    
    state.results_ui()
```

### Example 3: Multi-Page App with Navigation

```python
from nicegui import ui, app


def nav_header():
    """Shared navigation header for all pages."""
    with ui.header().classes('bg-blue-800 text-white'):
        with ui.row().classes('w-full max-w-screen-xl mx-auto items-center'):
            ui.label('UVO Search').classes('text-xl font-bold cursor-pointer').on(
                'click', lambda: ui.navigate.to('/')
            )
            ui.space()
            with ui.row().classes('gap-4'):
                ui.link('Vyhľadávanie', '/').classes('text-white no-underline hover:underline')
                ui.link('Obstarávatelia', '/procurers').classes('text-white no-underline hover:underline')
                ui.link('Dodávatelia', '/suppliers').classes('text-white no-underline hover:underline')
                ui.link('O aplikácii', '/about').classes('text-white no-underline hover:underline')


@ui.page('/')
def search_page():
    nav_header()
    with ui.column().classes('w-full max-w-screen-xl mx-auto p-4'):
        ui.label('Vyhľadávanie obstarávaní').classes('text-2xl font-bold mb-4')
        # ... search UI (see Example 1)


@ui.page('/procurers')
def procurers_page():
    nav_header()
    with ui.column().classes('w-full max-w-screen-xl mx-auto p-4'):
        ui.label('Obstarávatelia').classes('text-2xl font-bold mb-4')
        # ... procurer list/search


@ui.page('/suppliers')
def suppliers_page():
    nav_header()
    with ui.column().classes('w-full max-w-screen-xl mx-auto p-4'):
        ui.label('Dodávatelia').classes('text-2xl font-bold mb-4')
        # ... supplier list/search


@ui.page('/detail/{procurement_id}')
async def detail_page(procurement_id: str):
    nav_header()
    with ui.column().classes('w-full max-w-screen-xl mx-auto p-4'):
        spinner = ui.spinner('dots', size='xl')
        
        data = await fetch_procurement_detail(procurement_id)
        spinner.delete()
        
        if not data:
            ui.label('Obstarávanie nenájdené').classes('text-red-500')
            return
        
        ui.label(data['nazov']).classes('text-2xl font-bold')
        
        with ui.tabs() as tabs:
            tab_overview = ui.tab('Prehľad')
            tab_contracts = ui.tab('Zmluvy')
            tab_suppliers = ui.tab('Dodávatelia')
        
        with ui.tab_panels(tabs).classes('w-full'):
            with ui.tab_panel(tab_overview):
                with ui.grid(columns=2).classes('gap-4'):
                    ui.label('Obstarávateľ:').classes('font-semibold')
                    ui.label(data.get('obstaravatel', '-'))
                    ui.label('Hodnota:').classes('font-semibold')
                    ui.label(f"{data.get('hodnota', '-')} EUR")
                    ui.label('Stav:').classes('font-semibold')
                    ui.label(data.get('stav', '-'))
            
            with ui.tab_panel(tab_contracts):
                if data.get('zmluvy'):
                    ui.aggrid({
                        'columnDefs': [
                            {'headerName': 'Číslo', 'field': 'cislo'},
                            {'headerName': 'Predmet', 'field': 'predmet'},
                            {'headerName': 'Hodnota', 'field': 'hodnota'},
                            {'headerName': 'Dátum', 'field': 'datum'},
                        ],
                        'rowData': data['zmluvy'],
                    }).classes('w-full h-64')
                else:
                    ui.label('Žiadne zmluvy')
            
            with ui.tab_panel(tab_suppliers):
                for s in data.get('dodavatelia', []):
                    with ui.card().classes('w-full'):
                        ui.label(s['nazov']).classes('font-semibold')
                        ui.label(f"IČO: {s.get('ico', '-')}").classes('text-sm')


@ui.page('/about')
def about_page():
    nav_header()
    with ui.column().classes('w-full max-w-screen-xl mx-auto p-4'):
        ui.label('O aplikácii').classes('text-2xl font-bold mb-4')
        ui.markdown('''
        **UVO Search** je aplikácia na vyhľadávanie v slovenských verejných obstarávaniach.
        
        Dáta pochádzajú z [UVOstat.sk](https://www.uvostat.sk/) API.
        
        Zdrojový kód: [GitHub](https://github.com/...)
        ''')


ui.run(
    title='UVO Search',
    storage_secret='change-me-in-production',
    host='0.0.0.0',
    port=8080,
)
```

---

## 6. NiceGUI Version & Ecosystem

### Current State (April 2026)

| Metric | Value |
|--------|-------|
| **Latest version** | 3.9.0 (March 19, 2026) |
| **Python requirement** | 3.10+ |
| **GitHub stars** | ~15,300 |
| **License** | MIT |
| **Maintainer** | Zauberzeug GmbH (Germany) |
| **Release cadence** | Very active; minor releases every 1-2 weeks |
| **PyPI downloads** | Consistently growing; one of the top Python UI frameworks |

### Version 3.0 Highlights (breaking release)

- **Script mode** -- simpler single-file apps without `@ui.page` boilerplate
- **Tailwind 4** upgrade (dropped the `ui.element.tailwind` API, use `.classes()` directly)
- **Event system** for communication between UI and long-lived objects
- **Observable properties** -- props, classes, style auto-send updates
- **Root page parameter** for `ui.run()` to simplify single-page apps

### Tech Stack

- **Backend:** Python + FastAPI + uvicorn
- **Frontend:** Vue.js 3 + Quasar Framework + Tailwind CSS 4
- **Communication:** Socket.IO (WebSockets)
- **Data grid:** AG Grid Community Edition (bundled)

### Documentation Quality

- Comprehensive component reference at nicegui.io/documentation
- Interactive examples for every component
- Growing but not as extensive tutorial coverage as Streamlit
- Active GitHub Discussions (5,000+ threads)
- Talk Python to Me podcast episode #525 covers v3.0

### Community

- Active Discord server
- Regular releases with responsive maintainers
- Growing ecosystem of community extensions (e.g., nicegui-aggrid-enterprise)

---

## Updated Framework Comparison (with NiceGUI)

| Criteria | NiceGUI | Reflex | Streamlit |
|----------|---------|--------|-----------|
| **Version** | 3.9.0 | 0.7.x | 1.x |
| **GitHub Stars** | ~15,300 | ~6,000 | ~36,000 |
| **Architecture** | FastAPI + Vue/Quasar | FastAPI + React | Custom runner |
| **Dev Speed** | Fast | Fast | Fastest |
| **AG Grid** | Built-in (ui.aggrid) | Via rx.data_table | N/A |
| **Server-side Pagination** | Yes (ui.table) | Yes (components) | Manual |
| **Date Pickers** | Built-in (ui.date) | Via Radix | st.date_input |
| **Dialogs/Modals** | Built-in (ui.dialog) | Built-in | Workarounds |
| **Tabs** | Built-in (ui.tabs) | Built-in | st.tabs |
| **Async Support** | Native (FastAPI) | Native | Limited |
| **FastAPI Integration** | IS FastAPI | Compiles to FastAPI | Separate |
| **Custom API Routes** | Direct (@app.get) | Separate | Separate |
| **State Management** | Multi-scope storage | Class-based State | Session state (reruns) |
| **Responsive Design** | Tailwind 4 + Quasar | Tailwind + Radix | Limited |
| **Session Handling** | Per-user server-side | Per-user | Per-session |
| **Production Ready** | Yes | Pre-1.0 | Internal tools |
| **Learning Curve** | Low-Medium | Low-Medium | Very Low |
| **MCP Co-hosting** | Easy (same FastAPI) | Possible | Not practical |

---

## Recommendation

**NiceGUI is the recommended framework for UVO Search.** Here is the reasoning:

1. **FastAPI-native** -- The MCP server uses FastMCP which is built on FastAPI. NiceGUI IS FastAPI. This means zero impedance mismatch; you can add MCP endpoints and GUI pages in the same application or easily connect them.

2. **Built-in AG Grid + server-side pagination via ui.table** -- Both table components are available out of the box. `ui.table` handles server-side pagination natively, which is essential for searching across potentially thousands of procurement records.

3. **Mature and stable (v3.9)** -- Unlike Reflex (0.7.x pre-1.0), NiceGUI has reached version 3.x with a stable API. The 15k+ stars and weekly release cadence indicate a healthy project.

4. **All required components exist** -- date pickers, dialogs, tabs, cards, navigation, responsive layout, notifications, spinners. No need for workarounds or third-party extensions.

5. **Async-first** -- Every event handler can be `async`. Calling the MCP server or UVOstat API from the GUI is straightforward.

6. **Simpler deployment** -- Single Python process, standard Docker, no compile/build step (unlike Reflex which compiles to React).

### When NOT to use NiceGUI

- If you need pixel-perfect custom design (use FastAPI + React instead)
- If the app grows into a large SPA with complex client-side routing (consider a dedicated frontend)
- If you need horizontal scaling to thousands of concurrent users (WebSocket-per-user becomes a bottleneck)

---

## Integration Roadmap (Updated)

### Phase 1: MCP Server MVP (1-2 days)
- Same as original plan -- build MCP server with FastMCP
- Test with Claude Code via stdio transport

### Phase 2: NiceGUI Prototype (2-3 days)
1. `pip install nicegui httpx`
2. Create `gui/app.py` with search page (Example 1 above)
3. Connect to MCP server via httpx (REST) or mcp client SDK
4. Implement server-side pagination with `ui.table`
5. Add detail dialog for procurement records

### Phase 3: Multi-Page + Polish (2-3 days)
1. Add procurer/supplier search pages
2. Add detail page with tabs (Example 3)
3. Responsive layout with shared nav header
4. Loading states and error handling
5. Dark mode toggle via `app.storage.user`

### Phase 4: Production (1-2 days)
1. Docker Compose setup (MCP server + NiceGUI)
2. Environment-based configuration
3. Storage secret management
4. Health check endpoints

---

## Sources

- [NiceGUI Official Site](https://nicegui.io/)
- [NiceGUI Documentation](https://nicegui.io/documentation)
- [NiceGUI GitHub Repository](https://github.com/zauberzeug/nicegui) (~15.3k stars)
- [NiceGUI PyPI](https://pypi.org/project/nicegui/) (v3.9.0)
- [NiceGUI AG Grid Documentation](https://nicegui.io/documentation/aggrid)
- [NiceGUI Table Documentation](https://nicegui.io/documentation/table)
- [NiceGUI Dialog Documentation](https://nicegui.io/documentation/dialog)
- [NiceGUI Date Input Documentation](https://nicegui.io/documentation/date_input)
- [NiceGUI Storage Documentation](https://nicegui.io/documentation/storage)
- [NiceGUI Pages & Routing](https://nicegui.io/documentation/section_pages_routing)
- [NiceGUI Configuration & Deployment](https://nicegui.io/documentation/section_configuration_deployment)
- [NiceGUI FastAPI Example](https://github.com/zauberzeug/nicegui/blob/main/examples/fastapi/main.py)
- [NiceGUI Docker Hub](https://hub.docker.com/r/zauberzeug/nicegui)
- [FastAPI + NiceGUI Integration Guide (Jaehyeon Kim)](https://jaehyeon.me/blog/2025-11-19-fastapi-nicegui-template/)
- [NiceGUI Goes 3.0 -- Talk Python Podcast #525](https://talkpython.fm/episodes/show/525/nicegui-goes-3.0)
- [NiceGUI Server-Side Pagination Discussion](https://github.com/zauberzeug/nicegui/discussions/1903)
- [NiceGUI AG Grid Server-Side Pagination Request](https://github.com/zauberzeug/nicegui/discussions/5385)
- [NiceGUI Spinner / Loading Patterns Discussion](https://github.com/zauberzeug/nicegui/discussions/816)
- [NiceGUI v3 Changes Discussion](https://github.com/zauberzeug/nicegui/discussions/5331)
- [NiceGUI vs Streamlit Comparison (BitDoze)](https://www.bitdoze.com/streamlit-vs-nicegui/)
- [Choosing FastUI vs Streamlit vs NiceGUI (Simann AI)](https://www.simann.ai/post/choosing-the-right-framework-fastui-vs-streamlit-vs-nicegui)
