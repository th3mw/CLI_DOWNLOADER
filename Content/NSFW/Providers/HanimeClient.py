import os
import re
import time
import json
import base64
import hashlib
import subprocess
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

from Cryptodome.Cipher import AES
from Core.BaseClient import BaseClient


class HanimeClient(BaseClient):
    '''
    Client for scraping and streaming NSFW Anime from Hanime (https://hanime.tv/).
    '''
    KEY_PASSPHRASE = b'htv-insecure-handshake-v1'
    AAD = b'htv-insecure-v1'
    KEY = hashlib.sha256(KEY_PASSPHRASE).digest()

    def __init__(self, config=None, session=None, series_type='NSFW', content_filter=None):
        config = config or {}
        super().__init__(config.get('request_timeout', 30) if isinstance(config, dict) else 30, session)
        self.client_name = 'hanime'
        self.name = 'Hanime'
        self.provider_name = 'Hanime'
        hanime_config = config.get('hanime', {}) if isinstance(config, dict) else {}
        self.base_url = hanime_config.get('base_url', 'https://hanime.tv').rstrip('/')
        self.index_url = 'https://guest.freeanimehentai.net/api/v11/search_hvs'
        self.csrf_url = 'https://ct.hanime.tv/csrf-token'
        self.handshake_url = 'https://auth.hanime.tv/api/v11/handshake'
        self._cached_index = None
        self._cache_time = 0
        self._target_item = {}

    def _b64url_encode(self, data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode('utf-8').rstrip('=')

    def _b64url_decode(self, s: str) -> bytes:
        pad = len(s) % 4
        if pad:
            s += '=' * (4 - pad)
        return base64.urlsafe_b64decode(s)

    def _encrypt_payload(self, payload_dict: dict) -> str:
        payload_json = json.dumps(payload_dict)
        iv = os.urandom(12)
        cipher = AES.new(self.KEY, AES.MODE_GCM, nonce=iv)
        cipher.update(self.AAD)
        ciphertext, tag = cipher.encrypt_and_digest(payload_json.encode('utf-8'))
        
        envelope = {
            'v': 1,
            'alg': 'AES-256-GCM',
            'iv': self._b64url_encode(iv),
            'tag': self._b64url_encode(tag),
            'data': self._b64url_encode(ciphertext)
        }
        return self._b64url_encode(json.dumps(envelope).encode('utf-8'))

    def _decrypt_token(self, x_token_str: str) -> dict:
        raw_env = self._b64url_decode(x_token_str)
        envelope = json.loads(raw_env.decode('utf-8'))
        iv = self._b64url_decode(envelope['iv'])
        tag = self._b64url_decode(envelope['tag'])
        data = self._b64url_decode(envelope['data'])
        
        cipher = AES.new(self.KEY, AES.MODE_GCM, nonce=iv)
        cipher.update(self.AAD)
        decrypted = cipher.decrypt_and_verify(data, tag)
        return json.loads(decrypted.decode('utf-8'))

    def _get_wasm_signature(self):
        '''
        Generate WASM signature using node runtime.
        '''
        js_code = '''
const https = require('https');
https.get('https://hanime-cdn.com/js/vendor.6cb274d12de4872d245a5bc7781bdc5e.min.js', (res) => {
    let data = '';
    res.on('data', chunk => data += chunk);
    res.on('end', () => {
        global.window = {
            dispatchEvent: () => {},
            addEventListener: () => {},
            location: { origin: 'https://hanime.tv', href: 'https://hanime.tv', hostname: 'hanime.tv' }
        };
        global.window.window = global.window;
        global.location = global.window.location;
        global.document = { location: global.window.location };
        global.CustomEvent = class {};
        data = data.replace('__emval_get_property = (handle, key) => { handle = Emval.toValue(handle); key = Emval.toValue(key); return Emval.toHandle(handle[key]) };', 
                            '__emval_get_property = (handle, key) => { try { handle = Emval.toValue(handle) || global.window; } catch(e){ handle = global.window; } key = Emval.toValue(key); return Emval.toHandle(handle ? handle[key] : undefined); };');
        eval(data);
        setTimeout(() => {
            console.log(JSON.stringify({ ssignature: global.window.ssignature, stime: String(global.window.stime) }));
        }, 400);
    });
});
'''
        try:
            out = subprocess.check_output(['node', '-e', js_code], timeout=10).decode('utf-8').strip()
            sig_data = json.loads(out)
            return sig_data.get('ssignature'), sig_data.get('stime')
        except Exception as e:
            self.logger.warning(f"Failed to generate node WASM signature: {e}")
            return None, str(int(time.time()))

    def _get_csrf_token(self):
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Origin': self.base_url,
            'Referer': f'{self.base_url}/'
        }
        resp = self._send_request(self.csrf_url, extra_headers=headers, return_type='json', silent=True)
        if resp and isinstance(resp, dict):
            return resp.get('csrf_token')
        return None

    def _get_video_index(self):
        '''
        Fetch and cache complete Hanime database index.
        '''
        now = time.time()
        if self._cached_index and (now - self._cache_time < 3600):
            return self._cached_index

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Origin': self.base_url,
            'Referer': f'{self.base_url}/'
        }
        resp = self._send_request(self.index_url, extra_headers=headers, return_type='json', silent=True)
        if resp and isinstance(resp, dict) and 'data' in resp:
            self._cached_index = resp.get('data', [])
            self._cache_time = now
            return self._cached_index

        return self._cached_index or []

    def search(self, search_term):
        self.logger.info(f"Searching Hanime for: {search_term}")
        all_videos = self._get_video_index()
        if not all_videos:
            self.logger.warning("Could not retrieve Hanime video index")
            return None

        query = search_term.lower().strip()
        tokens = query.split()

        matches = []
        for v in all_videos:
            name = v.get('name', '')
            search_titles = v.get('search_titles', '')
            combined = f"{name} {search_titles}".lower()
            if all(t in combined for t in tokens):
                matches.append(v)

        if not matches:
            matches = [v for v in all_videos if query in v.get('name', '').lower() or query in v.get('slug', '').lower()]

        if not matches:
            self.logger.warning(f"No results found on Hanime for '{search_term}'")
            return None

        results = {}
        for idx, m in enumerate(matches[:15], start=1):
            name = m.get('name', 'Unknown')
            slug = m.get('slug', '')
            brand = m.get('brand', 'Hentai')
            year = (m.get('released_at') or '')[:4]
            likes = m.get('likes', 0)
            views = m.get('views', 0)
            cover = m.get('cover_url')
            poster = m.get('poster_url')

            meta_parts = ['[NSFW]']
            if year:
                meta_parts.append(f"Year: {year}")
            if brand:
                meta_parts.append(f"Brand: {brand}")
            if likes:
                meta_parts.append(f"★ {likes:,}")

            card_title = f"{name} ({year})" if year else name
            card_meta = " • ".join(meta_parts)

            results[idx] = {
                'title': card_title,
                'raw_title': name,
                'slug': slug,
                'id': m.get('id'),
                'brand': brand,
                'year': year,
                'views': views,
                'likes': likes,
                'cover_url': cover,
                'poster_url': poster,
                'media_type': 'nsfw',
                'card_title': card_title,
                'card_meta': card_meta
            }

        return results

    def fetch_episodes_list(self, target):
        self._target_item = target
        name = target.get('raw_title') or target.get('title', 'NSFW Video')
        slug = target.get('slug', '')
        vid_id = target.get('id')

        ep_num = 1
        ep_match = re.search(r'\b(\d+)\b$', name)
        if ep_match:
            try:
                ep_num = int(ep_match.group(1))
            except Exception:
                ep_num = 1

        return [{
            'episode': ep_num,
            'episodeName': self._windows_safe_string(name),
            'raw_name': name,
            'slug': slug,
            'id': vid_id,
            'season': 1
        }]

    def show_episode_results(self, items, *predefined_range):
        for item in items:
            name = item.get('raw_name') or item.get('episodeName')
            self._colprint('results', f"  [Episode {item.get('episode', 1)}] {name}")

    def get_season_ep_ranges(self, episodes):
        return {1: {'start': 1, 'end': len(episodes)}}

    def _fetch_single_episode_link(self, ep_data):
        ep_no = ep_data.get('episode', 1)
        slug = ep_data.get('slug')
        if not slug:
            return ep_no, {'error': 'Missing video slug'}

        ssignature, stime = self._get_wasm_signature()
        csrf_token = self._get_csrf_token()

        payload = {
            'timestamp_unix': int(time.time()),
            'directive': 'htv_player_handshake',
            'slug': slug
        }
        token = self._encrypt_payload(payload)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Origin': self.base_url,
            'Referer': f'{self.base_url}/videos/hentai/{slug}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'x-signature-version': 'web2',
            'x-signature': ssignature or '',
            'x-time': stime or str(int(time.time())),
            'x-csrf-token': csrf_token or ''
        }

        try:
            r = self.req_session.post(
                self.handshake_url,
                json={'token': token, 'csrf_token': csrf_token},
                headers=headers,
                timeout=15
            )
            x_token = r.headers.get('x-token')
            if not x_token:
                return ep_no, {'error': f'Handshake failed with status {r.status_code}'}

            sources_data = self._decrypt_token(x_token)
            sources = sources_data.get('sources', [])
            if not sources:
                return ep_no, {'error': 'No video sources found in handshake'}

            m3u8_links = {}
            for s in sources:
                src = s.get('src')
                height = s.get('height')
                kind = s.get('kind', 'normal')
                if not src or kind == 'promotion':
                    continue

                full_m3u8 = src if src.startswith('http') else f"{self.base_url}{src}"
                res_key = str(height)

                m3u8_links[res_key] = {
                    'resolution_size': f"{s.get('width', 0)}x{height}",
                    'downloadLink': full_m3u8,
                    'downloadType': 'hls',
                    'refererLink': f"{self.base_url}/videos/hentai/{slug}",
                    'duration': 0
                }

            if m3u8_links:
                return ep_no, m3u8_links

            return ep_no, {'error': 'No playable HLS streams found'}
        except Exception as e:
            self.logger.warning(f"Error resolving Hanime stream for {slug}: {e}")
            return ep_no, {'error': str(e)}

    def fetch_episode_links(self, episodes, ep_ranges):
        selected_eps = episodes
        if not selected_eps:
            return {}

        target_links = {}
        with ThreadPoolExecutor(max_workers=min(4, len(selected_eps))) as executor:
            results = list(executor.map(self._fetch_single_episode_link, selected_eps))

        for ep_no, res_dict in sorted(results, key=lambda x: x[0]):
            target_links[ep_no] = res_dict

        return target_links

    def set_out_names(self, target_series):
        title = self._windows_safe_string(target_series.get('raw_title') or target_series.get('title', 'NSFW'))
        return title, f"{title} - "

    def fetch_m3u8_links(self, target_ep_links, resolution, episode_prefix):
        episode_links = {}
        series_title = episode_prefix.rstrip(' -').strip()

        for ep_no, res_data in target_ep_links.items():
            if 'error' in res_data:
                continue

            chosen_res = None
            if str(resolution) in res_data:
                chosen_res = str(resolution)
            elif '720' in res_data:
                chosen_res = '720'
            elif '1080' in res_data:
                chosen_res = '1080'
            elif res_data:
                chosen_res = next(iter(res_data.keys()))

            if not chosen_res:
                continue

            stream_info = res_data[chosen_res]
            final_filename = self.format_media_filename(
                series_title=series_title,
                season=1,
                episode=ep_no,
                resolution=chosen_res,
                is_movie=False,
                ext='.mkv'
            )

            episode_links[ep_no] = {
                'link': stream_info.get('downloadLink'),
                'referer': stream_info.get('refererLink'),
                'file_name': final_filename,
                'resolution': chosen_res,
                'download_type': 'hls'
            }

        return episode_links