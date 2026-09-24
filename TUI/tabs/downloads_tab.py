"""
Active Downloads & Live Activity Tab for CLI Media Scraper TUI.
"""

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, RichLog, Label, ProgressBar, Button


class DownloadsTab(Static):
    """Active downloads and activity log tab."""

    def compose(self) -> ComposeResult:
        with Vertical(id="downloads-root"):
            yield Label("⚡ Active Activity & Download Log", classes="settings-section-title")
            yield RichLog(id="log-viewer", highlight=True, markup=True)

    def log_message(self, message: str) -> None:
        """Write formatted message to log viewer."""
        try:
            viewer = self.query_one("#log-viewer", RichLog)
            viewer.write(message)
        except Exception:
            pass
