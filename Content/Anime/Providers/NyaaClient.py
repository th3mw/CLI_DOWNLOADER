import re
import urllib.parse
import xml.etree.ElementTree as ET
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


class NyaaClient(BaseClient):
    '''
    Client for Anime Torrents (Nyaa.si + Kitsu API).
    Provides fast 720p, 1080p, and 4K UHD anime torrents with batch & single episode support.
    '''
    NYAA_MIRRORS = [
        'https://nyaa.si',
        'https://nyaa.land',
        'https://nyaa.net'
    ]

    def __init__(self, config=None, session=None, series_type=None, content_filter=None):
        super().__init__(session=session)
        self.config = config or {}
        self.series_type = series_type or 'Anime'
        self.content_filter = content_filter
        self.active_base_url = None
        self._target_anime = {}
        self._episodes_by_idx = {}

    def _generate_magnet(self, info_hash, title):
        '''Build magnet link with info_hash and public trackers'''
        encoded_title = urllib.parse.quote(title)
        tracker_args = "".join([f"&tr={urllib.parse.quote(t)}" for t in PUBLIC_TRACKERS])
        return f"magnet:?xt=urn:btih:{info_hash}&dn={encoded_title}{tracker_args}"

    def search(self, search_term):
        self.logger.info(f"Searching Anime for: {search_term}")
        results = {}
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

        try:
            r = self.req_session.get(f"https://kitsu.io/api/edge/anime?filter[text]={urllib.parse.quote(search_term)}&page[limit]=10", headers=headers, timeout=6)
            if r.status_code == 200:
                data = r.json().get('data', [])
                for idx, item in enumerate(data, start=1):
                    attr = item.get('attributes', {})
                    canonical = attr.get('canonicalTitle') or 'Unknown'
                    titles = attr.get('titles', {})
                    en_title = titles.get('en') or titles.get('en_jp') or canonical
                    jp_title = titles.get('ja_jp') or ''
                    
                    prem_year = (attr.get('startDate') or '')[:4]
                    rating = attr.get('averageRating')
                    score = f"★ {float(rating)/10:.1f}" if rating else None
                    ep_count = attr.get('episodeCount') or '?'
                    subtype = (attr.get('subtype') or 'TV').upper()

                    meta_parts = []
                    if score: meta_parts.append(score)
                    if prem_year: meta_parts.append(f"Year: {prem_year}")
                    meta_parts.append(f"[{subtype}]")
                    meta_parts.append(f"Eps: {ep_count}")

                    card_title = f"{en_title} ({prem_year})" if prem_year else en_title
                    card_meta = " • ".join(meta_parts)

                    results[idx] = {
                        'title': card_title,
                        'raw_title': en_title,
                        'canonical_title': canonical,
                        'jp_title': jp_title,
                        'year': prem_year,
                        'score': score,
                        'episodes_count': ep_count,
                        'type': subtype,
                        'media_type': 'anime',
                        'card_title': card_title,
                        'card_meta': card_meta
                    }
        except Exception as e:
            self.logger.warning(f"Kitsu search failed/timed out ({e}), falling back to direct Nyaa search")

        if not results:
            # Fallback: Query Nyaa directly for the search term
            nyaa_items = self._query_nyaa(search_term)
            if nyaa_items:
                results[1] = {
                    'title': f"{search_term} (Nyaa Releases)",
                    'raw_title': search_term,
                    'canonical_title': search_term,
                    'jp_title': '',
                    'year': '2024',
                    'score': None,
                    'episodes_count': '12',
                    'type': 'ANIME',
                    'media_type': 'anime',
                    'card_title': f"{search_term} (Nyaa Releases)",
                    'card_meta': f"[ANIME] • Releases: {len(nyaa_items)}"
                }

        if not results:
            self.logger.warning(f"No Anime found for '{search_term}'")
            return None

        return results

    def fetch_episodes_list(self, target):
        self._target_anime = target
        eps_count = target.get('episodes_count')
        try:
            total_eps = int(eps_count) if str(eps_count).isdigit() and int(eps_count) > 0 else 12
        except Exception:
            total_eps = 12

        episodes = []
        for i in range(1, total_eps + 1):
            ep_data = {
                'episode': i,
                'episodeName': self._windows_safe_string(f"{target.get('raw_title', 'Anime')} - {i:02d}"),
                'raw_name': f"Episode {i:02d}",
                'season': 1,
                'ep_no': i,
                'media_type': 'anime',
                'show_title': target.get('raw_title', target.get('title')),
                'canonical_title': target.get('canonical_title')
            }
            episodes.append(ep_data)
            self._episodes_by_idx[i] = ep_data

        return episodes

    def show_episode_results(self, items, *predefined_range):
        if not items:
            return
        if len(items) <= 24:
            for item in items:
                self._colprint('results', f"  Episode: {item.get('episodeName')}")
        else:
            first_ep = items[0].get('episode', 1)
            last_ep = items[-1].get('episode', len(items))
            self._colprint('results', f"  Episodes {first_ep:02d} – {last_ep:02d} ({len(items)} episodes ready)")

    def _query_nyaa(self, query):
        headers = {'User-Agent': 'Mozilla/5.0'}
        for mirror in self.NYAA_MIRRORS:
            try:
                url = f"{mirror}/?page=rss&q={urllib.parse.quote(query)}&c=1_2&f=0"
                r = self.req_session.get(url, headers=headers, timeout=5)
                if r.status_code == 200:
                    root = ET.fromstring(r.text)
                    channel = root.find('channel')
                    items = channel.findall('item') if channel is not None else []
                    ns = {'nyaa': 'https://nyaa.si/xmlns/nyaa'}
                    results = []
                    for it in items:
                        title = it.find('title').text if it.find('title') is not None else ''
                        seeds = int(it.find('nyaa:seeders', ns).text) if it.find('nyaa:seeders', ns) is not None else 0
                        peers = int(it.find('nyaa:leechers', ns).text) if it.find('nyaa:leechers', ns) is not None else 0
                        size = it.find('nyaa:size', ns).text if it.find('nyaa:size', ns) is not None else 'Unknown'
                        info_hash = it.find('nyaa:infoHash', ns).text if it.find('nyaa:infoHash', ns) is not None else ''
                        results.append({'title': title, 'seeds': seeds, 'peers': peers, 'size': size, 'hash': info_hash})
                    if results:
                        return results
            except Exception:
                continue
        return []

    def _fetch_single_episode_link(self, episode):
        ep_no = episode.get('ep_no') or episode.get('episode', 1)
        raw_title = episode.get('show_title') or self._target_anime.get('raw_title', 'Anime')
        canon_title = episode.get('canonical_title') or self._target_anime.get('canonical_title')

        clean_title = re.sub(r'[^a-zA-Z0-9 ]', '', raw_title)
        clean_canon = re.sub(r'[^a-zA-Z0-9 ]', '', canon_title) if canon_title else None

        queries = [
            f"{clean_title} - {ep_no:02d}",
            f"{clean_title} {ep_no:02d}",
            f"{clean_title} E{ep_no:02d}"
        ]
        if clean_canon and clean_canon.lower() != clean_title.lower():
            queries.append(f"{clean_canon} - {ep_no:02d}")
            queries.append(f"{clean_canon} {ep_no:02d}")

        raw_items = []
        for q in queries:
            items = self._query_nyaa(q)
            if items:
                raw_items = items
                break

        if not raw_items:
            return ep_no, None, {'error': f"No torrents found for Episode {ep_no:02d}"}

        candidates = []
        for it in raw_items:
            title = it.get('title', '')
            info_hash = it.get('hash', '')
            seeds = int(it.get('seeds', 0))
            peers = int(it.get('peers', 0))
            size = it.get('size', 'Unknown')
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
                'size': size,
                'title': title
            })

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

        return ep_no, resolution_links, {}

    def fetch_episode_links(self, episodes, ep_ranges):
        download_links = {}
        display_prefix = 'Episode'

        # Filter target episodes
        target_eps = []
        if isinstance(ep_ranges, dict):
            if 'specific_no' in ep_ranges:
                spec = set(ep_ranges.get('specific_no', []))
                start = ep_ranges.get('start', 1)
                end = ep_ranges.get('end', len(episodes))
                target_eps = [e for e in episodes if e['episode'] in spec or (start <= e['episode'] <= end)]
            else:
                target_eps = episodes
        else:
            target_eps = episodes

        if not target_eps:
            target_eps = episodes

        with ThreadPoolExecutor(max_workers=min(8, len(target_eps))) as executor:
            results = list(executor.map(self._fetch_single_episode_link, target_eps))

        for ep_no, link, err_dict in sorted(results, key=lambda x: float(x[0])):
            if link:
                download_links[ep_no] = link
                info = f"  Episode: {ep_no:02d}"
                for res_k, val in sorted(link.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0, reverse=True):
                    t_inf = val.get('torrent_info', {})
                    info += f" | {res_k}P ({t_inf.get('size', 'NA')} • {t_inf.get('seeds', 0)} seeds)"
                self._colprint('results', info)
            elif err_dict:
                self._show_episode_links(ep_no, err_dict, display_prefix)

        return download_links

    def set_out_names(self, target_series):
        title = self._windows_safe_string(target_series.get('title', 'Anime'))
        return title, f"{title} - "

    def fetch_m3u8_links(self, target_ep_links, resolution, episode_prefix):
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
            title = f"{title_clean} - S01 - E{ep_no:02d} - {res_key}P.mkv"
            seeds = t_info.get('seeds', 'N/A')
            peers = t_info.get('peers', 'N/A')
            size = t_info.get('size', 'Unknown')

            colprint('results', f"  Episode: {ep_no:02d} | {res_key}P | Seeds: {seeds} | Peers: {peers} | Size: {size} | Magnet Ready")

            episode_links[ep_no] = {
                'episode': f"{ep_no:02d}",
                'season': 1,
                'type': 'anime',
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
