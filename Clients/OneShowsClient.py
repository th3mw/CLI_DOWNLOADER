import json
import os
import re
import subprocess
from urllib.parse import quote_plus

from Clients.BaseClient import BaseClient


class OneShowsClient(BaseClient):
    '''
    Client for 1Shows (https://www.1shows.org) supporting Movies & TV Shows
    with high-quality direct download links.
    '''
    def __init__(self, config, session=None, series_type=None, content_filter=None):
        self.series_type = series_type
        self.content_filter = content_filter
        self.base_url = config.get('base_url', 'https://www.1shows.org/')
        self.search_url = config.get('search_url', 'https://www.1shows.org/api/search/query?query=')
        self.tv_url = config.get('tv_url', 'https://www.1shows.org/api/tv/')
        self.token_url = config.get('token_url', 'https://api.viduki.net/download-token')
        self.download_api = config.get('download_api', 'https://api.viduki.net/download/')
        self.manifest_url = config.get('manifest_url', 'https://www.1shows.org/makimaDL-manifest.json')
        self.hls_size_accuracy = config.get('hls_size_accuracy', 0)
        self.selector_strategy = config.get('alternate_resolution_selector', 'lowest')
        super().__init__(config.get('request_timeout', 30), session=session)
        self.header.update({
            'Referer': self.base_url,
            'Origin': self.base_url.rstrip('/')
        })
        self.logger.debug(f'OneShows client initialized with {config = }, {content_filter = }')

    def _show_search_results(self, key, details):
        '''Pretty print search results'''
        media_type = details.get('media_type', 'movie').upper()
        rating = details.get('vote_average', 'N/A')
        line = f"{key}: {details.get('title')} [{media_type}]" + \
               f"\n   | Year: {details.get('year')} | Rating: {rating}/10 | Overview: {details.get('overview', '')[:90]}..."
        self._colprint('results', line)

    def _decrypt_payload(self, payload, token):
        '''Decrypt WASM-encrypted download payload using Node.js WASM runtime'''
        wasm_path = '/tmp/makimaDL.wasm'
        manifest_path = '/tmp/makimaDL-manifest.json'
        try:
            if not os.path.exists(wasm_path) or not os.path.exists(manifest_path):
                manifest = self._send_request(self.manifest_url, return_type='json')
                if not manifest:
                    return None
                with open(manifest_path, 'w') as f:
                    json.dump(manifest, f)
                wasm_bytes = self._send_request(self.base_url.rstrip('/') + manifest['url'], return_type='content')
                if not wasm_bytes:
                    return None
                with open(wasm_path, 'wb') as f:
                    f.write(wasm_bytes)
            else:
                with open(manifest_path, 'r') as f:
                    manifest = json.load(f)

            js_code = f'''
const fs = require('fs');
const wasmBuffer = fs.readFileSync('{wasm_path}');
const manifest = {json.dumps(manifest)};
const payload = {json.dumps(payload)};
const token = {json.dumps(token)};

function hexToBytes(hex) {{
    const bytes = new Uint8Array(hex.length / 2);
    for (let i = 0; i < hex.length; i += 2) {{
        bytes[i / 2] = parseInt(hex.substr(i, 2), 16);
    }}
    return bytes;
}}

function writeToWasm(exports, allocFn, data) {{
    const ptr = exports[allocFn](data.length);
    new Uint8Array(exports.memory.buffer).set(data, ptr);
    return {{ ptr, len: data.length }};
}}

WebAssembly.instantiate(wasmBuffer, {{ env: {{ abort: () => {{ throw new Error('wasm abort'); }} }} }})
.then(res => {{
    const instance = res.instance;
    const exports = instance.exports;
    const map = manifest.exports;

    const tBytes = hexToBytes(token);
    const ivBytes = hexToBytes(payload.iv);
    const tagBytes = hexToBytes(payload.tag);
    const ctBytes = hexToBytes(payload.ct);

    const f = writeToWasm(exports, map.alloc, tBytes);
    const p = writeToWasm(exports, map.alloc, ivBytes);
    const m = writeToWasm(exports, map.alloc, ctBytes);
    const x = writeToWasm(exports, map.alloc, tagBytes);

    const outPtr = exports[map.alloc](ctBytes.length);
    const len = exports[map.decryptDownload](f.ptr, f.len, p.ptr, p.len, m.ptr, m.len, x.ptr, x.len, outPtr);

    if (len < 0) process.exit(1);

    const resultBytes = new Uint8Array(exports.memory.buffer, outPtr, len);
    console.log(new TextDecoder().decode(resultBytes));
}});
'''
            res = subprocess.run(['node', '-e', js_code], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                return json.loads(res.stdout.strip())
        except Exception as e:
            self.logger.error(f'Decryption failed: {e}')
        return None

    def search(self, keyword, search_limit=10):
        '''Search for content on 1Shows via TMDb search API'''
        search_key = quote_plus(keyword)
        search_url = f"{self.search_url}{search_key}"
        raw_data = self._send_request(search_url, return_type='json')
        if not raw_data or 'results' not in raw_data:
            return {}

        raw_results = raw_data['results']
        search_results = {}
        idx = 1
        for res in raw_results:
            if idx > search_limit:
                break
            media_type = res.get('media_type', 'movie')
            if self.content_filter and media_type != self.content_filter:
                continue

            title = res.get('title') or res.get('name', 'Unknown')
            release_date = res.get('release_date') or res.get('first_air_date') or 'XXXX'
            year = release_date.split('-')[0] if '-' in release_date else release_date

            item = {
                'title': title,
                'tmdb_id': res.get('id'),
                'media_type': media_type,
                'year': year,
                'vote_average': round(res.get('vote_average', 0.0), 1),
                'overview': res.get('overview', '')
            }
            search_results[idx] = item
            self._show_search_results(idx, item)
            idx += 1

        return search_results

    def fetch_episodes_list(self, target):
        '''Fetch episode list for a movie or TV show'''
        media_type = target.get('media_type', 'movie')
        tmdb_id = target.get('tmdb_id')
        title = target.get('title')

        if media_type == 'movie':
            return [{
                'episode': 1,
                'episodeName': self._windows_safe_string(f"{title}"),
                'tmdb_id': tmdb_id,
                'media_type': 'movie',
                'season': 1,
                'ep_no': 1
            }]

        # TV Show logic
        tv_info = self._send_request(f"{self.tv_url}{tmdb_id}", return_type='json')
        if not tv_info or 'seasons' not in tv_info:
            return []

        all_episodes = []
        ep_counter = 1
        for s in tv_info['seasons']:
            season_num = s.get('season_number', 0)
            if season_num == 0:  # Skip specials by default unless it's the only season
                continue
            ep_count = s.get('episode_count', 0)
            for ep_i in range(1, ep_count + 1):
                ep_name = f"{title} S{season_num:02d}E{ep_i:02d}"
                all_episodes.append({
                    'episode': ep_counter,
                    'episodeName': self._windows_safe_string(ep_name),
                    'tmdb_id': tmdb_id,
                    'media_type': 'tv',
                    'season': season_num,
                    'ep_no': ep_i
                })
                ep_counter += 1

        return all_episodes

    def show_episode_results(self, items, *predefined_range):
        '''Display episode list'''
        start, end = self._get_episode_range_to_show(items[0].get('episode'), items[-1].get('episode'), predefined_range[1], threshold=24)
        for item in items:
            if item.get('episode') >= start and item.get('episode') <= end:
                self._colprint('results', f"Episode: {item.get('episodeName')}")

    def _resolve_source_link(self, source_url):
        '''Resolve third-party redirect links to direct playable/downloadable file URLs'''
        try:
            if 'goodstream.cc' in source_url:
                res = self._send_request(source_url, return_type='text')
                if res:
                    pd_match = re.search(r'https?://pixeldrain\.com/u/([a-zA-Z0-9]+)', res)
                    if pd_match:
                        return f'https://pixeldrain.com/api/file/{pd_match.group(1)}'
                    file_match = re.search(r'href=["\'](https?://[^"\']+\.(?:mp4|mkv))["\']', res)
                    if file_match:
                        return file_match.group(1)
            elif 'pixeldrain.com/u/' in source_url:
                pd_match = re.search(r'https?://pixeldrain\.com/u/([a-zA-Z0-9]+)', source_url)
                if pd_match:
                    return f'https://pixeldrain.com/api/file/{pd_match.group(1)}'
            elif any(ext in source_url.lower() for ext in ['.mp4', '.mkv', '.avi']):
                return source_url
        except Exception as e:
            self.logger.debug(f'Failed resolving source URL {source_url}: {e}')
        return source_url

    def _fetch_single_episode_link(self, episode):
        ep_no = episode.get('episode')
        tmdb_id = episode.get('tmdb_id')
        media_type = episode.get('media_type', 'movie')
        season = episode.get('season', 1)
        ep_num = episode.get('ep_no', 1)

        self.logger.debug(f'Fetching direct download sources for {episode = }')

        # 1. Fetch token
        tok_data = self._send_request(self.token_url, extra_headers=self.header, return_type='json')
        if not tok_data or 'token' not in tok_data:
            self.logger.error('Failed to fetch download token')
            return ep_no, None, {'error': 'Failed to fetch download token'}

        token = tok_data['token']
        headers = dict(self.header)
        headers['x-download-token'] = token

        # 2. Fetch encrypted download payload
        endpoint = f"movie/{tmdb_id}" if media_type == 'movie' else f"tv/{tmdb_id}/{season}/{ep_num}"
        payload = self._send_request(f"{self.download_api}{endpoint}", extra_headers=headers, return_type='json')
        if not payload or 'ct' not in payload:
            self.logger.error('Failed to fetch download payload')
            return ep_no, None, {'error': 'Failed to fetch download payload'}

        # 3. Decrypt payload
        decrypted = self._decrypt_payload(payload, token)
        if not decrypted or 'sources' not in decrypted or not decrypted['sources']:
            self.logger.error('No download sources found after decryption')
            return ep_no, None, {'error': 'No download sources found'}

        sources = decrypted['sources']
        
        # Display Available Download Varieties (Source + Res + Size)
        ep_title = episode.get('episodeName', f"Episode {ep_no}")
        self._colprint('header', f"\nAvailable Download Varieties for {ep_title}:")
        
        for i, s in enumerate(sources, start=1):
            label = s.get('label', 'Direct Link')
            self._colprint('results', f"  {i:2d}: {label}")

        selected_idx = 1
        try:
            user_choice = self._colprint(
                'user_input',
                f"\nSelect download variety [1-{len(sources)}] [default=1]: ",
                input_type='recurring',
                input_dtype='int'
            )
            if user_choice and 1 <= int(user_choice) <= len(sources):
                selected_idx = int(user_choice)
        except Exception:
            selected_idx = 1

        chosen_source = sources[selected_idx - 1]
        selected_label = chosen_source.get('label', 'Direct Link')
        raw_url = chosen_source.get('url', '')

        self.logger.debug(f'Selected variety: {selected_label} -> {raw_url}')
        selected_url = self._resolve_source_link(raw_url)
        if not selected_url:
            return ep_no, None, {'error': 'Failed resolving download URL'}

        self._update_scraper_dict(ep_no, episode)
        self._update_scraper_dict(ep_no, {
            'streamLink': selected_url,
            'refererLink': self.base_url,
            'quality': selected_label
        })

        res_dict = {
            '1080': {
                'downloadLink': selected_url,
                'downloadType': 'http',
                'resolution_size': selected_label,
                'refererLink': self.base_url
            }
        }
        return ep_no, res_dict, None

    def fetch_episode_links(self, episodes, ep_ranges):
        '''Fetch download links for episodes in parallel'''
        download_links = {}
        ep_start, ep_end, specific_eps = ep_ranges['start'], ep_ranges['end'], ep_ranges.get('specific_no', [])
        display_prefix = 'Episode'

        selected_eps = [
            ep for ep in episodes
            if (float(ep.get('episode')) >= ep_start and float(ep.get('episode')) <= ep_end) or (float(ep.get('episode')) in specific_eps)
        ]
        if not selected_eps:
            return {}

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(10, len(selected_eps))) as executor:
            results = list(executor.map(self._fetch_single_episode_link, selected_eps))

        for ep_no, link, err_dict in sorted(results, key=lambda x: float(x[0])):
            if link:
                download_links[ep_no] = link
                self._show_episode_links(ep_no, link, display_prefix)
            elif err_dict:
                self._show_episode_links(ep_no, err_dict, display_prefix)

        return download_links

    def set_out_names(self, target_series):
        '''Set output names for downloads'''
        title = self._windows_safe_string(target_series['title'])
        target_dir = title if title.endswith(')') else f"{title} ({target_series['year']})"
        return target_dir, None

    def get_stream_link(self, episode_details, resolution):
        '''Return resolved direct download link'''
        ep_no = episode_details.get('episode')
        link_info = self.scraper_episode_dict.get(ep_no, {})
        stream_link = link_info.get('streamLink')
        if stream_link:
            return stream_link, stream_link
        return None, None
