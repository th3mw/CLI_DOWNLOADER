import http.client
import logging
import os
import re
import requests
import sys
import threading
import time
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed
from shutil import rmtree
from Core.commons import colprint, exec_os_cmd, retry, PRINT_THEMES, DISPLAY_COLORS


class ProgressBar:
    '''
    Built-in full-featured progress bar supporting single and multi-line concurrent progress reporting.
    Provides identical API to tqdm without requiring external packages.
    '''
    _lock = threading.RLock()
    _active_bars = []
    _lines_rendered = 0

    def __init__(self, total=100, desc='Downloading', unit='seg', unit_scale=False, unit_divisor=1024, bar_format=None, **kwargs):
        self.total = max(1, total) if total else 0
        self.desc = desc or ''
        self.unit = unit or ''
        self.unit_scale = unit_scale
        self.unit_divisor = unit_divisor
        self.n = 0
        self.postfix = ''
        self.start_time = time.time()
        self.last_render_time = 0
        self.bar_width = 25
        self.theme = PRINT_THEMES.get('results', '\033[94m') if DISPLAY_COLORS else ''
        self.reset = PRINT_THEMES.get('reset', '\033[0m') if DISPLAY_COLORS else ''

    def __enter__(self):
        self.start_time = time.time()
        with ProgressBar._lock:
            if self not in ProgressBar._active_bars:
                ProgressBar._active_bars.append(self)
            ProgressBar._redraw_all()
        return self

    def __exit__(self, *args):
        with ProgressBar._lock:
            if ProgressBar._lines_rendered > 1:
                sys.stdout.write(f'\033[{ProgressBar._lines_rendered}A')
                final_str = self._format_line(force=True)
                sys.stdout.write(f'\r\033[K{final_str}\n')
                if self in ProgressBar._active_bars:
                    ProgressBar._active_bars.remove(self)
                for bar in ProgressBar._active_bars:
                    sys.stdout.write(f'\r\033[K{bar._format_line()}\n')
                ProgressBar._lines_rendered = len(ProgressBar._active_bars)
            elif ProgressBar._lines_rendered == 1:
                final_str = self._format_line(force=True)
                sys.stdout.write(f'\r\033[K{final_str}\n')
                if self in ProgressBar._active_bars:
                    ProgressBar._active_bars.remove(self)
                ProgressBar._lines_rendered = 0
            else:
                final_str = self._format_line(force=True)
                sys.stdout.write(f'\r\033[K{final_str}\n')
                if self in ProgressBar._active_bars:
                    ProgressBar._active_bars.remove(self)
            sys.stdout.flush()

    def set_postfix_str(self, s, refresh=True):
        self.postfix = f', {s}' if s else ''
        if refresh:
            with ProgressBar._lock:
                ProgressBar._redraw_all()

    def _fmt_size(self, val):
        if not self.unit_scale:
            return f'{val:.0f}' if isinstance(val, float) else f'{val}'
        for u in ['B', 'KB', 'MB', 'GB', 'TB']:
            if val < self.unit_divisor or u == 'TB':
                return f'{val:.1f}{u}'
            val /= self.unit_divisor
        return f'{val:.1f}B'

    def _fmt_time(self, seconds):
        if seconds is None or seconds < 0 or seconds > 86400:
            return '--:--'
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f'{h:02d}:{m:02d}:{s:02d}' if h else f'{m:02d}:{s:02d}'

    def update(self, n=1):
        self.n += n
        now = time.time()
        if now - self.last_render_time >= 0.05 or self.n >= self.total:
            self.last_render_time = now
            with ProgressBar._lock:
                ProgressBar._redraw_all()

    def _format_line(self, force=False):
        now = time.time()
        elapsed = max(0.001, now - self.start_time)
        rate = self.n / elapsed if elapsed > 0.05 else 0

        # Format download speed / rate
        if self.unit_scale:
            rate_str = f'{self._fmt_size(rate)}/s'
        else:
            rate_str = f'{rate:.1f}{self.unit}/s' if self.unit else f'{rate:.1f}/s'

        c_desc = PRINT_THEMES.get('primary', '\033[38;5;39m') if DISPLAY_COLORS else ''
        c_bar = PRINT_THEMES.get('success', '\033[38;5;82m') if DISPLAY_COLORS else ''
        c_pct = PRINT_THEMES.get('bold', '\033[1m') if DISPLAY_COLORS else ''
        c_rate = PRINT_THEMES.get('warning', '\033[38;5;220m') if DISPLAY_COLORS else ''
        c_eta = PRINT_THEMES.get('secondary', '\033[38;5;141m') if DISPLAY_COLORS else ''
        c_muted = PRINT_THEMES.get('muted', '\033[38;5;244m') if DISPLAY_COLORS else ''
        c_reset = PRINT_THEMES.get('reset', '\033[0m') if DISPLAY_COLORS else ''

        if self.total > 0:
            pct = min(100, int((self.n / self.total) * 100))
            eta = ((self.total - self.n) / rate) if (rate > 0 and self.n < self.total) else 0
            eta_str = self._fmt_time(eta)
            filled = min(self.bar_width, int(self.bar_width * self.n / self.total))
            tail = '╸' if (filled < self.bar_width and pct > 0) else ''
            unfilled = max(0, self.bar_width - filled - len(tail))
            bar = '━' * filled + tail + '─' * unfilled
            n_str = self._fmt_size(self.n) if self.unit_scale else f'{self.n}'
            tot_str = self._fmt_size(self.total) if self.unit_scale else f'{self.total}'
            unit_suffix = f' {self.unit}' if (self.unit and not self.unit_scale) else ''
            return f'  {c_desc}{self.desc}{c_reset} {c_bar}{bar}{c_reset} {c_pct}{pct:3d}%{c_reset} {c_muted}•{c_reset} {n_str}/{tot_str}{unit_suffix} {c_muted}•{c_reset} {c_rate}{rate_str}{c_reset} {c_muted}•{c_reset} {c_eta}ETA {eta_str}{c_reset} {c_muted}{self.postfix}{c_reset}'
        else:
            n_str = self._fmt_size(self.n) if self.unit_scale else f'{self.n}'
            return f'  {c_desc}{self.desc}{c_reset} {n_str} {c_muted}•{c_reset} {c_rate}{rate_str}{c_reset} {c_muted}•{c_reset} [{self._fmt_time(elapsed)}]{c_muted}{self.postfix}{c_reset}'

    @classmethod
    def _redraw_all(cls):
        if not cls._active_bars:
            return
        if cls._lines_rendered > 0:
            sys.stdout.write(f'\033[{cls._lines_rendered}A')
        for bar in cls._active_bars:
            sys.stdout.write(f'\r\033[K{bar._format_line()}\n')
        cls._lines_rendered = len(cls._active_bars)
        sys.stdout.flush()


tqdm = ProgressBar


def _sort_subtitles_english_first(subtitles_dict):
    '''
    Sort subtitles dictionary so that English is always the first track (stream 0).
    Returns a list of tuples: [(lang_name, sub_file_or_url, is_default), ...]
    '''
    def is_english(lang_str):
        l = str(lang_str).lower()
        return 'eng' in l or l == 'en' or 'english' in l

    sorted_subs = []
    # English first
    for lang, url in subtitles_dict.items():
        if is_english(lang):
            sorted_subs.append((lang, url, True))
    # Non-English next
    for lang, url in subtitles_dict.items():
        if not is_english(lang):
            is_def = (len(sorted_subs) == 0)  # default if no English exists
            sorted_subs.append((lang, url, is_def))

    return sorted_subs


class BaseDownloader():
    '''
    Download Client for downloading files directly using requests and http.client
    '''
    def __init__(self, dl_config, ep_details, session=None):
        # logger init
        self.logger = logging.getLogger()
        self.ep_details = ep_details or {}
        # set downloader configuration
        self.out_file = ep_details.get('episodeName') or ep_details.get('out_file', 'media.mkv')
        self.out_dir = dl_config['download_dir']
        # add extra folder for season
        if ep_details.get('type', '') == 'tv':
            self.out_dir = f"{self.out_dir}{os.sep}Season-{ep_details['season']}"
        self.concurrency = dl_config.get('concurrency_per_file', 6) if dl_config.get('concurrency_per_file', 'auto') != 'auto' else 6
        self.parent_temp_dir = os.path.join(f'{self.out_dir}', 'temp_dir') if dl_config.get('temp_download_dir', 'auto') == 'auto' else dl_config['temp_download_dir']
        self.temp_dir = os.path.join(f"{self.parent_temp_dir}", f"{self.out_file.rsplit('.', 1)[0]}") #create temp directory per episode
        self.request_timeout = dl_config.get('request_timeout', 20)
        self.series_type = ep_details.get('type', 'series')
        self.subtitles = ep_details.get('subtitles', {})
        # special case for encrypted subtitles in kisskh client
        self.encrypted_subs_details = ep_details.get('encrypted_subs_details', {})
        self.thread_name_prefix = 'scraper-mp4-'

        # create a requests session and use across to re-use cookies
        self.req_session = session if session else requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=64, pool_maxsize=64, max_retries=3)
        self.req_session.mount('http://', adapter)
        self.req_session.mount('https://', adapter)

        # set http client usage based on config. As on Feb 21 2025, kisskh works with only http.client
        self.use_http_client = dl_config.get('use_http_client', False)

        self.req_session.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
            "Accept-Encoding": "*",
            "Connection": "keep-alive"
        }
        # update referer if defined
        if ep_details.get('refererLink'): self.req_session.headers.update({"Referer": ep_details['refererLink']})

    def _colprint(self, theme, text, **kwargs):
        '''
        Wrapper for color printer function
        '''
        if 'input' in theme:
            return colprint(theme, text, **kwargs)
        else:
            colprint(theme, text, **kwargs)

    def _get_raw_stream_data(self, url, stream=True, header=None):
        '''
        Fetch raw stream data using requests or http.client
        '''
        url = quote(url, safe=':/?&=%#')
        if self.use_http_client:
            # Use http.client for the request
            parsed_url = requests.utils.urlparse(url)
            conn_cls = http.client.HTTPSConnection if parsed_url.scheme == 'https' else http.client.HTTPConnection
            conn = conn_cls(parsed_url.netloc, timeout=self.request_timeout)
            path = (parsed_url.path or '/') + ('?' + parsed_url.query if parsed_url.query else '')
            headers = self.req_session.headers.copy()
            if header: headers.update(header)
            conn.request("GET", path, headers=headers)
            response = conn.getresponse()
            if response.status in [200, 206]:  # 206 means partial data (i.e., for chunked downloads)
                return response
            elif response.status in [301, 302, 303, 307, 308]:
                redirect_url = response.getheader('Location')
                if redirect_url:
                    if redirect_url.startswith('/'):
                        redirect_url = f"{parsed_url.scheme}://{parsed_url.netloc}{redirect_url}"
                    return self._get_raw_stream_data(redirect_url, stream, header)
                raise Exception(f'Failed with redirect status code {response.status} but no Location header')
            else:
                raise Exception(f'Failed with response code: {response.status}')
        else:
            # Use requests for the request
            headers = self.req_session.headers.copy()
            if header: headers.update(header)
            response = self.req_session.get(url, stream=stream, timeout=self.request_timeout, headers=headers)
            if response.status_code in [200, 206]:  # 206 means partial data (i.e., for chunked downloads)
                return response
            else:
                raise Exception(f'Failed with response code: {response.status_code}')

    def _get_stream_data(self, url, to_text=False, stream=False):
        response = self._get_raw_stream_data(url, stream)
        if self.use_http_client:
            data = response.read()
            return data.decode('utf-8') if to_text else data
        else:
            return response.text if to_text else response.content

    def _create_out_dirs(self):
        self.logger.debug(f'Creating output directories: {self.out_dir}')
        os.makedirs(self.out_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)

    def _remove_out_dirs(self):
        rmtree(self.temp_dir)

    def _cleanup_out_dirs(self):
        try:
            if os.path.exists(self.parent_temp_dir) and len(os.listdir(self.parent_temp_dir)) == 0:
                os.rmdir(self.parent_temp_dir)
        except Exception:
            pass
        try:
            if os.path.exists(self.out_dir) and len(os.listdir(self.out_dir)) == 0:
                os.rmdir(self.out_dir)
        except Exception:
            pass

    def _exec_cmd(self, cmd):
        self.logger.debug(f'Executing system command: {cmd}')
        return exec_os_cmd(cmd)

    def _get_display_prefix(self):
        try:
            if self.series_type.lower() == 'movie':
                return 'Movie'
            base_name = self.out_file.rsplit('.', 1)[0]
            m = re.search(r'(S\d+\s*-\s*E\d+|S\d+E\d+|E\d+)', base_name, re.IGNORECASE)
            if m:
                return m.group(1).replace(' ', '')
            ep_match = re.search(r'Episode\s*(\d+)', base_name, re.IGNORECASE)
            if ep_match:
                return f"Episode-{int(ep_match.group(1)):02d}"
            return base_name
        except Exception:
            return 'Downloading'

    def _create_chunk_header(self, start):
        end = start + self.chunk_size - 1
        return {'Range': f'bytes={start}-{end}'}

    @retry()
    def _download_chunk(self, chunk_details):
        '''
        download chunk file from download link based on defined chunk size. Reuse if already downloaded.

        Returns: (download_status, progress_bar_increment)
        '''
        try:
            dl_link, chunk_header, chunk_name = chunk_details
            chunk_file = os.path.join(f'{self.temp_dir}', f'{chunk_name}')

            # check if the chunk is already downloaded
            if os.path.isfile(chunk_file) and os.path.getsize(chunk_file) > 0:
                return (f'Chunk [{chunk_name}] already exists. Reusing.', os.path.getsize(chunk_file))

            # get the data for the chunk size defined in the header
            response = self._get_raw_stream_data(dl_link, False, chunk_header)

            # capture the size to update progress bar
            size = 0 
            with open(chunk_file, 'wb') as f:
                if isinstance(response, http.client.HTTPResponse):
                    while True:
                        chunk = response.read(self.chunk_size)
                        if not chunk:
                            break
                        size += f.write(chunk)
                else:
                    for chunk in response.iter_content(self.chunk_size):
                        if chunk:
                            size += f.write(chunk)

            return (f'Chunk [{chunk_name}] downloaded', size)

        except Exception as e:
            return (f'\nERROR: Chunk download failed [{chunk_name}] due to: {e}', 0)

    def _multi_threaded_download(self, download_func, urls, **metadata):
        reused_segments = 0
        failed_segments = 0
        ep_no = self._get_display_prefix()
        type = metadata.pop('type')
        self.logger.debug(f'[{ep_no}] Downloading {len(urls)} {type} using {self.concurrency} workers...')

        theme = PRINT_THEMES['results'] if DISPLAY_COLORS else ''
        metadata.update({
            'desc': f'Downloading {ep_no}',
            'file': sys.stdout,
            'ascii': '░▒█',
            'leave': True,
            'bar_format': theme + '{l_bar}{bar}' + theme + '{r_bar}'
        })

        # show progress of download using tqdm
        with tqdm(**metadata) as progress:
            # parallelize download of segments/chunks using a threadpool
            with ThreadPoolExecutor(max_workers=self.concurrency, thread_name_prefix=self.thread_name_prefix) as executor:
                results = [ executor.submit(download_func, ts_url) for ts_url in urls ]

                for result in as_completed(results):
                    status, size = result.result()
                    if 'ERROR' in status:
                        self._colprint('error', status)
                        failed_segments += 1
                    elif 'Reusing' in status:
                        reused_segments += 1
                        # update status only if segment is downloaded
                        progress.update(size)
                    else:
                        progress.update(size)

                    # add reused / failed segments/chunks status
                    seg_status = f'R/F: {reused_segments}/{failed_segments}'
                    progress.set_postfix_str(seg_status, refresh=True)

        self.logger.info(f'[{ep_no}] {type.capitalize()} download status: Total: {len(urls)} | Reused: {reused_segments} | Failed: {failed_segments}')
        if failed_segments > 0:
            raise Exception(f'Failed to download {failed_segments} / {len(urls)} {type}')

    def _merge_chunks(self, chunks_count):
        out_file = os.path.join(f'{self.out_dir}', f'{self.out_file}')

        with open(out_file, 'wb') as outfile:
            # iterate through the downloaded chunks
            for chunk_no in range(chunks_count):
                chunk_file = os.path.join(f"{self.temp_dir}", f"{self.out_file}.chunk{chunk_no}")
                # write the chunks to a single file
                with open(chunk_file, 'rb') as s:
                    outfile.write(s.read())
                # remove the merged chunk
                os.remove(chunk_file)

    def _download_subtitles(self):
        for sub_name in list(self.subtitles):
            sub_link = self.subtitles[sub_name]
            sub_file = os.path.join(self.temp_dir, sub_name.replace(' ', '_') + '_' + os.path.basename(sub_link.split('?')[0]))
            # update the dictionary pointing to downloaded file
            self.subtitles[sub_name] = sub_file

            try:
                self.logger.debug(f'Downloading {sub_name} subtitle from {sub_link} to {sub_file}')
                if not os.path.isfile(sub_file):
                    sub_content = self._get_stream_data(sub_link)
                    # download the subtitle to local
                    with open(sub_file, 'wb') as f:
                        f.write(sub_content)

                if self.encrypted_subs_details.get(sub_name):
                    self._decrypt_subtitle_file(sub_file, **self.encrypted_subs_details[sub_name])

                if sub_file.endswith('.vtt'):
                    srt_file = sub_file[:-4] + '.srt'
                    try:
                        if not os.path.isfile(srt_file):
                            self.logger.debug(f'Converting VTT subtitle to SRT: {srt_file}')
                            exec_os_cmd(f'ffmpeg -y -loglevel warning -i "{sub_file}" "{srt_file}"')
                        if os.path.isfile(srt_file) and os.path.getsize(srt_file) > 0:
                            sub_file = srt_file
                    except Exception as e:
                        self.logger.warning(f'Failed to convert VTT to SRT: {e}')

                self.subtitles[sub_name] = sub_file

            except Exception as e:
                self.logger.warning(f'Failed to download {sub_name} subtitle with error: {e}')
                self.subtitles.pop(sub_name)

    def _decrypt_subtitle_file(self, sub_file, **kwargs):
        self.logger.debug(f'Decrypting subtitle file: {sub_file}')
        decrypter = kwargs['decrypter']
        subs_key, subs_iv = kwargs['key'], kwargs['iv']

        with open(sub_file, 'r', encoding='utf-8') as file:
            lines = file.readlines()

        decryption_fail_count = 0
        total_line_count = 0
        with open(sub_file, 'w', encoding='utf-8') as file:
            for line in lines:
                if line.strip() and not line.strip().isdigit() and "-->" not in line:
                    try:
                        # decrypt and replace subtitle text lines
                        file.write(decrypter(line.strip(), subs_key, subs_iv) + '\n')
                        total_line_count += 1
                    except:
                        # write the line as-is if decryption fails
                        file.write(line)
                        decryption_fail_count += 1
                else:
                    # write sequence numbers, timestamps, and empty lines as-is
                    file.write(line)
        if decryption_fail_count > 0:
            self.logger.warning(f'Failed to decrypt {decryption_fail_count}/{total_line_count} lines in the subtitle file')

    def _handle_incomplete_cache(self):
        '''Check if incomplete cached chunks exist in temp_dir'''
        if not os.path.isdir(self.temp_dir):
            return
        cached_files = [
            f for f in os.listdir(self.temp_dir)
            if os.path.isfile(os.path.join(self.temp_dir, f)) and os.path.getsize(os.path.join(self.temp_dir, f)) > 0
        ]
        if cached_files:
            self.logger.info(f'[{self.out_file}] Resuming download with {len(cached_files)} cached chunk(s)...')

    def _add_subtitles(self):
        out_file = os.path.join(f'{self.out_dir}', f'{self.out_file}')
        is_mkv = out_file.lower().endswith('.mkv')
        # ffmpeg can't do in-place conversion. So, create a temp file and replace the original file
        temp_out_file = os.path.join(f'{self.out_dir}', f'temp_{self.out_file}')
        command = [f'ffmpeg -loglevel warning -i "{out_file}"']
        maps = ['-map 0:v -map 0:a'] if self.subtitles else []
        metadata = []

        sub_codec = '-c:s srt' if is_mkv else '-c:s mov_text'

        # Prepare the command if subtitles are present (English first)
        sorted_subs = _sort_subtitles_english_first(self.subtitles)
        for i, (lang, url, is_default) in enumerate(sorted_subs, start=1):
            sub_idx = i - 1
            command.append(f'-i "{url}"')
            maps.append(f'-map {i}')
            metadata.append(f'-metadata:s:s:{sub_idx} title="{lang}"')
            metadata.append(f'-metadata:s:s:{sub_idx} language=eng')
            if is_default:
                metadata.append(f'-disposition:s:{sub_idx} default+forced')
            else:
                metadata.append(f'-disposition:s:{sub_idx} 0')

        sub_flag = f'{sub_codec} ' if self.subtitles else ''
        metadata.append(f'-c:v copy -c:a copy {sub_flag}-bsf:a aac_adtstoasc "{temp_out_file}"')

        cmd = ' '.join(command + maps + metadata)
        self._exec_cmd(cmd)

        # Replace original file with the new file
        os.replace(temp_out_file, out_file)

    def start_download(self, dl_link):
        # set chunk size to 4MiB for high throughput
        self.chunk_size = 4 * 1024 * 1024
        # check incomplete cache and create output directory
        self._handle_incomplete_cache()
        self._create_out_dirs()

        self.logger.debug('Fetching stream data')
        dl_data = self._get_raw_stream_data(dl_link, True)
        if isinstance(dl_data, http.client.HTTPResponse):
            file_size = int(dl_data.getheader('content-length') or dl_data.getheader('Content-Length') or 0)
        else:
            file_size = int(dl_data.headers.get('content-length', 0))

        chunks = range(0, file_size, self.chunk_size)
        chunk_urls = [[dl_link, self._create_chunk_header(chunk), f'{self.out_file}.chunk{chunk_no}'] for chunk_no, chunk in enumerate(chunks)] 

        self.logger.debug('Downloading chunks')
        metadata = {
            'type': 'chunks',
            'total': file_size,
            'unit': 'iB',
            'unit_scale': True,
            'unit_divisor': 1024
        }
        concurrency = self.concurrency if self.concurrency is not None else 8
        self._multi_threaded_download(self._download_chunk, chunk_urls, concurrency=concurrency, **metadata)

        self.logger.debug('Merging chunks to single file')
        self._merge_chunks(len(chunks))

        if self.subtitles:
            self.logger.debug('Downloading subtitles')
            self._download_subtitles()
            self.logger.debug('Adding subtitles to the video')
            self._add_subtitles()

        # remove temp dir once completed and dir is empty
        self.logger.debug('Removing temporary directories')
        self._remove_out_dirs()
        return 0, 'Success'

        return (0, None)