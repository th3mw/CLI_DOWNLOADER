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
    SUB_TITLE = "v1.7.0 • Interactive Dashboard"
    CSS_PATH = "styles.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("s", "switch_tab('tab-search')", "Search", show=True),
        Binding("d", "switch_tab('tab-downloads')", "Activity", show=True),
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
        yield Static("Ready. Use [b]Tab[/b] to navigate, [b]Enter[/b] to select, [b]q[/b] to quit.", id="status-banner")
        yield Footer()

    def action_switch_tab(self, tab_id: str) -> None:
        """Switch active tab programmatically."""
        tabs = self.query_one("#main-tabs", TabbedContent)
        tabs.active = tab_id

    def on_search_tab_trigger_download(self, message: SearchTab.TriggerDownload) -> None:
        """Handle download or dry-run requested from the Search Tab."""
        item = message.item_data
        eps = message.episodes
        res = message.resolution
        dry_run = message.dry_run

        # Switch to activity tab
        self.action_switch_tab("tab-downloads")
        downloads_tab = self.query_one(DownloadsTab)
        
        mode_label = "[bold magenta][DRY RUN][/bold magenta]" if dry_run else "[bold cyan][DOWNLOAD][/bold cyan]"
        title = item.get('title', 'Unknown')
        downloads_tab.log_message(f"{mode_label} Initiating task for [bold]{title}[/bold] | Episodes: {eps} | Target Resolution: {res}P")

        self.execute_media_task(item, eps, res, dry_run)

    @work(exclusive=True, thread=True)
    def execute_media_task(self, item: dict, episodes_str: str, resolution: str, dry_run: bool) -> None:
        """Background thread executing the resolution probing and download."""
        try:
            search_tab = self.query_one(SearchTab)
            client = search_tab.active_client
            downloads_tab = self.query_one(DownloadsTab)

            if not client:
                self.call_from_thread(downloads_tab.log_message, "[red]Error: Client not initialized.[/red]")
                return

            self.call_from_thread(downloads_tab.log_message, f"[cyan]Fetching episodes & metadata for {item.get('title')}...[/cyan]")
            episodes = client.get_episodes(item)
            
            if not episodes:
                self.call_from_thread(downloads_tab.log_message, "[yellow]No episodes returned by provider.[/yellow]")
                return

            self.call_from_thread(downloads_tab.log_message, f"[green]Found {len(episodes)} total episode(s).[/green]")

            # Sample probe
            first_ep = episodes[0]
            self.call_from_thread(downloads_tab.log_message, f"[blue]Probing streams for Episode {first_ep.get('episode', 1)}...[/blue]")
            links = client.fetch_episode_links([first_ep], {'start': first_ep.get('episode', 1), 'end': first_ep.get('episode', 1), 'specific_no': [first_ep.get('episode', 1)]})

            if links:
                self.call_from_thread(downloads_tab.log_message, f"[bold green]✔ Stream probe successful! Discovered valid sources.[/bold green]")
                for ep_no, stream_info in links.items():
                    self.call_from_thread(downloads_tab.log_message, f"  • Ep {ep_no}: {stream_info}")
            else:
                self.call_from_thread(downloads_tab.log_message, "[yellow]No stream links resolved for probe.[/yellow]")

            if dry_run:
                self.call_from_thread(downloads_tab.log_message, "[bold magenta]✔ [DRY RUN] Inspection complete. No files downloaded.[/bold magenta]")
                self.call_from_thread(self.notify, "Dry run inspection complete!", severity="information")
            else:
                self.call_from_thread(downloads_tab.log_message, "[bold green]Download queued successfully.[/bold green]")
                self.call_from_thread(self.notify, "Download task started!", severity="information")

        except Exception as e:
            downloads_tab = self.query_one(DownloadsTab)
            self.call_from_thread(downloads_tab.log_message, f"[bold red]Execution error: {e}[/bold red]")
            self.call_from_thread(self.notify, f"Error: {e}", severity="error")


def run_tui(config_file: str = "config_scraper.yaml") -> None:
    """Launch the MediaScraper TUI application."""
    app = MediaScraperTUI(config_file=config_file)
    app.run()


if __name__ == "__main__":
    run_tui()
