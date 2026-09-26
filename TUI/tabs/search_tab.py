"""
Search & Browse Tab for CLI Media Scraper TUI.
Next-gen flat, fluid, keyboard-native terminal interface (Awesome-TUI style).
Strict 4-layer Separation of Concerns between Torrents and Direct Streams.
"""

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Static, Input, Button, Select, DataTable, Label
)
from textual.message import Message

from Core.provider_factory import CATEGORIES, CATEGORY_PROVIDERS, create_client, get_providers_for_category
from Core.commons import load_yaml


def generate_health_bar(seeds: int, max_seeds: int = 500, width: int = 8) -> str:
    """Generate a visual terminal bar meter for peer swarm health."""
    if not isinstance(seeds, int) or seeds <= 0:
        return f"[#64748b]{'░' * width}[/#64748b] 0"
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

    return f"[{bar_color}]{'█' * filled}[/{bar_color}][#1e293b]{'░' * unfilled}[/#1e293b] {seeds}s"


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
        tags.append("[#64748b]x264[/#64748b]")
    if "hdr" in t_lower or "dv" in t_lower or "dovi" in t_lower:
        tags.append("[bold #f59e0b]HDR[/bold #f59e0b]")
    return " ".join(tags[:3]) if tags else "[#64748b]REL[/#64748b]"


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
            # Top Command Bar (Flat, Seamless, Non-Boxy)
            with Horizontal(id="search-controls", classes="search-row"):
                yield Button("⛩️ [1] Anime", id="cat-btn-anime", classes="cat-btn -active-anime")
                yield Button("🎬 [2] Movies", id="cat-btn-movies", classes="cat-btn")
                yield Button("📺 [3] TV", id="cat-btn-tv", classes="cat-btn")
                yield Button("🔞 [4] NSFW", id="cat-btn-nsfw", classes="cat-btn")

                # Provider Select
                prov_options = self._get_provider_options("Anime")
                initial_prov = prov_options[0][1] if prov_options else "anikoto"
                yield Select(prov_options, value=initial_prov, id="provider-select", allow_blank=False)

                # Search Input & Trigger
                yield Input(placeholder="Search (e.g. Solo Leveling, Inception, Breaking Bad)...", id="search-input")
                yield Button("🔍 Run", variant="success", id="btn-search")

            # Main Master-Detail Split Container
            with Horizontal(id="search-split-container"):
                # Left Pane: Search Results Table
                with Vertical(id="results-pane"):
                    yield Static("📋 SEARCH RESULTS", classes="pane-header-title")
                    yield DataTable(id="results-table", cursor_type="row")

                # Right Pane: Target Inspector & Interactive Release Matrix
                with Vertical(id="details-pane"):
                    yield Static("[bold #38bdf8]🎯 TARGET INSPECTOR[/bold #38bdf8]  •  [bold #c084fc]⛩️ ANIME[/bold #c084fc]", id="details-card-header")
                    yield Static("Select an item from the results table on the left to inspect releases.", id="details-meta")
                    yield Static("", id="details-synopsis")
                    
                    # Context-Aware Controls Strip (Audio / Episodes / Scope)
                    with Horizontal(id="dynamic-controls-strip"):
                        yield Label("Audio:", classes="inline-label", id="lbl-audio-pref")
                        audio_opts = [
                            ("🇯🇵 Sub (Japanese)", "sub"),
                            ("🇺🇸 Dub (English)", "dub"),
                            ("🌐 Dual Audio", "dual")
                        ]
                        yield Select(audio_opts, value="sub", id="audio-pref-select", allow_blank=False)

                        yield Label("Episodes:", classes="inline-label", id="lbl-episode-range")
                        yield Input(value="1", placeholder="1-12, all", id="episode-range-input")

                        yield Static("🎬 Full Feature Film", id="badge-movie-scope", classes="movie-badge-inline")

                    # Interactive Release Matrix Table
                    yield Static("⚡ AVAILABLE RELEASES & STREAMS (PROBED / AGGREGATED)", classes="pane-header-title")
                    with Vertical(id="release-matrix-container"):
                        yield DataTable(id="release-matrix-table", cursor_type="row")

                    # Bottom Action Bar
                    with Horizontal(id="action-buttons-strip"):
                        yield Button("⚡ Probe [Space]", id="btn-probe", disabled=True)
                        yield Button("⬇ Download [d]", variant="primary", id="btn-download", disabled=True)
                        yield Button("🧪 Dry Run [r]", variant="default", id="btn-dryrun", disabled=True)

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
            table.add_columns("#", "Title", "Format", "Episodes", "Score")
        elif category_name == "Movies":
            table.add_columns("#", "Title", "Year", "Torrents / Releases", "Top Seeds")
        elif category_name == "TV Shows":
            table.add_columns("#", "Title", "Year / Status", "Rating", "Meta")
        else: # NSFW
            table.add_columns("#", "Title", "Brand", "Episodes", "Status")

    def _configure_matrix_columns(self) -> None:
        """Configure the columns for the interactive Release Matrix table."""
        matrix = self.query_one("#release-matrix-table", DataTable)
        matrix.clear(columns=True)
        matrix.add_columns("#", "Quality", "Size", "Swarm / Health", "Release Group / Description", "Tags")

    def _apply_category_ui_state(self, category_name: str) -> None:
        """Show/hide form elements according to the active category (Separation of Concerns)."""
        self.active_category = category_name
        header_title = self.query_one("#details-card-header", Static)
        
        lbl_audio = self.query_one("#lbl-audio-pref", Label)
        select_audio = self.query_one("#audio-pref-select", Select)
        lbl_eps = self.query_one("#lbl-episode-range", Label)
        input_eps = self.query_one("#episode-range-input", Input)
        badge_movie = self.query_one("#badge-movie-scope", Static)

        # Update category buttons styling
        btn_anime = self.query_one("#cat-btn-anime", Button)
        btn_movies = self.query_one("#cat-btn-movies", Button)
        btn_tv = self.query_one("#cat-btn-tv", Button)
        btn_nsfw = self.query_one("#cat-btn-nsfw", Button)

        for btn in [btn_anime, btn_movies, btn_tv, btn_nsfw]:
            btn.remove_class("-active-anime", "-active-movies", "-active-tv", "-active-nsfw")

        if category_name == "Anime":
            header_title.update("[bold #38bdf8]🎯 TARGET INSPECTOR[/bold #38bdf8]  •  [bold #c084fc]⛩️ ANIME[/bold #c084fc]")
            btn_anime.add_class("-active-anime")
            lbl_audio.display = True
            select_audio.display = True
            lbl_eps.display = True
            input_eps.display = True
            badge_movie.display = False
            lbl_eps.update("Episodes:")
            input_eps.placeholder = "1-12, all"
        elif category_name == "Movies":
            header_title.update("[bold #38bdf8]🎯 TARGET INSPECTOR[/bold #38bdf8]  •  [bold #38bdf8]🎬 MOVIE[/bold #38bdf8]")
            btn_movies.add_class("-active-movies")
            lbl_audio.display = False
            select_audio.display = False
            lbl_eps.display = False
            input_eps.display = False
            badge_movie.display = True
        elif category_name == "TV Shows":
            header_title.update("[bold #38bdf8]🎯 TARGET INSPECTOR[/bold #38bdf8]  •  [bold #34d399]📺 TV SHOW[/bold #34d399]")
            btn_tv.add_class("-active-tv")
            lbl_audio.display = False
            select_audio.display = False
            lbl_eps.display = True
            input_eps.display = True
            badge_movie.display = False
            lbl_eps.update("Episodes:")
            input_eps.placeholder = "S01E01-E10, 1-12"
        else: # NSFW
            header_title.update("[bold #38bdf8]🎯 TARGET INSPECTOR[/bold #38bdf8]  •  [bold #fb7185]🔞 NSFW[/bold #fb7185]")
            btn_nsfw.add_class("-active-nsfw")
            lbl_audio.display = False
            select_audio.display = False
            lbl_eps.display = True
            input_eps.display = True
            badge_movie.display = False
            lbl_eps.update("Episodes:")
            input_eps.placeholder = "1, 1-2, all"

    def switch_category_by_name(self, cat_name: str) -> None:
        """Switch category from category buttons or keyboard shortcuts."""
        self._apply_category_ui_state(cat_name)
        self._configure_table_columns(cat_name)
        
        prov_select = self.query_one("#provider-select", Select)
        new_options = self._get_provider_options(cat_name)
        prov_select.set_options(new_options)
        if new_options:
            prov_select.value = new_options[0][1]
            self.active_provider = new_options[0][1]

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle provider change."""
        if event.select.id == "provider-select":
            self.active_provider = str(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks."""
        btn_id = event.button.id
        if btn_id == "btn-search":
            self.action_execute_search()
        elif btn_id == "cat-btn-anime":
            self.switch_category_by_name("Anime")
        elif btn_id == "cat-btn-movies":
            self.switch_category_by_name("Movies")
        elif btn_id == "cat-btn-tv":
            self.switch_category_by_name("TV Shows")
        elif btn_id == "cat-btn-nsfw":
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

        cat = self.active_category
        prov = str(self.query_one("#provider-select", Select).value)
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
            self.app.notify("No matches found. Try refining keywords.", severity="warning")
            return

        for idx, item in enumerate(self.current_results, start=1):
            title = item.get('title', item.get('raw_title', 'Unknown'))
            if category == "Anime":
                format_badge = item.get('format', item.get('type', '[TV]'))
                sub_cnt = item.get('sub_episodes', item.get('total_episodes', '1'))
                dub_cnt = item.get('dub_episodes', 0)
                ep_badge = f"Sub:{sub_cnt} Dub:{dub_cnt}" if dub_cnt else f"Ep:{sub_cnt}"
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
                    self.app.notify(f"Selected: {q}P ({size})", severity="information")
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
            f"[bold white]{title}[/bold white]",
        ]
        if romaji and romaji != title:
            meta_lines.append(f"[dim]{romaji}[/dim]")

        meta_parts = []
        if rating and rating != 'N/A':
            meta_parts.append(f"[bold #f59e0b]★ {rating}[/bold #f59e0b]")
        if year and year != 'N/A':
            meta_parts.append(f"Year: {year}")
        if eps and eps != 'N/A':
            meta_parts.append(f"Episodes: {eps}")

        if meta_parts:
            meta_lines.append("  •  ".join(meta_parts))

        if genres:
            genre_str = ", ".join(genres) if isinstance(genres, list) else str(genres)
            meta_lines.append(f"[dim]Genres: {genre_str}[/dim]")

        self.query_one("#details-meta", Static).update("\n".join(meta_lines))
        self.query_one("#details-synopsis", Static).update(f"[italic #64748b]{synopsis}[/italic #64748b]")

        # Update episode placeholder if known
        if isinstance(eps, int) or (isinstance(eps, str) and eps.isdigit()):
            self.query_one("#episode-range-input", Input).placeholder = f"1-{eps}"
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

        for idx, r in enumerate(releases[:20], start=1):
            q_raw = str(r.get('quality', '1080')).upper().replace('P', '')
            q_badge = f"[bold #38bdf8]{q_raw}P[/bold #38bdf8]" if q_raw in ["2160", "1080"] else f"[#64748b]{q_raw}P[/#64748b]"
            size = r.get('size', 'Unknown')
            seeds = r.get('seeds', 0)
            health_bar = generate_health_bar(seeds)
            raw_title = r.get('raw_title', r.get('title', 'Scene Release'))
            tags = extract_release_tags(raw_title)
            clean_grp = raw_title[:40]
            matrix.add_row(f"[{idx}]", q_badge, size, health_bar, clean_grp, tags, key=str(idx-1))

        # Default select first release
        if self.probed_releases:
            self.selected_matrix_release = self.probed_releases[0]

    def action_probe_releases(self) -> None:
        """Trigger background worker to probe available streams/torrent releases."""
        if not self.selected_item or not self.active_client:
            return
        
        self.query_one("#btn-probe", Button).loading = True
        self.app.notify("Probing streams / releases in background...", severity="information")
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
            self.app.notify(f"✔ Probed {len(synthesized_releases)} release(s)!", severity="information")

    def _dispatch_download(self, dry_run: bool = False) -> None:
        """Emit download trigger event to parent App."""
        if not self.selected_item:
            self.app.notify("Select an item first!", severity="warning")
            return

        eps = self.query_one("#episode-range-input", Input).value.strip() or "1"
        res = "1080"
        if self.selected_matrix_release:
            res = str(self.selected_matrix_release.get('quality', '1080'))

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


