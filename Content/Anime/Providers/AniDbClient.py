import os
import re
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup as BS

from Core.BaseClient import BaseClient


class AniDbClient(BaseClient):
    '''
    Client for scraping and fetching anime HLS streams from AniDB (https://anidb.app/).
    '''
    def __init__(self, config=None, session=None, series_type=None, content_filter=None):
        config = config or {}
        super().__init__(config.get('request_timeout', 30) if isinstance(config, dict) else 30, session)
        self.client_name = 'anidb'
        self.name = 'AniDB'
        self.provider_name = 'AniDB'
        anidb_config = config.get('anidb', {}) if isinstance(config, dict) else {}
        self.base_url = anidb_config.get('base_url', 'https://anidb.app').rstrip('/')
        self.browse_url = anidb_config.get('search_url', f'{self.base_url}/browse?q=')
        self.suggestions_url = f'{self.base_url}/search/suggestions?q='
        self.episodes_url = f'{self.base_url}/api/frontend/anime/'
        self.languages_url = f'{self.base_url}/api/frontend/episode/'
        self.audio_preference = (config.get('audio_preference') or 'sub').lower()
        if self.audio_preference == 'dub':
            self.preferred_languages = ['eng', 'dub', 'jpn', 'sub']
        else:
            self.preferred_languages = ['jpn', 'sub', 'eng', 'dub']
        self.series_type = series_type
        self.content_filter = content_filter
        self.selector_strategy = anidb_config.get('alternate_resolution_selector', 'lowest') if isinstance(anidb_config, dict) else 'lowest'
        self.hls_size_accuracy = anidb_config.get('hls_size_accuracy', 0) if isinstance(anidb_config, dict) else 0

        # Set default session headers
        self.req_session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': f'{self.base_url}/',
            'Accept-Encoding': 'gzip, deflate',
        })

    def search(self, search_key: str, search_limit: int = 10) -> dict:
        '''
        Search for anime by keyword using /browse?q= and /search/suggestions fallback.
        Returns dict of indexed results with metadata.
        '''
        search_key = search_key.strip()
        encoded_query = quote(search_key)
        target_url = f'{self.browse_url}{encoded_query}'

        self.logger.debug(f'Searching AniDB for: {search_key} at {target_url}')
        resp_html = self._send_request(target_url, referer=f'{self.base_url}/')

        results = {}
        idx = 1

        if resp_html:
            soup = BS(resp_html, 'html.parser')
            cards = soup.select('a.anime-card')

            for card in cards:
                href = card.get('href', '')
                if not href or '/anime/' not in href:
                    continue

                if not href.startswith('http'):
                    href = f'{self.base_url}{href}'

                # Extract anime_id from slug-id
                slug_part = href.rstrip('/').split('/')[-1]
                anime_id_match = re.search(r'-(\d+)$', slug_part)
                anime_id = anime_id_match.group(1) if anime_id_match else slug_part

                title = card.get('title')
                if not title:
                    title_elem = card.select_one('p.text-xs, p.text-sm, p.font-semibold')
                    title = title_elem.get_text(strip=True) if title_elem else 'Unknown Title'

                # Extract badges (type, rating)
                type_badge = card.select_one('span.badge-orange, span.badge')
                anime_type = type_badge.get_text(strip=True) if type_badge else 'TV'

                score_badge = card.select_one('span.badge-gray')
                rating = score_badge.get_text(strip=True) if score_badge else ''

                results[idx] = {
                    'title': title,
                    'url': href,
                    'anime_id': anime_id,
                    'type': anime_type,
                    'rating': rating,
                }
                idx += 1
                if idx > search_limit:
                    break

        # Fallback to search suggestions endpoint if browse returned no cards
        if not results:
            self.logger.debug(f'Trying suggestions fallback for: {search_key}')
            sug_resp = self._send_request(f'{self.suggestions_url}{encoded_query}', referer=f'{self.base_url}/')
            if sug_resp:
                sug_soup = BS(sug_resp, 'html.parser')
                sug_items = sug_soup.select('a[data-search-item]')
                for item in sug_items:
                    href = item.get('href', '')
                    if not href or '/anime/' not in href:
                        continue
                    if not href.startswith('http'):
                        href = f'{self.base_url}{href}'

                    slug_part = href.rstrip('/').split('/')[-1]
                    anime_id_match = re.search(r'-(\d+)$', slug_part)
                    anime_id = anime_id_match.group(1) if anime_id_match else slug_part

                    title_el = item.select_one('p.font-medium, p.text-sm')
                    title = title_el.get_text(strip=True) if title_el else 'Unknown Title'

                    meta_el = item.select_one('p.text-xs, p.text-muted')
                    meta_text = meta_el.get_text(strip=True) if meta_el else ''
                    anime_type = meta_text.split('·')[0].strip() if '·' in meta_text else 'Anime'

                    results[idx] = {
                        'title': title,
                        'url': href,
                        'anime_id': anime_id,
                        'type': anime_type,
                        'rating': '',
                    }
                    idx += 1
                    if idx > search_limit:
                        break

        return results

    def fetch_episodes_list(self, target_series: dict) -> list:
        '''
        Fetch all available episodes for a selected anime series.
        Returns list of episode dicts.
        '''
        anime_id = target_series.get('anime_id')
        if not anime_id:
            return []

        url = f'{self.episodes_url}{anime_id}/episodes'
        self.logger.debug(f'Fetching episodes from {url}')
        resp_json = self._send_request(
            url,
            referer=target_series.get('url', f'{self.base_url}/'),
            extra_headers={'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'},
            return_type='json'
        )

        episodes = []
        if resp_json and isinstance(resp_json.get('episodes'), list):
            for ep_data in resp_json['episodes']:
                ep_no = ep_data.get('number', 0)
                ep_id = ep_data.get('id')
                num2 = ep_data.get('number2', 0)
                is_filler = ep_data.get('filler', False)
                ep_name = f'Episode {ep_no}' if not num2 or num2 == ep_no else f'Episode {ep_no}-{num2}'

                ep_dict = {
                    'episode': ep_no,
                    'episodeName': ep_name,
                    'episode_id': ep_id,
                    'number2': num2,
                    'filler': is_filler,
                    'title': target_series.get('title', ''),
                    'anime_id': anime_id,
                    'season': 1,
                    'type': 'anime'
                }
                self._update_scraper_dict(ep_no, ep_dict)
                episodes.append(ep_dict)

        # Ensure sorted by episode number
        episodes.sort(key=lambda x: x.get('episode', 0))
        return episodes

    def show_episode_results(self, items: list, *predefined_range):
        '''
        Display episode range selection in terminal.
        '''
        if not items:
            return
        if len(items) <= 24:
            for ep in items:
                ep_no = ep.get('episode')
                n2 = ep.get('number2')
                ep_label = f"  Episode {ep_no:02d}" if not n2 or n2 == ep_no else f"  Episode {ep_no:02d}–{n2:02d}"
                if ep.get('filler'):
                    ep_label += ' (Filler)'
                self._colprint('results', ep_label)
        else:
            first_ep = items[0].get('episode', 1)
            last_ep = items[-1].get('episode', len(items))
            self._colprint('results', f"  Episodes {first_ep:02d} – {last_ep:02d} ({len(items)} episodes ready)")

    def _fetch_single_episode_link(self, ep: dict):
        '''
        Fetch stream (HLS m3u8) links for a single episode.
        Returns (ep_no, m3u8_links_dict)
        '''
        ep_no = ep.get('episode')
        ep_id = ep.get('episode_id')
        if not ep_id:
            return ep_no, {'error': 'Episode ID missing'}

        # Fetch languages
        lang_url = f'{self.languages_url}{ep_id}/languages'
        lang_resp = self._send_request(
            lang_url,
            referer=f'{self.base_url}/anime/{ep.get("anime_id")}',
            extra_headers={'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'},
            return_type='json',
            silent=True
        )

        if not lang_resp or not isinstance(lang_resp.get('languages'), list) or not lang_resp['languages']:
            return ep_no, {'error': 'No audio languages available'}

        languages = lang_resp['languages']

        # Prioritize languages based on preference
        ordered_langs = []
        for pref in self.preferred_languages:
            for l in languages:
                code = l.get('code', '').lower()
                name = l.get('name', '').lower()
                if (pref in code or pref in name) and l not in ordered_langs:
                    ordered_langs.append(l)
        for l in languages:
            if l not in ordered_langs:
                ordered_langs.append(l)

        for lang in ordered_langs:
            embed_url = lang.get('embed_url')
            if not embed_url:
                continue

            embed_html = self._send_request(embed_url, referer=f'{self.base_url}/', silent=True)
            if not embed_html:
                continue

            m3u8_match = re.search(r'file:\s*[\'\"]([^\'\"]+master\.m3u8[^\'\"]*)[\'\"]', embed_html)
            if not m3u8_match:
                # General fallback for any .m3u8
                m3u8_match = re.search(r'file:\s*[\'\"]([^\'\"]+\.m3u8[^\'\"]*)[\'\"]', embed_html)

            if m3u8_match:
                master_m3u8_url = m3u8_match.group(1)
                referer = f'{self.base_url}/'
                m3u8_links = self._parse_m3u8_links(master_m3u8_url, referer)
                if m3u8_links:
                    return ep_no, m3u8_links
                else:
                    return ep_no, {
                        '720': {
                            'downloadLink': master_m3u8_url,
                            'downloadType': 'hls',
                            'refererLink': referer,
                            'duration': 0,
                        }
                    }

        return ep_no, {'error': 'Failed to resolve m3u8 link from embed players'}

    def fetch_episode_links(self, episodes: list, ep_ranges: dict) -> dict:
        '''
        Fetch download links for selected episodes in parallel.
        Returns dict: {ep_no: {'1080': {'downloadLink': ..., 'downloadType': 'hls', ...}, ...}}
        '''
        selected_eps = [ep for ep in episodes if self._is_episode_selected(ep.get('episode'), ep_ranges)]
        if not selected_eps:
            return {}

        target_links = {}
        with ThreadPoolExecutor(max_workers=min(8, len(selected_eps))) as executor:
            results = list(executor.map(self._fetch_single_episode_link, selected_eps))

        for ep_no, res_dict in sorted(results, key=lambda x: x[0]):
            target_links[ep_no] = res_dict

        return target_links

    def _is_episode_selected(self, ep_no, ep_ranges):
        '''Check if an episode number falls within selected ranges'''
        if ep_ranges is None:
            return True
        if isinstance(ep_ranges, dict):
            if 1 in ep_ranges and isinstance(ep_ranges[1], dict):
                ep_ranges = ep_ranges[1]

            if 'start' in ep_ranges and 'end' in ep_ranges:
                if ep_ranges['start'] <= ep_no <= ep_ranges['end']:
                    return True
            if 'specific_no' in ep_ranges and ep_no in ep_ranges['specific_no']:
                return True
            return False
        return True

    def set_out_names(self, target_series: dict):
        '''
        Set output directory and episode prefix.
        Returns: (target_dir, episode_prefix)
        '''
        title = self._windows_safe_string(target_series.get('title', 'Unknown'))
        series_dir = self._windows_safe_string(title)
        episode_prefix = f"{title} -"
        return series_dir, episode_prefix

    def get_season_ep_ranges(self, episodes: list) -> dict:
        '''
        Return episode ranges organized by season.
        AniDB anime episodes are grouped under season 1.
        '''
        season_ep_ranges = {}
        for ep in episodes:
            season = ep.get('season', 1)
            if season not in season_ep_ranges:
                season_ep_ranges[season] = {'start': ep['episode'], 'end': ep['episode']}
            else:
                season_ep_ranges[season]['start'] = min(season_ep_ranges[season]['start'], ep['episode'])
                season_ep_ranges[season]['end'] = max(season_ep_ranges[season]['end'], ep['episode'])
        return season_ep_ranges

    def cleanup(self):
        '''Override cleanup if needed'''
        pass
