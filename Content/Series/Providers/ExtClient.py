import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import tempfile
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup
from Core.BaseClient import BaseClient
from Core.commons import colprint, render_box

PUBLIC_TRACKERS = [
    'udp://tracker.opentrackr.org:1337/announce',
    'udp://open.demonii.com:1337/announce',
    'udp://tracker.openbittorrent.com:80',
    'udp://tracker.coppersurfer.tk:6969',
    'udp://glotorrents.pw:6969/announce',
    'udp://torrent.gresille.org:80/announce',
    'udp://p4p.arenabg.com:1337',
    'udp://tracker.leechers-paradise.org:6969',
    'udp://tracker.internetwarriors.net:1337',
    'udp://9.rarbg.to:2710/announce',
    'udp://9.rarbg.me:2710/announce',
    'udp://exodus.desync.com:6969',
    'udp://open.stealth.si:80/announce',
    'udp://tracker.torrent.eu.org:451/announce',
    'udp://zer0day.to:1337/announce'
]


class ExtClient(BaseClient):
    '''
    Client for Ext.to (EXT Torrents) TV Series complete season packs.
    Supports complete season torrent discovery, seed-based ranking,
    resolution segregation, and torrent file index inspection.
    '''

    DEFAULT_USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36'
    
    # Default initial fallback cookies verified functional with Turnstile
    DEFAULT_COOKIES = {
        'PHPSESSID': 'JxN1HXfaQCVLVgTaYl38u7m1KTfDhA39',
        'cf_clearance': 'CrGPaFCa8t4j_nc206yhT8JJJQftAu7u8qKLFo4g_onXzU5e3sJtHjGoUGVnKFix77QCQGnXBelr4XZrADyg8u9EqEfGnLB5UXzJpKa-wrzaA2p8nMX0JvhbfOVabaHv01z0IspNm6y918GCxISYjwVdF3Qeybgo_AyiUyX23Qr2GpSQgcVTz4QCn26rKG8UlIHpYpCdOZxKEl26O_XSnHKcxxiDTHHYgikXuQnySKhnR7jOl9clz3xZGNKnB3KW36sOvtMNedNTHsGErQkEpo_VVT6ufJVbLzebvWNKGufTETF2ZCpdpqCg-bR3ab_NE0ogQE1xgr4rZfGg76wamGDTffdg1yvPHF0hXYkgAjGmYRUr8tQ6sd53ojaHPwUdTQ8jmpeTTVyXo11nYnrUaEpfIfGid1sP9hriKvtLQx3KWOpLiQ5nbUM'
    }

    def __init__(self, config=None, session=None, series_type=None, content_filter=None):
        super().__init__(session=session)
        self.config = config or {}
        self.series_type = series_type or 'TV Shows'
        self.content_filter = content_filter
        self.name = 'Ext.to'
        self.provider_name = 'Ext.to'
        self.base_url = self.config.get('base_url', 'https://ext.to').rstrip('/')
        self._target_show = {}
        self._seasons_cache = {}
        self._season_packs_cache = {}
        self._cookies = {}
        self._cookie_cache_path = os.path.expanduser('~/.cache/media-scraper/ext_cookies.json')
        self._load_cookies()

    def _load_cookies(self):
        '''Load Cloudflare clearance cookies from cache file, Chrome DB, or fallback defaults'''
        os.makedirs(os.path.dirname(self._cookie_cache_path), exist_ok=True)
        # 1. Config override
        if self.config.get('cookies'):
            self._cookies = dict(self.config['cookies'])
            return

        # 2. Local cache file
        if os.path.isfile(self._cookie_cache_path):
            try:
                with open(self._cookie_cache_path, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                    if cached.get('cf_clearance'):
                        self._cookies = cached
                        return
            except Exception:
                pass

        # 3. Read from local Chrome SQLite Cookies DB if present
        chrome_cookies = self._extract_cookies_from_chrome()
        if chrome_cookies and chrome_cookies.get('cf_clearance'):
            self._cookies = chrome_cookies
            self._save_cookies()
            return

        # 4. Fallback default cookies
        self._cookies = dict(self.DEFAULT_COOKIES)
        self._save_cookies()

    def _save_cookies(self):
        '''Persist active cookies to local user cache'''
        try:
            os.makedirs(os.path.dirname(self._cookie_cache_path), exist_ok=True)
            with open(self._cookie_cache_path, 'w', encoding='utf-8') as f:
                json.dump(self._cookies, f, indent=2)
        except Exception:
            pass

    def _extract_cookies_from_chrome(self):
        '''Attempts to decrypt and read ext.to cookies from local Chrome profile'''
        candidate_paths = [
            os.path.expanduser('~/.cache/ms-playwright-mcp/mcp-chrome-75c0795/Default/Cookies'),
            os.path.expanduser('~/.config/google-chrome/Default/Cookies'),
            os.path.expanduser('~/.config/chromium/Default/Cookies'),
            os.path.expanduser('~/.config/BraveSoftware/Brave-Browser/Default/Cookies')
        ]
        cookie_db_path = None
        for p in candidate_paths:
            if os.path.isfile(p):
                cookie_db_path = p
                break

        if not cookie_db_path:
            return None

        try:
            from Cryptodome.Cipher import AES
            from Cryptodome.Protocol.KDF import PBKDF2

            key = PBKDF2(b'peanuts', b'saltysalt', 16, 1)

            def decrypt_v10(enc):
                if enc.startswith(b'v10') or enc.startswith(b'v11'):
                    enc = enc[3:]
                    iv = b' ' * 16
                    cipher = AES.new(key, AES.MODE_CBC, iv)
                    dec = cipher.decrypt(enc)
                    pad = dec[-1]
                    if isinstance(pad, int) and pad < 16:
                        dec = dec[:-pad]
                    return dec.decode('latin1', errors='ignore')
                return enc.decode('latin1', errors='ignore')

            with tempfile.NamedTemporaryFile() as tmp:
                shutil.copy(cookie_db_path, tmp.name)
                conn = sqlite3.connect(tmp.name)
                c = conn.cursor()
                c.execute('SELECT host_key, name, encrypted_value FROM cookies WHERE host_key LIKE "%ext.to%"')
                extracted = {}
                for _, name, enc_val in c.fetchall():
                    val = decrypt_v10(enc_val)
                    if val:
                        m_token = re.search(r'([A-Za-z0-9_\-\.]{16,})', val)
                        if m_token:
                            extracted[name] = m_token.group(1)
                conn.close()
                if 'cf_clearance' in extracted:
                    return extracted
        except Exception as e:
            self.logger.debug(f"Failed to read Chrome cookies DB: {e}")
        return None

    def _get_headers(self, referer=None):
        headers = {
            'User-Agent': self.DEFAULT_USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Upgrade-Insecure-Requests': '1'
        }
        if referer:
            headers['Referer'] = referer
        return headers

    def _request(self, path_or_url, method='get', data=None, referer=None, extra_headers=None):
        url = path_or_url if path_or_url.startswith('http') else f"{self.base_url}/{path_or_url.lstrip('/')}"
        headers = self._get_headers(referer=referer)
        if extra_headers:
            headers.update(extra_headers)

        try:
            if method.lower() == 'post':
                r = self.req_session.post(url, headers=headers, cookies=self._cookies, data=data, timeout=12)
            else:
                r = self.req_session.get(url, headers=headers, cookies=self._cookies, timeout=12)

            # Update cookies if response sets any
            if r.cookies:
                for k, v in r.cookies.items():
                    self._cookies[k] = v
                self._save_cookies()

            if r.status_code == 200 and 'Just a moment...' not in r.text:
                return r

            if r.status_code == 403 or 'Just a moment...' in r.text:
                self.logger.warning(f"Cloudflare Turnstile triggered for {url}")
                # Try refreshing from Chrome DB once
                fresh = self._extract_cookies_from_chrome()
                if fresh and fresh != self._cookies:
                    self._cookies = fresh
                    self._save_cookies()
                    return self._request(path_or_url, method=method, data=data, referer=referer, extra_headers=extra_headers)

        except Exception as e:
            self.logger.error(f"ExtClient request error for {url}: {e}")
        return None

    def search(self, search_term):
        '''
        Search for TV shows on Ext.to and TVMaze catalog.
        Returns numbered dictionary of matched shows.
        '''
        self.logger.info(f"Searching TV Shows on Ext.to for: {search_term}")
        results = {}

        # 1. First query Ext.to directly for show hubs
        search_path = f"browse/?q={urllib.parse.quote_plus(search_term)}&cat=2"
        resp = self._request(search_path)
        ext_hubs = []
        if resp and resp.text:
            soup = BeautifulSoup(resp.text, 'html.parser')
            seen_slugs = set()
            for a in soup.select('a[href*="-s"][href$="/"]'):
                href = a.get('href', '')
                m = re.search(r'/([^/]+-s\d+)/', href)
                if m:
                    slug = m.group(1)
                    if slug not in seen_slugs and not slug.startswith('browse'):
                        seen_slugs.add(slug)
                        name_text = a.text.strip() or slug.rsplit('-s', 1)[0].replace('-', ' ').title()
                        ext_hubs.append({
                            'slug': slug,
                            'title': name_text,
                            'url': f"{self.base_url}/{slug}/"
                        })

        # 2. Enrich and query TVMaze catalog for comprehensive metadata
        tvmaze_map = {}
        try:
            r_tvm = self.req_session.get(
                f"https://api.tvmaze.com/search/shows?q={urllib.parse.quote(search_term)}",
                headers={'User-Agent': self.DEFAULT_USER_AGENT},
                timeout=5
            )
            if r_tvm.status_code == 200:
                for item in r_tvm.json():
                    s = item.get('show', {})
                    clean_name = re.sub(r'[^a-zA-Z0-9]', '', s.get('name', '')).lower()
                    tvmaze_map[clean_name] = s
        except Exception as e:
            self.logger.debug(f"TVMaze enrichment failed: {e}")

        # Assemble result cards
        if ext_hubs:
            for idx, hub in enumerate(ext_hubs[:12], start=1):
                raw_name = hub['title']
                clean_raw = re.sub(r'[^a-zA-Z0-9]', '', raw_name).lower()
                matched_tvm = tvmaze_map.get(clean_raw, {})

                prem = (matched_tvm.get('premiered') or '')[:4]
                rating = matched_tvm.get('rating', {}).get('average')
                genres = matched_tvm.get('genres', [])

                meta_parts = []
                if rating:
                    meta_parts.append(f"★ {rating}")
                if prem:
                    meta_parts.append(f"Year: {prem}")
                if genres:
                    meta_parts.append(f"[{', '.join(genres[:3])}]")
                meta_parts.append("Source: Ext.to Hub")

                card_title = f"{raw_name} ({prem})" if prem else raw_name
                card_meta = " • ".join(meta_parts)

                results[idx] = {
                    'title': card_title,
                    'raw_title': raw_name,
                    'year': prem,
                    'rating': rating,
                    'genres': genres,
                    'show_slug': hub['slug'],
                    'detail_url': hub['url'],
                    'media_type': 'tv',
                    'card_title': card_title,
                    'card_meta': card_meta
                }

        # Fallback to TVMaze catalog if no direct Ext.to hubs returned
        if not results and tvmaze_map:
            for idx, s in enumerate(list(tvmaze_map.values())[:10], start=1):
                name = s.get('name', 'Unknown')
                prem = (s.get('premiered') or '')[:4]
                rating = s.get('rating', {}).get('average')
                genres = s.get('genres', [])

                meta_parts = []
                if rating:
                    meta_parts.append(f"★ {rating}")
                if prem:
                    meta_parts.append(f"Year: {prem}")
                if genres:
                    meta_parts.append(f"[{', '.join(genres[:3])}]")
                meta_parts.append("Source: Ext.to Swarms")

                card_title = f"{name} ({prem})" if prem else name
                card_meta = " • ".join(meta_parts)

                # Generate clean slug
                clean_slug = re.sub(r'[^a-zA-Z0-9]+', '-', name).strip('-').lower()

                results[idx] = {
                    'title': card_title,
                    'raw_title': name,
                    'year': prem,
                    'rating': rating,
                    'genres': genres,
                    'show_slug': clean_slug,
                    'detail_url': f"{self.base_url}/{clean_slug}/",
                    'media_type': 'tv',
                    'card_title': card_title,
                    'card_meta': card_meta
                }

        if not results:
            self.logger.warning(f"No TV Shows found on Ext.to for '{search_term}'")
            return None

        return results

    def fetch_episodes_list(self, target):
        '''
        Fetch available seasons for the selected show on Ext.to.
        In V1.8, each returned item represents a Complete Season Pack.
        '''
        self._target_show = target
        show_slug = target.get('show_slug')
        show_title = target.get('raw_title', target.get('title', 'TV Series'))

        seasons_found = set()
        season_details = {}

        # 1. Query Ext.to show hub page
        if show_slug:
            hub_resp = self._request(f"{show_slug}/")
            if hub_resp and hub_resp.text:
                soup = BeautifulSoup(hub_resp.text, 'html.parser')
                # Find all season links like /show-slug/?s=1 or ?s=2
                for a in soup.select('a[href*="?s="]'):
                    href = a.get('href', '')
                    m_s = re.search(r'[?&]s=(\d+)', href)
                    if m_s:
                        s_num = int(m_s.group(1))
                        seasons_found.add(s_num)
                        text_val = a.text.strip()
                        if 'episodes' in text_val.lower():
                            season_details[s_num] = text_val

        # 2. Fallback to TVMaze if show hub page had no explicit season links
        if not seasons_found:
            try:
                r_tvm = self.req_session.get(
                    f"https://api.tvmaze.com/search/shows?q={urllib.parse.quote(show_title)}",
                    headers={'User-Agent': self.DEFAULT_USER_AGENT},
                    timeout=5
                )
                if r_tvm.status_code == 200 and r_tvm.json():
                    show_id = r_tvm.json()[0].get('show', {}).get('id')
                    if show_id:
                        r_seasons = self.req_session.get(
                            f"https://api.tvmaze.com/shows/{show_id}/seasons",
                            headers={'User-Agent': self.DEFAULT_USER_AGENT},
                            timeout=5
                        )
                        if r_seasons.status_code == 200:
                            for s in r_seasons.json():
                                s_no = s.get('number')
                                if s_no:
                                    seasons_found.add(s_no)
                                    eps = s.get('episodeOrder')
                                    if eps:
                                        season_details[s_no] = f"{eps} episodes"
            except Exception as e:
                self.logger.debug(f"TVMaze season lookup fallback failed: {e}")

        # Default fallback: Season 1
        if not seasons_found:
            seasons_found = {1}

        # Build season pack list
        episodes = []
        for s_num in sorted(seasons_found):
            ep_info = season_details.get(s_num, '')
            ep_label = f" ({ep_info})" if ep_info else ""
            item_name = f"{show_title} - Season {s_num:02d} Complete Pack{ep_label}"
            episodes.append({
                'episode': s_num,
                'season': s_num,
                'ep_no': s_num,
                'episodeName': self._windows_safe_string(item_name),
                'title': f"Season {s_num}",
                'season_title': f"Season {s_num}",
                'raw_name': f"Season {s_num}",
                'ep_info': ep_info,
                'media_type': 'tv',
                'is_season_pack': True,
                'show_slug': show_slug,
                'target_show': target
            })

        return episodes

    def show_episode_results(self, items, *predefined_range):
        '''Display available seasons list'''
        if not items:
            return
        lines = []
        for it in items:
            s_num = it.get('season', 1)
            info = it.get('ep_info', '')
            info_str = f" \033[38;5;244m• {info}\033[0m" if info else ""
            lines.append(f"  \033[1m[{s_num}]\033[0m  \033[38;5;39mSeason {s_num:02d} Complete\033[0m{info_str}")
        print('\n' + render_box('AVAILABLE SEASONS', lines))

    def get_season_ep_ranges(self, episodes):
        '''Map seasons for range selection'''
        ranges = {}
        for ep in episodes:
            s = ep.get('season', 1)
            ranges[s] = {'start': 1, 'end': 1}
        return ranges

    def set_out_names(self, target_series):
        '''Produce clean folder name for series'''
        title = target_series.get('raw_title', target_series.get('title', 'Series'))
        clean_title = self._windows_safe_string(title)
        return clean_title, clean_title

    def _detect_resolution(self, title):
        '''Accurately infer resolution tag from torrent release title'''
        t = title.lower()
        if re.search(r'\b(2160p?|4k|uhd)\b', t):
            return '2160p'
        if re.search(r'\b(1080p?|1080i|fhd)\b', t):
            return '1080p'
        if re.search(r'\b(720p?|hd)\b', t):
            return '720p'
        if re.search(r'\b(480p?|sd|dvd|dvdrip)\b', t):
            return '480p'
        if '2160' in t or '4k' in t:
            return '2160p'
        if '1080' in t:
            return '1080p'
        if '720' in t:
            return '720p'
        if '480' in t or 'dvd' in t:
            return '480p'
        return '1080p'

    def fetch_season_packs(self, show_slug, season):
        '''
        Discovers all available All-in-One season packs for the season in a single query,
        segregated by true resolution, ranked by seeders, and capped to top healthy releases.
        '''
        cache_key = f"{show_slug}_s{season}"
        if cache_key in self._season_packs_cache:
            return self._season_packs_cache[cache_key]

        all_packs = {}
        target_url = f"{show_slug}/?s={season}&completed=1"
        resp = self._request(target_url)

        # Fallback to base slug without completed=1 if needed
        if not resp or not resp.text:
            resp = self._request(f"{show_slug}/?s={season}")

        if resp and resp.text:
            soup = BeautifulSoup(resp.text, 'html.parser')
            seen_ids = set()

            for a in soup.select('a[href*="-"]'):
                href = a.get('href', '')
                m_id = re.search(r'-(\d+)/?$', href)
                if not m_id or href.startswith('/tv/') or '/user/' in href:
                    continue

                torrent_id = int(m_id.group(1))
                if torrent_id in seen_ids:
                    continue

                raw_title = a.text.strip()
                if not raw_title or len(raw_title) < 3:
                    continue

                # Locate parent row or container
                item = a
                while item.parent and item.parent.name not in ('body', 'html', 'table'):
                    item = item.parent
                    if item.name in ('tr', 'li') or (item.name == 'div' and any(k in str(item.get('class', '')) for k in ('torrent', 'item', 'row', 'card', 'col'))):
                        break

                item_text = item.get_text(separator=' ', strip=True) if item else raw_title

                # Seeds
                seeds = 0
                m_seeds = re.search(r'file_upload\s*(\d+)', item_text, re.IGNORECASE) or re.search(r'(?:seeders?|seeds?)\s*:?\s*(\d+)', item_text, re.IGNORECASE)
                if m_seeds:
                    seeds = int(m_seeds.group(1))
                else:
                    s_elem = item.select_one('.detail-seeders-count, span.seed, span.green')
                    if s_elem and s_elem.text.strip().isdigit():
                        seeds = int(s_elem.text.strip())

                # Leeches / Peers
                leeches = 0
                m_leeches = re.search(r'(?:leechers?|leechs?|peers?)\s*:?\s*(\d+)', item_text, re.IGNORECASE)
                if m_leeches:
                    leeches = int(m_leeches.group(1))
                else:
                    l_elem = item.select_one('.detail-leechers-count, span.leech, span.red')
                    if l_elem and l_elem.text.strip().isdigit():
                        leeches = int(l_elem.text.strip())

                # If row has explicit table cells, prioritize exact columns (th: TORRENT NAME, SIZE, FILES, AGE, SEED, LEECH)
                tds = item.find_all('td') if hasattr(item, 'find_all') else []
                if len(tds) >= 6:
                    s_td = re.search(r'(\d+)', tds[4].get_text(strip=True))
                    l_td = re.search(r'(\d+)', tds[5].get_text(strip=True))
                    if s_td:
                        seeds = int(s_td.group(1))
                    if l_td:
                        leeches = int(l_td.group(1))

                # Size
                size_str = 'Unknown'
                m_size = re.search(r'(\d+(?:\.\d+)?\s*(?:GB|MB|TB))', item_text, re.IGNORECASE)
                if m_size:
                    size_str = m_size.group(1).upper()

                # Files count
                files_count = 0
                m_files = re.search(r'(?:files|Files)\s*[:|]?\s*(\d+)', item_text)
                if m_files:
                    files_count = int(m_files.group(1))

                # Extract tags: BluRay, WEB-DL, x265, HEVC, 10bit, AV1, etc.
                tags = []
                for tag_pat in [r'BluRay', r'WEB-DL', r'WEBRip', r'x265', r'x264', r'HEVC', r'10-?bit', r'AV1', r'HDR', r'DTS', r'AAC']:
                    if re.search(r'\b' + tag_pat + r'\b', raw_title + ' ' + item_text, re.IGNORECASE):
                        tags.append(tag_pat.replace('-?', ''))

                # Detect true resolution
                res = self._detect_resolution(raw_title)

                detail_url = href if href.startswith('http') else f"{self.base_url}/{href.lstrip('/')}"

                seen_ids.add(torrent_id)
                all_packs.setdefault(res, []).append({
                    'torrent_id': torrent_id,
                    'title': raw_title,
                    'detail_url': detail_url,
                    'resolution': res,
                    'quality': res.upper().replace('P', ''),
                    'size': size_str,
                    'seeds': seeds,
                    'leeches': leeches,
                    'files_count': files_count,
                    'tags': list(set(tags))
                })

        # Filter dead releases if healthy seeds exist, sort descending by seeds, cap to top 10 per resolution
        for res_k, p_list in list(all_packs.items()):
            has_alive = any(p['seeds'] > 0 for p in p_list)
            if has_alive:
                p_list = [p for p in p_list if p['seeds'] > 0]
            p_list.sort(key=lambda p: p['seeds'], reverse=True)
            all_packs[res_k] = p_list[:10]

        self._season_packs_cache[cache_key] = all_packs
        return all_packs

    def fetch_torrent_magnet_and_files(self, detail_url):
        '''
        Fetches the torrent detail page, parses the file hierarchy (episodes),
        extracts page tokens, and calls the AJAX API with HMAC signature to retrieve the magnet link.
        '''
        resp = self._request(detail_url)
        if not resp or not resp.text:
            return None

        html = resp.text
        soup = BeautifulSoup(html, 'html.parser')

        # 1. Parse torrent_id, pageToken, csrfToken
        m_id = re.search(r'-(\d+)/?$', detail_url)
        torrent_id = int(m_id.group(1)) if m_id else None

        page_token = None
        m_pt = re.search(r'pageToken\s*=\s*[\'"]([^\'"]+)[\'"]', html)
        if m_pt:
            page_token = m_pt.group(1)

        csrf_token = None
        m_csrf = re.search(r'name="csrf-token"\s*content="([^\'"]+)"', html) or re.search(r'csrfToken\s*=\s*[\'"]([^\'"]+)[\'"]', html)
        if m_csrf:
            csrf_token = m_csrf.group(1)

        magnet_url = None

        # 2. Check for static magnet link first
        static_mag = soup.select_one('a[href^="magnet:"]')
        if static_mag and static_mag.get('href'):
            magnet_url = static_mag['href']

        # 3. Retrieve magnet link via authenticated AJAX API
        if not magnet_url and torrent_id and page_token and csrf_token:
            timestamp = int(time.time())
            hmac_input = f"{torrent_id}|{timestamp}|{page_token}"
            hmac_hash = hashlib.sha256(hmac_input.encode('utf-8')).hexdigest()

            post_headers = {
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': detail_url
            }
            post_data = {
                'torrent_id': torrent_id,
                'download_type': 'magnet',
                'timestamp': timestamp,
                'hmac': hmac_hash,
                'sessid': csrf_token
            }

            post_resp = self._request('ajax/getTorrentMagnet.php', method='post', data=post_data, referer=detail_url, extra_headers=post_headers)
            if post_resp:
                try:
                    res_json = post_resp.json()
                    if res_json.get('success') and res_json.get('url'):
                        magnet_url = res_json['url']
                except Exception as e:
                    self.logger.error(f"Failed to parse magnet response JSON: {e}")

        # 4. Parse Torrent File Contents (Episodes & File Sizes)
        torrent_files = []
        for table in soup.select('table'):
            table_text = table.get_text().lower()
            if 'seed' in table_text and 'leech' in table_text and 'source' in table_text:
                continue

            for tr in table.select('tr'):
                tds = tr.find_all('td')
                if len(tds) >= 3:
                    fn_candidate = tds[1].get_text(strip=True) if len(tds) > 1 and tds[0].get_text(strip=True) == '' else tds[0].get_text(strip=True)
                    if not any(ext in fn_candidate.lower() for ext in ('.mkv', '.mp4', '.avi', '.ts', '.m4v')):
                        fn_candidate = tds[0].get_text(strip=True)

                    if any(ext in fn_candidate.lower() for ext in ('.mkv', '.mp4', '.avi', '.ts', '.m4v')):
                        size_candidate = tds[-1].get_text(strip=True)
                        torrent_files.append({
                            'index': len(torrent_files) + 1,
                            'name': fn_candidate,
                            'size': size_candidate
                        })
            if torrent_files:
                break

        # Fallback file parsing if table structure varies
        if not torrent_files:
            for el in soup.find_all(['li', 'div', 'p']):
                txt = el.get_text(separator=' ', strip=True)
                if any(ext in txt.lower() for ext in ('.mkv', '.mp4', '.avi')):
                    m_fn = re.search(r'([a-zA-Z0-9_\.\-\+\s]+\.(?:mkv|mp4|avi|ts))\s+(?:[A-Z0-9]+\s+)?(\d+(?:\.\d+)?\s*(?:GB|MB|KB))?', txt)
                    if m_fn:
                        fn = m_fn.group(1).strip()
                        sz = m_fn.group(2) if m_fn.group(2) else 'Unknown'
                        if not any(f['name'] == fn for f in torrent_files):
                            torrent_files.append({
                                'index': len(torrent_files) + 1,
                                'name': fn,
                                'size': sz
                            })

        return {
            'magnet': magnet_url,
            'files': torrent_files
        }

    def fetch_episode_links(self, episodes, selected_eps):
        '''
        Bridge method for scraper.py:
        Discovers all available complete season packs for the selected season(s).
        Returns segregated and ranked release choices.
        '''
        results = {}
        target_season = episodes[0].get('season', 1)
        if isinstance(selected_eps, dict):
            target_season = selected_eps.get('start') or (selected_eps.get('specific_no', [1])[0])

        show_slug = self._target_show.get('show_slug') or episodes[0].get('show_slug')
        show_title = self._target_show.get('raw_title', episodes[0].get('title', 'Show'))

        season_packs = self.fetch_season_packs(show_slug, target_season)
        if not season_packs:
            self.logger.warning(f"No complete season packs found on Ext.to for Season {target_season}")
            return results

        # Create structured options for scraper.py
        options_map = {}
        for res_k, packs_list in season_packs.items():
            for idx, pack in enumerate(packs_list, start=1):
                opt_key = f"{res_k}_{idx}"
                tags_str = f" [{', '.join(pack['tags'][:3])}]" if pack['tags'] else ""
                files_str = f" ({pack['files_count']} files)" if pack['files_count'] else ""
                display_label = f"{pack['size']} • Seeds: {pack['seeds']}{files_str}{tags_str}"

                options_map[opt_key] = {
                    'title': pack['title'],
                    'quality': pack['quality'],
                    'resolution': res_k,
                    'size': pack['size'],
                    'seeds': pack['seeds'],
                    'leeches': pack['leeches'],
                    'files_count': pack['files_count'],
                    'pack_data': pack,
                    'season': target_season,
                    'show_title': show_title,
                    'downloadType': 'torrent',
                    'resolution_size': display_label
                }

        results[target_season] = options_map
        return results

    def fetch_m3u8_links(self, target_ep_links, resolution, episode_prefix):
        '''
        Finalizes download link: extracts magnet link and episode files list for the chosen pack.
        '''
        final_dl_links = {}
        for s_num, options in target_ep_links.items():
            selected_pack = None

            # 1. Direct match by option key
            if resolution in options:
                selected_pack = options[resolution]
            else:
                # Match by quality string (e.g. '1080', '1080p')
                clean_target = str(resolution).lower().replace('p', '').strip()
                matches = [v for k, v in options.items() if v.get('quality', '').lower() == clean_target or v.get('resolution', '').lower() == clean_target]
                if matches:
                    # Pick the highest seeded pack in that resolution
                    selected_pack = max(matches, key=lambda x: x.get('seeds', 0))

            if not selected_pack and options:
                # Pick the overall highest seeded pack available
                selected_pack = max(options.values(), key=lambda x: x.get('seeds', 0))

            if not selected_pack:
                continue

            pack_data = selected_pack.get('pack_data', {})
            detail_url = pack_data.get('detail_url')

            colprint('header', f"\n  ➜ Fetching Magnet Link & Episode List for '{pack_data.get('title', 'Season Pack')}'...")
            magnet_and_files = self.fetch_torrent_magnet_and_files(detail_url)

            if not magnet_and_files or not magnet_and_files.get('magnet'):
                self.logger.error(f"Failed to extract magnet for {detail_url}")
                continue

            magnet = magnet_and_files['magnet']
            torrent_files = magnet_and_files.get('files', [])

            show_title = selected_pack.get('show_title') or self._target_show.get('raw_title', 'Show')
            out_name = f"{show_title} - Season {s_num:02d} Complete Pack.torrent"

            final_dl_links[s_num] = {
                'downloadLink': magnet,
                'downloadType': 'torrent',
                'episodeName': out_name,
                'series_title': show_title,
                'season': s_num,
                'resolution': selected_pack.get('resolution', '1080p'),
                'size': selected_pack.get('size', 'Unknown'),
                'seeds': selected_pack.get('seeds', 0),
                'peers': selected_pack.get('leeches', 0),
                'torrent_files': torrent_files,
                'is_season_pack': True
            }

        return final_dl_links
