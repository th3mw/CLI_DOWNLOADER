"""
Search & Browse Tab for CLI Media Scraper TUI.
Allows searching across all categories and providers with live results,
resolution selection, live release probing, and instant action buttons.
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
        def __init__(self, item_data: dict, episodes: str, resolution: str, audio_preference: str = "sub", category: str = "Anime", provider: str = "", dry_run: bool = False) -> None:
            self.item_data = item_data
            self.episodes = episodes
            self.resolution = resolution
            self.audio_preference = audio_preference
            self.category = category
            self.provider = provider
            self.dry_run = dry_run
            super().__init__()

    def __init__(self, config: dict = None, **kwargs):
        super().__init__(**kwargs)
        self.config = config or load_yaml('config_scraper.yaml')
        self.current_results = []
        self.selected_item = None
        self.active_client = None
        self.active_category = "Anime"
        self.active_provider = "anikoto"
        self.probed_releases = {}

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
                    initial_prov = prov_options[0][1] if prov_options else "anikoto"
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
                    with Horizontal(id="details-header-row"):
                        yield Label("🎯 Target Selection & Details", id="details-title")
                        yield Static("⛩️ ANIME", id="category-badge-label", classes="category-badge badge-anime")

                    yield Static("Select an item from the search results to inspect metadata and queue download.", id="details-meta")
                    yield Static("", id="details-synopsis")
                    
                    # Context-Aware Dynamic Controls Box
                    with Vertical(id="dynamic-controls-box"):
                        # Audio Preference (Anime specific)
                        with Horizontal(classes="form-field-row", id="row-audio-pref"):
                            yield Label("Audio Language:", classes="form-label")
                            audio_opts = [
                                ("🇯🇵 Sub (Original Japanese)", "sub"),
                                ("🇺🇸 Dub (English Dubbed)", "dub"),
                                ("🌐 Dual Audio / Multi", "dual")
                            ]
                            yield Select(audio_opts, value="sub", id="audio-pref-select", classes="form-widget", allow_blank=False)

                        # Episode Range (Anime / TV / NSFW)
                        with Horizontal(classes="form-field-row", id="row-episode-range"):
                            yield Label("Episode Range:", classes="form-label", id="label-episode-range")
                            yield Input(value="1", placeholder="e.g. 1-12, all, 1", id="episode-range-input", classes="form-widget")

                        # Movie Static Badge (Movies specific)
                        with Horizontal(classes="form-field-row", id="row-movie-badge"):
                            yield Label("Content Scope:", classes="form-label")
                            yield Static("🎬 Full Feature Film (Single Movie)", classes="badge-full-movie form-widget")

                        # Target Resolution / Release
                        with Horizontal(classes="form-field-row", id="row-resolution"):
                            yield Label("Resolution / Release:", classes="form-label")
                            res_options = [
                                ("1080P • Full HD (Recommended)", "1080"),
                                ("2160P • 4K UHD", "2160"),
                                ("720P • HD", "720"),
                                ("480P • SD", "480"),
                                ("360P • Mobile", "360"),
                            ]
                            yield Select(res_options, value="1080", id="resolution-select", classes="form-widget", allow_blank=False)

                    with Horizontal(classes="action-btn-row"):
                        yield Button("⚡ Probe Releases", id="btn-probe", disabled=True)
                        yield Button("⬇ Download", variant="primary", id="btn-download", disabled=True)
                        yield Button("🧪 Dry Run", variant="default", id="btn-dryrun", disabled=True)

    def on_mount(self) -> None:
        """Configure initial DataTable columns and UI state."""
        self._configure_table_columns("Anime")
        self._apply_category_ui_state("Anime")

    def _get_provider_options(self, category_name: str):
        """Retrieve list of (Label, Key) tuples for a category."""
        providers = get_providers_for_category(category_name)
        return [(p.get('label', p['key']), p['key']) for p in providers]

    def _configure_table_columns(self, category_name: str) -> None:
        """Dynamically configure DataTable columns based on category."""
        table = self.query_one("#results-table", DataTable)
        table.clear(columns=True)
        if category_name == "Anime":
            table.add_columns("#", "Title", "Format / Type", "Episodes (Sub/Dub)", "Score / Status")
        elif category_name == "Movies":
            table.add_columns("#", "Title", "Year", "Torrents / Releases", "Top Seeds / Quality")
        elif category_name == "TV Shows":
            table.add_columns("#", "Title", "Year / Status", "Rating", "IMDb / Meta")
        else: # NSFW
            table.add_columns("#", "Title", "Brand / Format", "Episodes", "Status")

    def _apply_category_ui_state(self, category_name: str) -> None:
        """Show/hide form rows according to the active category."""
        self.active_category = category_name
        badge = self.query_one("#category-badge-label", Static)
        
        row_audio = self.query_one("#row-audio-pref")
        row_eps = self.query_one("#row-episode-range")
        row_movie = self.query_one("#row-movie-badge")
        label_eps = self.query_one("#label-episode-range", Label)
        input_eps = self.query_one("#episode-range-input", Input)

        if category_name == "Anime":
            badge.update("⛩️ ANIME")
            badge.remove_class("badge-movie", "badge-tv", "badge-nsfw")
            badge.add_class("badge-anime")
            row_audio.display = True
            row_eps.display = True
            row_movie.display = False
            label_eps.update("Episode Range:")
            input_eps.placeholder = "e.g. 1-12, all, 1"
        elif category_name == "Movies":
            badge.update("🎬 MOVIE")
            badge.remove_class("badge-anime", "badge-tv", "badge-nsfw")
            badge.add_class("badge-movie")
            row_audio.display = False
            row_eps.display = False
            row_movie.display = True
        elif category_name == "TV Shows":
            badge.update("📺 TV SHOW")
            badge.remove_class("badge-anime", "badge-movie", "badge-nsfw")
            badge.add_class("badge-tv")
            row_audio.display = False
            row_eps.display = True
            row_movie.display = False
            label_eps.update("Season & Episodes:")
            input_eps.placeholder = "e.g. S01E01-E10, 1-12, all"
        else: # NSFW
            badge.update("🔞 NSFW")
            badge.remove_class("badge-anime", "badge-movie", "badge-tv")
            badge.add_class("badge-nsfw")
            row_audio.display = False
            row_eps.display = True
            row_movie.display = False
            label_eps.update("Episode Range:")
            input_eps.placeholder = "e.g. 1, 1-2"

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle category or provider change."""
        if event.select.id == "category-select":
            cat = str(event.value)
            self._apply_category_ui_state(cat)
            self._configure_table_columns(cat)
            
            prov_select = self.query_one("#provider-select", Select)
            new_options = self._get_provider_options(cat)
            prov_select.set_options(new_options)
            if new_options:
                prov_select.value = new_options[0][1]
                self.active_provider = new_options[0][1]
        elif event.select.id == "provider-select":
            self.active_provider = str(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks."""
        btn_id = event.button.id
        if btn_id == "btn-search":
            self.action_execute_search()
        elif btn_id == "btn-probe":
            self.action_probe_releases()
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
        self.active_category = cat
        self.active_provider = prov

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
            cat_cfg = dict(self.config.get(category, {}) or {})
            audio_pref = "sub"
            try:
                audio_pref = str(self.query_one("#audio-pref-select", Select).value)
            except Exception:
                pass

            client = create_client(category, provider, cat_cfg, audio_preference=audio_pref)
            if not client:
                self.app.call_from_thread(self._on_search_failed, f"Failed to initialize provider '{provider}' for '{category}'")
                return

            self.active_client = client
            results = client.search(query)
            self.app.call_from_thread(self._on_search_complete, results, category)
        except Exception as e:
            self.app.call_from_thread(self._on_search_failed, str(e))

    def _on_search_complete(self, results, category: str) -> None:
        """Populate DataTable with search results formatted per category."""
        self.query_one("#btn-search", Button).loading = False
        table = self.query_one("#results-table", DataTable)
        table.clear()
        
        if isinstance(results, dict):
            self.current_results = list(results.values())
        elif isinstance(results, list):
            self.current_results = results
        else:
            self.current_results = []

        if not self.current_results:
            self.app.notify("No matches found. Try refining search keywords.", severity="warning")
            return

        for idx, item in enumerate(self.current_results, start=1):
            title = item.get('title', item.get('raw_title', 'Unknown'))
            if category == "Anime":
                format_badge = item.get('format', item.get('type', '[TV]'))
                sub_cnt = item.get('sub_episodes', item.get('total_episodes', '1'))
                dub_cnt = item.get('dub_episodes', 0)
                ep_badge = f"Sub: {sub_cnt} • Dub: {dub_cnt}" if dub_cnt else f"Episodes: {sub_cnt}"
                score = f"★ {item.get('score', item.get('rating', 'N/A'))}"
                table.add_row(str(idx), title, format_badge, ep_badge, score, key=str(idx-1))
            elif category == "Movies":
                year = str(item.get('year', 'N/A'))
                all_rels = item.get('all_releases', [])
                rel_info = f"{len(all_rels)} releases" if all_rels else str(item.get('qualities', 'Available'))
                top_seeds = f"Seeds: {max((r.get('seeds', 0) for r in all_rels), default='N/A')}" if all_rels else str(item.get('size', 'Ready'))
                table.add_row(str(idx), title, year, rel_info, top_seeds, key=str(idx-1))
            elif category == "TV Shows":
                year = str(item.get('year', 'N/A'))
                rating = f"★ {item.get('rating', 'N/A')}"
                imdb = item.get('imdb_id') or (", ".join(item.get('genres', [])[:2]) if item.get('genres') else 'Ready')
                table.add_row(str(idx), title, year, rating, imdb, key=str(idx-1))
            else: # NSFW
                brand = item.get('brand', item.get('type', 'Hentai'))
                eps = str(item.get('episodes', item.get('total_episodes', '1')))
                status = item.get('status', 'Ready')
                table.add_row(str(idx), title, brand, f"Eps: {eps}", status, key=str(idx-1))

        self.app.notify(f"Discovered {len(self.current_results)} match(es)!", severity="information")
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
        btn_probe = self.query_one("#btn-probe", Button)

        if not item:
            self.query_one("#details-meta", Static).update("No item selected.")
            self.query_one("#details-synopsis", Static).update("")
            btn_dl.disabled = True
            btn_dry.disabled = True
            btn_probe.disabled = True
            return

        btn_dl.disabled = False
        btn_dry.disabled = False
        btn_probe.disabled = False

        title = item.get('title', item.get('raw_title', 'Unknown Title'))
        romaji = item.get('romaji_title') or item.get('japanese_title')
        year = item.get('year', 'N/A')
        rating = item.get('rating', item.get('score', 'N/A'))
        genres = item.get('genres', [])
        synopsis = item.get('synopsis', item.get('description', 'No synopsis available.'))
        eps = item.get('episodes', item.get('total_episodes', item.get('sub_episodes', 'Available')))
        
        meta_lines = [
            f"[bold cyan]Title:[/bold cyan] {title}",
        ]
        if romaji and romaji != title:
            meta_lines.append(f"[italic #8b949e]Romaji:[/italic #8b949e] {romaji}")

        meta_parts = []
        if year and year != 'N/A':
            meta_parts.append(f"[bold]Year:[/bold] {year}")
        if rating and rating != 'N/A':
            meta_parts.append(f"[bold]Rating:[/bold] ★ {rating}")
        if eps and eps != 'N/A':
            meta_parts.append(f"[bold]Episodes:[/bold] {eps}")

        if meta_parts:
            meta_lines.append("  •  ".join(meta_parts))

        if genres:
            genre_str = ", ".join(genres) if isinstance(genres, list) else str(genres)
            meta_lines.append(f"[bold]Genres:[/bold] {genre_str}")

        self.query_one("#details-meta", Static).update("\n".join(meta_lines))
        self.query_one("#details-synopsis", Static).update(f"[italic]{synopsis}[/italic]")

        # Update episode placeholder if known
        if isinstance(eps, int) or (isinstance(eps, str) and eps.isdigit()):
            self.query_one("#episode-range-input", Input).placeholder = f"e.g. 1-{eps}, all, 1"
            if int(eps) > 1:
                self.query_one("#episode-range-input", Input).value = f"1-{eps}"
            else:
                self.query_one("#episode-range-input", Input).value = "1"

        # If item contains pre-parsed qualities or torrent releases, update resolution options
        if item.get('all_releases'):
            self._populate_resolution_options_from_releases(item['all_releases'])

    def _populate_resolution_options_from_releases(self, releases: list) -> None:
        """Populate resolution dropdown with distinct torrent releases."""
        res_select = self.query_one("#resolution-select", Select)
        options = []
        for idx, r in enumerate(releases[:12], start=1):
            q = str(r.get('quality', '1080')).upper().replace('P', '')
            size = r.get('size', 'Unknown')
            seeds = r.get('seeds', 0)
            tag = r.get('raw_title', '')[:30]
            opt_key = f"{q}_{idx}"
            opt_label = f"{q}P • {size} • Seeds: {seeds} • {tag}"
            options.append((opt_label, opt_key))
        
        if options:
            res_select.set_options(options)
            # Default to top 1080p release if present
            default_opt = next((k for lbl, k in options if k.startswith('1080')), options[0][1])
            res_select.value = default_opt

    def action_probe_releases(self) -> None:
        """Trigger background worker to probe available streams/torrent releases."""
        if not self.selected_item or not self.active_client:
            return
        
        self.query_one("#btn-probe", Button).loading = True
        self.app.notify("Probing available releases and streams...", severity="information")
        self._run_probe_worker(self.active_client, self.selected_item)

    @work(exclusive=True, thread=True)
    def _run_probe_worker(self, client, target_item: dict) -> None:
        """Background worker fetching episode list and probing first episode links."""
        try:
            episodes = client.fetch_episodes_list(target_item)
            if not episodes:
                self.app.call_from_thread(self._on_probe_complete, None, "No episodes found for probing")
                return

            sample_ep = episodes[0]
            links = client.fetch_episode_links([sample_ep], {'start': sample_ep.get('episode', 1), 'end': sample_ep.get('episode', 1), 'specific_no': [sample_ep.get('episode', 1)]})
            self.app.call_from_thread(self._on_probe_complete, links, None)
        except Exception as e:
            self.app.call_from_thread(self._on_probe_complete, None, str(e))

    def _on_probe_complete(self, links: dict, error_msg: str = None) -> None:
        """Update resolution select with probed release metadata."""
        self.query_one("#btn-probe", Button).loading = False
        if error_msg or not links:
            self.app.notify(f"Probe notice: {error_msg or 'No stream links found'}", severity="warning")
            return

        sample_ep_links = next(iter(links.values()), {})
        if not sample_ep_links:
            self.app.notify("Probe completed, no resolutions returned.", severity="warning")
            return

        options = []
        for opt_k, opt_d in sample_ep_links.items():
            if isinstance(opt_d, dict):
                q = str(opt_d.get('quality', opt_k)).upper()
                size_meta = opt_d.get('resolution_size') or f"{opt_d.get('size', 'N/A')} • Seeds: {opt_d.get('seeds', 'N/A')}"
                opt_label = f"{q} • {size_meta}"
                options.append((opt_label, opt_k))
            else:
                options.append((f"{opt_k}P", str(opt_k)))

        if options:
            res_select = self.query_one("#resolution-select", Select)
            res_select.set_options(options)
            res_select.value = options[0][1]
            self.app.notify(f"✔ Successfully probed {len(options)} release option(s)!", severity="information")

    def _dispatch_download(self, dry_run: bool = False) -> None:
        """Emit download trigger event to parent App."""
        if not self.selected_item:
            self.app.notify("Select an item first!", severity="warning")
            return

        eps = self.query_one("#episode-range-input", Input).value.strip() or "1"
        res = str(self.query_one("#resolution-select", Select).value)
        audio_pref = "sub"
        try:
            audio_pref = str(self.query_one("#audio-pref-select", Select).value)
        except Exception:
            pass

        self.post_message(self.TriggerDownload(
            item_data=self.selected_item,
            episodes=eps,
            resolution=res,
            audio_preference=audio_pref,
            category=self.active_category,
            provider=self.active_provider,
            dry_run=dry_run
        ))

