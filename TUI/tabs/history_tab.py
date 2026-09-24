"""
History and Incomplete Downloads Tab for CLI Media Scraper TUI.
Allows browsing download history, tracking statuses, and resuming interrupted jobs.
"""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static, Button, DataTable, Select, Label

from Core import history_manager


class HistoryTab(Static):
    """History and resume management tab."""

    def compose(self) -> ComposeResult:
        with Vertical(id="history-root"):
            # Header filter controls
            with Horizontal(id="history-controls", classes="search-row"):
                yield Label("Filter Status: ")
                status_options = [
                    ("All Records", "all"),
                    ("Completed", "completed"),
                    ("In Progress", "in_progress"),
                    ("Failed", "failed"),
                ]
                yield Select(status_options, value="all", id="history-filter-select", allow_blank=False)
                yield Button("🔄 Refresh", id="btn-refresh-history", variant="default")
                yield Button("🗑 Clear History", id="btn-clear-history", variant="error")

            # History Data Table
            with Vertical(id="history-table-container"):
                yield DataTable(id="history-table", cursor_type="row")

            with Horizontal(classes="history-btn-row"):
                yield Button("▶ Resume Selected Download", variant="primary", id="btn-resume-selected", disabled=True)

    def on_mount(self) -> None:
        """Initialize columns and load history records."""
        table = self.query_one("#history-table", DataTable)
        table.add_columns("ID", "Title", "Season/Ep", "Resolution", "Provider", "Status", "Created At")
        self.reload_history()

    def reload_history(self) -> None:
        """Fetch records from sqlite and populate the table."""
        try:
            history_manager.init_db()
            filter_val = str(self.query_one("#history-filter-select", Select).value)
            status_arg = None if filter_val == "all" else filter_val
            records = history_manager.get_history(limit=100, status=status_arg)

            table = self.query_one("#history-table", DataTable)
            table.clear()

            for r in records:
                s_ep = f"S{r['season']:02d}E{r['episode']:02d}" if r['season'] else f"Ep {r['episode']}"
                status_str = r['status'] or 'unknown'
                
                # Color code status
                if status_str == 'completed':
                    status_badge = "[bold green]COMPLETED[/bold green]"
                elif status_str == 'failed':
                    status_badge = "[bold red]FAILED[/bold red]"
                elif status_str == 'in_progress':
                    status_badge = "[bold yellow]IN PROGRESS[/bold yellow]"
                else:
                    status_badge = status_str

                table.add_row(
                    str(r['id']),
                    r['title'],
                    s_ep,
                    str(r['resolution'] or 'N/A'),
                    str(r['provider'] or 'N/A'),
                    status_badge,
                    str(r['created_at'])[:16],
                    key=str(r['id'])
                )
        except Exception as e:
            self.app.notify(f"Failed to load history: {e}", severity="error")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "history-filter-select":
            self.reload_history()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-refresh-history":
            self.reload_history()
            self.app.notify("History refreshed!", severity="information")
        elif event.button.id == "btn-clear-history":
            history_manager.clear_history()
            self.reload_history()
            self.app.notify("History records cleared.", severity="warning")
        elif event.button.id == "btn-resume-selected":
            self.app.notify("Resume handler invoked for selected job.", severity="information")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.query_one("#btn-resume-selected", Button).disabled = False
