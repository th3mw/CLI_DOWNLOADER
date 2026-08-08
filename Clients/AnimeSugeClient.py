import os
import re
import base64
from urllib.parse import quote

from Clients.BaseClient import BaseClient


class AnimeSugeClient(BaseClient):
    '''
    Client for animesuge.cz site supporting anime streaming without Cloudflare/Turnstile protection.
    Uses pure HTTP requests — no browser automation required.
    '''
    def __init__(self, config, session=None, series_type=None, content_filter=None, **kwargs):
        self.series_type = series_type
        self.content_filter = content_filter
        self.base_url = config.get('base_url', 'https://animesuge.cz')
        self.search_url = config.get('search_url', self.base_url + '/filter?keyword=')
        self.episode_list_url = config.get('episode_list_url', self.base_url + '/ajax/episode/list/')
        self.server_list_url = config.get('server_list_url', self.base_url + '/ajax/server/list?servers=')
        self.server_url = config.get('server_url', self.base_url + '/ajax/server?get=')
        self.vidtube_get_sources_url = config.get('vidtube_get_sources_url', 'https://vidtube.site/stream/getSourcesNew?id=')
        self.selector_strategy = config.get('alternate_resolution_selector', 'lowest')
        self.hls_size_accuracy = config.get('hls_size_accuracy', 0)
        self.preferred_server_types = config.get('preferred_server_types', ['sub', 'hsub', 'dub'])
        self.vidtube_origin = config.get('vidtube_origin', 'https://vidtube.site/')
        super().__init__(config.get('request_timeout', 30), session)

    def _compute_vrf(self, anime_id):
        '''
        Compute the vrf (verification) token required by AnimeSuge's AJAX endpoints.
        This is a port of the JavaScript j() function which uses:
        1. RC4 cipher with key "ysJhV6U27FVIjjuk"
        2. Base64 encoding
        3. Character code shifting (mod 8 pattern)
        4. Base64 encoding again
        5. ROT13 cipher
        '''
        def _rc4(key, data):
            n = list(range(256))
            r = 0
            for u in range(256):
                r = (r + n[u] + ord(key[u % len(key)])) % 256
                n[u], n[r] = n[r], n[u]
            u, r = 0, 0
            s = ''
            for a in range(len(data)):
                u = (u + 1) % 256
                r = (r + n[u]) % 256
                n[u], n[r] = n[r], n[u]
                s += chr(ord(data[a]) ^ n[(n[u] + n[r]) % 256])
            return s

        def _b64_encode(data_str):
            return base64.b64encode(data_str.encode('latin1')).decode('ascii')

        def _rot13(c):
            o = ord(c)
            if 65 <= o <= 90:
                return chr((o - 65 + 13) % 26 + 65)
            elif 97 <= o <= 122:
                return chr((o - 97 + 13) % 26 + 97)
            return c

        # The JavaScript: j(t) = rot13(b64(char_shift(rc4("ysJhV6U27FVIjjuk", encodeURIComponent(t))))
        # But encodeURIComponent of a number is just the number itself
        encoded = str(anime_id)
        rc4_result = _rc4('ysJhV6U27FVIjjuk', encoded)
        b64_result = _b64_encode(rc4_result)

        char_shifted = ''
        for idx, c in enumerate(b64_result):
            s = ord(c)
            mod = idx % 8
            if mod == 0: s -= 3
            elif mod == 1: s += 3
            elif mod == 2: s -= 4
            elif mod == 3: s += 2
            elif mod == 4: s -= 2
            elif mod == 5: s += 5
            elif mod == 6: s += 4
            elif mod == 7: s += 5
            char_shifted += chr(s)

        b64_result2 = _b64_encode(char_shifted)
        return ''.join(_rot13(c) for c in b64_result2)

    def _get_server_list(self, anime_id, episode_data_ids):
        '''
        Fetch the server list for a given episode's data-ids.
        Returns HTML containing server elements.
        CRITICAL: base64 + characters must be URL-encoded (%2B)
        '''
        encoded_ids = episode_data_ids.replace('+', '%2B')
        resp = self._send_request(
            f'{self.server_list_url}{encoded_ids}',
            referer=f'{self.base_url}/anime',
            extra_headers={'X-Requested-With': 'XMLHttpRequest'},
            return_type='json'
        )
        if resp and resp.get('status') == 200:
            return resp.get('result', '')
        self.logger.warning(f'Failed to fetch server list: {resp}')
        return ''

    def _get_stream_url(self, link_id):
        '''
        Fetch the stream (embed) URL for a given server's link-id.
        Returns the vidtube embed URL.
        CRITICAL: base64 + characters must be URL-encoded (%2B)
        '''
        encoded_link = link_id.replace('+', '%2B')
        resp = self._send_request(
            f'{self.server_url}{encoded_link}',
            referer=f'{self.base_url}/anime',
            extra_headers={'X-Requested-With': 'XMLHttpRequest'},
            return_type='json'
        )
        if resp and resp.get('status') == 200:
            return resp.get('result', {}).get('url')
        self.logger.warning(f'Failed to fetch stream URL: {resp}')
        return None

    def _get_m3u8_from_vidtube(self, stream_url):
        '''
        Given a vidtube embed URL, fetch the page to extract the media ID,
        then call getSourcesNew to get the m3u8 URL.
        '''
        page_html = self._send_request(stream_url, referer=f'{self.base_url}/')
        if not page_html:
            return None

        # Extract data-id (vidtube media ID) from the page
        match = re.search(r'data-id="(\d+)"', page_html)
        if not match:
            self.logger.warning('Could not find vidtube media ID on stream page')
            return None

        vidtube_id = match.group(1)
        # Extract the type from the stream URL path
        parts = stream_url.rstrip('/').split('/')
        vid_type = parts[-1] if parts else 'sub'

        # Call getSourcesNew API
        sources_resp = self._send_request(
            f'{self.vidtube_get_sources_url}{vidtube_id}&type={vid_type}',
            referer=stream_url,
            extra_headers={'X-Requested-With': 'XMLHttpRequest'},
            return_type='json'
        )
        if sources_resp and isinstance(sources_resp.get('sources'), dict):
            m3u8_url = sources_resp['sources'].get('file')
            subtitles = {}
            tracks = sources_resp.get('tracks', [])
            if isinstance(tracks, list):
                for track in tracks:
                    if isinstance(track, dict) and track.get('file'):
                        label = track.get('label', 'English')
                        subtitles[label] = track['file']
            return m3u8_url, subtitles

        self.logger.warning(f'Could not get m3u8 from vidtube: {sources_resp}')
        return None, {}

    def _fetch_tooltip_info(self, anime_id):
        '''Fetch tooltip metadata (status, release year) via AJAX'''
        if not anime_id:
            return {}
        tooltip_url = f"{self.base_url}/ajax/anime/tooltip/{anime_id}"
        resp_html = self._send_request(tooltip_url, extra_headers={'X-Requested-With': 'XMLHttpRequest'}, silent=True)
        if not resp_html:
            return {}
        tsoup = self._get_bsoup_from_html(resp_html)
        meta_info = {}
        for div in tsoup.select('div.meta > div'):
            txt = div.text.strip()
            if 'Status:' in txt:
                meta_info['status'] = txt.replace('Status:', '').strip()
            elif 'Aired:' in txt:
                aired_str = txt.replace('Aired:', '').strip()
                meta_info['aired'] = aired_str
                yr_match = re.search(r'\b(20\d\d|19\d\d)\b', aired_str)
                if yr_match:
                    meta_info['year'] = yr_match.group(1)
        return meta_info

    def _show_search_results(self, key, details):
        '''Pretty print search results in a structured 2-line layout matching KissKh'''
        title = details.get('title', 'Unknown')
        jp_title = details.get('jp_title')
        full_title = f"{title} - {jp_title}" if (jp_title and jp_title != title) else title

        ep_total = details.get('episodes', '?')
        sub_cnt = details.get('sub_cnt')
        dub_cnt = details.get('dub_cnt')
        ep_info = f"{ep_total}"
        if sub_cnt or dub_cnt:
            sd_parts = []
            if sub_cnt: sd_parts.append(f"Sub: {sub_cnt}")
            if dub_cnt: sd_parts.append(f"Dub: {dub_cnt}")
            ep_info += f" ({', '.join(sd_parts)})"

        status = details.get('status', 'N/A')
        year = details.get('year', 'N/A')
        anime_type = details.get('anime_type', '')

        line = f"{key}: {full_title}"
        if anime_type:
            line += f" [{anime_type}]"
        line += f"\n   | Episodes: {ep_info}"
        if status != 'N/A':
            line += f" | Status: {status}"
        if year != 'N/A':
            line += f" | Released: {year}"

        self._colprint('results', line)

    def search(self, keyword, search_limit=10):
        '''
        Search AnimeSuge for anime matching the keyword.
        Returns a dict of {index: result_dict}
        '''
        search_url = f'{self.search_url}{quote(keyword)}'
        html = self._send_request(search_url)
        if not html:
            return {}

        soup = self._get_bsoup_from_html(html)
        results = {}
        seen_ids = set()
        raw_items = []

        for item in soup.select('div.item'):
            if len(raw_items) >= search_limit:
                break
            a_poster = item.select_one('a.poster[data-tip]')
            if not a_poster:
                continue
            anime_id = a_poster.get('data-tip')
            if not anime_id or anime_id in seen_ids:
                continue
            seen_ids.add(anime_id)

            href = a_poster.get('href', '')
            img = item.find('img')
            title = img.get('alt') if (img and img.get('alt')) else 'Unknown'

            a_name = item.select_one('div.name a')
            jp_title = a_name.get('data-jp') if a_name else None
            if a_name and not title:
                title = a_name.text.strip()

            span_type = item.select_one('span.type')
            anime_type = span_type.text.strip() if span_type else ''

            span_total = item.select_one('div.dub-sub-total span.total')
            ep_total = span_total.text.strip() if span_total else '?'

            span_sub = item.select_one('div.dub-sub-total span.sub')
            sub_cnt = span_sub.text.strip() if span_sub else None

            span_dub = item.select_one('div.dub-sub-total span.dub')
            dub_cnt = span_dub.text.strip() if span_dub else None

            slug_match = re.search(r'/anime/([^/]+)', href)
            slug = slug_match.group(1) if slug_match else ''
            if '/ep-' in slug:
                slug = slug.split('/ep-')[0]

            anime_url = f"{self.base_url}/anime/{slug}" if slug else href

            raw_items.append({
                'title': title,
                'jp_title': jp_title,
                'anime_id': anime_id,
                'slug': slug,
                'anime_url': anime_url,
                'episodes': ep_total,
                'sub_cnt': sub_cnt,
                'dub_cnt': dub_cnt,
                'anime_type': anime_type,
            })

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=5) as executor:
            tooltips = list(executor.map(lambda it: self._fetch_tooltip_info(it['anime_id']), raw_items))

        for idx, (item, tooltip) in enumerate(zip(raw_items, tooltips), 1):
            item.update(tooltip)
            results[idx] = item
            self._show_search_results(idx, item)

        return results

    def _get_bsoup_from_html(self, html):
        from bs4 import BeautifulSoup as BS
        return BS(html, 'html.parser')

    def fetch_episodes_list(self, target):
        '''
        Fetch the full episode list for a selected anime.
        Returns a list of episode dicts: [{episode: 1, type: 'sub', data_id: 133908, data_ids: '...', server_id: 133908}, ...]
        '''
        anime_id = target.get('anime_id')
        vrf_token = self._compute_vrf(anime_id)

        resp = self._send_request(
            f'{self.episode_list_url}{anime_id}?vrf={vrf_token}',
            referer=f'{self.base_url}/anime',
            extra_headers={'X-Requested-With': 'XMLHttpRequest'},
            return_type='json'
        )

        if not resp or resp.get('status') != 200:
            self.logger.error(f'Failed to fetch episode list: {resp}')
            return []

        html = resp.get('result', '')
        # Parse episode links: data-id, data-slug, data-sub, data-dub, data-ids
        ep_pattern = r'data-id="(\d+)"[^>]*data-slug="(\d+)"[^>]*data-sub="(\d)"[^>]*data-dub="(\d)"[^>]*data-ids="([^"]+)"'
        episodes = []
        seen_eps = set()

        for match in re.finditer(ep_pattern, html):
            data_id, slug, sub, dub, data_ids = match.groups()
            ep_no = int(slug)
            if ep_no in seen_eps:
                continue
            seen_eps.add(ep_no)
            self._update_scraper_dict(ep_no, {
                'episodeName': f'Episode {ep_no}',
                'data_id': int(data_id),
                'data_ids': data_ids,
            })
            episodes.append({
                'episode': ep_no,
                'type': 'sub' if sub == '1' else ('dub' if dub == '1' else 'unknown'),
                'data_id': int(data_id),
                'data_ids': data_ids,
                'server_id': int(data_id),
                'season': 1,
            })

        # Sort by episode number
        episodes.sort(key=lambda x: x['episode'])
        return episodes

    def show_episode_results(self, items, *predefined_range):
        '''Pretty print episode list'''
        start, end = self._get_episode_range_to_show(
            items[0]['episode'], items[-1]['episode'],
            predefined_range[0] if predefined_range else None
        )

        for ep in items:
            if start <= ep['episode'] <= end:
                ep_label = f'Episode {ep["episode"]}'
                if ep.get('type'):
                    ep_label += f' ({ep["type"]})'
                self._colprint('results', ep_label)

    def _fetch_single_episode_link(self, ep):
        ep_no = ep.get('episode')
        self.logger.debug(f'Fetching server list for episode {ep_no}')
        server_html = self._get_server_list(ep.get('anime_id', 0), ep['data_ids'])
        if not server_html:
            return ep_no, {'error': 'Failed to fetch server list'}

        servers = []
        for type_match in re.finditer(r'data-type="(sub|hsub|dub)"[^>]*>.*?<div class="server-list">(.*?)</div>\s*</div>\s*</div>', server_html, re.DOTALL):
            srv_type = type_match.group(1)
            srv_list_html = type_match.group(2)
            for link_match in re.finditer(r'data-link-id="([^"]+)"', srv_list_html):
                servers.append((srv_type, link_match.group(1)))

        if not servers:
            return ep_no, {'error': 'No servers found for this episode'}

        link_id = None
        for preferred_type in self.preferred_server_types:
            for srv_type, lid in servers:
                if srv_type == preferred_type:
                    link_id = lid
                    break
            if link_id:
                break

        if not link_id:
            link_id = servers[0][1]

        stream_url = self._get_stream_url(link_id)
        if not stream_url:
            return ep_no, {'error': 'Failed to fetch stream URL'}

        m3u8_url, subtitles = self._get_m3u8_from_vidtube(stream_url)
        if not m3u8_url:
            return ep_no, {'error': 'Failed to fetch m3u8 link'}

        m3u8_links = self._parse_m3u8_links(m3u8_url, self.vidtube_origin)
        if m3u8_links:
            if subtitles:
                for res_dict in m3u8_links.values():
                    res_dict['subtitles'] = subtitles
            return ep_no, m3u8_links
        else:
            return ep_no, {
                '720': {
                    'downloadLink': m3u8_url,
                    'downloadType': 'hls',
                    'refererLink': self.vidtube_origin,
                    'subtitles': subtitles,
                    'duration': 0,
                }
            }

    def fetch_episode_links(self, episodes, ep_ranges):
        '''
        Fetch download links (m3u8 URLs) for selected episodes in parallel.
        Returns dict: {ep_no: {'original': {'downloadLink': m3u8, 'downloadType': 'hls', 'refererLink': referer}}}
        '''
        selected_eps = [ep for ep in episodes if self._is_episode_selected(ep.get('episode'), ep_ranges)]
        if not selected_eps:
            return {}

        target_links = {}
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(10, len(selected_eps))) as executor:
            results = list(executor.map(self._fetch_single_episode_link, selected_eps))

        for ep_no, res_dict in sorted(results, key=lambda x: x[0]):
            target_links[ep_no] = res_dict

        return target_links

    def _is_episode_selected(self, ep_no, ep_ranges):
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

    def set_out_names(self, target_series):
        '''
        Set output directory and episode prefix.
        Returns: (target_dir, episode_prefix)
        '''
        title = self._windows_safe_string(target_series.get('title', 'Unknown'))
        series_dir = self._windows_safe_string(title)
        episode_prefix = f"{title} -"
        return series_dir, episode_prefix

    def get_season_ep_ranges(self, episodes):
        '''
        Return episode ranges organized by season.
        AnimeSuge groups all episodes under season 1.
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
