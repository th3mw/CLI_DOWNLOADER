import os
import shutil
import subprocess
import sys
import time

from Core.BaseDownloader import BaseDownloader
from Core.commons import colprint, render_box


class TorrentDownloader(BaseDownloader):
    '''
    Dedicated downloader engine for BitTorrent / Magnet links.
    - Uses aria2c for high-speed terminal downloading with live seeds, peers, and speed metrics.
    - Automatically opens default desktop torrent clients (qBittorrent/Transmission) via xdg-open if aria2c is not found.
    '''
    def __init__(self, dl_config, ep_details):
        super().__init__(dl_config, ep_details)
        self.aria_path = shutil.which('aria2c')

    def start_download(self, magnet_link):
        self._create_out_dirs()
        title = self.ep_details.get('title', 'Movie')
        quality = self.ep_details.get('resolution', '1080p')
        size = self.ep_details.get('size', 'Unknown')
        seeds = self.ep_details.get('seeds', 'N/A')
        peers = self.ep_details.get('peers', 'N/A')

        if self.aria_path:
            colprint('header', f"\n  ➜ Launching aria2c BitTorrent Downloader...")
            colprint('predefined', f"  [Seeds: {seeds} | Peers: {peers} | Size: {size}]")

            cmd = [
                self.aria_path,
                magnet_link,
                '--seed-time=0',
                '--summary-interval=1',
                f'--dir={self.out_dir}',
                '--max-connection-per-server=16',
                '--enable-dht=true',
                '--dht-listen-port=6881-6999',
                '--file-allocation=none',
                '--console-log-level=warn',
                '--download-result=hide'
            ]

            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=sys.stdout,
                    stderr=sys.stderr,
                    text=True
                )
                proc.wait()
                if proc.returncode == 0:
                    return 0, 'Download complete'
                else:
                    return proc.returncode, f"aria2c exited with code {proc.returncode}"
            except KeyboardInterrupt:
                proc.terminate()
                return 1, 'Download aborted by user'
            except Exception as e:
                return 1, str(e)

        # Fallback if aria2c is not installed
        card_lines = [
            f"Movie: {title} [{quality}]",
            f"Size: {size} • Seeds: {seeds} • Peers: {peers}",
            "",
            "ℹ️  To download directly in terminal at max speed, install aria2:",
            "    Debian/Ubuntu:  sudo apt install aria2",
            "    Arch Linux:     sudo pacman -S aria2",
            "    Fedora:         sudo dnf install aria2",
            "",
            "🔗 Magnet Link (click or copy into your torrent client):",
            f"{magnet_link[:100]}..."
        ]
        print('\n' + render_box('MAGNET LINK READY', card_lines))

        # Attempt to launch system default torrent client via xdg-open
        try:
            if shutil.which('xdg-open'):
                subprocess.Popen(['xdg-open', magnet_link], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                colprint('results', "  [✓] Sent magnet link to default system torrent client (xdg-open).")
        except Exception:
            pass

        return 0, 'Magnet link delivered'
