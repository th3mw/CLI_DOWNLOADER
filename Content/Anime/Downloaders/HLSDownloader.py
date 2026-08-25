import os
import re

from Core.commons import retry
from Core.BaseDownloader import BaseDownloader, _sort_subtitles_english_first

NON_MEDIA_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.svg', '.ico',
    '.xls', '.xlsx', '.doc', '.docx', '.pdf', '.bin', '.txt', '.html', '.htm'
}


def _sanitize_segment_name(filename):
    '''
    Sanitize segment filename:
    1. Strip URL query parameters (?foo=bar) and URL fragments (#xyz).
    2. Extract only the basename.
    3. If extension is a non-media extension (e.g. .jpg, .png, .xls) or missing, rename to .ts.
    '''
    clean_filename = filename.split('?')[0].split('#')[0]
    base_name = os.path.basename(clean_filename.replace('\\', '/'))
    name, ext = os.path.splitext(base_name)
    if ext.lower() in NON_MEDIA_EXTENSIONS or ext.lower() not in {'.ts', '.aac', '.mp4', '.m4s', '.vtt'}:
        return name + '.ts'
    return base_name


def _strip_fake_header(data):
    '''
    Some CDNs (like VidTube) obfuscate MPEG-TS segments by prepending fake image/file headers (PNG, JPEG, etc.).
    Locate the first 188-byte aligned TS sync byte (0x47) and strip the leading fake header bytes.
    '''
    if isinstance(data, bytes) and len(data) > 376 and data[0] != 0x47:
        data_len = len(data)
        for i in range(min(2048, data_len - 188)):
            if data[i] == 0x47 and data[i + 188] == 0x47:
                return data[i:]
    return data


def _get_iso_lang(lang_str):
    l = str(lang_str).lower().strip()
    if 'eng' in l: return 'eng'
    if 'spa' in l or 'esp' in l: return 'spa'
    if 'fre' in l or 'fra' in l: return 'fre'
    if 'ger' in l or 'deu' in l: return 'ger'
    if 'jap' in l or 'jpn' in l: return 'jpn'
    if 'chi' in l or 'zho' in l: return 'chi'
    if 'rus' in l: return 'rus'
    if 'por' in l: return 'por'
    if 'ita' in l: return 'ita'
    if 'ind' in l: return 'ind'
    if 'ara' in l: return 'ara'
    if 'kor' in l: return 'kor'
    return 'eng'


class HLSDownloader(BaseDownloader):
    '''Download Client for HLS files'''
    # References: https://github.com/Oshan96/monkey-dl/blob/master/anime_downloader/util/hls_downloader.py
    # https://github.com/josephcappadona/m3u8downloader/blob/master/m3u8downloader/m3u8.py

    def __init__(self, dl_config, ep_details, session=None):
        # initialize base downloader
        super().__init__(dl_config, ep_details, session)
        # initialize HLS specific configuration
        self.m3u8_file = os.path.join(f'{self.temp_dir}', 'uwu.m3u8')
        self.thread_name_prefix = 'scraper-hls-'

    def _has_uri(self, m3u8_data):
        if not m3u8_data:
            return False
        if isinstance(m3u8_data, bytes):
            m3u8_data = m3u8_data.decode('utf-8', errors='ignore')
        method = re.search(r'#EXT-X-KEY:METHOD=([A-Z0-9\-]+)', m3u8_data)
        if method and method.group(1) != "NONE":
            return True
        return False

    def _collect_uri_iv(self, m3u8_data, m3u8_link=None):
        if isinstance(m3u8_data, bytes):
            m3u8_data = m3u8_data.decode('utf-8', errors='ignore')
        uri_match = re.search(r'URI="([^"]+)"', m3u8_data)
        iv_match = re.search(r'IV=([0-9a-fA-FxX]+)', m3u8_data)
        
        uri = uri_match.group(1) if uri_match else None
        iv = iv_match.group(1) if iv_match else None
        
        if uri and m3u8_link:
            if not uri.startswith('http'):
                if uri.startswith('//'):
                    uri = 'https:' + uri
                else:
                    base_url = '/'.join(m3u8_link.split('/')[:-1])
                    uri = base_url + '/' + uri.lstrip('/')
        return uri, iv

    def _download_key(self, key_uri):
        '''Download encryption key file directly to temp_dir without renaming or stripping headers'''
        try:
            key_file = os.path.join(self.temp_dir, 'sign.bin')
            if os.path.isfile(key_file) and os.path.getsize(key_file) > 0:
                return (f'Key file already exists', 1)
            data = self._get_stream_data(key_uri)
            with open(key_file, "wb") as f:
                f.write(data)
            return (f'Key file downloaded', 1)
        except Exception as e:
            self.logger.error(f'Failed to download key file: {e}')
            return (f'Key download failed: {e}', 0)

    def _collect_ts_urls(self, m3u8_link, m3u8_data):
        if isinstance(m3u8_data, bytes):
            m3u8_data = m3u8_data.decode('utf-8', errors='ignore')
        # Improved regex to handle all cases. (get all lines except those starting with #)
        base_url = '/'.join(m3u8_link.split('/')[:-1])
        normalize_url = lambda url, base_url: (url if url.startswith('http') else 'https:' + url if url.startswith('//') else base_url + '/' + url)
        # Preserve exact playlist order while removing duplicates
        urls = list(dict.fromkeys(normalize_url(m.group(0), base_url) for m in re.finditer("^(?!#).+$", m3u8_data, re.MULTILINE)))

        return urls

    @retry()
    def _download_segment(self, ts_url):
        '''
        download segment file from url. Reuse if already downloaded.

        Returns: (download_status, progress_bar_increment)
        '''
        try:
            segment_file_nm = _sanitize_segment_name(ts_url)
            segment_file = os.path.join(f"{self.temp_dir}", f"{segment_file_nm}")

            # check if the segment is already downloaded
            if os.path.isfile(segment_file) and os.path.getsize(segment_file) > 0:
                return (f'Segment file [{segment_file_nm}] already exists. Reusing.', 1)

            data = self._get_stream_data(ts_url)
            clean_data = _strip_fake_header(data)

            with open(segment_file, "wb") as ts_file:
                ts_file.write(clean_data)

            return (f'Segment file [{segment_file_nm}] downloaded', 1)

        except Exception as e:
            return (f'\nERROR: Segment download failed [{segment_file_nm}] due to: {e}', 0)

    def _rewrite_m3u8_file(self, m3u8_data):
        if isinstance(m3u8_data, bytes):
            m3u8_data = m3u8_data.decode('utf-8', errors='ignore')
        # ffmpeg doesn't accept backward slash in key file irrespective of platform
        key_temp_dir = self.temp_dir.replace('\\', '/')
        local_key_file = f"{key_temp_dir}/sign.bin"

        if self._has_uri(m3u8_data):
            m3u8_content = re.sub(r'URI="[^"]+"', f'URI="{local_key_file}"', m3u8_data, count=1)
        else:
            m3u8_content = m3u8_data

        # Rewrite each segment reference line to local sanitized file path
        new_lines = []
        for line in m3u8_content.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                sanitized_name = _sanitize_segment_name(stripped)
                new_lines.append(os.path.join(self.temp_dir, sanitized_name))
            else:
                new_lines.append(line)

        with open(self.m3u8_file, 'w', encoding='utf-8') as m3u8_f:
            m3u8_f.write('\n'.join(new_lines) + '\n')

    def _handle_incomplete_cache(self):
        '''Check if incomplete cached segments exist in temp_dir'''
        if not os.path.isdir(self.temp_dir):
            return
        cached_files = [
            f for f in os.listdir(self.temp_dir)
            if os.path.isfile(os.path.join(self.temp_dir, f)) and os.path.getsize(os.path.join(self.temp_dir, f)) > 0
            and not f.endswith('.m3u8') and not f.endswith('.bin') and not f.endswith('.key')
        ]
        if cached_files:
            self.logger.info(f'[{self.out_file}] Resuming download with {len(cached_files)} cached segment(s)...')

    def _convert_to_mp4(self):
        out_file = os.path.join(f'{self.out_dir}', f'{self.out_file}')
        is_mkv = out_file.lower().endswith('.mkv')
        command = [f'ffmpeg -y -nostdin -loglevel warning -allowed_extensions ALL -i "{self.m3u8_file}"']
        maps = ['-map 0:v -map 0:a'] if self.subtitles else []
        metadata = []

        sub_codec = '-c:s srt' if is_mkv else '-c:s mov_text'

        # Prepare the command if subtitles are present (English first)
        sorted_subs = _sort_subtitles_english_first(self.subtitles)
        for i, (lang, url, is_default) in enumerate(sorted_subs, start=1):
            sub_idx = i - 1
            iso_code = _get_iso_lang(lang)
            command.append(f'-i "{url}"')
            maps.append(f'-map {i}')
            metadata.append(f'-metadata:s:s:{sub_idx} title="{lang}"')
            metadata.append(f'-metadata:s:s:{sub_idx} language={iso_code}')
            if is_default:
                metadata.append(f'-disposition:s:{sub_idx} default+forced')
            else:
                metadata.append(f'-disposition:s:{sub_idx} 0')

        sub_flag = f'{sub_codec} ' if self.subtitles else ''
        metadata.append(f'-c:v copy -c:a copy {sub_flag}-bsf:a aac_adtstoasc "{out_file}"')

        cmd = ' '.join(command + maps + metadata)
        self._exec_cmd(cmd)

    def start_download(self, m3u8_link):
        # check incomplete cache and create output directory
        self._handle_incomplete_cache()
        self._create_out_dirs()

        iv = None
        self.logger.debug('Fetching stream data')
        m3u8_data = self._get_stream_data(m3u8_link, True)

        self.logger.debug('Check if stream is encrypted/mapped')
        if self._has_uri(m3u8_data):
            self.logger.debug('Stream is encrypted/mapped. Collect iv data and download key')
            key_uri, iv = self._collect_uri_iv(m3u8_data, m3u8_link)
            if key_uri:
                status = self._download_key(key_uri)
                if status[1] == 0:
                    self.logger.error(f'Failed to download key/map file with error: {status[0]}')

        # did not run into HLS with IV during development, so skipping it
        if iv:
            raise Exception("Current code cannot decode IV links")

        self.logger.debug('Collect m3u8 segment urls')
        ts_urls = self._collect_ts_urls(m3u8_link, m3u8_data)

        self.logger.debug('Downloading collected segments')
        metadata = {
            'type': 'segments',
            'total': len(ts_urls),
            'unit': 'seg'
        }
        self._multi_threaded_download(self._download_segment, ts_urls, **metadata)

        self.logger.debug('Rewrite m3u8 file with downloaded segments paths')
        self._rewrite_m3u8_file(m3u8_data)

        if self.subtitles:
            self.logger.debug('Downloading subtitles')
            self._download_subtitles()

        self.logger.debug('Converting m3u8 segments to media container')
        self._convert_to_mp4()

        # remove temp dir once completed and dir is empty
        self.logger.debug('Removing temporary directories')
        self._remove_out_dirs()

        return (0, None)
