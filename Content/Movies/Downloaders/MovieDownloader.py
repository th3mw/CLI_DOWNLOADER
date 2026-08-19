import os
import sys
import time
import requests
from urllib.parse import quote
from shutil import rmtree

from Core.commons import colprint, exec_os_cmd, retry, PRINT_THEMES, DISPLAY_COLORS, pretty_time
from Core.BaseDownloader import BaseDownloader, ProgressBar, _sort_subtitles_english_first
from Content.Anime.Downloaders.HLSDownloader import HLSDownloader


class MovieDownloader(BaseDownloader):
    '''
    Dedicated downloader for full-length movies.
    Supports:
    - High-speed direct streaming with live download speed (MB/s) and ETA.
    - Resumable partial file downloads via HTTP Range headers.
    - Seamless HLS m3u8 fallback for HLS movie sources.
    - FFmpeg container packaging to MKV with forced English subtitles.
    '''
    def __init__(self, dl_config, ep_details):
        super().__init__(dl_config, ep_details)
        self.stream_chunk_size = 1024 * 1024  # 1MB buffer for fast streaming

    def _download_direct_stream(self, dl_link, out_file_path):
        '''
        Download direct HTTP/HTTPS media file using stream chunking with resume support.
        '''
        part_file_path = f"{out_file_path}.part"
        existing_bytes = os.path.getsize(part_file_path) if os.path.isfile(part_file_path) else 0

        headers = self.req_session.headers.copy()
        if self.referer_link:
            headers['Referer'] = self.referer_link

        # Check total file size via HEAD request
        total_size = 0
        try:
            head_resp = self.req_session.head(dl_link, headers=headers, timeout=self.request_timeout, allow_redirects=True)
            if head_resp.status_code == 200:
                total_size = int(head_resp.headers.get('content-length', 0))
        except Exception:
            pass

        # If partial file exists and server supports Range, resume download
        if existing_bytes > 0:
            if total_size and existing_bytes >= total_size:
                # File already fully downloaded to part file
                os.replace(part_file_path, out_file_path)
                return True
            headers['Range'] = f"bytes={existing_bytes}-"
            self.logger.info(f"Resuming movie download from byte {existing_bytes} / {total_size}...")

        theme = PRINT_THEMES['results'] if DISPLAY_COLORS else ''
        progress_bar = ProgressBar(
            total=total_size if total_size > 0 else 100,
            desc=f"Downloading Movie",
            unit='B',
            unit_scale=True,
            unit_divisor=1024,
            bar_format=theme + '{l_bar}{bar}' + theme + '{r_bar}'
        )

        if existing_bytes > 0:
            progress_bar.update(existing_bytes)

        open_mode = 'ab' if existing_bytes > 0 else 'wb'

        with self.req_session.get(dl_link, headers=headers, stream=True, timeout=self.request_timeout) as resp:
            if resp.status_code not in [200, 206]:
                raise Exception(f"Failed with response code: {resp.status_code}")

            if total_size == 0:
                content_len = resp.headers.get('content-length')
                if content_len:
                    total_size = existing_bytes + int(content_len)
                    progress_bar.total = total_size

            with open(part_file_path, open_mode) as f:
                for chunk in resp.iter_content(chunk_size=self.stream_chunk_size):
                    if chunk:
                        f.write(chunk)
                        progress_bar.update(len(chunk))

        progress_bar.close()

        # Rename .part to final destination
        if os.path.isfile(part_file_path):
            os.replace(part_file_path, out_file_path)
            return True
        return False

    def start_download(self, dl_link):
        self._create_out_dirs()
        out_file_path = os.path.join(self.out_dir, self.out_file)

        # Check if source is HLS m3u8
        is_hls = (self.download_type == 'hls') or ('.m3u8' in dl_link.lower())
        
        if is_hls:
            self.logger.debug(f'Movie source is HLS: delegating to HLSDownloader engine for {dl_link}')
            hls_dl = HLSDownloader({
                'download_dir': self.out_dir,
                'temp_dir': self.parent_temp_dir,
                'concurrency_per_file': self.concurrency,
                'request_timeout': self.request_timeout,
                'use_http_client': self.use_http_client
            }, self.ep_details)
            hls_dl.start_download(dl_link)
            return

        # Direct HTTP Stream Download
        self.logger.info(f"Starting direct movie download: {dl_link} -> {out_file_path}")
        self._download_direct_stream(dl_link, out_file_path)

        # Process Subtitles if present
        if self.subtitles:
            self.logger.debug('Downloading movie subtitles')
            self._download_subtitles()
            self.logger.debug('Muxing subtitles into movie container')
            self._add_subtitles()

        # Cleanup temporary files
        self._remove_out_dirs()
