import os
import platform
import shutil
import subprocess
import sys
import webbrowser

from Core.BaseDownloader import BaseDownloader
from Core.commons import colprint, render_box


class TorrentDownloader(BaseDownloader):
    '''
    Dedicated cross-platform downloader engine for BitTorrent / Magnet links.
    - If aria2c is installed: Downloads directly in the terminal with live speeds, seeds/peers, and auto-quits.
    - If aria2c is not installed: Seamlessly delegates to the system's default torrent client (FDM, qBittorrent,
      Transmission, etc.) across Windows, macOS, and Linux via native system handlers.
    '''
    def __init__(self, dl_config, ep_details):
        super().__init__(dl_config, ep_details)
        self.aria_path = shutil.which('aria2c')

    def _open_in_system_client(self, magnet_link):
        '''Cross-platform launcher for default OS magnet handler'''
        os_name = platform.system()
        try:
            if os_name == 'Windows':
                os.startfile(magnet_link)
                return True
            elif os_name == 'Darwin':  # macOS
                subprocess.Popen(['open', magnet_link], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            elif os_name == 'Linux':
                if shutil.which('xdg-open'):
                    subprocess.Popen(['xdg-open', magnet_link], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return True
            
            # Universal fallback
            return webbrowser.open(magnet_link)
        except Exception:
            return False

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
                '--summary-interval=0',
                f'--dir={self.out_dir}',
                '--max-connection-per-server=16',
                '--enable-dht=true',
                '--dht-listen-port=6881-6999',
                '--file-allocation=none',
                '--console-log-level=error',
                '--download-result=hide',
                '--show-console-readout=true'
            ]

            try:
                proc = subprocess.Popen(
                    cmd,
                    stdin=None,
                    stdout=None,
                    stderr=None
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

        # Instructions & fallback if aria2c is not found
        card_lines = [
            f"Movie: {title} [{quality}]",
            f"Size: {size} • Seeds: {seeds} • Peers: {peers}",
            "",
            "ℹ️  To download directly inside your terminal at max speed, install aria2:",
            "    Linux:    sudo apt install aria2  (or pacman -S aria2 / dnf install aria2)",
            "    macOS:    brew install aria2",
            "    Windows:  winget install aria2  (or choco install aria2)",
            "",
            "🔗 Magnet Link (click to open or copy):",
            f"{magnet_link[:120]}..."
        ]
        print('\n' + render_box('MAGNET LINK READY', card_lines))

        opened = self._open_in_system_client(magnet_link)
        if opened:
            colprint('results', "  [✓] Sent magnet link to default system torrent client.")
        else:
            colprint('results', "  [✓] Magnet link generated. Copy the link above into your torrent client.")

        return 0, 'Magnet link delivered'
