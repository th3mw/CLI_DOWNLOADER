import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup
from Core.BaseClient import BaseClient
from Core.commons import colprint

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
    'udp://tracker.torrent.eu.org:451/announce',
    'udp://zer0day.ch:1337/announce'
]


class TGxClient(BaseClient):
    '''
    Client for TorrentGalaxy (TGx) TV Series Torrents.
    Provides high-speed 720p, 1080p, and 4K UHD torrents across all seasons & episodes.
    '''
    MIRRORS = [
        'https://torrentgalaxy.one',
        'https://torrentgalaxy.info',
        'https://torrentgalaxy.to',
        'https://tgx.rs',
        'https://tgx.to'
    ]

    def __init__(self, config=None, session=None, series_type=None, content_filter=None):
        super().__init__(session=session)
        self.config = config or {}
        self.series_type = series_type or 'TV Shows'
        self.content_filter = content_filter
        self.name = 'TorrentGalaxy'
        self.provider_name = 'TorrentGalaxy'
        self.base_url = self.config.get('base_url', 'https://torrentgalaxy.one').rstrip('/')
        self.active_base_url = self.base_url
        self._target_show = {}
        self._episodes_by_idx = {}
        self._tgx_cache = {}

    def _get_page(self, path):
        '''Try mirrors in sequence until a valid HTML page is returned'''
        mirrors = [self.active_base_url] + [m for m in self.MIRRORS if m != self.active_base_url]
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9'
        }
        for mirror in mirrors:
            if not mirror:
                continue
            url = f"{mirror.rstrip('/')}/{path.lstrip('/')}"
            try:
                r = self.req_session.get(url, headers=headers, timeout=6)
                if r.status_code == 200 and len(r.text) > 500:
                    self.active_base_url = mirror
                    return r.text
            except Exception as e:
                self.logger.debug(f"Mirror {mirror} failed for {path}: {e}")
                continue
        return None

    def _generate_magnet(self, info_hash, title):
        '''Build magnet link with info_hash, display name, and public tracker list'''
        encoded_title = urllib.parse.quote(title)
        tracker_args = "".join([f"&tr={urllib.parse.quote(t)}" for t in PUBLIC_TRACKERS])
        return f"magnet:?xt=urn:btih:{info_hash}&dn={encoded_title}{tracker_args}"

    def _fetch_magnet_from_detail(self, detail_path):
        '''Fetch magnet link directly from post detail page'''
        html = self._get_page(detail_path)
        if not html:
            return None
        soup = BeautifulSoup(html, 'html.parser')
        magnet_elem = soup.select_one('a[href^="magnet:"]')
        if magnet_elem and magnet_elem.get('href'):
            return magnet_elem['href']
        return None

    def search(self, search_term):
        self.logger.info(f"Searching TV Shows on TorrentGalaxy for: {search_term}")
        results = {}
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

        # Query TVMaze for accurate show catalog
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
            self.logger.error(f"TVMaze search failed: {e}")

        # Fallback to direct TGx search if TVMaze didn't yield results
        if not results:
            search_path = f"get-posts/keywords:{urllib.parse.quote_plus(search_term)}"
            html = self._get_page(search_path)
            if html:
                soup = BeautifulSoup(html, 'html.parser')
                rows = soup.select('.tgxtablerow')
                for idx, row in enumerate(rows[:10], start=1):
                    title_elem = row.select_one('a.txlight[title], a[href*="/post-detail/"]')
                    if not title_elem:
                        continue
                    raw_title = title_elem.get('title') or title_elem.text.strip()
                    detail_path = title_elem.get('href') or ''
                    size_elem = row.select_one('.badge-secondary, span.badge')
                    size = size_elem.text.strip() if size_elem else 'Unknown'

                    results[idx] = {
                        'title': raw_title,
                        'raw_title': raw_title,
                        'detail_path': detail_path,
                        'size': size,
                        'media_type': 'tv',
                        'card_title': raw_title,
                        'card_meta': f"Size: {size}"
                    }

        if not results:
            self.logger.warning(f"No TV Shows found on TorrentGalaxy for '{search_term}'")
            return None

        return results

    def fetch_episodes_list(self, target):
        self._target_show = target
        show_id = target.get('show_id')
        headers = {'User-Agent': 'Mozilla/5.0'}

        episodes = []
        if show_id:
            try:
                r = self.req_session.get(f"https://api.tvmaze.com/shows/{show_id}/episodes", headers=headers, timeout=6)
                if r.status_code == 200:
                    raw_eps = r.json()
                    for idx, ep in enumerate(raw_eps, start=1):
                        season = ep.get('season', 1)
                        ep_number = ep.get('number', idx)
                        ep_name = ep.get('name') or f"Episode {ep_number}"
                        label = f"{target.get('raw_title', 'Series')} - S{season:02d}E{ep_number:02d} - {ep_name}"
                        ep_key = f"s{season:02d}e{ep_number:02d}"

                        item = {
                            'episode': ep_key,
                            'ep_no': ep_number,
                            'season': season,
                            'episodeName': self._windows_safe_string(label),
                            'media_type': 'tv',
                            'title': ep_name,
                            'target_show': target
                        }
                        episodes.append(item)
                        self._episodes_by_idx[ep_key] = item
            except Exception as e:
                self.logger.error(f"Failed to fetch TVMaze episodes: {e}")

        if not episodes:
            # Single entry fallback
            title = target.get('title', 'TV Series')
            episodes.append({
                'episode': 's01e01',
                'ep_no': 1,
                'season': 1,
                'episodeName': self._windows_safe_string(f"{title} - S01E01"),
                'media_type': 'tv',
                'title': title,
                'target_show': target
            })

        return episodes

    def show_episode_results(self, items, *predefined_range):
        '''Display episode overview'''
        if not items:
            return
        if len(items) <= 24:
            for item in items:
                self._colprint('results', f"  {item.get('episodeName')}")
        else:
            first_ep = items[0].get('episode', 's01e01')
            last_ep = items[-1].get('episode', f"s01e{len(items):02d}")
            self._colprint('results', f"  Episodes {first_ep} – {last_ep} ({len(items)} episodes ready)")

    def _query_tgx_for_episode(self, show_name, season, ep_number):
        '''Search TGx for specific episode release torrents'''
        cache_key = f"{show_name}_s{season:02d}e{ep_number:02d}".lower()
        if cache_key in self._tgx_cache:
            return self._tgx_cache[cache_key]

        show_cache_key = f"show_{show_name}".lower()
        if show_cache_key not in self._tgx_cache:
            search_path = f"get-posts/keywords:{urllib.parse.quote_plus(show_name)}"
            html = self._get_page(search_path)
            rows = []
            if html:
                soup = BeautifulSoup(html, 'html.parser')
                rows = soup.select('.tgxtablerow')
            self._tgx_cache[show_cache_key] = rows

        rows = self._tgx_cache[show_cache_key]

        # If not in show cache, try specific episode query
        if not rows:
            query = f"{show_name} S{season:02d}E{ep_number:02d}"
            search_path = f"get-posts/keywords:{urllib.parse.quote_plus(query)}"
            html = self._get_page(search_path)
            if html:
                soup = BeautifulSoup(html, 'html.parser')
                rows = soup.select('.tgxtablerow')

        items = []

        ep_pattern = re.compile(rf'\bS0?{season}E0?{ep_number}\b', re.I)
        range_pattern = re.compile(rf'\bS0?{season}E(\d+)-(\d+)\b', re.I)
        season_pattern = re.compile(rf'\b(?:S0?{season}|Season[\s.]{season})\b', re.I)

        for row in rows:
            title_elem = row.select_one('a.txlight[title], a[href*="/post-detail/"]')
            if not title_elem:
                continue

            raw_title = title_elem.get('title') or title_elem.text.strip()
            detail_path = title_elem.get('href') or ''

            # Match against episode patterns
            is_match = False
            priority = 0

            if ep_pattern.search(raw_title):
                is_match = True
                priority = 100
            else:
                range_match = range_pattern.search(raw_title)
                if range_match:
                    try:
                        r_start = int(range_match.group(1))
                        r_end = int(range_match.group(2))
                        if r_start <= ep_number <= r_end:
                            is_match = True
                            priority = 50
                    except ValueError:
                        pass
                elif season_pattern.search(raw_title):
                    is_match = True
                    priority = 10

            if not is_match:
                continue

            size_elem = row.select_one('.badge-secondary, span.badge')
            size = size_elem.text.strip() if size_elem else 'Unknown'

            seed_elem = row.select_one('font[color="green"], span[style*="color:green"]')
            peer_elem = row.select_one('font[color="#ff0000"], span[style*="color:red"]')
            try:
                seeds = int(seed_elem.text.strip()) if seed_elem and seed_elem.text.strip().isdigit() else 0
            except ValueError:
                seeds = 0
            try:
                peers = int(peer_elem.text.strip()) if peer_elem and peer_elem.text.strip().isdigit() else 0
            except ValueError:
                peers = 0

            quality = '1080'
            if re.search(r'\b(2160p|4k|uhd)\b', raw_title, re.I):
                quality = '2160'
            elif re.search(r'\b(1080p|1080i|fhd)\b', raw_title, re.I):
                quality = '1080'
            elif re.search(r'\b(720p|hd)\b', raw_title, re.I):
                quality = '720'
            elif re.search(r'\b(480p|sd)\b', raw_title, re.I):
                quality = '480'

            items.append({
                'raw_title': raw_title,
                'detail_path': detail_path,
                'size': size,
                'seeds': seeds,
                'peers': peers,
                'quality': quality,
                'priority': priority
            })

        # Sort by priority (exact episode > range > season pack) then seed count
        items.sort(key=lambda x: (x['priority'], x['seeds']), reverse=True)
        self._tgx_cache[cache_key] = items
        return items

    def _fetch_single_episode_link(self, episode):
        ep_key = episode.get('episode', 's01e01')
        target = episode.get('target_show') or self._target_show or {}
        show_name = target.get('raw_title') or target.get('title', 'TV Series')
        season = episode.get('season', 1)
        ep_no = episode.get('ep_no', 1)

        tgx_items = self._query_tgx_for_episode(show_name, season, ep_no)
        if not tgx_items:
            return ep_key, None, {'error': f'No torrents found for S{season:02d}E{ep_no:02d}'}

        qual_groups = {}
        for it in tgx_items:
            q = it.get('quality', '1080')
            if q not in qual_groups:
                qual_groups[q] = it

        resolution_links = {}

        def resolve_item(q_key, itm):
            d_path = itm.get('detail_path')
            if not d_path:
                return None
            magnet = self._fetch_magnet_from_detail(d_path)
            if magnet:
                return q_key, {
                    'downloadLink': magnet,
                    'downloadType': 'torrent',
                    'resolution_size': f"{itm.get('size', 'Unknown')} • Seeds: {itm.get('seeds', 0)}",
                    'torrent_info': itm
                }
            return None

        with ThreadPoolExecutor(max_workers=min(4, len(qual_groups))) as ex:
            futures = [ex.submit(resolve_item, q, itm) for q, itm in qual_groups.items()]
            for fut in futures:
                res = fut.result()
                if res:
                    q_key, res_dict = res
                    resolution_links[q_key] = res_dict

        if not resolution_links:
            return ep_key, None, {'error': f'Failed to resolve magnet links for S{season:02d}E{ep_no:02d}'}

        self._update_scraper_dict(ep_key, episode)
        self._update_scraper_dict(ep_key, {
            'streamLink': next(iter(resolution_links.values())).get('downloadLink'),
            'refererLink': self.base_url,
            'subtitles': {}
        })

        return ep_key, resolution_links, {}

    def fetch_episode_links(self, episodes, ep_ranges):
        download_links = {}
        for ep in episodes:
            ep_key, link, err_dict = self._fetch_single_episode_link(ep)
            if link:
                download_links[ep_key] = link
            elif err_dict:
                self._show_episode_links(ep_key, err_dict, 'Series')
        return download_links

    def set_out_names(self, target_series):
        title = self._windows_safe_string(target_series.get('raw_title') or target_series.get('title', 'TV Series'))
        return title, f"{title} - "

    def get_season_ep_ranges(self, episodes):
        '''Return episode ranges organized by season'''
        season_ep_ranges = {}
        for ep in episodes:
            season = ep.get('season', 1)
            ep_no = ep.get('ep_no', 1)
            if season not in season_ep_ranges:
                season_ep_ranges[season] = {'start': ep_no, 'end': ep_no}
            else:
                season_ep_ranges[season]['start'] = min(season_ep_ranges[season]['start'], ep_no)
                season_ep_ranges[season]['end'] = max(season_ep_ranges[season]['end'], ep_no)
        return season_ep_ranges

    def fetch_m3u8_links(self, target_ep_links, resolution, episode_prefix):
        '''Return resolved magnet download items for selected resolution'''
        episode_links = {}

        for ep_key, res_data in target_ep_links.items():
            res_key = str(resolution).replace('P', '').replace('p', '')
            res_dict = res_data.get(res_key, {})

            if not res_dict and res_data:
                res_key = next(iter(res_data.keys()))
                res_dict = res_data[res_key]

            selected_magnet = res_dict.get('downloadLink')
            t_info = res_dict.get('torrent_info', {})

            ep_meta = self._episodes_by_idx.get(ep_key, {})
            season = ep_meta.get('season', 1)
            ep_no = ep_meta.get('ep_no', 1)

            title_clean = episode_prefix.rstrip(' -')
            title = f"{episode_prefix}S{season:02d}E{ep_no:02d} [{res_key}P].mkv"
            seeds = t_info.get('seeds', 'N/A')
            peers = t_info.get('peers', 'N/A')
            size = t_info.get('size', 'Unknown')

            colprint('results', f"  Series | S{season:02d}E{ep_no:02d} | {res_key}P | Seeds: {seeds} | Peers: {peers} | Size: {size} | Magnet Ready")

            episode_links[ep_key] = {
                'episode': f"S{season:02d}E{ep_no:02d}",
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
                'info_hash': t_info.get('hash', '')
            }

        return episode_links
