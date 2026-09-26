"""
Active Downloads & Live Activity Tab for CLI Media Scraper TUI.
Provides real-time task progress, engine indicators, speed counters,
and syntax-highlighted streaming activity logs.
"""

from datetime import datetime
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, RichLog, Label, ProgressBar, Button


class DownloadsTab(Static):
    """Active downloads and activity log tab."""

    def compose(self) -> ComposeResult:
        with Vertical(id="downloads-root"):
            # Header Metrics Panel
            with Vertical(id="downloads-summary-panel"):
                yield Label("⚡ Active Activity & Engine Status", classes="pane-title")
                with Horizontal(id="downloads-metrics-row"):
                    with Vertical(classes="metric-card"):
                        yield Label("STATUS", classes="metric-label")
                        yield Static("IDLE / READY", id="metric-status-val", classes="metric-value")

                    with Vertical(classes="metric-card"):
                        yield Label("TARGET ITEM", classes="metric-label")
                        yield Static("None Selected", id="metric-target-val", classes="metric-value")

                    with Vertical(classes="metric-card"):
                        yield Label("DOWNLOAD ENGINE", classes="metric-label")
                        yield Static("HLS / Torrent", id="metric-engine-val", classes="metric-value")

                    with Vertical(classes="metric-card"):
                        yield Label("PROGRESS", classes="metric-label")
                        yield Static("0% (0.0 MB/s)", id="metric-progress-val", classes="metric-value")

                yield ProgressBar(id="task-progress-bar", total=100, show_eta=True, classes="task-progress")

            # Real-Time Log Viewer
            yield Label("📜 Real-Time Execution Log", classes="pane-title")
            yield RichLog(id="log-viewer", highlight=True, markup=True)

    def update_task_metrics(self, status: str = None, target: str = None, engine: str = None, progress_str: str = None, percentage: float = None) -> None:
        """Update the metrics cards dynamically."""
        if status:
            self.query_one("#metric-status-val", Static).update(status)
        if target:
            self.query_one("#metric-target-val", Static).update(target[:30])
        if engine:
            self.query_one("#metric-engine-val", Static).update(engine)
        if progress_str:
            self.query_one("#metric-progress-val", Static).update(progress_str)
        if percentage is not None:
            p_bar = self.query_one("#task-progress-bar", ProgressBar)
            p_bar.progress = min(100.0, max(0.0, percentage))

    def log_message(self, message: str) -> None:
        """Write formatted message with timestamp to log viewer."""
        try:
            viewer = self.query_one("#log-viewer", RichLog)
            time_tag = f"[#8b949e]{datetime.now().strftime('%H:%M:%S')}[/#8b949e]"
            viewer.write(f"{time_tag} {message}")
        except Exception:
            pass

