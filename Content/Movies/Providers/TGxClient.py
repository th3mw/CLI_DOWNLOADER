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
    Client for TorrentGalaxy (TGx) Movie Torrents.
    Provides high-speed 4K UHD, 1080p, and 720p movie torrents with active seed/peer tracking.
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
        self.series_type = series_type or 'Movies'
        self.content_filter = content_filter
        self.name = 'TorrentGalaxy'
        self.provider_name = 'TorrentGalaxy'
        self.base_url = self.config.get('base_url', 'https://torrentgalaxy.one').rstrip('/')
        self.active_base_url = self.base_url
        self._target_movie = None
        self._search_cache = {}

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
        self.logger.info(f"Searching TorrentGalaxy for: {search_term}")
        search_path = f"get-posts/keywords:{urllib.parse.quote_plus(search_term)}"
        html = self._get_page(search_path)

        if not html:
            self.logger.warning(f"No response from TorrentGalaxy for '{search_term}'")
            return None

        soup = BeautifulSoup(html, 'html.parser')
        rows = soup.select('.tgxtablerow')
        if not rows:
            self.logger.warning(f"No movie torrents found on TorrentGalaxy for '{search_term}'")
            return None

        results = {}
        raw_items = []

        for row in rows:
            title_elem = row.select_one('a.txlight[title], a[href*="/post-detail/"]')
            if not title_elem:
                continue

            raw_title = title_elem.get('title') or title_elem.text.strip()
            detail_path = title_elem.get('href') or ''

            # Exclude non-movie / music / software if in movies mode
            cat_elem = row.select_one('.tgxtablecell a[href*="category:"]')
            cat_name = cat_elem.text.strip().lower() if cat_elem else ''
            if cat_name in ['music', 'software', 'games', 'ebooks']:
                continue

            # Parse size
            size_elem = row.select_one('.badge-secondary, span.badge')
            size = size_elem.text.strip() if size_elem else 'Unknown'

            # Parse seeds and peers
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

            # Parse quality
            quality = '1080'
            if re.search(r'\b(2160p|4k|uhd)\b', raw_title, re.I):
                quality = '2160'
            elif re.search(r'\b(1080p|1080i|fhd)\b', raw_title, re.I):
                quality = '1080'
            elif re.search(r'\b(720p|hd)\b', raw_title, re.I):
                quality = '720'
            elif re.search(r'\b(480p|sd)\b', raw_title, re.I):
                quality = '480'

            # Parse year
            year_match = re.search(r'\b(19\d\d|20\d\d)\b', raw_title)
            year = year_match.group(1) if year_match else None

            # Clean display title
            clean_name = re.split(r'\b(19\d\d|20\d\d|2160p|1080p|720p|480p|web|bluray|h264|x264|hevc|x265)\b', raw_title, flags=re.I)[0]
            clean_name = clean_name.replace('.', ' ').replace('_', ' ').strip(' -')
            if not clean_name:
                clean_name = raw_title

            raw_items.append({
                'raw_title': raw_title,
                'clean_title': clean_name,
                'detail_path': detail_path,
                'size': size,
                'seeds': seeds,
                'peers': peers,
                'quality': quality,
                'year': year
            })

        if not raw_items:
            return None

        # Sort by seeds descending
        raw_items.sort(key=lambda x: x['seeds'], reverse=True)

        for idx, item in enumerate(raw_items[:15], start=1):
            meta_parts = []
            if item['year']:
                meta_parts.append(f"Year: {item['year']}")
            meta_parts.append(f"Quality: {item['quality']}P")
            meta_parts.append(f"Size: {item['size']}")
            meta_parts.append(f"Seeds: {item['seeds']}")
            meta_parts.append(f"Peers: {item['peers']}")

            card_title = item['raw_title']
            card_meta = " • ".join(meta_parts)

            results[idx] = {
                'title': f"{item['clean_title']} ({item['year']})" if item['year'] else item['clean_title'],
                'raw_title': item['raw_title'],
                'detail_path': item['detail_path'],
                'year': item['year'],
                'quality': item['quality'],
                'size': item['size'],
                'seeds': item['seeds'],
                'peers': item['peers'],
                'media_type': 'movie',
                'all_items': raw_items,
                'card_title': card_title,
                'card_meta': card_meta
            }

        return results

    def fetch_episodes_list(self, target):
        '''Movies are single entities - return 1 episode item'''
        self._target_movie = target
        title = target.get('title')
        return [{
            'episode': 1,
            'episodeName': self._windows_safe_string(f"{title}"),
            'media_type': 'movie',
            'season': 1,
            'ep_no': 1,
            'target_movie': target
        }]

    def show_episode_results(self, items, *predefined_range):
        '''Display episode overview'''
        for item in items:
            self._colprint('results', f"Movie: {item.get('episodeName')}")

    def _fetch_single_episode_link(self, episode):
        ep_no = episode.get('episode', 1)
        target = episode.get('target_movie') or self._target_movie or {}
        all_items = target.get('all_items', [target])

        # Group items by quality (2160, 1080, 720, 480) picking the best seeded item per quality
        qual_groups = {}
        for it in all_items:
            q = it.get('quality', '1080')
            if q not in qual_groups:
                qual_groups[q] = it

        # Always ensure the chosen target item is included
        target_q = target.get('quality', '1080')
        qual_groups[target_q] = target

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
            return ep_no, None, {'error': 'Failed to resolve magnet links for selected movie'}

        self._update_scraper_dict(ep_no, episode)
        self._update_scraper_dict(ep_no, {
            'streamLink': next(iter(resolution_links.values())).get('downloadLink'),
            'refererLink': self.base_url,
            'subtitles': {}
        })

        return ep_no, resolution_links, {}

    def fetch_episode_links(self, episodes, ep_ranges):
        download_links = {}
        for ep in episodes:
            ep_no, link, err_dict = self._fetch_single_episode_link(ep)
            if link:
                download_links[ep_no] = link
            elif err_dict:
                self._show_episode_links(ep_no, err_dict, 'Movie')
        return download_links

    def set_out_names(self, target_series):
        title = self._windows_safe_string(target_series.get('title', 'Movie'))
        return title, f"{title} - "

    def fetch_m3u8_links(self, target_ep_links, resolution, episode_prefix):
        '''Return resolved magnet download items for selected resolution'''
        episode_links = {}

        for ep_no, res_data in target_ep_links.items():
            res_key = str(resolution).replace('P', '').replace('p', '')
            res_dict = res_data.get(res_key, {})

            if not res_dict and res_data:
                res_key = next(iter(res_data.keys()))
                res_dict = res_data[res_key]

            selected_magnet = res_dict.get('downloadLink')
            t_info = res_dict.get('torrent_info', {})

            title_clean = episode_prefix.rstrip(' -')
            title = f"{episode_prefix}{ep_no:02d} [{res_key}P].mkv"
            seeds = t_info.get('seeds', 'N/A')
            peers = t_info.get('peers', 'N/A')
            size = t_info.get('size', 'Unknown')

            colprint('results', f"  Movie | {res_key}P | Seeds: {seeds} | Peers: {peers} | Size: {size} | Magnet Ready")

            episode_links[ep_no] = {
                'episode': f"{ep_no:02d}",
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
