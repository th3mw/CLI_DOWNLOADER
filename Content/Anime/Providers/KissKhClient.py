import re
from urllib.parse import quote_plus

from Core.BaseClient import BaseClient
from Core.commons import exec_js


class KissKhClient(BaseClient):
    '''
    Client for kisskh site supporting Anime, Asian Drama, Hollywood movies and TV shows
    '''
    def __init__(self, config, session=None, series_type=None, content_filter=None):
        self.series_type = series_type
        self.content_filter = content_filter
        self.name = 'KissKh'
        self.provider_name = 'KissKh'
        self.audio_preference = (config.get('audio_preference') or 'sub').lower() if isinstance(config, dict) else 'sub'
        self.base_url = config.get('base_url', 'https://kisskh.co').rstrip('/')
        search_path = config.get('search_url', '/api/DramaList/Search?q=')
        self.search_url = search_path if search_path.startswith('http') else f"{self.base_url}/{search_path.lstrip('/')}"
        series_path = config.get('series_url', '/api/DramaList/Drama/')
        self.series_url = series_path if series_path.startswith('http') else f"{self.base_url}/{series_path.lstrip('/')}"
        ep_path = config.get('episode_url', '/api/DramaList/Episode/{id}.png?err=false&ts=&time=&kkey=')
        self.episode_url = ep_path if ep_path.startswith('http') else f"{self.base_url}/{ep_path.lstrip('/')}"
        sub_path = config.get('subtitles_url', '/api/Sub/{id}?kkey=')
        self.subtitles_url = sub_path if sub_path.startswith('http') else f"{self.base_url}/{sub_path.lstrip('/')}"
        self.preferred_urls = config['preferred_urls'] if config.get('preferred_urls') else []
        self.blacklist_urls = config['blacklist_urls'] if config.get('blacklist_urls') else []
        self.selector_strategy = config.get('alternate_resolution_selector', 'lowest')
        self.hls_size_accuracy = config.get('hls_size_accuracy', 0)
        super().__init__(config.get('request_timeout', 30), session=session)
        self.logger.debug(f'KissKh client initialized with {config = }, {content_filter = }')
        self.token_generation_js_code = None
        # site specific details required to create token
        self.subGuid = "VgV52sWhwvBSf8BsM3BRY9weWiiCbtGp"
        self.viGuid = "62f176f3bb1b5b8e70e39932ad34a0c7"
        self.appVer = "2.8.10"
        self.platformVer = 4830201
        self.appName = "kisskh"
        self.DECRYPT_VIDEO_KEY = b'AmSmZVcH93UQUezi'
        self.DECRYPT_VIDEO_IV = bytes([
            (1382367819 >> 24) & 0xff, (1382367819 >> 16) & 0xff, (1382367819 >> 8) & 0xff, 1382367819 & 0xff,
            (1465333859 >> 24) & 0xff, (1465333859 >> 16) & 0xff, (1465333859 >> 8) & 0xff, 1465333859 & 0xff,
            (1902406224 >> 24) & 0xff, (1902406224 >> 16) & 0xff, (1902406224 >> 8) & 0xff, 1902406224 & 0xff,
            (1164854838 >> 24) & 0xff, (1164854838 >> 16) & 0xff, (1164854838 >> 8) & 0xff, 1164854838 & 0xff
        ])
        # key and iv for decrypting subtitles
        self.DECRYPT_SUBS_KEY = b'8056483646328763'
        self.DECRYPT_SUBS_IV = b'6852612370185273'
        self.DECRYPT_SUBS_KEY2 = b'AmSmZVcH93UQUezi'
        self.DECRYPT_SUBS_IV2 = b'ReBKWW8cqdjPEnF6'

    def _show_search_results(self, key, details):
        '''Pretty print search results'''
        line = f"{key}: {details.get('title')} | Country: {details.get('country')}" + \
               f"\n   | Episodes: {details.get('episodesCount', 'NA')} | Released: {details.get('year')} | Status: {details.get('status')}"
        self._colprint('results', line)

    def _get_token(self, episode_id, uid):
        '''Create token required to fetch stream & subtitle links'''
        if self.token_generation_js_code is None:
            self.logger.debug('Fetching token generation js code...')
            js_data = self._get_bsoup(self.base_url)
            script_url = None
            if js_data:
                script_srcs = [
                    script['src'] for script in js_data.find_all('script')
                    if script.get('src') and 'common.js' in script['src']
                ]
                if script_srcs:
                    script_src = script_srcs[0]
                    script_url = script_src if script_src.startswith('http') else f"{self.base_url.rstrip('/')}/{script_src.lstrip('/')}"
            
            if not script_url:
                script_url = f"{self.base_url.rstrip('/')}/common.js?v=9082123"

            self.logger.debug(f'Fetching token generation script: {script_url}')
            self.token_generation_js_code = self._send_request(script_url, return_type='text')
            if self.token_generation_js_code is None:
                self.logger.error('Failed to fetch token generation script')
                return None

        polyfill = """
        var window = globalThis;
        window.location = { href: 'https://kisskh.co/', URL: 'https://kisskh.co/' };
        window.document = { referrer: 'https://kisskh.co/', platform: 'Linux x86_64' };
        window.navigator = { userAgent: 'Mozilla/5.0 (X11; Linux x86_64)', platform: 'Linux x86_64', appName: 'Netscape', appCodeName: 'Mozilla' };
        """
        eval_expr = f'_0x54b991("{episode_id}", null, "{self.appVer}", "{uid}", {self.platformVer}, "{self.appName}", "{self.appName}", "{self.appName}", "{self.appName}", "{self.appName}", "{self.appName}")'
        js_code = f"{polyfill}\n{self.token_generation_js_code}\nconsole.log({eval_expr});"

        try:
            token = exec_js(js_code)
            return token if token else None
        except Exception as e:
            self.logger.error(f'Error generating kkey token: {e}')
            return None

    def search(self, keyword, search_limit=10):
        '''Search for content on KissKh site'''
        search_results = {}
        idx = 1
        search_types = {'1': 'Asian Drama', '2': 'Movies', '3': 'Anime', '4': 'Hollywood'}

        # Determine target codes based on content_filter
        allowed_codes = None
        if self.content_filter == 'anime':
            allowed_codes = ['3']
        elif self.content_filter == 'movie':
            allowed_codes = ['2', '4']
        elif self.content_filter == 'tv':
            allowed_codes = ['1']

        # url encode search keyword
        search_key = quote_plus(keyword)

        for code, type_name in search_types.items():
            if allowed_codes and code not in allowed_codes:
                continue
            self.logger.debug(f'Searching for {type_name} with keyword: {keyword}')
            search_url = self.search_url + search_key + '&type=' + str(code)
            raw_search_data = self._send_request(search_url, return_type='json')
            if not raw_search_data or not isinstance(raw_search_data, list):
                continue
            search_data = raw_search_data[:search_limit]

            def _fetch_detail(result):
                series_id = result.get('id')
                if not series_id:
                    return None
                series_data = self._send_request(self.series_url + str(series_id), return_type='json')
                if not series_data or not isinstance(series_data, dict):
                    return None
                item = {
                    'title': series_data.get('title', 'Unknown'),
                    'series_id': series_id,
                    'country': series_data.get('country', 'N/A'),
                    'episodesCount': series_data.get('episodesCount', 'N/A'),
                    'series_type': series_data.get('type', 'N/A'),
                    'status': series_data.get('status', 'N/A'),
                    'episodes': series_data.get('episodes', [])
                }
                try:
                    item['year'] = series_data['releaseDate'].split('-')[0]
                except Exception:
                    item['year'] = 'XXXX'
                return item

            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(10, len(search_data))) as executor:
                detailed_items = list(executor.map(_fetch_detail, search_data))

            for item in detailed_items:
                if item:
                    item['episodes_count'] = item.get('episodesCount', '')
                    item['type'] = item.get('series_type', '')
                    search_results[idx] = item
                    idx += 1

        return search_results

    def fetch_episodes_list(self, target):
        '''Fetch episode information'''
        all_episodes_list = []
        episodes = target.get('episodes', [])
        title = target.get('title', 'Unknown')
        is_movie = str(target.get('series_type', '')).lower() == 'movie' or str(target.get('type', '')).lower() == 'movie'

        self.logger.debug(f'Extracting episode details for {title}')
        for episode in episodes:
            try:
                raw_num = episode.get('number')
                ep_no = int(float(raw_num)) if str(raw_num).replace('.', '').isdigit() else raw_num
            except Exception:
                ep_no = episode.get('number', 1)

            ep_name = self.format_media_filename(
                series_title=title,
                season=1,
                episode=ep_no,
                is_movie=is_movie
            )
            all_episodes_list.append({
                'episode': ep_no,
                'season': 1,
                'type': 'anime' if self.content_filter == 'anime' else ('movie' if is_movie else 'tv'),
                'title': title,
                'episodeName': ep_name,
                'episodeId': episode['id'],
                'episodeSubs': episode.get('sub', 0)
            })

        return all_episodes_list[::-1]   # return episodes in ascending

    def show_episode_results(self, items, *predefined_range):
        '''Display episode list'''
        if not items:
            return
        if len(items) <= 24:
            for item in items:
                ep_num = item.get('episode', 1)
                try:
                    ep_str = f"Episode {int(float(ep_num)):02d}"
                except Exception:
                    ep_str = f"Episode {ep_num}"
                self._colprint('results', f"  {ep_str}")
        else:
            first_ep = items[0].get('episode', 1)
            last_ep = items[-1].get('episode', len(items))
            try:
                f_str = f"{int(float(first_ep)):02d}"
                l_str = f"{int(float(last_ep)):02d}"
            except Exception:
                f_str = str(first_ep)
                l_str = str(last_ep)
            self._colprint('results', f"  Episodes {f_str} – {l_str} ({len(items)} episodes ready)")

    def _fetch_single_episode_link(self, episode):
        ep_no = episode.get('episode')
        try:
            self.logger.debug(f'Processing {episode = }')
            token = self._get_token(episode.get('episodeId'), self.viGuid)
            if token is None:
                self.logger.warning(f'Failed to generate token for episode: {ep_no}')
                return ep_no, None, {'error': 'Failed to generate token'}
            dl_links = self._send_request(self.episode_url.format(id=str(episode.get('episodeId'))) + token, return_type='json', silent=True)
            if dl_links is None:
                self.logger.warning(f'Failed to fetch stream link for episode: {ep_no}')
                return ep_no, None, {'error': 'Failed to fetch stream link'}

            video_data = dl_links.get('Video', {})
            if isinstance(video_data, str):
                if video_data.startswith('http'):
                    link = video_data
                elif video_data:
                    try:
                        link = self._aes_decrypt(video_data, self.DECRYPT_VIDEO_KEY, self.DECRYPT_VIDEO_IV)
                    except Exception as e:
                        self.logger.error(f'Failed to decrypt video payload: {e}')
                        link = None
                else:
                    link = None
            elif isinstance(video_data, dict):
                qualities = video_data.get('qualities', {})
                link = qualities.get('1080', qualities.get('720', qualities.get('480', video_data.get('url'))))
            else:
                link = None

            if link is None:
                return ep_no, None, {'error': 'No stream link found'}

            if 'tickcounter.com' in link:
                return ep_no, None, {'error': 'Not Released Yet'}

            self._update_scraper_dict(ep_no, episode)
            self._update_scraper_dict(ep_no, {'streamLink': link, 'refererLink': self.base_url})

            if episode.get('episodeSubs', 0) > 0:
                token = self._get_token(episode.get('episodeId'), self.subGuid)
                if token is not None:
                    subtitles = self._send_request(self.subtitles_url.format(id=str(episode.get('episodeId'))) + token, return_type='json', silent=True)
                    if subtitles:
                        subtitles_dict = {sub['label']: sub['src'] for sub in subtitles}
                        self._update_scraper_dict(ep_no, {'subtitles': subtitles_dict})

                        encrypted_subs_details = {}
                        for k, v in subtitles_dict.items():
                            encryption_type = v.split('?')[0].split('.')[-1]
                            if encryption_type == 'txt':
                                encrypted_subs_details[k] = {'key': self.DECRYPT_SUBS_KEY, 'iv': self.DECRYPT_SUBS_IV, 'decrypter': self._aes_decrypt}
                            elif encryption_type == 'txt1':
                                encrypted_subs_details[k] = {'key': self.DECRYPT_SUBS_KEY2, 'iv': self.DECRYPT_SUBS_IV2, 'decrypter': self._aes_decrypt}

                        if encrypted_subs_details:
                            self._update_scraper_dict(ep_no, {'encrypted_subs_details': encrypted_subs_details})

            if isinstance(dl_links.get('Video'), dict):
                qualities = dl_links['Video'].get('qualities', {})
                m3u8_links = {}
                for quality, quality_link in qualities.items():
                    m3u8_links[quality] = {
                        'downloadLink': quality_link,
                        'downloadType': 'mp4' if '.mp4' in quality_link else 'hls',
                        'resolution_size': f'{quality}x0',
                        'refererLink': self.base_url
                    }
            else:
                link_type = 'mp4' if '.mp4' in link else 'hls'
                m3u8_links = {
                    '720': {
                        'downloadLink': link,
                        'downloadType': link_type,
                        'resolution_size': '1280x720',
                        'refererLink': self.base_url
                    }
                }

            return ep_no, m3u8_links, None
        except Exception as e:
            self.logger.warning(f'Episode {ep_no} processing failed: {e}')
            return ep_no, None, {'error': str(e)}

    def _is_episode_selected(self, ep_no, ep_ranges):
        if ep_ranges is None:
            return True
        if isinstance(ep_ranges, dict):
            if 1 in ep_ranges and isinstance(ep_ranges[1], dict):
                ep_ranges = ep_ranges[1]
            try:
                ep_f = float(ep_no)
            except Exception:
                return True
            if 'start' in ep_ranges and 'end' in ep_ranges:
                if ep_ranges['start'] <= ep_f <= ep_ranges['end']:
                    return True
            if 'specific_no' in ep_ranges and ep_f in [float(x) for x in ep_ranges['specific_no']]:
                return True
            return False
        return True

    def fetch_episode_links(self, episodes, ep_ranges):
        '''Fetch download links for episodes in parallel'''
        download_links = {}
        display_prefix = 'Movie' if episodes and episodes[0].get('type') == 'movie' else 'Episode'

        selected_eps = [ep for ep in episodes if self._is_episode_selected(ep.get('episode'), ep_ranges)]
        if not selected_eps:
            return {}

        from concurrent.futures import ThreadPoolExecutor
        workers = min(6, len(selected_eps))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(self._fetch_single_episode_link, selected_eps))

        for ep_no, m3u8_links, err_dict in sorted(results, key=lambda x: float(x[0]) if str(x[0]).replace('.', '').isdigit() else 0):
            if m3u8_links:
                download_links[ep_no] = m3u8_links
            elif err_dict:
                self._show_episode_links(ep_no, err_dict, display_prefix)

        return download_links

    def set_out_names(self, target_series):
        '''Set output directory and episode prefix'''
        title = self._windows_safe_string(target_series['title'])
        series_dir = title if title.endswith(')') else f"{title} ({target_series.get('year', '')})".strip()
        episode_prefix = f"{title} -"
        return series_dir, episode_prefix

    def get_season_ep_ranges(self, episodes):
        '''Return episode ranges organized by season'''
        season_ep_ranges = {}
        for ep in episodes:
            season = ep.get('season', 1)
            ep_val = ep.get('episode', 1)
            try:
                ep_num = int(float(ep_val))
            except Exception:
                ep_num = 1
            if season not in season_ep_ranges:
                season_ep_ranges[season] = {'start': ep_num, 'end': ep_num}
            else:
                season_ep_ranges[season]['start'] = min(season_ep_ranges[season]['start'], ep_num)
                season_ep_ranges[season]['end'] = max(season_ep_ranges[season]['end'], ep_num)
        return season_ep_ranges
