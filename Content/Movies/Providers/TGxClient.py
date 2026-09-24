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
    Groups torrent releases by distinct movie with single-card search results
    and unified multi-resolution selection (2160p, 1080p, 720p, 480p).
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

    def _clean_movie_title(self, raw_title):
        '''Extract clean movie name and release year from release title'''
        ym = re.search(r'\b(19\d\d|20\d\d)\b', raw_title)
        year = ym.group(1) if ym else None

        split_match = re.split(r'\b(19\d\d|20\d\d|2160p|1080p|720p|480p|web|bluray|h264|x264|hevc|x265|dvd|hdrip|bdrip)\b', raw_title, flags=re.I)
        name = split_match[0]
        name = re.sub(r'[\._\(\)\[\]]', ' ', name)
        name = re.sub(r'\s+', ' ', name).strip(' -')
        if not name:
            name = raw_title
        return name, year

    def _extract_release_tag(self, raw_title):
        '''Extract release tags such as codec, audio, source from raw title'''
        split_parts = re.split(r'\b(19\d\d|20\d\d|2160p|1080p|720p|480p)\b', raw_title, flags=re.I)
        if len(split_parts) >= 3:
            tag = ' '.join(split_parts[2:])
        else:
            tag = raw_title
        tag = re.sub(r'[\._\[\]\(\)]', ' ', tag)
        tag = re.sub(r'\s+', ' ', tag).strip(' -')
        return tag[:40] if tag else 'Release'

    def search(self, search_term):
        self.logger.info(f"Searching TorrentGalaxy for: {search_term}")
        search_path = f"get-posts/keywords:{urllib.parse.quote_plus(search_term)}"
        html = self._get_page(search_path)

        soup = BeautifulSoup(html, 'html.parser') if html else None
        rows = soup.select('.tgxtablerow') if soup else []

        # Fallback if no results and search term starts with article (e.g. 'The ')
        if not rows:
            alt_term = re.sub(r'^(the|a|an)\s+', '', search_term, flags=re.I).strip()
            if alt_term and alt_term.lower() != search_term.lower():
                self.logger.debug(f"Retrying TGx search with alt term: '{alt_term}'")
                search_path_alt = f"get-posts/keywords:{urllib.parse.quote_plus(alt_term)}"
                html_alt = self._get_page(search_path_alt)
                if html_alt:
                    soup = BeautifulSoup(html_alt, 'html.parser')
                    rows = soup.select('.tgxtablerow')

        if not rows:
            self.logger.warning(f"No movie torrents found on TorrentGalaxy for '{search_term}'")
            return None

        movie_groups = {}

        for row in rows:
            title_elem = row.select_one('a.txlight[title], a[href*="/post-detail/"]')
            if not title_elem:
                continue

            raw_title = title_elem.get('title') or title_elem.text.strip()
            detail_path = title_elem.get('href') or ''

            # Exclude non-movie categories
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

            clean_name, year = self._clean_movie_title(raw_title)
            group_key = (clean_name.lower(), year)

            release_item = {
                'raw_title': raw_title,
                'clean_title': clean_name,
                'detail_path': detail_path,
                'size': size,
                'seeds': seeds,
                'peers': peers,
                'quality': quality,
                'year': year
            }

            if group_key not in movie_groups:
                movie_groups[group_key] = {
                    'clean_title': clean_name,
                    'year': year,
                    'all_releases': []
                }

            movie_groups[group_key]['all_releases'].append(release_item)

        if not movie_groups:
            return None

        # Sort movie groups by highest top seed
        sorted_groups = sorted(
            movie_groups.values(),
            key=lambda g: max(r['seeds'] for r in g['all_releases']),
            reverse=True
        )

        results = {}

        for idx, g in enumerate(sorted_groups[:15], start=1):
            clean_title = g['clean_title']
            year = g['year']
            all_rels = g['all_releases']

            # Deduplicate and sort releases by quality then seeds
            def rel_sort_key(r):
                q = r['quality']
                q_val = 30000 if q == '2160' else (20000 if q == '1080' else (10000 if q == '720' else 0))
                return q_val + r['seeds']

            sorted_rels = sorted(all_rels, key=rel_sort_key, reverse=True)
            avail_qualities = list(dict.fromkeys([r['quality'] for r in sorted_rels]))

            q_str = ", ".join([f"{q}p" for q in avail_qualities])
            top_seeds = max(r['seeds'] for r in sorted_rels)

            meta_parts = []
            if year:
                meta_parts.append(f"Year: {year}")
            meta_parts.append(f"Torrents: {len(sorted_rels)}")
            meta_parts.append(f"Qualities: {q_str}")
            meta_parts.append(f"Top Seeds: {top_seeds}")

            movie_display_title = f"{clean_title} ({year})" if year else clean_title

            results[idx] = {
                'title': movie_display_title,
                'raw_title': clean_title,
                'year': year,
                'qualities': avail_qualities,
                'all_releases': sorted_rels,
                'media_type': 'movie',
                'card_title': movie_display_title,
                'card_meta': " • ".join(meta_parts)
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
            'target_movie': target,
            'all_releases': target.get('all_releases', [])
        }]

    def show_episode_results(self, items, *predefined_range):
        '''Display episode overview'''
        for item in items:
            self._colprint('results', f"Movie: {item.get('episodeName')}")

    def _fetch_single_episode_link(self, episode):
        ep_no = episode.get('episode', 1)
        target = episode.get('target_movie') or self._target_movie or {}
        all_releases = episode.get('all_releases') or target.get('all_releases', [])

        if not all_releases:
            return ep_no, None, {'error': 'No releases available for this movie'}

        # Group releases by quality and select diverse top-seeded releases
        by_quality = {}
        for r in all_releases:
            q = str(r.get('quality', '1080'))
            by_quality.setdefault(q, []).append(r)

        for q in by_quality:
            by_quality[q].sort(key=lambda x: x.get('seeds', 0), reverse=True)

        chosen_releases = []
        quality_quotas = {'1080': 5, '720': 4, '2160': 4, '480': 2}
        pref_order = ['1080', '720', '2160', '480']

        for q in pref_order:
            if q in by_quality:
                quota = quality_quotas.get(q, 3)
                chosen_releases.extend(by_quality[q][:quota])
        for q, rels in by_quality.items():
            if q not in pref_order:
                chosen_releases.extend(rels[:2])

        # Deduplicate while preserving order
        seen_combos = set()
        deduped_chosen = []
        for r in chosen_releases:
            combo_key = (r['quality'], r.get('size'), r.get('seeds'), r.get('detail_path'))
            if combo_key not in seen_combos:
                seen_combos.add(combo_key)
                deduped_chosen.append(r)
            if len(deduped_chosen) >= 12:
                break
        chosen_releases = deduped_chosen

        resolution_links = {}

        def resolve_release_magnet(opt_key, rel_item):
            d_path = rel_item.get('detail_path')
            if not d_path:
                return None
            magnet = self._fetch_magnet_from_detail(d_path)
            if magnet:
                tag = self._extract_release_tag(rel_item.get('raw_title', ''))
                return opt_key, {
                    'downloadLink': magnet,
                    'downloadType': 'torrent',
                    'quality': f"{rel_item['quality']}P",
                    'size': rel_item.get('size', 'Unknown'),
                    'seeds': rel_item.get('seeds', 0),
                    'peers': rel_item.get('peers', 0),
                    'release_title': rel_item.get('raw_title', ''),
                    'resolution_size': f"{rel_item.get('size')} • Seeds: {rel_item.get('seeds')} • Peers: {rel_item.get('peers')} • {tag}",
                    'torrent_info': rel_item
                }
            return None

        with ThreadPoolExecutor(max_workers=min(8, len(chosen_releases))) as ex:
            futures = [ex.submit(resolve_release_magnet, f"{itm['quality']}_{i}", itm) for i, itm in enumerate(chosen_releases, start=1)]
            for fut in futures:
                res = fut.result()
                if res:
                    opt_k, res_dict = res
                    resolution_links[opt_k] = res_dict

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
        '''Return resolved magnet download items for selected release/resolution'''
        episode_links = {}

        for ep_no, res_data in target_ep_links.items():
            res_dict = None

            # 1. Exact option key match (e.g. '1080_1')
            if str(resolution) in res_data:
                res_dict = res_data[str(resolution)]
            else:
                # 2. Match by quality string (e.g. '1080', '720', '2160')
                clean_q = str(resolution).upper().replace('P', '')
                for k, v in res_data.items():
                    if str(v.get('quality', '')).upper().replace('P', '') == clean_q or k.startswith(clean_q):
                        res_dict = v
                        break

            if not res_dict and res_data:
                res_dict = next(iter(res_data.values()))

            selected_magnet = res_dict.get('downloadLink')
            t_info = res_dict.get('torrent_info', {})
            res_label = res_dict.get('quality', '1080P')

            title_clean = episode_prefix.rstrip(' -')
            title = f"{episode_prefix}{ep_no:02d} [{res_label}].mkv"
            seeds = res_dict.get('seeds', t_info.get('seeds', 'N/A'))
            peers = res_dict.get('peers', t_info.get('peers', 'N/A'))
            size = res_dict.get('size', t_info.get('size', 'Unknown'))

            colprint('results', f"  Movie | {res_label} | Seeds: {seeds} | Peers: {peers} | Size: {size} | Magnet Ready")

            episode_links[ep_no] = {
                'episode': f"{ep_no:02d}",
                'title': title_clean,
                'episodeName': title,
                'out_file': title,
                'downloadLink': selected_magnet,
                'downloadType': 'torrent',
                'resolution': res_label,
                'subtitles': [],
                'size': size,
                'seeds': seeds,
                'peers': peers,
                'info_hash': t_info.get('hash', '')
            }

        return episode_links
