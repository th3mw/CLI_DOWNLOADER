"""
Main Textual Application for CLI Media Scraper & Downloader.
Provides an interactive dashboard for searching, resolution probing,
downloading, and configuration management.
"""

import os
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer, TabbedContent, TabPane, Static

from TUI.tabs.search_tab import SearchTab
from TUI.tabs.history_tab import HistoryTab
from TUI.tabs.settings_tab import SettingsTab
from TUI.tabs.downloads_tab import DownloadsTab
from Core.commons import load_yaml


class MediaScraperTUI(App):
    """Main Textual Application for Media Scraper."""

    TITLE = "🎬 CLI MEDIA SCRAPER & DOWNLOADER"
    SUB_TITLE = "v1.8.0 • Next-Gen Keyboard-Native Dashboard"
    CSS_PATH = "styles.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("slash", "focus_search", "Search [/]", show=True),
        Binding("1", "quick_category('Anime')", "⛩️ Anime", show=True),
        Binding("2", "quick_category('Movies')", "🎬 Movies", show=True),
        Binding("3", "quick_category('TV Shows')", "📺 TV", show=True),
        Binding("4", "quick_category('Hentai (NSFW)')", "🔞 NSFW", show=True),
        Binding("p", "trigger_probe", "Probe [p]", show=True),
        Binding("d", "trigger_download", "Download [d]", show=True),
        Binding("r", "trigger_dryrun", "Dry Run [r]", show=True),
        Binding("s", "switch_tab('tab-search')", "Search Tab", show=False),
        Binding("a", "switch_tab('tab-downloads')", "Activity", show=True),
        Binding("h", "switch_tab('tab-history')", "History", show=True),
        Binding("c", "switch_tab('tab-settings')", "Settings", show=True),
    ]

    def __init__(self, config_file: str = "config_scraper.yaml", **kwargs):
        super().__init__(**kwargs)
        self.config_file = config_file
        self.config_data = load_yaml(config_file) or {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="tab-search", id="main-tabs"):
            with TabPane("🔍 Search & Browse", id="tab-search"):
                yield SearchTab(config=self.config_data)
            with TabPane("📥 Activity & Logs", id="tab-downloads"):
                yield DownloadsTab()
            with TabPane("📜 History & Resume", id="tab-history"):
                yield HistoryTab()
            with TabPane("⚙️ Settings", id="tab-settings"):
                yield SettingsTab(config_path=self.config_file)
        yield Static("Ready. [b]1-4[/b] Category  [b]/[/b] Search  [b]p[/b] Probe  [b]d[/b] Download  [b]r[/b] Dry Run  [b]q[/b] Quit", id="status-banner")
        yield Footer()

    def action_switch_tab(self, tab_id: str) -> None:
        """Switch active tab programmatically."""
        tabs = self.query_one("#main-tabs", TabbedContent)
        tabs.active = tab_id

    def action_focus_search(self) -> None:
        """Focus the search input bar directly."""
        self.action_switch_tab("tab-search")
        try:
            search_input = self.query_one("#search-input")
            search_input.focus()
        except Exception:
            pass

    def action_quick_category(self, category_name: str) -> None:
        """Quick switch category using numbers 1-4."""
        self.action_switch_tab("tab-search")
        try:
            search_tab = self.query_one(SearchTab)
            search_tab.switch_category_by_name(category_name)
        except Exception:
            pass

    def action_trigger_probe(self) -> None:
        """Trigger release probe via keyboard shortcut 'p'."""
        try:
            search_tab = self.query_one(SearchTab)
            search_tab.action_probe_releases()
        except Exception:
            pass

    def action_trigger_download(self) -> None:
        """Trigger download via keyboard shortcut 'd'."""
        try:
            search_tab = self.query_one(SearchTab)
            search_tab._dispatch_download(dry_run=False)
        except Exception:
            pass

    def action_trigger_dryrun(self) -> None:
        """Trigger dry run inspection via keyboard shortcut 'r'."""
        try:
            search_tab = self.query_one(SearchTab)
            search_tab._dispatch_download(dry_run=True)
        except Exception:
            pass

    def on_search_tab_trigger_download(self, message: SearchTab.TriggerDownload) -> None:
        """Handle download or dry-run requested from the Search Tab."""
        item = message.item_data
        eps = message.episodes
        res = message.resolution
        audio_pref = message.audio_preference
        cat = message.category
        prov = message.provider
        dry_run = message.dry_run
        selected_rel = message.selected_release

        # Switch to activity tab
        self.action_switch_tab("tab-downloads")
        downloads_tab = self.query_one(DownloadsTab)
        
        mode_label = "[bold magenta][DRY RUN][/bold magenta]" if dry_run else "[bold cyan][DOWNLOAD][/bold cyan]"
        title = item.get('title', item.get('raw_title', 'Unknown'))
        downloads_tab.log_message(f"{mode_label} Initiating task for [bold]{title}[/bold] | Category: {cat} | Provider: {prov} | Episodes: {eps} | Target: {res}")
        downloads_tab.update_task_metrics(
            status="[cyan]INITIALIZING[/cyan]",
            target=title,
            engine=f"{prov} ({cat})",
            progress_str="Starting workers...",
            percentage=10
        )

        self.execute_media_task(item, eps, res, audio_pref, cat, prov, dry_run, selected_rel)

    @work(exclusive=True, thread=True)
    def execute_media_task(self, item: dict, episodes_str: str, resolution: str, audio_preference: str, category: str, provider: str, dry_run: bool, selected_release: dict = None) -> None:
        """Background thread executing the resolution probing, inspection, and download."""
        downloads_tab = self.query_one(DownloadsTab)
        try:
            search_tab = self.query_one(SearchTab)
            client = search_tab.active_client

            if not client:
                cat_cfg = dict(self.config_data.get(category, {}) or {})
                from Core.provider_factory import create_client
                client = create_client(category, provider, cat_cfg, audio_preference=audio_preference)

            if not client:
                self.call_from_thread(downloads_tab.log_message, f"[red]Error: Client for '{provider}' could not be initialized.[/red]")
                self.call_from_thread(downloads_tab.update_task_metrics, status="[red]FAILED[/red]", progress_str="Client init failed")
                return

            if hasattr(client, 'audio_preference'):
                client.audio_preference = audio_preference

            title_clean = item.get('title', item.get('raw_title', 'Unknown'))
            series_title, episode_prefix = client.set_out_names(item)
            cat_cfg = dict(self.config_data.get(category, {}) or {})
            base_dir = os.path.expanduser(cat_cfg.get('download_dir', '~/Videos'))
            save_dir = os.path.join(base_dir, series_title)

            resolved_links = {}

            # Direct dispatch if selected_release from Release Matrix has a direct magnet or url
            if selected_release and (selected_release.get('magnet') or selected_release.get('url')):
                q_tag = selected_release.get('quality', resolution)
                dl_type = 'torrent' if selected_release.get('magnet') else 'stream'
                resolved_links[1] = {
                    'magnet': selected_release.get('magnet'),
                    'url': selected_release.get('url'),
                    'out_file': f"{series_title} [{q_tag}P].mkv",
                    'resolution': f"{q_tag}P",
                    'downloadType': dl_type,
                    'seeds': selected_release.get('seeds', 0),
                    'size': selected_release.get('size', 'Unknown')
                }
                self.call_from_thread(downloads_tab.log_message, f"[green]Release Matrix selection resolved directly: {q_tag}P ({dl_type.upper()})[/green]")
            else:
                self.call_from_thread(downloads_tab.log_message, f"[cyan]Fetching episodes & metadata for [bold]{title_clean}[/bold]...[/cyan]")
                episodes = client.fetch_episodes_list(item)
                
                if not episodes:
                    self.call_from_thread(downloads_tab.log_message, "[yellow]No episodes returned by provider.[/yellow]")
                    self.call_from_thread(downloads_tab.update_task_metrics, status="[yellow]NO EPISODES[/yellow]")
                    return

                self.call_from_thread(downloads_tab.log_message, f"[green]Discovered {len(episodes)} total item(s).[/green]")

                # Parse episode range
                target_eps = []
                range_dict = {'start': 1, 'end': 1, 'specific_no': [1]}

                if category == "Movies" or len(episodes) == 1:
                    target_eps = [episodes[0]]
                    ep_start = episodes[0].get('episode', 1)
                    range_dict = {'start': ep_start, 'end': ep_start, 'specific_no': [ep_start]}
                else:
                    ep_str_clean = episodes_str.strip().lower()
                    if ep_str_clean == "all":
                        target_eps = episodes
                        range_dict = {
                            'start': episodes[0].get('episode', 1),
                            'end': episodes[-1].get('episode', len(episodes)),
                            'specific_no': [e.get('episode', i) for i, e in enumerate(episodes, start=1)]
                        }
                    elif "-" in ep_str_clean:
                        parts = ep_str_clean.split("-", 1)
                        try:
                            s_num = int(parts[0].replace('s', '').replace('e', '').strip())
                            e_num = int(parts[1].replace('s', '').replace('e', '').strip())
                            target_eps = [e for i, e in enumerate(episodes, start=1) if s_num <= (e.get('episode') if isinstance(e.get('episode'), int) else i) <= e_num]
                            range_dict = {'start': s_num, 'end': e_num, 'specific_no': list(range(s_num, e_num + 1))}
                        except ValueError:
                            target_eps = [episodes[0]]
                    elif "," in ep_str_clean:
                        nums = [int(n.strip()) for n in ep_str_clean.split(",") if n.strip().isdigit()]
                        target_eps = [e for i, e in enumerate(episodes, start=1) if (e.get('episode') if isinstance(e.get('episode'), int) else i) in nums]
                        range_dict = {'start': min(nums or [1]), 'end': max(nums or [1]), 'specific_no': nums}
                    else:
                        try:
                            single_num = int(ep_str_clean)
                            target_eps = [e for i, e in enumerate(episodes, start=1) if (e.get('episode') if isinstance(e.get('episode'), int) else i) == single_num]
                            if not target_eps and 1 <= single_num <= len(episodes):
                                target_eps = [episodes[single_num - 1]]
                            range_dict = {'start': single_num, 'end': single_num, 'specific_no': [single_num]}
                        except ValueError:
                            target_eps = [episodes[0]]

                if not target_eps:
                    target_eps = [episodes[0]]

                self.call_from_thread(downloads_tab.log_message, f"[blue]Resolving links & streams for {len(target_eps)} episode(s)...[/blue]")
                target_ep_links = client.fetch_episode_links(target_eps, range_dict)
                if not target_ep_links:
                    self.call_from_thread(downloads_tab.log_message, "[red]Failed to resolve links for selected episodes.[/red]")
                    self.call_from_thread(downloads_tab.update_task_metrics, status="[red]LINK FAILED[/red]")
                    return

                resolved_links = client.fetch_m3u8_links(target_ep_links, resolution, episode_prefix)
                if not resolved_links:
                    self.call_from_thread(downloads_tab.log_message, "[red]Failed to resolve final download stream / magnet links.[/red]")
                    self.call_from_thread(downloads_tab.update_task_metrics, status="[red]MANIFEST FAILED[/red]")
                    return

            # Audio label
            audio_label = '🇯🇵 Sub (Original Japanese)'
            if audio_preference == 'dub':
                audio_label = '🇺🇸 English Dubbed (Dub)'
            elif audio_preference == 'dual':
                audio_label = '🌐 Dual Audio / Multi-Audio'

            first_item = next(iter(resolved_links.values()), {})
            dl_type = first_item.get('downloadType', 'stream').upper()
            res_label = first_item.get('resolution') or f"{resolution}P"

            # Pre-Download Inspection summary
            self.call_from_thread(downloads_tab.log_message, "\n[bold #38bdf8]╭── PRE-DOWNLOAD INSPECTION ───────────────────────────────────────────╮[/bold #38bdf8]")
            self.call_from_thread(downloads_tab.log_message, f"│ [bold]Series:[/bold]     [#38bdf8]{series_title}[/#38bdf8]")
            self.call_from_thread(downloads_tab.log_message, f"│ [bold]Category:[/bold]   {category}  •  [bold]Provider:[/bold] {provider}")
            self.call_from_thread(downloads_tab.log_message, f"│ [bold]Save Path:[/bold]  [#f59e0b]{save_dir}[/#f59e0b]")
            self.call_from_thread(downloads_tab.log_message, f"│ [bold]Resolution:[/bold][#34d399]{res_label}[/#34d399] ({dl_type})")
            if category == "Anime":
                self.call_from_thread(downloads_tab.log_message, f"│ [bold]Audio:[/bold]      {audio_label}")
            self.call_from_thread(downloads_tab.log_message, f"│ [bold]Queued:[/bold]     {len(resolved_links)} item(s) ready")
            self.call_from_thread(downloads_tab.log_message, "[bold #38bdf8]╰──────────────────────────────────────────────────────────────────────╯[/bold #38bdf8]\n")

            for ep_key, dl_meta in resolved_links.items():
                size_str = dl_meta.get('size', 'Unknown')
                seeds_str = f" | Seeds: {dl_meta.get('seeds')}" if dl_meta.get('seeds') is not None else ""
                out_name = dl_meta.get('out_file', dl_meta.get('episodeName', str(ep_key)))
                self.call_from_thread(downloads_tab.log_message, f"  • [bold]{out_name}[/bold] | [dim]{size_str}{seeds_str}[/dim]")

            if dry_run:
                self.call_from_thread(downloads_tab.update_task_metrics, status="[magenta]DRY RUN COMPLETE[/magenta]", target=series_title, engine=dl_type, progress_str=f"{len(resolved_links)} verified", percentage=100)
                self.call_from_thread(downloads_tab.log_message, "\n[bold magenta]✔ [DRY RUN] Inspection complete. No files downloaded.[/bold magenta]")
                self.call_from_thread(self.notify, "Dry run inspection complete!", severity="information")
            else:
                self.call_from_thread(downloads_tab.update_task_metrics, status="[yellow]DOWNLOADING[/yellow]", target=series_title, engine=dl_type, progress_str="Starting engine...", percentage=30)
                self.call_from_thread(downloads_tab.log_message, f"\n[bold green]⚡ Starting download process for {len(resolved_links)} file(s)...[/bold green]")
                
                # Execute Download
                from Core.provider_factory import get_downloader
                downloader_cls = get_downloader(category, dl_type)
                dl_config = dict(self.config_data.get('DownloaderConfig', {}) or {})
                dl_config['download_dir'] = save_dir
                
                os.makedirs(save_dir, exist_ok=True)
                downloader = downloader_cls(client, dl_config)
                
                total_items = len(resolved_links)
                for item_i, (ep_key, dl_data) in enumerate(resolved_links.items(), start=1):
                    try:
                        self.call_from_thread(downloads_tab.log_message, f"[cyan]Downloading ({item_i}/{total_items}): {dl_data.get('out_file')}...[/cyan]")
                        self.call_from_thread(downloads_tab.update_task_metrics, status=f"[yellow]ITEM {item_i}/{total_items}[/yellow]", progress_str=f"Downloading {dl_data.get('out_file', '')[:20]}", percentage=int((item_i / total_items) * 100))
                        
                        downloader.download(dl_data)
                        
                        # Record in history
                        from Core import history_manager
                        history_manager.init_db()
                        history_manager.add_history(
                            title=series_title,
                            episode=int(ep_key) if str(ep_key).isdigit() else 1,
                            season=1,
                            resolution=str(res_label),
                            provider=provider,
                            status='completed',
                            file_path=os.path.join(save_dir, dl_data.get('out_file', ''))
                        )
                        self.call_from_thread(downloads_tab.log_message, f"[bold green]✔ Successfully downloaded {dl_data.get('out_file')}[/bold green]")
                    except Exception as dl_err:
                        self.call_from_thread(downloads_tab.log_message, f"[bold red]✗ Failed to download {dl_data.get('out_file')}: {dl_err}[/bold red]")

                self.call_from_thread(downloads_tab.update_task_metrics, status="[green]COMPLETED[/green]", target=series_title, engine=dl_type, progress_str="100% Succeeded", percentage=100)
                self.call_from_thread(self.notify, "Download task completed!", severity="information")

        except Exception as e:
            self.call_from_thread(downloads_tab.update_task_metrics, status="[red]ERROR[/red]", progress_str=str(e)[:30])
            self.call_from_thread(downloads_tab.log_message, f"[bold red]Execution error: {e}[/bold red]")
            self.call_from_thread(self.notify, f"Error: {e}", severity="error")


def run_tui(config_file: str = "config_scraper.yaml") -> None:
    """Launch the MediaScraper TUI application."""
    app = MediaScraperTUI(config_file=config_file)
    app.run()


if __name__ == "__main__":
    run_tui()

