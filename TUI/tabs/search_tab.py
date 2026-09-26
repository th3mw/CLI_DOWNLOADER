"""
Search & Browse Tab for CLI Media Scraper TUI.
Allows searching across all categories and providers with live results,
interactive Release Matrix (Awesome-TUI style), resolution probing,
and keyboard-native controls with strict Separation of Concerns.
"""

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Static, Input, Button, Select, DataTable, Label, 
    ProgressBar, Rule
)
from textual.message import Message

from Core.provider_factory import CATEGORIES, CATEGORY_PROVIDERS, create_client, get_providers_for_category
from Core.commons import load_yaml


def generate_health_bar(seeds: int, max_seeds: int = 500, width: int = 8) -> str:
    """Generate a visual terminal bar meter for peer swarm health."""
    if not isinstance(seeds, int) or seeds <= 0:
        return f"[#8b949e]{'░' * width}[/#8b949e] Seeds: 0"
    ratio = min(1.0, seeds / max_seeds)
    filled = max(1, int(ratio * width))
    unfilled = width - filled
    
    if seeds > 200:
        bar_color = "#34d399" # Emerald
    elif seeds > 50:
        bar_color = "#38bdf8" # Sky cyan
    elif seeds > 10:
        bar_color = "#f59e0b" # Amber
    else:
        bar_color = "#fb7185" # Crimson

    return f"[{bar_color}]{'█' * filled}[/{bar_color}][#232d42]{'░' * unfilled}[/#232d42] Seeds: {seeds}"


def extract_release_tags(title: str) -> str:
    """Extract standard scene tags from release title."""
    tags = []
    t_lower = str(title).lower()
    if "remux" in t_lower:
        tags.append("[bold #c084fc]REMUX[/bold #c084fc]")
    if "proper" in t_lower or "repack" in t_lower:
        tags.append("[bold #38bdf8]PROPER[/bold #38bdf8]")
    if "bluray" in t_lower or "blu-ray" in t_lower or "bdrip" in t_lower:
        tags.append("[#38bdf8]BluRay[/#38bdf8]")
    elif "web-dl" in t_lower or "webrip" in t_lower or "web" in t_lower:
        tags.append("[#34d399]WEB-DL[/#34d399]")
    if "av1" in t_lower:
        tags.append("[bold #f59e0b]AV1[/bold #f59e0b]")
    elif "hevc" in t_lower or "x265" in t_lower or "h.265" in t_lower:
        tags.append("[#38bdf8]x265[/#38bdf8]")
    elif "x264" in t_lower or "h.264" in t_lower:
        tags.append("[#8b949e]x264[/#8b949e]")
    if "hdr" in t_lower or "dv" in t_lower or "dovi" in t_lower:
        tags.append("[bold #f59e0b]HDR[/bold #f59e0b]")
    return " ".join(tags[:3]) if tags else "[#8b949e]RELEASE[/#8b949e]"


class SearchTab(Static):
    """Interactive media search and selection tab."""

    class ResultSelected(Message):
        """Emitted when a user selects a search result."""
        def __init__(self, item_data: dict) -> None:
            self.item_data = item_data
            super().__init__()

    class TriggerDownload(Message):
        """Emitted when a user clicks download."""
        def __init__(self, item_data: dict, episodes: str, resolution: str, audio_preference: str = "sub", category: str = "Anime", provider: str = "", dry_run: bool = False, selected_release: dict = None) -> None:
            self.item_data = item_data
            self.episodes = episodes
            self.resolution = resolution
            self.audio_preference = audio_preference
            self.category = category
            self.provider = provider
            self.dry_run = dry_run
            self.selected_release = selected_release
            super().__init__()

    def __init__(self, config: dict = None, **kwargs):
        super().__init__(**kwargs)
        self.config = config or load_yaml('config_scraper.yaml')
        self.current_results = []
        self.selected_item = None
        self.active_client = None
        self.active_category = "Anime"
        self.active_provider = "anikoto"
        self.probed_releases = []
        self.selected_matrix_release = None

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

                # Quick Category Filter Bar
                with Horizontal(id="quick-category-bar"):
                    yield Button("⛩️ [1] Anime", id="quick-cat-anime", classes="quick-cat-btn -active-anime")
                    yield Button("🎬 [2] Movies", id="quick-cat-movies", classes="quick-cat-btn")
                    yield Button("📺 [3] TV Shows", id="quick-cat-tv", classes="quick-cat-btn")
                    yield Button("🔞 [4] NSFW", id="quick-cat-nsfw", classes="quick-cat-btn")

            # Main Split View: Left Results Table, Right Details & Actions
            with Horizontal(id="search-split-container"):
                with Vertical(id="results-pane"):
                    yield Label("📋 Search Results", classes="pane-title")
                    yield DataTable(id="results-table", cursor_type="row")

                with Vertical(id="details-pane"):
                    with Horizontal(id="details-header-row"):
                        yield Label("🎯 Target Inspector", id="details-title")
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

                        # Target Resolution Dropdown (Fallback/Direct stream)
                        with Horizontal(classes="form-field-row", id="row-resolution"):
                            yield Label("Target Bitrate:", classes="form-label", id="label-resolution")
                            res_options = [
                                ("1080P • Full HD (Recommended)", "1080"),
                                ("2160P • 4K UHD", "2160"),
                                ("720P • HD", "720"),
                                ("480P • SD", "480"),
                                ("360P • Mobile", "360"),
                            ]
                            yield Select(res_options, value="1080", id="resolution-select", classes="form-widget", allow_blank=False)

                    # Interactive Release Matrix Widget
                    yield Label("⚡ Available Releases & Streams Matrix", classes="pane-title", id="label-release-matrix")
                    with Vertical(id="release-matrix-container"):
                        yield DataTable(id="release-matrix-table", cursor_type="row")

                    with Horizontal(classes="action-btn-row"):
                        yield Button("⚡ Probe Releases", id="btn-probe", disabled=True)
                        yield Button("⬇ Download", variant="primary", id="btn-download", disabled=True)
                        yield Button("🧪 Dry Run", variant="default", id="btn-dryrun", disabled=True)

    def on_mount(self) -> None:
        """Configure initial DataTable columns and UI state."""
        self._configure_table_columns("Anime")
        self._configure_matrix_columns()
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

    def _configure_matrix_columns(self) -> None:
        """Configure the columns for the interactive Release Matrix table."""
        matrix = self.query_one("#release-matrix-table", DataTable)
        matrix.clear(columns=True)
        matrix.add_columns("#", "Quality", "Size", "Health / Swarm", "Format & Release Group", "Tags")

    def _apply_category_ui_state(self, category_name: str) -> None:
        """Show/hide form rows according to the active category (Separation of Concerns)."""
        self.active_category = category_name
        badge = self.query_one("#category-badge-label", Static)
        
        row_audio = self.query_one("#row-audio-pref")
        row_eps = self.query_one("#row-episode-range")
        row_movie = self.query_one("#row-movie-badge")
        label_eps = self.query_one("#label-episode-range", Label)
        input_eps = self.query_one("#episode-range-input", Input)

        # Update category quick filter buttons
        cat_btn_anime = self.query_one("#quick-cat-anime", Button)
        cat_btn_movie = self.query_one("#quick-cat-movies", Button)
        cat_btn_tv = self.query_one("#quick-cat-tv", Button)
        cat_btn_nsfw = self.query_one("#quick-cat-nsfw", Button)

        for btn in [cat_btn_anime, cat_btn_movie, cat_btn_tv, cat_btn_nsfw]:
            btn.remove_class("-active-anime", "-active-movie", "-active-tv", "-active-nsfw")

        if category_name == "Anime":
            badge.update("⛩️ ANIME")
            badge.remove_class("badge-movie", "badge-tv", "badge-nsfw")
            badge.add_class("badge-anime")
            cat_btn_anime.add_class("-active-anime")
            row_audio.display = True
            row_eps.display = True
            row_movie.display = False
            label_eps.update("Episode Range:")
            input_eps.placeholder = "e.g. 1-12, all, 1"
        elif category_name == "Movies":
            badge.update("🎬 MOVIE")
            badge.remove_class("badge-anime", "badge-tv", "badge-nsfw")
            badge.add_class("badge-movie")
            cat_btn_movie.add_class("-active-movie")
            row_audio.display = False
            row_eps.display = False
            row_movie.display = True
        elif category_name == "TV Shows":
            badge.update("📺 TV SHOW")
            badge.remove_class("badge-anime", "badge-movie", "badge-nsfw")
            badge.add_class("badge-tv")
            cat_btn_tv.add_class("-active-tv")
            row_audio.display = False
            row_eps.display = True
            row_movie.display = False
            label_eps.update("Season & Episodes:")
            input_eps.placeholder = "e.g. S01E01-E10, 1-12, all"
        else: # NSFW
            badge.update("🔞 NSFW")
            badge.remove_class("badge-anime", "badge-movie", "badge-tv")
            badge.add_class("badge-nsfw")
            cat_btn_nsfw.add_class("-active-nsfw")
            row_audio.display = False
            row_eps.display = True
            row_movie.display = False
            label_eps.update("Episode Range:")
            input_eps.placeholder = "e.g. 1, 1-2"

    def switch_category_by_name(self, cat_name: str) -> None:
        """Switch category from quick filter button or power shortcut."""
        cat_select = self.query_one("#category-select", Select)
        cat_select.value = cat_name
        self._apply_category_ui_state(cat_name)
        self._configure_table_columns(cat_name)
        
        prov_select = self.query_one("#provider-select", Select)
        new_options = self._get_provider_options(cat_name)
        prov_select.set_options(new_options)
        if new_options:
            prov_select.value = new_options[0][1]
            self.active_provider = new_options[0][1]

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
        elif btn_id == "quick-cat-anime":
            self.switch_category_by_name("Anime")
        elif btn_id == "quick-cat-movies":
            self.switch_category_by_name("Movies")
        elif btn_id == "quick-cat-tv":
            self.switch_category_by_name("TV Shows")
        elif btn_id == "quick-cat-nsfw":
            self.switch_category_by_name("Hentai (NSFW)")
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
        """Handle selection in either Results Table or Release Matrix."""
        if event.data_table.id == "results-table":
            try:
                row_idx = int(event.row_key.value)
                if 0 <= row_idx < len(self.current_results):
                    item = self.current_results[row_idx]
                    self._update_details(item)
            except Exception:
                pass
        elif event.data_table.id == "release-matrix-table":
            try:
                matrix_idx = int(event.row_key.value)
                if 0 <= matrix_idx < len(self.probed_releases):
                    self.selected_matrix_release = self.probed_releases[matrix_idx]
                    q = self.selected_matrix_release.get('quality', '1080')
                    size = self.selected_matrix_release.get('size', 'Ready')
                    self.app.notify(f"Selected Release: {q}P ({size})", severity="information")
            except Exception:
                pass

    def _update_details(self, item: dict = None) -> None:
        """Render details in the right pane and populate initial Release Matrix."""
        self.selected_item = item
        self.selected_matrix_release = None
        self.probed_releases = []
        
        btn_dl = self.query_one("#btn-download", Button)
        btn_dry = self.query_one("#btn-dryrun", Button)
        btn_probe = self.query_one("#btn-probe", Button)
        matrix = self.query_one("#release-matrix-table", DataTable)
        matrix.clear()

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
            f"[bold #38bdf8]Title:[/bold #38bdf8] [bold white]{title}[/bold white]",
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

        # If item contains pre-parsed torrent releases (e.g. from TGx or YTS), populate Release Matrix directly
        if item.get('all_releases'):
            self._populate_release_matrix(item['all_releases'])

    def _populate_release_matrix(self, releases: list) -> None:
        """Populate interactive Release Matrix table with detailed release rows."""
        self.probed_releases = releases
        matrix = self.query_one("#release-matrix-table", DataTable)
        matrix.clear()
        
        if not releases:
            return

        for idx, r in enumerate(releases[:15], start=1):
            q_raw = str(r.get('quality', '1080')).upper().replace('P', '')
            q_badge = f"[bold #38bdf8]{q_raw}P[/bold #38bdf8]" if q_raw in ["2160", "1080"] else f"[#8b949e]{q_raw}P[/#8b949e]"
            size = r.get('size', 'Unknown')
            seeds = r.get('seeds', 0)
            health_bar = generate_health_bar(seeds)
            raw_title = r.get('raw_title', r.get('title', 'Scene Release'))
            tags = extract_release_tags(raw_title)
            
            # Format/Group summary
            clean_grp = raw_title[:45]
            matrix.add_row(f"[{idx}]", q_badge, size, health_bar, clean_grp, tags, key=str(idx-1))

        # Default select first release
        if self.probed_releases:
            self.selected_matrix_release = self.probed_releases[0]

    def action_probe_releases(self) -> None:
        """Trigger background worker to probe available streams/torrent releases."""
        if not self.selected_item or not self.active_client:
            return
        
        self.query_one("#btn-probe", Button).loading = True
        self.app.notify("Probing releases & streams in background...", severity="information")
        self._run_probe_worker(self.active_client, self.selected_item)

    @work(exclusive=True, thread=True)
    def _run_probe_worker(self, client, target_item: dict) -> None:
        """Background worker fetching episode list and probing links."""
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
        """Update Release Matrix with probed stream/torrent metadata."""
        self.query_one("#btn-probe", Button).loading = False
        if error_msg or not links:
            self.app.notify(f"Probe notice: {error_msg or 'No stream links returned'}", severity="warning")
            return

        sample_ep_links = next(iter(links.values()), {})
        if not sample_ep_links:
            self.app.notify("Probe completed, no releases discovered.", severity="warning")
            return

        synthesized_releases = []
        for opt_k, opt_d in sample_ep_links.items():
            if isinstance(opt_d, dict):
                synthesized_releases.append({
                    'quality': opt_d.get('quality', opt_k),
                    'size': opt_d.get('size', opt_d.get('resolution_size', 'Direct Stream')),
                    'seeds': opt_d.get('seeds', 100),
                    'raw_title': opt_d.get('raw_title', f"Stream Source ({opt_k}P)"),
                    'magnet': opt_d.get('magnet'),
                    'url': opt_d.get('url')
                })
            else:
                synthesized_releases.append({
                    'quality': str(opt_k),
                    'size': 'Direct CDN Stream',
                    'seeds': 100,
                    'raw_title': f"Direct Stream ({opt_k}P)",
                    'url': str(opt_d)
                })

        if synthesized_releases:
            self._populate_release_matrix(synthesized_releases)
            self.app.notify(f"✔ Successfully probed {len(synthesized_releases)} release option(s)!", severity="information")

    def _dispatch_download(self, dry_run: bool = False) -> None:
        """Emit download trigger event to parent App."""
        if not self.selected_item:
            self.app.notify("Select an item first!", severity="warning")
            return

        eps = self.query_one("#episode-range-input", Input).value.strip() or "1"
        res = "1080"
        if self.selected_matrix_release:
            res = str(self.selected_matrix_release.get('quality', '1080'))
        else:
            try:
                res = str(self.query_one("#resolution-select", Select).value)
            except Exception:
                pass

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
            dry_run=dry_run,
            selected_release=self.selected_matrix_release
        ))

