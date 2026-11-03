import os
import platform
import re
import shutil
import subprocess
import sys
import webbrowser

from Core.BaseDownloader import BaseDownloader
from Core.commons import colprint, render_box
from Core.aria2_provisioner import get_aria2_path


class TorrentDownloader(BaseDownloader):
    '''
    Dedicated cross-platform downloader engine for BitTorrent / Magnet links.
    - Respects 'torrent_client' config: 'aria2' (in-terminal), 'system' (FDM/qBittorrent), or 'auto'.
    - If aria2 is selected or auto: Uses system aria2c or auto-provisions bundled static binary.
    - If system client is selected: Directly opens default desktop app via OS URI handler.
    - Supports selective episode / file downloading for complete season packs.
    '''
    def __init__(self, dl_config, ep_details):
        super().__init__(dl_config, ep_details)
        self.torrent_client_pref = str(dl_config.get('torrent_client', 'auto')).lower().strip()
        self.dl_config = dl_config

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

    def _parse_selected_indices(self, raw_input, max_index):
        '''Parse user input into comma-separated 1-based indices for --select-file'''
        if not raw_input or str(raw_input).strip().lower() in ('all', ''):
            return None
        selected = set()
        for part in str(raw_input).replace(' ', '').split(','):
            if '-' in part:
                tokens = part.split('-', 1)
                try:
                    s = int(tokens[0]) if tokens[0] else 1
                    e = int(tokens[1]) if tokens[1] else max_index
                    for i in range(min(s, e), max(s, e) + 1):
                        if 1 <= i <= max_index:
                            selected.add(i)
                except ValueError:
                    continue
            elif part.isdigit():
                i = int(part)
                if 1 <= i <= max_index:
                    selected.add(i)

        if not selected or len(selected) == max_index:
            return None
        return ','.join(map(str, sorted(selected)))

    def _probe_aria2_files(self, aria_path, magnet_link):
        '''Probe files inside magnet link using aria2c -S'''
        cmd = [
            aria_path,
            magnet_link,
            '-S',
            '--bt-metadata-only=true',
            '--bt-stop-timeout=15',
            '--console-log-level=error'
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=18)
            files = []
            for line in res.stdout.split('\n'):
                m = re.match(r'^\s*(\d+)\|(.+?)\|(.+)$', line)
                if m:
                    idx = int(m.group(1))
                    path = m.group(2).strip()
                    size = m.group(3).strip()
                    files.append({'index': idx, 'name': path, 'size': size})
            return files
        except Exception:
            return []

    def start_download(self, magnet_link):
        self._create_out_dirs()
        title = self.ep_details.get('series_title') or self.ep_details.get('title', 'Content')
        quality = self.ep_details.get('resolution', '1080p')
        size = self.ep_details.get('size', 'Unknown')
        seeds = self.ep_details.get('seeds', 'N/A')
        peers = self.ep_details.get('peers', 'N/A')
        is_season_pack = self.ep_details.get('is_season_pack', False)
        season_num = self.ep_details.get('season', 1)

        content_label = f"Season {season_num} Complete Pack" if is_season_pack else ("Series" if self.ep_details.get('type') == 'tv' else "Movie")

        # 1. Direct System Desktop App Mode (FDM, qBittorrent, Transmission)
        if self.torrent_client_pref in ('system', 'desktop', 'fdm', 'qbittorrent'):
            card_lines = [
                f"{content_label}: {title} [{quality}]",
                f"Size: {size} • Seeds: {seeds} • Peers: {peers}",
                "",
                "🔗 Magnet Link sent to your default desktop torrent client.",
                f"{magnet_link[:100]}..."
            ]
            print('\n' + render_box('DESKTOP TORRENT CLIENT', card_lines))
            opened = self._open_in_system_client(magnet_link)
            if opened:
                colprint('results', "  [✓] Sent magnet link to default system torrent client.")
            else:
                colprint('results', "  [✓] Magnet ready. Copy the link into your torrent client.")
            return 0, 'Sent to desktop torrent client'

        # 2. In-Terminal / Auto Mode with aria2c
        aria_path = get_aria2_path(auto_provision=True)

        if aria_path:
            # Check for selective file download in season pack
            select_file_arg = None
            torrent_files = self.ep_details.get('torrent_files')

            # If season pack and files not pre-cached, attempt quick probe
            if is_season_pack and not torrent_files:
                colprint('header', f"\n  ➜ Inspecting Torrent file hierarchy...")
                torrent_files = self._probe_aria2_files(aria_path, magnet_link)

            # Interactive file selection prompt if multi-file pack
            if torrent_files and len(torrent_files) > 1:
                file_lines = []
                for f in torrent_files:
                    f_idx = f.get('index', 1)
                    f_name = f.get('name', 'Episode')
                    f_size = f.get('size', '')
                    size_tag = f" • {f_size}" if f_size else ""
                    file_lines.append(f"  \033[1m[{f_idx}]\033[0m  \033[38;5;39m{f_name}\033[0m\033[38;5;244m{size_tag}\033[0m")

                box_title = f"SEASON {season_num} EPISODE LIST ({len(torrent_files)} items)"
                print('\n' + render_box(box_title, file_lines))

                try:
                    user_sel = input(f"\n  ➜ Select episodes to download (e.g. 1-{len(torrent_files)} or 1,3,5) [default=all]: ").strip()
                except (KeyboardInterrupt, EOFError):
                    print()
                    user_sel = 'all'

                selected_indices = self._parse_selected_indices(user_sel, len(torrent_files))
                if selected_indices:
                    select_file_arg = f"--select-file={selected_indices}"
                    colprint('predefined', f"  [✓] Downloading selected episode indices: {selected_indices}")
                else:
                    colprint('results', "  [✓] Downloading all episodes in season pack.")

            colprint('header', f"\n  ➜ Launching aria2c BitTorrent Downloader...")
            colprint('predefined', f"  [Seeds: {seeds} | Peers: {peers} | Size: {size}]")

            cmd = [
                aria_path,
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
            if select_file_arg:
                cmd.append(select_file_arg)

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

        # 3. Fallback if aria2c cannot be provisioned or run
        card_lines = [
            f"{content_label}: {title} [{quality}]",
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
