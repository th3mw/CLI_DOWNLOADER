"""
Search & Browse Tab for CLI Media Scraper TUI.
Allows searching across all categories and providers with live results,
resolution selection, and instant action buttons.
"""

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Static, Input, Button, Select, DataTable, Label, 
    Checkbox, OptionList, ProgressBar, Rule
)
from textual.message import Message

from Core.provider_factory import CATEGORIES, CATEGORY_PROVIDERS, create_client, get_providers_for_category
from Core.commons import load_yaml


class SearchTab(Static):
    """Interactive media search and selection tab."""

    class ResultSelected(Message):
        """Emitted when a user selects a search result."""
        def __init__(self, item_data: dict) -> None:
            self.item_data = item_data
            super().__init__()

    class TriggerDownload(Message):
        """Emitted when a user clicks download."""
        def __init__(self, item_data: dict, episodes: str, resolution: str, dry_run: bool = False) -> None:
            self.item_data = item_data
            self.episodes = episodes
            self.resolution = resolution
            self.dry_run = dry_run
            super().__init__()

    def __init__(self, config: dict = None, **kwargs):
        super().__init__(**kwargs)
        self.config = config or load_yaml('config_scraper.yaml')
        self.current_results = []
        self.selected_item = None
        self.active_client = None

    def compose(self) -> ComposeResult:
        with Vertical(id="search-tab-root"):
            # Controls Header Card
            with Vertical(id="search-controls"):
                with Horizontal(classes="search-row"):
                    # Category Select
                    cat_options = [(name, name) for name in ["Anime", "Movies", "TV Shows", "Hentai (NSFW)"]]
                    yield Select(cat_options, value="Anime", id="category-select", prompt="Select Category", allow_blank=False)
                    
                    # Provider Select (initial: Anime providers)
                    prov_options = self._get_provider_options("Anime")
                    initial_prov = prov_options[0][1] if prov_options else None
                    yield Select(prov_options, value=initial_prov, id="provider-select", prompt="Select Provider", allow_blank=False)

                    # Search Input
                    yield Input(placeholder="Search titles (e.g. Solo Leveling, Inception, Breaking Bad)...", id="search-input")
                    yield Button("🔍 Search", variant="success", id="btn-search")

            # Main Split View: Left Results Table, Right Details & Actions
            with Horizontal(id="search-split-container"):
                with Vertical(id="results-pane"):
                    yield Label("📋 Search Results", classes="settings-section-title")
                    yield DataTable(id="results-table", cursor_type="row")

                with Vertical(id="details-pane"):
                    yield Label("🎯 Target Selection & Details", id="details-header")
                    yield Static("Select an item from the search results to inspect metadata and queue download.", id="details-meta")
                    yield Static("", id="details-synopsis")
                    
                    with Vertical(id="resolution-container"):
                        yield Label("Episodes to Download (e.g. 1-12, 1):")
                        yield Input(value="1", placeholder="Episodes (e.g. 1-12, all)", id="episode-range-input")
                        
                        yield Label("Target Resolution:")
                        res_options = [
                            ("1080P • Full HD (Recommended)", "1080"),
                            ("2160P • 4K UHD", "2160"),
                            ("720P • HD", "720"),
                            ("480P • SD", "480"),
                            ("360P • Mobile", "360"),
                        ]
                        yield Select(res_options, value="1080", id="resolution-select", allow_blank=False)

                    with Horizontal(classes="action-btn-row"):
                        yield Button("⬇ Download", variant="primary", id="btn-download", disabled=True)
                        yield Button("🧪 Dry Run", variant="default", id="btn-dryrun", disabled=True)

    def on_mount(self) -> None:
        """Configure DataTable columns."""
        table = self.query_one("#results-table", DataTable)
        table.add_columns("#", "Title", "Year / Type", "Provider Info")

    def _get_provider_options(self, category_name: str):
        """Retrieve list of (Label, Key) tuples for a category."""
        providers = get_providers_for_category(category_name)
        return [(p.get('label', p['key']), p['key']) for p in providers]

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle category switch to reload provider options."""
        if event.select.id == "category-select":
            cat = str(event.value)
            prov_select = self.query_one("#provider-select", Select)
            new_options = self._get_provider_options(cat)
            prov_select.set_options(new_options)
            if new_options:
                prov_select.value = new_options[0][1]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks."""
        btn_id = event.button.id
        if btn_id == "btn-search":
            self.action_execute_search()
        elif btn_id == "btn-download":
            self._dispatch_download(dry_run=False)
        elif btn_id == "btn-dryrun":
            self._dispatch_download(dry_run=True)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Trigger search when pressing Enter in search input."""
        if event.input.id == "search-input":
            self.action_execute_search()

    def action_execute_search(self) -> None:
        """Gather search parameters and execute search in background worker."""
        query = self.query_one("#search-input", Input).value.strip()
        if not query:
            self.app.notify("Please enter a title to search!", severity="warning")
            return

        cat = str(self.query_one("#category-select", Select).value)
        prov = str(self.query_one("#provider-select", Select).value)

        self.app.notify(f"Searching for '{query}' on {prov} ({cat})...", severity="information")
        self.query_one("#btn-search", Button).loading = True
        
        # Clear existing results
        table = self.query_one("#results-table", DataTable)
        table.clear()
        self.current_results = []
        self._update_details(None)

        self._run_search_worker(cat, prov, query)

    @work(exclusive=True, thread=True)
    def _run_search_worker(self, category: str, provider: str, query: str) -> None:
        """Background thread executing the provider search."""
        try:
            cat_cfg = self.config.get(category, {})
            client = create_client(category, provider, cat_cfg)
            if not client:
                self.app.call_from_thread(self._on_search_failed, f"Failed to initialize provider {provider}")
                return

            self.active_client = client
            results = client.search(query)
            self.app.call_from_thread(self._on_search_complete, results)
        except Exception as e:
            self.app.call_from_thread(self._on_search_failed, str(e))

    def _on_search_complete(self, results: list) -> None:
        """Populate DataTable with search results."""
        self.query_one("#btn-search", Button).loading = False
        table = self.query_one("#results-table", DataTable)
        table.clear()
        self.current_results = results or []

        if not self.current_results:
            self.app.notify("No matches found. Try refining search keywords.", severity="warning")
            return

        for idx, item in enumerate(self.current_results, start=1):
            title = item.get('title', 'Unknown')
            year = str(item.get('year', item.get('type', 'N/A')))
            extra = item.get('quality', item.get('server', item.get('meta', 'Ready')))
            table.add_row(str(idx), title, year, extra, key=str(idx-1))

        self.app.notify(f"Discovered {len(self.current_results)} match(es)!", severity="information")
        # Auto-focus and select first row
        table.focus()
        if len(self.current_results) > 0:
            self._update_details(self.current_results[0])

    def _on_search_failed(self, error_msg: str) -> None:
        """Handle search errors."""
        self.query_one("#btn-search", Button).loading = False
        self.app.notify(f"Search failed: {error_msg}", severity="error")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Update details panel when user clicks or selects a row."""
        try:
            row_idx = int(event.row_key.value)
            if 0 <= row_idx < len(self.current_results):
                item = self.current_results[row_idx]
                self._update_details(item)
        except Exception:
            pass

    def _update_details(self, item: dict = None) -> None:
        """Render details in the right pane."""
        self.selected_item = item
        btn_dl = self.query_one("#btn-download", Button)
        btn_dry = self.query_one("#btn-dryrun", Button)

        if not item:
            self.query_one("#details-meta", Static).update("No item selected.")
            self.query_one("#details-synopsis", Static).update("")
            btn_dl.disabled = True
            btn_dry.disabled = True
            return

        btn_dl.disabled = False
        btn_dry.disabled = False

        title = item.get('title', 'Unknown Title')
        year = item.get('year', 'N/A')
        rating = item.get('rating', 'N/A')
        genres = item.get('genres', [])
        synopsis = item.get('synopsis', item.get('description', 'No synopsis available.'))
        eps = item.get('episodes', item.get('total_episodes', 'Available'))

        meta_lines = [
            f"[bold cyan]Title:[/bold cyan] {title}",
            f"[bold]Year:[/bold] {year}  •  [bold]Rating:[/bold] ★ {rating}  •  [bold]Episodes:[/bold] {eps}",
            f"[bold]Genres:[/bold] {', '.join(genres) if isinstance(genres, list) else genres}"
        ]
        self.query_one("#details-meta", Static).update("\n".join(meta_lines))
        self.query_one("#details-synopsis", Static).update(f"[italic]{synopsis}[/italic]")

    def _dispatch_download(self, dry_run: bool = False) -> None:
        """Emit download trigger event to parent App."""
        if not self.selected_item:
            self.app.notify("Select an item first!", severity="warning")
            return

        eps = self.query_one("#episode-range-input", Input).value.strip() or "1"
        res = str(self.query_one("#resolution-select", Select).value)

        self.post_message(self.TriggerDownload(
            item_data=self.selected_item,
            episodes=eps,
            resolution=res,
            dry_run=dry_run
        ))
