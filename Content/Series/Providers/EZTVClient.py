import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from Core.BaseClient import BaseClient
from Core.commons import colprint, render_box

PUBLIC_TRACKERS = [
    'udp://open.demonii.com:1337/announce',
    'udp://tracker.openbittorrent.com:80',
    'udp://tracker.coppersurfer.tk:6969',
    'udp://glotorrents.pw:6969/announce',
    'udp://tracker.opentrackr.org:1337/announce',
    'udp://torrent.gresille.org:80/announce',
    'udp://p4p.arenabg.com:1337',
    'udp://tracker.leechers-paradise.org:6969',
    'udp://tracker.internetwarriors.net:1337',
    'udp://9.rarbg.to:2710/announce',
    'udp://9.rarbg.me:2710/announce',
    'udp://exodus.desync.com:6969',
    'udp://open.stealth.si:80/announce',
    'udp://tracker.torrent.eu.org:451/announce'
]


class EZTVClient(BaseClient):
    '''
    Client for TV Show Torrents (EZTV + Apibay / TVMaze).
    Provides high-speed 720p, 1080p, and 4K UHD torrents across all seasons & episodes.
    '''
    EZTV_MIRRORS = [
        'https://eztvx.to',
        'https://eztv.re',
        'https://eztv.wf',
        'https://eztv.tf',
        'https://eztv.yt'
    ]

    def __init__(self, config=None, session=None, series_type=None, content_filter=None):
        super().__init__(session=session)
        self.config = config or {}
        self.series_type = series_type or 'TV Shows'
        self.content_filter = content_filter
        self.active_base_url = None
        self._target_show = {}
        self._episodes_by_idx = {}
        self._eztv_cache = {}

    def _generate_magnet(self, info_hash, title):
        '''Build magnet link with public trackers'''
        encoded_title = urllib.parse.quote(title)
        tracker_args = "".join([f"&tr={urllib.parse.quote(t)}" for t in PUBLIC_TRACKERS])
        return f"magnet:?xt=urn:btih:{info_hash}&dn={encoded_title}{tracker_args}"

    def search(self, search_term):
        self.logger.info(f"Searching TV Shows for: {search_term}")
        results = {}
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

        try:
            r = self.req_session.get(f"https://api.tvmaze.com/search/shows?q={urllib.parse.quote(search_term)}", headers=headers, timeout=6)
            if r.status_code == 200:
                shows = r.json()
                for idx, item in enumerate(shows, start=1):
                    s = item.get('show', {})
                    name = s.get('name', 'Unknown')
                    prem = (s.get('premiered') or '')[:4]
                    rating = s.get('rating', {}).get('average')
                    genres = s.get('genres', [])
                    imdb_id = s.get('externals', {}).get('imdb')
                    show_id = s.get('id')

                    meta_parts = []
                    if rating:
                        meta_parts.append(f"★ {rating}")
                    if prem:
                        meta_parts.append(f"Year: {prem}")
                    if genres:
                        meta_parts.append(f"[{', '.join(genres[:3])}]")
                    if imdb_id:
                        meta_parts.append(f"IMDb: {imdb_id}")

                    card_title = f"{name} ({prem})" if prem else name
                    card_meta = " • ".join(meta_parts)

                    results[idx] = {
                        'title': card_title,
                        'raw_title': name,
                        'year': prem,
                        'rating': rating,
                        'genres': genres,
                        'imdb_id': imdb_id,
                        'show_id': show_id,
                        'media_type': 'tv',
                        'card_title': card_title,
                        'card_meta': card_meta
                    }
        except Exception as e:
            self.logger.error(f"Search failed: {e}")

        if not results:
            self.logger.warning(f"No TV Shows found for '{search_term}'")
            return None

        return results

    def fetch_episodes_list(self, target):
        self._target_show = target
        show_id = target.get('show_id')
        headers = {'User-Agent': 'Mozilla/5.0'}

        episodes = []
        try:
            r = self.req_session.get(f"https://api.tvmaze.com/shows/{show_id}/episodes", headers=headers, timeout=6)
            if r.status_code == 200:
                raw_eps = r.json()
                for idx, ep in enumerate(raw_eps, start=1):
                    s_num = ep.get('season', 1)
                    e_num = ep.get('number', 1)
                    ep_name = ep.get('name') or f"Episode {e_num}"
                    ep_data = {
                        'episode': idx,
                        'episodeName': self._windows_safe_string(f"S{s_num:02d}E{e_num:02d} - {ep_name}"),
                        'raw_name': ep_name,
                        'season': s_num,
                        'ep_no': e_num,
                        'media_type': 'tv',
                        'show_title': target.get('raw_title', target.get('title')),
                        'imdb_id': target.get('imdb_id')
                    }
                    episodes.append(ep_data)
                    self._episodes_by_idx[idx] = ep_data
        except Exception as e:
            self.logger.error(f"Failed to fetch episodes list: {e}")

        # Pre-fetch EZTV pages in background
        imdb_id = target.get('imdb_id')
        if imdb_id:
            self._preload_eztv(imdb_id)

        return episodes

    def _preload_eztv(self, imdb_id):
        clean_imdb = str(imdb_id).replace('tt', '')
        headers = {'User-Agent': 'Mozilla/5.0'}
        cached_torrents = []

        def fetch_page(page_num):
            for mirror in self.EZTV_MIRRORS:
                try:
                    r = self.req_session.get(f"{mirror}/api/get-torrents?imdb_id={clean_imdb}&limit=100&page={page_num}", headers=headers, timeout=4)
                    if r.status_code == 200:
                        return r.json().get('torrents', [])
                except Exception:
                    continue
            return []

        with ThreadPoolExecutor(max_workers=4) as ex:
            pages = ex.map(fetch_page, range(1, 6))
            for p in pages:
                cached_torrents.extend(p)

        self._eztv_cache[imdb_id] = cached_torrents

    def show_episode_results(self, items, *predefined_range):
        current_season = None
        for item in items:
            season = item.get('season', 1)
            if season != current_season:
                current_season = season
                self._colprint('header', f"\n--- Season {season} ---")
            self._colprint('results', f"  Episode {item.get('ep_no'):02d}: {item.get('raw_name')}")

    def _query_eztv_torrents(self, imdb_id):
        if not imdb_id:
            return []
        if imdb_id in self._eztv_cache:
            return self._eztv_cache[imdb_id]

        clean_imdb = str(imdb_id).replace('tt', '')
        headers = {'User-Agent': 'Mozilla/5.0'}
        for mirror in self.EZTV_MIRRORS:
            try:
                r = self.req_session.get(f"{mirror}/api/get-torrents?imdb_id={clean_imdb}&limit=100", headers=headers, timeout=4)
                if r.status_code == 200:
                    torrents = r.json().get('torrents', [])
                    if torrents:
                        self._eztv_cache[imdb_id] = torrents
                        return torrents
            except Exception:
                continue
        return []

    def _query_apibay_torrents(self, show_name, season, episode):
        headers = {'User-Agent': 'Mozilla/5.0'}
        clean_name = re.sub(r'[^a-zA-Z0-9 ]', '', show_name)
        short_name = re.sub(r'\b(of|the|a|an)\b', '', clean_name, flags=re.IGNORECASE).strip()
        queries = [
            f"{clean_name} S{season:02d}E{episode:02d}",
            f"{short_name} S{season:02d}E{episode:02d}"
        ]

        for q in queries:
            try:
                r = self.req_session.get(f"https://apibay.org/q.php?q={urllib.parse.quote(q)}&cat=200", headers=headers, timeout=4)
                if r.status_code == 200:
                    items = r.json()
                    if items and isinstance(items, list) and items[0].get('name') != 'No results returned':
                        return items
            except Exception:
                continue
        return []

    def _format_size(self, size_bytes):
        try:
            b = float(size_bytes)
            if b >= 1024 ** 3:
                return f"{b / (1024 ** 3):.2f} GB"
            elif b >= 1024 ** 2:
                return f"{b / (1024 ** 2):.1f} MB"
            return f"{b / 1024:.0f} KB"
        except Exception:
            return "Unknown"

    def _fetch_single_episode_link(self, episode):
        ep_idx = episode.get('episode', 1)
        ep_no = episode.get('ep_no', ep_idx)
        season = episode.get('season', 1)
        show_title = episode.get('show_title') or self._target_show.get('raw_title', 'Show')
        imdb_id = episode.get('imdb_id') or self._target_show.get('imdb_id')

        candidates = []

        # 1. Try EZTV Torrents (from cache or API)
        eztv_torrents = self._query_eztv_torrents(imdb_id)
        for t in eztv_torrents:
            if int(t.get('season', 0)) == season and int(t.get('episode', 0)) == ep_no:
                title = t.get('title', '')
                magnet = t.get('magnet_url')
                seeds = int(t.get('seeds', 0))
                peers = int(t.get('peers', 0))
                size_str = self._format_size(t.get('size_bytes', 0))

                q = '480'
                if '2160' in title or '4k' in title.lower():
                    q = '2160'
                elif '1080' in title:
                    q = '1080'
                elif '720' in title:
                    q = '720'

                candidates.append({
                    'quality': q,
                    'magnet': magnet,
                    'seeds': seeds,
                    'peers': peers,
                    'size': size_str,
                    'title': title
                })

        # 2. Try Apibay Torrents
        apibay_items = self._query_apibay_torrents(show_title, season, ep_no)
        for it in apibay_items:
            title = it.get('name', '')
            info_hash = it.get('info_hash', '')
            seeds = int(it.get('seeders', 0))
            peers = int(it.get('leechers', 0))
            size_str = self._format_size(it.get('size', 0))
            magnet = self._generate_magnet(info_hash, title)

            q = '480'
            if '2160' in title or '4k' in title.lower():
                q = '2160'
            elif '1080' in title:
                q = '1080'
            elif '720' in title:
                q = '720'

            candidates.append({
                'quality': q,
                'magnet': magnet,
                'seeds': seeds,
                'peers': peers,
                'size': size_str,
                'title': title
            })

        if not candidates:
            return ep_idx, None, {'error': f"No torrents found for S{season:02d}E{ep_no:02d}"}

        # Group by resolution, picking candidate with highest seeds
        resolution_links = {}
        by_res = {}
        for c in candidates:
            by_res.setdefault(c['quality'], []).append(c)

        for res_k, items_list in by_res.items():
            best = max(items_list, key=lambda x: x['seeds'])
            resolution_links[res_k] = {
                'downloadLink': best['magnet'],
                'downloadType': 'torrent',
                'resolution_size': f"{best['size']} • Seeds: {best['seeds']}",
                'torrent_info': best
            }

        return ep_idx, resolution_links, {}

    def fetch_episode_links(self, episodes, ep_ranges):
        download_links = {}
        display_prefix = 'Episode'

        # Filter target episodes based on ep_ranges
        target_eps = []
        if isinstance(ep_ranges, dict):
            if 'specific_no' in ep_ranges:
                spec = set(ep_ranges.get('specific_no', []))
                start = ep_ranges.get('start', 1)
                end = ep_ranges.get('end', len(episodes))
                target_eps = [e for e in episodes if e['episode'] in spec or (start <= e['episode'] <= end)]
            else:
                for s_num, s_range in ep_ranges.items():
                    s_spec = set(s_range.get('specific_no', []))
                    s_start = s_range.get('start', 1)
                    s_end = s_range.get('end', 999)
                    for e in episodes:
                        if e.get('season') == s_num:
                            if e.get('ep_no') in s_spec or (s_start <= e.get('ep_no') <= s_end):
                                target_eps.append(e)
        else:
            target_eps = episodes

        if not target_eps:
            target_eps = episodes

        with ThreadPoolExecutor(max_workers=min(8, len(target_eps))) as executor:
            results = list(executor.map(self._fetch_single_episode_link, target_eps))

        for ep_idx, link, err_dict in sorted(results, key=lambda x: float(x[0])):
            ep_item = self._episodes_by_idx.get(ep_idx, {})
            s_num = ep_item.get('season', 1)
            e_num = ep_item.get('ep_no', ep_idx)

            if link:
                download_links[ep_idx] = link
                info = f"  S{s_num:02d}E{e_num:02d}"
                for res_k, val in sorted(link.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0, reverse=True):
                    t_inf = val.get('torrent_info', {})
                    info += f" | {res_k}P ({t_inf.get('size', 'NA')} • {t_inf.get('seeds', 0)} seeds)"
                self._colprint('results', info)
            elif err_dict:
                self._show_episode_links(ep_idx, err_dict, display_prefix)

        return download_links

    def set_out_names(self, target_series):
        title = self._windows_safe_string(target_series.get('title', 'TV Show'))
        return title, f"{title} - "

    def fetch_m3u8_links(self, target_ep_links, resolution, episode_prefix):
        episode_links = {}

        for ep_idx, res_data in target_ep_links.items():
            res_key = str(resolution).replace('P', '').replace('p', '')
            res_dict = res_data.get(res_key, {})

            if not res_dict and res_data:
                # fallback to closest resolution
                res_key = next(iter(res_data.keys()))
                res_dict = res_data[res_key]

            selected_magnet = res_dict.get('downloadLink')
            t_info = res_dict.get('torrent_info', {})

            ep_item = self._episodes_by_idx.get(ep_idx, {})
            s_num = ep_item.get('season', 1)
            e_num = ep_item.get('ep_no', ep_idx)
            raw_ep_name = ep_item.get('raw_name', f"Episode {e_num}")

            title_clean = episode_prefix.rstrip(' -')
            title = f"{episode_prefix}S{s_num:02d}E{e_num:02d} - {raw_ep_name} [{res_key}P].mkv"
            seeds = t_info.get('seeds', 'N/A')
            peers = t_info.get('peers', 'N/A')
            size = t_info.get('size', 'Unknown')

            colprint('results', f"  S{s_num:02d}E{e_num:02d} | {res_key}P | Seeds: {seeds} | Peers: {peers} | Size: {size} | Magnet Ready")

            episode_links[ep_idx] = {
                'episode': f"{e_num:02d}",
                'season': s_num,
                'type': 'tv',
                'title': title_clean,
                'episodeName': title,
                'out_file': title,
                'downloadLink': selected_magnet,
                'downloadType': 'torrent',
                'resolution': f"{res_key}P",
                'subtitles': [],
                'size': size,
                'seeds': seeds,
                'peers': peers,
                'info_hash': t_info.get('info_hash', '')
            }

        return episode_links
