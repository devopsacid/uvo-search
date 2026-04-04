# Frontend Documentation

## Overview

The UVO Search frontend is a **NiceGUI application** (Python + FastAPI + Quasar/Vue + Tailwind CSS) with a fully Slovak-language interface. It provides a web UI for searching, filtering, and browsing Slovak government procurement data.

**Key Files**:
- `src/uvo_gui/__main__.py` — Entry point
- `src/uvo_gui/app.py` — App setup and page registration
- `src/uvo_gui/mcp_client.py` — HTTP client for calling MCP server tools
- `src/uvo_gui/components/layout.py` — Shared layout shell (header + sidebar)
- `src/uvo_gui/pages/` — Individual page implementations
- `src/uvo_gui/config.py` — Settings (environment variables)

## Starting the Frontend

```bash
uv run python -m uvo_gui
```

The app starts on `http://localhost:8080` and connects to the MCP server at `http://localhost:8000/mcp` (configurable via `MCP_SERVER_URL`).

## App Setup

**File**: `src/uvo_gui/app.py`

```python
from nicegui import ui
import uvo_gui.pages.about
import uvo_gui.pages.procurers
import uvo_gui.pages.search
import uvo_gui.pages.suppliers
from uvo_gui.config import GuiSettings

settings = GuiSettings()

def start() -> None:
    ui.run(
        title="UVO Search",
        storage_secret=settings.storage_secret,
        host=settings.gui_host,
        port=settings.gui_port,
    )
```

**What happens**:
1. Import pages — each `@ui.page(...)` decorator registers a route
2. Load settings from environment (`.env` file)
3. Call `ui.run()` to start the NiceGUI server

**Configuration** (`GuiSettings` in `config.py`):
- `mcp_server_url` — URL of MCP server (default: `http://localhost:8000/mcp`)
- `storage_secret` — Secret key for NiceGUI session storage (required, from env)
- `gui_host` — Bind address (default: `0.0.0.0`)
- `gui_port` — Listen port (default: `8080`)

## Layout Component

**File**: `src/uvo_gui/components/layout.py`

The shared layout provides a consistent UI shell across all pages:
- **Header** — Title and subtitle
- **Sidebar** — Navigation with 4 items
- **Page container** — Content area where each page renders

### Usage

```python
from uvo_gui.components.layout import layout

@ui.page("/my-page")
async def my_page() -> None:
    with layout(current_path="/my-page"):
        # Your page content here
        ui.label("Hello")
```

### Structure

```
┌─────────────────────────────────────────┐
│  Header: UVO Search (Vestník...)        │  (bg-white, border-b)
├──────────────┬─────────────────────────┤
│ Sidebar      │                         │
│ • Vyhľadáv.  │    Page Content         │
│ • Obstarav.  │    (w-full, h-full)     │
│ • Dodavaté.  │                         │
│ • O aplikácii│                         │
└──────────────┴─────────────────────────┘
```

**Navigation Items**:
```python
NAV_ITEMS = [
    ("🔍", "Vyhľadávanie", "/"),
    ("🏢", "Obstaravatelia", "/procurers"),
    ("🤝", "Dodavatelia", "/suppliers"),
    ("ℹ️", "O aplikácii", "/about"),
]
```

**Styling**:
- Active item: `bg-blue-100 text-blue-700 font-medium`
- Inactive item: `text-slate-500 hover:bg-slate-100`

## Pages

### 1. Search Page (`/`)

**File**: `src/uvo_gui/pages/search.py`

Main search interface with split-panel layout:
- **Left panel** — Search form + result list + pagination
- **Right panel** — Detail view of selected procurement

#### State Class

```python
@dataclass
class SearchState:
    query: str = ""
    date_from: str = ""
    date_to: str = ""
    results: list[dict] = field(default_factory=list)
    total: int = 0
    page: int = 1
    per_page: int = 20
    loading: bool = False
    error: str = ""
    selected: dict | None = None
```

#### Key Methods

- `async def search()` — Execute search with current parameters, reset to page 1
- `async def goto_page(page: int)` — Navigate to specific page
- `async def select(item: dict)` — Select an item for detail view

#### Components

**list_view()** — `@ui.refreshable` function rendering left panel:
- Input field for full-text search (`bind_value` to `query`)
- Two date inputs (`bind_value` to `date_from`, `date_to`)
- Search button → calls `_state.search()`
- Result cards (clickable, highlights selected)
- Pagination buttons → call `_state.goto_page()`

**detail_view()** — `@ui.refreshable` function rendering right panel:
- Procurement title, CPV code, status badges
- 2x2 grid: Procurer, Value, Date, CPV Code
- List of suppliers with IČO

#### State Management Pattern

```python
_state = SearchState()  # Module-level singleton

async def _fetch() -> None:
    _state.loading = True
    list_view.refresh()      # Trigger re-render
    detail_view.refresh()
    try:
        data = await mcp_client.call_tool("search_completed_procurements", {...})
        _state.results = data.get("items", [])
        _state.total = data.get("total", 0)
    finally:
        _state.loading = False
        list_view.refresh()  # Trigger final re-render
```

**Why this pattern?**
- Module-level `_state` persists across page refreshes
- `@ui.refreshable` functions re-render when called with `.refresh()`
- State changes trigger refresh, which reads new state values

#### Calling MCP Tools

```python
data = await mcp_client.call_tool(
    "search_completed_procurements",
    {
        "q": self.query,
        "date_from": self.date_from,
        "date_to": self.date_to,
        "limit": self.per_page,
        "offset": self.offset,
    }
)
```

Returns: `{"items": [...], "total": N}`

### 2. Procurers Page (`/procurers`)

**File**: `src/uvo_gui/pages/procurers.py`

Browse contracting authorities (obstaravatelia).

#### State Class

```python
@dataclass
class ProcurersState:
    query: str = ""
    results: list[dict] = field(default_factory=list)
    total: int = 0
    loading: bool = False
    error: str = ""
```

#### Layout

- Title: "Obstaravatelia"
- Search form: text input + search button
- Results: 3-column grid of cards showing:
  - Procurer name
  - Number of contracts ("Zákazky: N")
  - Total value ("X,XXX €")

#### MCP Tool

```python
data = await mcp_client.call_tool(
    "find_procurer",
    {"name_query": self.query, "limit": 20, "offset": 0}
)
```

Returns: `{"items": [...], "total": N}`

### 3. Suppliers Page (`/suppliers`)

**File**: `src/uvo_gui/pages/suppliers.py`

Browse companies that won government contracts.

#### State Class

```python
@dataclass
class SuppliersState:
    query: str = ""
    results: list[dict] = field(default_factory=list)
    total: int = 0
    loading: bool = False
    error: str = ""
```

#### Layout

- Title: "Dodavatelia"
- Search form: text input (accepts name OR IČO) + search button
- Results: 3-column grid of cards showing:
  - Supplier name
  - IČO (company registration number)
  - Number of contracts
  - Total value

#### Smart Search

```python
if self.query.isdigit():
    arguments["ico"] = self.query
else:
    arguments["name_query"] = self.query
```

If query is all digits, search by IČO; otherwise by name.

#### MCP Tool

```python
data = await mcp_client.call_tool(
    "find_supplier",
    {"name_query": self.query, "limit": 20, "offset": 0}
    # or {"ico": self.query, "limit": 20, "offset": 0}
)
```

Returns: `{"items": [...], "total": N}`

### 4. About Page (`/about`)

**File**: `src/uvo_gui/pages/about.py`

Minimal information page.

**Content**:
- Title: "O aplikácii UVO Search"
- Description: "Aplikácia na prehliadanie dát z Vestníka verejného obstarávania SR. Dáta pochádzajú z portálu UVO a európskeho registra TED."
- Data sources: "uvo.gov.sk · ted.europa.eu"

No state or data fetching required.

## MCP Client

**File**: `src/uvo_gui/mcp_client.py`

```python
async def call_tool(tool_name: str, arguments: dict) -> dict:
    """Call a tool on the MCP server and return the parsed JSON response."""
    async with streamablehttp_client(_settings.mcp_server_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            for content in result.content:
                if hasattr(content, "text"):
                    return json.loads(content.text)
            raise ValueError(f"No text content in response from {tool_name}")
```

**Usage**:
```python
# In an async function (all page handlers are async)
data = await mcp_client.call_tool("search_completed_procurements", {
    "q": "software",
    "limit": 20,
    "offset": 0,
})
```

**Error Handling**:
- Raised exceptions are caught in page functions
- Display error message to user: `ui.label(f"Chyba pri vyhľadávaní: {exc}")`
- Caller must check `error` field in state

## How to Add a New Page

1. **Create file**: `src/uvo_gui/pages/my_feature.py`

2. **Define state class**:
   ```python
   from dataclasses import dataclass, field
   
   @dataclass
   class MyState:
       param1: str = ""
       results: list[dict] = field(default_factory=list)
       loading: bool = False
       error: str = ""
       
       async def fetch_data(self) -> None:
           self.loading = True
           my_view.refresh()
           try:
               data = await mcp_client.call_tool(...)
               self.results = data.get("items", [])
           finally:
               self.loading = False
               my_view.refresh()
   
   _state = MyState()
   ```

3. **Define view function**:
   ```python
   @ui.refreshable
   def my_view() -> None:
       if _state.loading:
           ui.spinner()
           return
       if _state.error:
           ui.label(_state.error).classes("text-red-600")
           return
       # Render results...
   ```

4. **Define page handler**:
   ```python
   @ui.page("/my-feature")
   async def my_feature_page() -> None:
       with layout(current_path="/my-feature"):
           my_view()
   ```

5. **Register in app.py**:
   ```python
   import uvo_gui.pages.my_feature  # noqa: F401
   ```

6. **Add to navigation** (optional):
   ```python
   # In layout.py, add to NAV_ITEMS:
   ("🎨", "My Feature", "/my-feature")
   ```

## Testing

**File**: `tests/gui/`

### Test Setup

`tests/conftest.py`:
```python
pytest_plugins = ["nicegui.testing.general_fixtures"]
```

This plugin must be in the **root** `conftest.py` only — not in subdirectory conftest files.

### Test Fixtures

- `user` — Browser automation fixture for interacting with the app
- `client` — FastAPI test client
- `layout_user` — Special fixture for testing layout in isolation (see below)

### Example Test

```python
async def test_search_page(user: User):
    # Navigate to page
    await user.open("/")
    
    # Find and fill search input
    search_input = user.find("input[placeholder*='Kľúčové']")
    await search_input.fill("stavebnictvom")
    
    # Find and click search button
    search_btn = user.find("button:contains('Hľadať')")
    await search_btn.click()
    
    # Wait and verify results
    await user.should_see("Výsledky:")
```

### NiceGUI Testing Gotchas

1. **`user.should_see()` and `user.should_not_see()`** — Use these, not `should_contain`
2. **Click events don't bubble** — Attach `.on("click", ...)` to the exact element
3. **Root conftest only** — `pytest_plugins` goes in `tests/conftest.py`, not `tests/gui/conftest.py`
4. **Async test app** — Run separate test apps for GUI and MCP tests: `pytest tests/gui/ -v` and `pytest tests/mcp/ -v`

### Testing Layout in Isolation

For testing pages without the full app:

**File**: `tests/gui/layout_test_app.py`

Create a minimal test app that imports and mounts only the layout + your component.

Use `layout_user` fixture:
```python
async def test_my_page(layout_user: User):
    # layout_user is pre-configured to test pages with layout
    await layout_user.open("/my-feature")
    await layout_user.should_see("My Content")
```

## Styling

**Framework**: Tailwind CSS + Quasar

**Common Classes**:
- Spacing: `p-4`, `m-2`, `gap-3`
- Text: `text-sm`, `font-semibold`, `text-slate-700`
- Colors: `bg-blue-100`, `text-green-700`, `border-slate-200`
- Layout: `w-full`, `flex`, `items-center`, `justify-between`

**Components**:
- `ui.label()` — Text (no interaction)
- `ui.input()` — Text input (supports `bind_value`)
- `ui.button()` — Clickable button
- `ui.card()` — Container with border and shadow
- `ui.row()` — Horizontal flexbox
- `ui.column()` — Vertical flexbox
- `ui.grid()` — CSS grid layout
- `ui.scroll_area()` — Scrollable container
- `ui.spinner()` — Loading indicator
- `ui.badge()` — Tag/label

## Common Patterns

### Binding State to Inputs

```python
ui.input().bind_value(_state, "query")
```

Any change to the input updates `_state.query`; changes to `_state.query` update the input.

### Triggering Async Functions from Buttons

```python
ui.button("Click me", on_click=_state.search)  # Works if search is a coroutine
```

**Problem**: Pagination buttons need to call `goto_page(page_num)` with an argument.

**Solution**: Use `asyncio.ensure_future()`:
```python
import asyncio

ui.button(
    "Next →",
    on_click=lambda: asyncio.ensure_future(_state.goto_page(_state.page + 1))
)
```

### Refreshing Multiple Views

```python
async def _fetch(self):
    list_view.refresh()    # Queue for re-render
    detail_view.refresh()  # Queue for re-render
    # ... do work ...
    list_view.refresh()    # Actually render (twice if needed)
    detail_view.refresh()
```

Call `.refresh()` before async work to show loading state, then again after.

## NiceGUI 3.9 Gotchas

1. **No `ui.page_container`** — Use `ui.column().classes("w-full h-full")` instead
2. **Async in sync handlers** — Use `asyncio.ensure_future(coro())`, not `ui.timer(0, ..., once=True)`
3. **Module-level state** — `_state = StateClass()` is the established pattern (not instance variables)
4. **Refresh for reactivity** — `@ui.refreshable` functions + `.refresh()` calls = data binding
