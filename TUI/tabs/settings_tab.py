"""
Settings & Configuration Tab for CLI Media Scraper TUI.
Allows visual inspection and modification of config_scraper.yaml.
"""

import os
import yaml
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Static, Input, Button, Select, Switch, Label

from Core.commons import load_yaml


class SettingsTab(Static):
    """Configuration management tab."""

    def __init__(self, config_path: str = 'config_scraper.yaml', **kwargs):
        super().__init__(**kwargs)
        self.config_path = config_path
        self.config_data = load_yaml(config_path) or {}

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="settings-container"):
            yield Label("📁 Download Directories", classes="settings-section-title")
            
            with Horizontal(classes="settings-row"):
                yield Label("Anime Path:", classes="settings-label")
                anime_dir = self.config_data.get('Anime', {}).get('download_dir', '~/Videos/Anime')
                yield Input(value=str(anime_dir), id="input-anime-dir", classes="settings-input")

            with Horizontal(classes="settings-row"):
                yield Label("Movies Path:", classes="settings-label")
                movies_dir = self.config_data.get('Movies', {}).get('download_dir', '~/Videos/Movies')
                yield Input(value=str(movies_dir), id="input-movies-dir", classes="settings-input")

            with Horizontal(classes="settings-row"):
                yield Label("TV Shows Path:", classes="settings-label")
                tv_dir = self.config_data.get('TV Shows', {}).get('download_dir', '~/Videos/Series')
                yield Input(value=str(tv_dir), id="input-tv-dir", classes="settings-input")

            with Horizontal(classes="settings-row"):
                yield Label("NSFW Path:", classes="settings-label")
                nsfw_dir = self.config_data.get('Hentai (NSFW)', {}).get('download_dir', '~/Videos/Anime/Hentai (NSFW)')
                yield Input(value=str(nsfw_dir), id="input-nsfw-dir", classes="settings-input")

            yield Label("⚡ Engines & Preferences", classes="settings-section-title")

            with Horizontal(classes="settings-row"):
                yield Label("Torrent Client:", classes="settings-label")
                tc_val = self.config_data.get('DownloaderConfig', {}).get('torrent_client', 'auto')
                tc_options = [
                    ("Auto (aria2 if present, else desktop client)", "auto"),
                    ("aria2 (In-Terminal Downloader)", "aria2"),
                    ("System Desktop Client (FDM, qBittorrent, etc.)", "system"),
                ]
                yield Select(tc_options, value=tc_val, id="select-torrent-client", allow_blank=False)

            with Horizontal(classes="settings-row"):
                yield Label("Default Audio:", classes="settings-label")
                audio_val = self.config_data.get('AudioPreference', {}).get('default_audio', 'sub')
                audio_options = [
                    ("Sub (Original Japanese Audio)", "sub"),
                    ("Dub (English Dubbed Audio)", "dub"),
                    ("Dual (Dual Audio Preferred)", "dual"),
                ]
                yield Select(audio_options, value=audio_val, id="select-audio-pref", allow_blank=False)

            with Horizontal(classes="settings-row"):
                yield Label("Max Parallel Downloads:", classes="settings-label")
                max_p = str(self.config_data.get('DownloaderConfig', {}).get('max_parallel_downloads', 2))
                yield Input(value=max_p, id="input-max-parallel", classes="settings-input")

            yield Label("🗜 Post-Processing & Compression", classes="settings-section-title")

            with Horizontal(classes="settings-row"):
                yield Label("Auto-Compress Video:", classes="settings-label")
                compress_active = bool(self.config_data.get('PostProcessing', {}).get('auto_compress', False))
                yield Switch(value=compress_active, id="switch-auto-compress")

            with Horizontal(classes="settings-row"):
                yield Label("Encoder Codec:", classes="settings-label")
                codec_val = self.config_data.get('PostProcessing', {}).get('codec', 'hevc')
                codec_options = [("HEVC / H.265 (High Efficiency)", "hevc"), ("AV1 (Next-Gen)", "av1"), ("H.264 / AVC (Legacy)", "h264")]
                yield Select(codec_options, value=codec_val, id="select-codec", allow_blank=False)

            yield Button("💾 Save Settings", variant="success", id="btn-save-settings")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save-settings":
            self.save_settings()

    def save_settings(self) -> None:
        """Persist updated settings back to YAML configuration file."""
        try:
            # Download paths
            if 'Anime' not in self.config_data: self.config_data['Anime'] = {}
            self.config_data['Anime']['download_dir'] = self.query_one("#input-anime-dir", Input).value.strip()

            if 'Movies' not in self.config_data: self.config_data['Movies'] = {}
            self.config_data['Movies']['download_dir'] = self.query_one("#input-movies-dir", Input).value.strip()

            if 'TV Shows' not in self.config_data: self.config_data['TV Shows'] = {}
            self.config_data['TV Shows']['download_dir'] = self.query_one("#input-tv-dir", Input).value.strip()

            if 'Hentai (NSFW)' not in self.config_data: self.config_data['Hentai (NSFW)'] = {}
            self.config_data['Hentai (NSFW)']['download_dir'] = self.query_one("#input-nsfw-dir", Input).value.strip()

            # Engine & Audio
            if 'DownloaderConfig' not in self.config_data: self.config_data['DownloaderConfig'] = {}
            self.config_data['DownloaderConfig']['torrent_client'] = str(self.query_one("#select-torrent-client", Select).value)
            
            try:
                max_p = int(self.query_one("#input-max-parallel", Input).value.strip())
                self.config_data['DownloaderConfig']['max_parallel_downloads'] = max_p
            except ValueError:
                pass

            if 'AudioPreference' not in self.config_data: self.config_data['AudioPreference'] = {}
            self.config_data['AudioPreference']['default_audio'] = str(self.query_one("#select-audio-pref", Select).value)

            # Compression
            if 'PostProcessing' not in self.config_data: self.config_data['PostProcessing'] = {}
            self.config_data['PostProcessing']['auto_compress'] = self.query_one("#switch-auto-compress", Switch).value
            self.config_data['PostProcessing']['codec'] = str(self.query_one("#select-codec", Select).value)

            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.config_data, f, default_flow_style=False, sort_keys=False)

            self.app.notify("Configuration saved successfully!", severity="information")
        except Exception as e:
            self.app.notify(f"Failed to save settings: {e}", severity="error")
