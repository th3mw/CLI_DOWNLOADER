import urllib.parse
from urllib.parse import quote_plus
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


class YTSClient(BaseClient):
    '''
    Client for YTS (YIFY) Movie Torrents API.
    Provides fast, high-quality 720p, 1080p, and 4K UHD torrents with seed/peer metrics.
    '''
    MIRRORS = [
        'https://yts.lt',
        'https://yts.ag',
        'https://yts.am',
        'https://yts.do',
        'https://yts.mx'
    ]

    def __init__(self, config=None, session=None, series_type=None, content_filter=None):
        super().__init__(session=session)
        self.config = config or {}
        self.series_type = series_type or 'Movies'
        self.content_filter = content_filter
        self.name = 'YTS'
        self.provider_name = 'YTS'
        self.active_base_url = None
        self._chosen_torrent = None

    def _get_api_response(self, endpoint, params=None):
        '''Try mirrors in sequence until a valid JSON response is received'''
        mirrors = [self.active_base_url] + [m for m in self.MIRRORS if m != self.active_base_url] if self.active_base_url else self.MIRRORS
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        for mirror in mirrors:
            if not mirror:
                continue
            url = f"{mirror.rstrip('/')}/{endpoint.lstrip('/')}"
            try:
                r = self.req_session.get(url, params=params, headers=headers, timeout=4)
                if r.status_code == 200:
                    resp = r.json()
                    if resp and isinstance(resp, dict) and resp.get('status') == 'ok':
                        self.active_base_url = mirror
                        return resp
            except Exception as e:
                self.logger.debug(f"Mirror {mirror} failed: {e}")
                continue
        return None

    def _generate_magnet(self, info_hash, movie_title):
        '''Build magnet link with info_hash, display name, and public tracker list'''
        encoded_title = urllib.parse.quote(movie_title)
        tracker_args = "".join([f"&tr={urllib.parse.quote(t)}" for t in PUBLIC_TRACKERS])
        return f"magnet:?xt=urn:btih:{info_hash}&dn={encoded_title}{tracker_args}"

    def search(self, search_term):
        self.logger.info(f"Searching YTS for: {search_term}")
        data = self._get_api_response('api/v2/list_movies.json', params={
            'query_term': search_term,
            'sort_by': 'download_count',
            'limit': 15
        })

        if not data or not data.get('data', {}).get('movies'):
            self.logger.warning(f"No movies found on YTS for '{search_term}'")
            return None

        raw_movies = data['data']['movies']
        results = {}

        for idx, m in enumerate(raw_movies, start=1):
            title = m.get('title_english') or m.get('title', 'Unknown')
            year = m.get('year')
            rating = m.get('rating')
            genres = m.get('genres', [])
            torrents = m.get('torrents', [])

            qualities = list(dict.fromkeys([t.get('quality', '') for t in torrents if t.get('quality')]))
            q_str = ", ".join(qualities) if qualities else "720p, 1080p"

            meta_parts = []
            if rating and float(rating) > 0:
                meta_parts.append(f"★ {rating}")
            if year:
                meta_parts.append(f"Year: {year}")
            if genres:
                meta_parts.append(f"[{', '.join(genres[:3])}]")
            if q_str:
                meta_parts.append(f"Qualities: {q_str}")

            card_title = f"{title}"
            card_meta = " • ".join(meta_parts)

            results[idx] = {
                'title': f"{title} ({year})" if year else title,
                'raw_title': title,
                'year': year,
                'rating': rating,
                'genres': genres,
                'torrents': torrents,
                'id': m.get('id'),
                'media_type': 'movie',
                'card_title': card_title,
                'card_meta': card_meta
            }

        return results

    def fetch_episodes_list(self, target):
        '''Movies are single entities - return 1 episode item'''
        title = target.get('title')
        return [{
            'episode': 1,
            'episodeName': self._windows_safe_string(f"{title}"),
            'media_type': 'movie',
            'season': 1,
            'ep_no': 1,
            'torrents': target.get('torrents', []),
            'target_movie': target
        }]

    def show_episode_results(self, items, *predefined_range):
        '''Display episode list'''
        for item in items:
            self._colprint('results', f"Episode: {item.get('episodeName')}")

    def _fetch_single_episode_link(self, episode):
        ep_no = episode.get('episode', 1)
        torrents = episode.get('torrents', [])

        if not torrents:
            return ep_no, None, {'error': 'No torrents available for this title'}

        # Sort: 2160p, 1080p, 720p
        def sort_key(t):
            q = str(t.get('quality', '')).lower()
            seeds = int(t.get('seeds', 0))
            bonus = 1000 if 'bluray' in str(t.get('type', '')).lower() else 0
            if '2160' in q or '4k' in q:
                return 30000 + bonus + seeds
            if '1080' in q:
                return 20000 + bonus + seeds
            if '720' in q:
                return 10000 + bonus + seeds
            return seeds

        sorted_torrents = sorted(torrents, key=sort_key, reverse=True)

        variety_lines = []
        default_choice = 1
        for i, t in enumerate(sorted_torrents, start=1):
            q = str(t.get('quality', '1080p')).upper()
            t_type = t.get('type', 'bluray').capitalize()
            size = t.get('size', 'Unknown')
            seeds = t.get('seeds', 0)
            peers = t.get('peers', 0)
            rec = " (Recommended)" if ('1080' in q and default_choice == 1) else ""
            if rec and default_choice == 1:
                default_choice = i
            label = f"{q:<5} • {t_type:<6} ({size:>9}) • Seeds: {seeds:<4} | Peers: {peers:<4}{rec}"
            variety_lines.append(f"\033[1m[{i:2d}]\033[0m  {label}")

        print('\n' + render_box('AVAILABLE TORRENT QUALITIES', variety_lines))

        selected_idx = default_choice
        try:
            user_choice = self._colprint(
                'user_input',
                f"\n  ➜ Select torrent quality [1-{len(sorted_torrents)}] [default={default_choice}]: ",
                input_type='recurring',
                input_dtype='int'
            )
            if user_choice and 1 <= int(user_choice) <= len(sorted_torrents):
                selected_idx = int(user_choice)
        except Exception:
            selected_idx = default_choice

        chosen_t = sorted_torrents[selected_idx - 1]
        self._chosen_torrent = chosen_t

        q_clean = str(chosen_t.get('quality', '1080')).upper().replace('P', '')
        t_type = chosen_t.get('type', 'bluray').capitalize()
        size = chosen_t.get('size', 'Unknown')
        seeds = chosen_t.get('seeds', 0)
        peers = chosen_t.get('peers', 0)
        info_hash = chosen_t.get('hash', '')

        magnet = self._generate_magnet(info_hash, f"{episode.get('episodeName')} [{q_clean}P] [YTS]")

        colprint('results', f"  Selected: {q_clean}P • {t_type} ({size}) • Seeds: {seeds} | Peers: {peers}")

        # Return chosen resolution as the single selected resolution
        resolution_links = {
            q_clean: {
                'downloadLink': magnet,
                'downloadType': 'torrent',
                'resolution_size': f"{size} • Seeds: {seeds}",
                'torrent_info': chosen_t
            }
        }

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
            t_info = res_dict.get('torrent_info', getattr(self, '_chosen_torrent', {}))

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
