import base64
import os
import re
from urllib.parse import quote, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

from Cryptodome.Cipher import AES

from Core.BaseClient import BaseClient


class AnikotoClient(BaseClient):
    '''
    Client for anikoto.cz — high-speed Anime streaming provider.
    Features:
    - Pure HTTP requests (zero browser automation required).
    - Rich search metadata: Japanese title, sub/dub counts, format badges, rating, year.
    - Direct multi-resolution HLS master stream extraction (1080p, 720p, 480p, 360p).
    - Embedded WebVTT subtitle extraction and multi-audio (Sub / Dub) routing.
    '''
    MEGAPLAY_KEY = b'i?LMTAx0Q6,:}50U'.ljust(32, b'\0')
    MEGAPLAY_IV = b"W0;27ToaUpl_P%'c"

    def __init__(self, config, session=None, series_type=None, content_filter=None, **kwargs):
        self.series_type = series_type
        self.content_filter = content_filter
        self.name = 'AniKoto'
        self.provider_name = 'AniKoto'
        self.base_url = config.get('base_url', 'https://anikoto.cz').rstrip('/')
        self.search_url = config.get('search_url', self.base_url + '/filter?keyword=')
        self.episode_list_url = config.get('episode_list_url', self.base_url + '/ajax/episode/list/')
        self.server_list_url = config.get('server_list_url', self.base_url + '/ajax/server/list?servers=')
        self.server_url = config.get('server_url', self.base_url + '/ajax/server?get=')
        self.tooltip_url = config.get('tooltip_url', self.base_url + '/ajax/anime/tooltip/')
        self.hls_size_accuracy = config.get('hls_size_accuracy', 0)
        self.audio_preference = (config.get('audio_preference') or 'sub').lower()
        if self.audio_preference in ('dub', 'english'):
            self.preferred_server_types = ['dub', 'hsub', 'sub']
        else:
            self.preferred_server_types = config.get('preferred_server_types', ['sub', 'hsub', 'dub'])

        super().__init__(config.get('request_timeout', 30), session)

    def _compute_vrf(self, anime_id):
        '''
        Compute the verification token required by Anikoto AJAX endpoints.
        RC4 cipher ('ysJhV6U27FVIjjuk') + Base64 + mod-8 shift + Base64 + Rot13.
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

    def _decrypt_megaplay_sources(self, enc_str):
        '''
        Decrypt AES-256-CBC ciphertext from MegaPlay / Vidstream getSourcesNew API.
        '''
        try:
            enc_fixed = str(enc_str).replace('-', '+').replace('_', '/')
            enc_fixed += '=' * ((4 - len(enc_fixed) % 4) % 4)
            ciphertext = base64.b64decode(enc_fixed)

            cipher = AES.new(self.MEGAPLAY_KEY, AES.MODE_CBC, iv=self.MEGAPLAY_IV)
            decrypted = cipher.decrypt(ciphertext)
            pad_len = decrypted[-1]
            if 1 <= pad_len <= 16:
                decrypted = decrypted[:-pad_len]
            return decrypted.decode('utf-8', errors='ignore')
        except Exception as e:
            self.logger.debug(f'MegaPlay decryption error: {e}')
            return ''

    def _fetch_tooltip_info(self, anime_id):
        '''Fetch tooltip metadata (rating score, airing status, release year) via AJAX'''
        if not anime_id:
            return {}
        tooltip_url = f"{self.tooltip_url}{anime_id}"
        resp_html = self._send_request(tooltip_url, extra_headers={'X-Requested-With': 'XMLHttpRequest'}, silent=True)
        if not resp_html:
            return {}
        tsoup = self._get_bsoup_from_html(resp_html)
        meta_info = {}
        for div in tsoup.select('div.meta > div, div.meta span'):
            txt = div.text.strip()
            if 'Status:' in txt:
                meta_info['status'] = txt.replace('Status:', '').strip()
            elif 'Aired:' in txt:
                aired_str = txt.replace('Aired:', '').strip()
                meta_info['aired'] = aired_str
                yr_match = re.search(r'\b(20\d\d|19\d\d)\b', aired_str)
                if yr_match:
                    meta_info['year'] = yr_match.group(1)
            elif 'Score:' in txt or 'Rating:' in txt:
                score_match = re.search(r'(\d+\.\d+)', txt)
                if score_match:
                    meta_info['score'] = score_match.group(1)
        return meta_info

    def _show_search_results(self, key, details):
        '''Render search result card matching standard layout'''
        title = details.get('title', 'Unknown')
        jp_title = details.get('jp_title')
        full_title = f"{title} ({jp_title})" if (jp_title and jp_title != title) else title

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
        score = details.get('score')
        anime_type = details.get('anime_type', '')

        line = f"{key}: {full_title}"
        if anime_type:
            line += f" [{anime_type}]"
        line += f"\n   | Episodes: {ep_info}"
        if score:
            line += f" | Rating: ★ {score}"
        if status != 'N/A':
            line += f" | Status: {status}"
        if year != 'N/A':
            line += f" | Year: {year}"

        self._colprint('results', line)

    def search(self, keyword, search_limit=10):
        '''
        Search AniKoto for anime matching the keyword.
        Returns a dict of {index: result_dict}
        '''
        search_url = f'{self.search_url}{quote(keyword)}'
        html = self._send_request(search_url)
        if not html:
            return {}

        soup = self._get_bsoup_from_html(html)
        results = {}
        seen_ids = set()

        for item in soup.select('.item, .anime-item'):
            title_tag = item.select_one('a.name.d-title, a.dynamic-name, .film-name a, h3 a')
            if not title_tag:
                img_tag = item.select_one('img[alt]')
                if img_tag and img_tag.get('alt'):
                    title = img_tag['alt'].strip()
                else:
                    continue
            else:
                title = title_tag.text.strip()

            link = title_tag['href'] if (title_tag and title_tag.has_attr('href')) else ''
            if not link:
                a_tag = item.select_one('a[href*="/watch/"]')
                if a_tag:
                    link = a_tag['href']

            if not link.startswith('http'):
                link = f"{self.base_url}{link}" if link.startswith('/') else f"{self.base_url}/{link}"

            # Japanese / Romaji title
            jp_title = title_tag.get('data-jp') if title_tag else None

            # Tooltip ID / Anime ID
            tip_div = item.select_one('[data-tip]')
            anime_id = tip_div.get('data-tip') if tip_div else None
            if anime_id and anime_id in seen_ids:
                continue
            if anime_id:
                seen_ids.add(anime_id)

            # Metadata badges (Sub, Dub, Total, Type)
            sub_span = item.select_one('.ep-status.sub span')
            dub_span = item.select_one('.ep-status.dub span')
            tot_span = item.select_one('.ep-status.total span')
            type_div = item.select_one('.meta .right, .film-poster .tick-item')

            sub_cnt = sub_span.text.strip() if sub_span else None
            dub_cnt = dub_span.text.strip() if dub_span else None
            episodes = tot_span.text.strip() if tot_span else (sub_cnt or dub_cnt or '?')
            anime_type = type_div.text.strip() if type_div else 'TV'

            idx = len(results) + 1
            results[idx] = {
                'title': title,
                'jp_title': jp_title,
                'link': link,
                'anime_id': anime_id,
                'episodes': episodes,
                'sub_cnt': sub_cnt,
                'dub_cnt': dub_cnt,
                'anime_type': anime_type,
                'status': 'N/A',
                'year': 'N/A',
                'score': None
            }

            if idx >= search_limit:
                break

        # Enrich results with tooltip metadata in parallel (max 5 workers)
        if results:
            def _enrich(item):
                a_id = item.get('anime_id')
                if a_id:
                    meta = self._fetch_tooltip_info(a_id)
                    item.update({k: v for k, v in meta.items() if v})

            with ThreadPoolExecutor(max_workers=min(5, len(results))) as ex:
                ex.map(_enrich, results.values())

        for k, v in results.items():
            meta_parts = []
            if v.get('anime_type'): meta_parts.append(f"[{v['anime_type']}]")
            if v.get('episodes'): meta_parts.append(f"Eps: {v['episodes']}")
            if v.get('score'): meta_parts.append(f"★ {v['score']}")
            if v.get('status') and v['status'] != 'N/A': meta_parts.append(v['status'])
            if v.get('year') and v['year'] != 'N/A': meta_parts.append(v['year'])

            v['card_title'] = f"{v['title']} ({v['year']})" if (v.get('year') and v['year'] != 'N/A') else v['title']
            v['card_meta'] = " • ".join(meta_parts)

        return results

    def _get_bsoup_from_html(self, html):
        from bs4 import BeautifulSoup as BS
        return BS(html, 'html.parser')

    def fetch_episodes_list(self, target):
        '''
        Fetch all available episodes for the selected anime series from AniKoto.
        '''
        anime_id = target.get('anime_id')
        watch_url = target.get('link', '')

        # If anime_id not present in target, fetch from watch page #watch-main data-id
        if not anime_id and watch_url:
            html = self._send_request(watch_url, silent=True)
            if html:
                soup = self._get_bsoup_from_html(html)
                wm = soup.select_one('#watch-main')
                if wm and wm.has_attr('data-id'):
                    anime_id = wm['data-id']

        if not anime_id:
            self.logger.error('Could not extract Anime ID for episode listing')
            return []

        ep_list_url = f"{self.episode_list_url}{anime_id}"
        resp = self._send_request(ep_list_url, extra_headers={'X-Requested-With': 'XMLHttpRequest'}, return_type='json')
        if not resp or 'result' not in resp:
            self.logger.error(f'Failed to fetch episode list from {ep_list_url}')
            return []

        soup = self._get_bsoup_from_html(resp['result'])
        episodes = []
        series_title = target.get('title', 'Anime')

        for a in soup.select('.episodes a, a[data-id], a[data-ids]'):
            data_id = a.get('data-id')
            data_ids = a.get('data-ids')
            num_str = a.get('data-num') or a.get('data-slug') or '1'
            try:
                ep_no = int(num_str)
            except ValueError:
                ep_no = len(episodes) + 1

            raw_name = a.text.strip()
            ep_title_clean = re.sub(r'^\d+\s*', '', raw_name)
            name_label = f"{series_title} - E{ep_no:02d}" + (f" - {ep_title_clean}" if ep_title_clean else "")

            sub_avail = a.get('data-sub') == '1'
            dub_avail = a.get('data-dub') == '1'

            episodes.append({
                'episode': ep_no,
                'ep_no': ep_no,
                'episodeName': self._windows_safe_string(name_label),
                'data_id': data_id,
                'data_ids': data_ids,
                'anime_id': anime_id,
                'sub_available': sub_avail,
                'dub_available': dub_avail,
                'show_title': series_title
            })

        return episodes

    def show_episode_results(self, items, *predefined_range):
        '''Display episode overview'''
        for item in items:
            self._colprint('results', f"Episode: {item.get('episodeName')}")

    def _get_server_list(self, anime_id, episode_data_ids):
        '''
        Fetch server list HTML for an episode's data-ids.
        '''
        encoded_ids = episode_data_ids.replace('+', '%2B')
        vrf = self._compute_vrf(anime_id)
        url = f"{self.server_list_url}{encoded_ids}&vrf={vrf}"
        resp = self._send_request(url, extra_headers={'X-Requested-With': 'XMLHttpRequest'}, return_type='json', silent=True)
        if resp and resp.get('status') == 200 and 'result' in resp:
            return resp['result']
        return None

    def _resolve_server_embed(self, link_id):
        '''
        Fetch the decrypted video embed URL for a given server link-id.
        '''
        encoded_id = link_id.replace('+', '%2B')
        vrf = self._compute_vrf(link_id)
        url = f"{self.server_url}{encoded_id}&vrf={vrf}"
        resp = self._send_request(url, extra_headers={'X-Requested-With': 'XMLHttpRequest'}, return_type='json', silent=True)
        if resp and resp.get('status') == 200 and 'result' in resp:
            result = resp['result']
            if isinstance(result, dict) and 'url' in result:
                return result['url']
        return None

    def _extract_stream_sources(self, embed_url):
        '''
        Fetch and decrypt master m3u8 sources from MegaPlay / Vidstream embed.
        '''
        try:
            parsed = urlparse(embed_url)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            match = re.search(r'/(?:stream|videojs)/(?:s-\d+/)?(\d+)', parsed.path)
            if not match:
                return None, {}

            real_id = match.group(1)
            parts = parsed.path.rstrip('/').split('/')
            vid_type = parts[-1] if parts else 'sub'

            for ep_name in ['getSourcesNew', 'getSources']:
                sources_url = f"{origin}/stream/{ep_name}?id={real_id}&type={vid_type}"
                resp = self._send_request(
                    sources_url,
                    referer=embed_url,
                    extra_headers={'X-Requested-With': 'XMLHttpRequest'},
                    return_type='json',
                    silent=True
                )
                if not resp:
                    continue

                subtitles = {}
                tracks = resp.get('tracks', [])
                if isinstance(tracks, list):
                    for tr in tracks:
                        if isinstance(tr, dict) and tr.get('file'):
                            label = tr.get('label', 'English')
                            subtitles[label] = tr['file']

                # Case A: Encrypted payload ("enc")
                if 'enc' in resp and resp['enc']:
                    dec_json = self._decrypt_megaplay_sources(resp['enc'])
                    if dec_json:
                        import json
                        try:
                            dec_obj = json.loads(dec_json)
                            m3u8_url = dec_obj.get('file')
                            if m3u8_url:
                                return m3u8_url, subtitles
                        except Exception:
                            pass

                # Case B: Plain sources object
                if isinstance(resp.get('sources'), dict) and resp['sources'].get('file'):
                    return resp['sources']['file'], subtitles
                elif isinstance(resp.get('sources'), list) and resp['sources'] and resp['sources'][0].get('file'):
                    return resp['sources'][0]['file'], subtitles

        except Exception as e:
            self.logger.debug(f'Error extracting stream sources from {embed_url}: {e}')

        return None, {}

    def _fetch_single_episode_link(self, episode):
        '''
        Resolve streaming servers and master m3u8 playlists for an episode.
        '''
        ep_no = episode.get('ep_no') or episode.get('episode', 1)
        anime_id = episode.get('anime_id')
        data_ids = episode.get('data_ids')

        if not anime_id or not data_ids:
            return ep_no, None, {'error': 'Missing anime_id or data_ids'}

        server_html = self._get_server_list(anime_id, data_ids)
        if not server_html:
            return ep_no, None, {'error': f'Failed to retrieve server list for episode {ep_no}'}

        soup = self._get_bsoup_from_html(server_html)

        # Categorize servers by type (dub, sub)
        servers_by_type = {}
        for type_div in soup.select('.type[data-type]'):
            stype = type_div.get('data-type', 'sub').lower()
            servers_by_type[stype] = type_div.select('li[data-link-id]')

        # Resolve servers according to preferred audio types
        server_candidates = []
        for ptype in self.preferred_server_types:
            if ptype in servers_by_type and servers_by_type[ptype]:
                server_candidates.extend(servers_by_type[ptype])
                break

        if not server_candidates:
            server_candidates = soup.select('li[data-link-id]')

        if not server_candidates:
            return ep_no, None, {'error': f'No streaming servers available for episode {ep_no}'}

        merged_m3u8_links = {}
        all_subtitles = {}

        for s_elem in server_candidates:
            link_id = s_elem.get('data-link-id')
            if not link_id:
                continue

            embed_url = self._resolve_server_embed(link_id)
            if not embed_url:
                continue

            parsed = urlparse(embed_url)
            stream_origin = f"{parsed.scheme}://{parsed.netloc}"
            stream_referer = stream_origin.rstrip('/') + '/'

            m3u8_url, subtitles = self._extract_stream_sources(embed_url)
            if not m3u8_url:
                continue

            if subtitles:
                all_subtitles.update(subtitles)

            m3u8_links = self._parse_m3u8_links(m3u8_url, stream_referer)
            if m3u8_links:
                for res_k, res_v in m3u8_links.items():
                    if res_k not in merged_m3u8_links:
                        merged_m3u8_links[res_k] = res_v
            elif not merged_m3u8_links:
                merged_m3u8_links['720'] = {
                    'downloadLink': m3u8_url,
                    'downloadType': 'hls',
                    'refererLink': stream_referer,
                    'duration': 0,
                }

            if any(r in merged_m3u8_links for r in ['1080', '1080p']) and any(r in merged_m3u8_links for r in ['720', '720p', '480', '480p', '360', '360p']):
                break

        if merged_m3u8_links:
            if all_subtitles:
                for res_dict in merged_m3u8_links.values():
                    res_dict['subtitles'] = all_subtitles

            self._update_scraper_dict(ep_no, episode)
            self._update_scraper_dict(ep_no, {
                'streamLink': next(iter(merged_m3u8_links.values())).get('downloadLink'),
                'refererLink': stream_referer,
                'subtitles': all_subtitles
            })
            return ep_no, merged_m3u8_links

        return ep_no, {'error': f'Failed to extract streaming playlist for episode {ep_no}'}

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

    def fetch_episode_links(self, episodes, ep_ranges):
        '''
        Fetch download links (m3u8 URLs) for selected episodes in parallel.
        Uses controlled concurrency (max 5 workers).
        '''
        selected_eps = [ep for ep in episodes if self._is_episode_selected(ep.get('episode'), ep_ranges)]
        if not selected_eps:
            return {}

        target_links = {}
        workers = min(5, len(selected_eps))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(self._fetch_single_episode_link, selected_eps))

        for ep_no, res_dict in sorted(results, key=lambda x: x[0]):
            target_links[ep_no] = res_dict

        return target_links

    def set_out_names(self, target_series):
        '''
        Set output directory and episode prefix.
        Returns: (target_dir, episode_prefix)
        '''
        title = self._windows_safe_string(target_series.get('title', 'Unknown'))
        series_dir = self._windows_safe_string(title)
        episode_prefix = f"{title} -"
        return series_dir, episode_prefix
