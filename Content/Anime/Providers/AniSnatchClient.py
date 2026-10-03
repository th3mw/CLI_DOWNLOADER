import json
import os
import re
import subprocess
import shutil
from urllib.parse import urljoin, urlparse

from Core.BaseClient import BaseClient
from Core.commons import (
    colprint,
    render_box,
    truncate_ansi,
    visible_len,
    PRINT_THEMES,
    DISPLAY_COLORS
)


class AniSnatchClient(BaseClient):
    '''
    Client for scraping and fetching anime HLS streams from AniSnatch (https://anisnatch.top/).
    Features:
    - Encrypted binary communication protocol (XOR + Pako decompression via Node bridge).
    - Rich anime search metadata (scores, dub flags, ratings, air dates, episode counts).
    - Multi-server, multi-audio (Sub, Soft-Sub, Dub) extraction.
    - Master HLS playlist multi-resolution stream parsing (1080p, 720p, 480p, 360p).
    - Embedded WebVTT subtitles & opening/ending skip timestamps.
    '''

    def __init__(self, config, session=None, series_type=None, content_filter=None, **kwargs):
        self.series_type = series_type
        self.content_filter = content_filter
        self.client_name = 'anisnatch'
        self.name = 'AniSnatch'
        self.provider_name = 'AniSnatch'
        anisnatch_config = config.get('anisnatch', {}) if isinstance(config, dict) else {}
        self.base_url = anisnatch_config.get('base_url', 'https://anisnatch.top').rstrip('/')
        self.hls_size_accuracy = anisnatch_config.get('hls_size_accuracy', 0)
        self.audio_preference = (config.get('audio_preference') or 'sub').lower()

        self.engine_path = os.path.join(os.path.dirname(__file__), 'anisnatch_engine.js')
        self.node_binary = self._find_node_binary()

        super().__init__(anisnatch_config.get('request_timeout', 30), session)

    def _find_node_binary(self):
        '''Find node or bun binary in system PATH'''
        for bin_name in ['bun', 'node', 'nodejs']:
            path = shutil.which(bin_name)
            if path:
                return path
        return 'node'

    def _call_engine(self, action, *args):
        '''Execute anisnatch_engine.js with given arguments and return parsed JSON'''
        cmd = [self.node_binary, self.engine_path, action] + [str(a) for a in args]
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=45,
                check=False
            )
            if res.returncode != 0:
                self.logger.error(f'AniSnatch engine error ({action}): {res.stderr.strip()}')
                return None
            stdout = res.stdout.strip()
            if not stdout:
                return None
            return json.loads(stdout)
        except subprocess.TimeoutExpired:
            self.logger.error(f'AniSnatch engine timed out for action {action}')
            return None
        except Exception as e:
            self.logger.error(f'Failed to execute AniSnatch engine: {e}')
            return None

    def search(self, search_key):
        '''
        Search AniSnatch catalog for anime title.
        Returns a dictionary mapping integer index (1..N) to anime metadata dictionary.
        '''
        self.logger.debug(f'Searching AniSnatch for: {search_key}')
        resp = self._call_engine('search', search_key, 1)
        if not resp or not resp.get('success'):
            self.logger.warning(f'No search results or request failed for: {search_key}')
            return {}

        anime_list = resp.get('data', {}).get('anime', [])
        if not anime_list:
            return {}

        results = {}
        for idx, item in enumerate(anime_list, start=1):
            title = item.get('title') or item.get('title_en') or 'Unknown Title'
            title_en = item.get('title_en')
            anime_id = item.get('id')
            score = item.get('score', 0)
            ep_count = item.get('episodes') or item.get('lastep') or '?'
            v_type = item.get('type') or 'Anime'
            dub_flag = item.get('dub', 0)
            status = item.get('status') or ''
            rating = item.get('rating') or ''
            picture = item.get('picture')

            # Build readable metadata line
            meta_parts = [f"Type: {v_type}"]
            if score and float(score) > 0:
                meta_parts.append(f"★ {score}")
            if ep_count and ep_count != '?':
                meta_parts.append(f"Episodes: {ep_count}")

            audio_tags = ['Sub']
            if dub_flag == 1 or dub_flag is True:
                audio_tags.append('Dub')
            meta_parts.append(f"Audio: {' + '.join(audio_tags)}")

            if status and status != 'N/A':
                meta_parts.append(status)

            entry = {
                'id': anime_id,
                'anime_id': anime_id,
                'title': title,
                'title_en': title_en,
                'type': v_type,
                'score': score,
                'episodes': ep_count,
                'dub': dub_flag,
                'status': status,
                'rating': rating,
                'picture': picture,
                'card_title': title,
                'card_meta': " • ".join(meta_parts),
                'link': f"{self.base_url}/anime/{anime_id}"
            }
            results[idx] = entry

        return results

    def show_search_results(self, results):
        '''Renders search results in structured visual cards.'''
        if not results:
            colprint('warning', '  ⚠ No anime found on AniSnatch matching your search.')
            return

        c_idx = (PRINT_THEMES['secondary'] + PRINT_THEMES['bold']) if DISPLAY_COLORS else ''
        c_title = (PRINT_THEMES['header'] + PRINT_THEMES['bold']) if DISPLAY_COLORS else ''
        c_meta = PRINT_THEMES['muted'] if DISPLAY_COLORS else ''
        c_reset = PRINT_THEMES['reset'] if DISPLAY_COLORS else ''

        lines = []
        for idx, item in results.items():
            title = item.get('card_title', item.get('title', 'Unknown'))
            meta = item.get('card_meta', '')
            lines.append(f"  {c_idx}[{idx:02d}]{c_reset}  {c_title}{title}{c_reset}")
            if meta:
                lines.append(f"        {c_meta}{meta}{c_reset}")
            lines.append('')

        if lines and lines[-1] == '':
            lines.pop()

        print('\n' + render_box('ANISNATCH SEARCH RESULTS', lines, max_width=90, indent=2))

    def fetch_episodes_list(self, target):
        '''
        Fetch episode list for selected anime item.
        Returns a list of episode dicts.
        '''
        anime_id = target.get('anime_id') or target.get('id')
        if not anime_id:
            self.logger.error('Missing anime_id in target dict')
            return []

        resp = self._call_engine('episodes', anime_id)
        if not resp or not resp.get('success'):
            self.logger.error(f'Failed to fetch episode list for anime ID: {anime_id}')
            return []

        raw_eps = resp.get('episodes', [])
        episodes = []
        for ep in raw_eps:
            ep_num = ep.get('number')
            if ep_num is None:
                continue
            ep_num = int(ep_num)

            ep_entry = {
                'episode': ep_num,
                'episode_name': ep.get('title') or f'Episode {ep_num}',
                'anime_id': anime_id,
                'data_id': ep_num,
                'air_date': ep.get('airDate'),
                'duration': ep.get('duration'),
                'sub': ep.get('sub', True),
                'dub': ep.get('dub', False),
                'season': 1
            }
            self._update_scraper_dict(ep_num, {
                'episodeName': ep_entry['episode_name'],
                'anime_id': anime_id,
                'episode': ep_num
            })
            episodes.append(ep_entry)

        episodes.sort(key=lambda x: x['episode'])
        return episodes

    def show_episode_results(self, items, *predefined_range):
        '''Pretty print episode list'''
        if not items:
            return
        if len(items) <= 24:
            for ep in items:
                ep_label = f"  Episode {ep['episode']:02d}: {ep.get('episode_name', '')}"
                audio_tags = []
                if ep.get('sub'): audio_tags.append('Sub')
                if ep.get('dub'): audio_tags.append('Dub')
                if audio_tags:
                    ep_label += f" [{' + '.join(audio_tags)}]"
                colprint('results', ep_label)
        else:
            first_ep = items[0].get('episode', 1)
            last_ep = items[-1].get('episode', len(items))
            colprint('results', f"  Episodes {first_ep:02d} – {last_ep:02d} ({len(items)} episodes ready)")

    def _parse_m3u8_links(self, m3u8_url, referer_url):
        '''
        Fetch and parse master HLS playlist to extract available resolution streams.
        Returns dict of quality -> stream dict.
        '''
        try:
            resp = self._send_request(m3u8_url, referer=referer_url, return_type='text', silent=True)
            if not resp or '#EXTM3U' not in resp:
                return {}

            resolutions = {}
            lines = [l.strip() for l in resp.splitlines() if l.strip()]
            for i, line in enumerate(lines):
                if line.startswith('#EXT-X-STREAM-INF:'):
                    # Extract resolution height (e.g. 1920x1080 -> 1080)
                    res_match = re.search(r'RESOLUTION=(\d+)x(\d+)', line)
                    if res_match:
                        height = res_match.group(2)
                    else:
                        # Fallback by bandwidth
                        bw_match = re.search(r'BANDWIDTH=(\d+)', line)
                        bw = int(bw_match.group(1)) if bw_match else 0
                        if bw >= 4000000: height = '1080'
                        elif bw >= 2000000: height = '720'
                        elif bw >= 1000000: height = '480'
                        else: height = '360'

                    if i + 1 < len(lines) and not lines[i + 1].startswith('#'):
                        stream_path = lines[i + 1]
                        stream_url = urljoin(m3u8_url, stream_path)
                        resolutions[height] = {
                            'resolution_size': f'{height}p',
                            'downloadLink': stream_url,
                            'downloadType': 'hls',
                            'refererLink': referer_url,
                            'duration': 0
                        }

            # Return sorted resolutions high -> low
            sorted_res = {}
            for k in sorted(resolutions.keys(), key=lambda x: int(x) if x.isdigit() else 0, reverse=True):
                sorted_res[k] = resolutions[k]
            return sorted_res
        except Exception as e:
            self.logger.debug(f'Error parsing m3u8 playlist {m3u8_url}: {e}')
            return {}

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

    def _fetch_single_episode_servers(self, ep):
        '''Fetch server streams and resolutions for a single episode'''
        ep_no = ep.get('episode')
        anime_id = ep.get('anime_id')

        audio_pref = 'dub' if self.audio_preference in ('dub', 'english') else 'sub'
        res = self._call_engine('fast_streams', anime_id, ep_no, audio_pref)
        if not res or not res.get('success'):
            return ep_no, {'error': f'No streams available for episode {ep_no}'}

        stream_items = res.get('streams', [])
        if not stream_items:
            return ep_no, {'error': f'Empty stream list for episode {ep_no}'}

        merged_m3u8_links = {}
        all_subtitles = {}

        for item in stream_items:
            idx = item.get('serverIdx', 1)
            srv_name = item.get('serverName', f'Server {idx}')
            srv_type = item.get('serverType', 'Sub')
            srv_id = item.get('serverId', str(idx))
            stream = item.get('stream', {})

            m3u8_url = stream.get('m3u8')
            if not m3u8_url:
                continue

            player_url = stream.get('playerUrl') or f"{self.base_url}/"
            parsed_p = urlparse(player_url)
            stream_referer = f"{parsed_p.scheme}://{parsed_p.netloc}/"

            subs = stream.get('subtitles', [])
            if isinstance(subs, list):
                for sub_item in subs:
                    if isinstance(sub_item, dict) and sub_item.get('file'):
                        lang_label = sub_item.get('label', 'English')
                        all_subtitles[lang_label] = sub_item['file']

            m3u8_links = self._parse_m3u8_links(m3u8_url, stream_referer)
            if not m3u8_links:
                m3u8_links = {
                    '1080': {
                        'resolution_size': '1080p (Direct)',
                        'downloadLink': m3u8_url,
                        'downloadType': 'hls',
                        'refererLink': stream_referer,
                        'duration': 0
                    }
                }

            for res_k, res_v in m3u8_links.items():
                res_dict = dict(res_v)
                res_dict['server_name'] = srv_name
                res_dict['server_type'] = srv_type
                res_dict['server_id'] = srv_id
                res_dict['quality'] = res_k

                key = f"srv{idx}_{res_k}"
                merged_m3u8_links[key] = res_dict
                if res_k not in merged_m3u8_links:
                    merged_m3u8_links[res_k] = res_dict

        if merged_m3u8_links:
            if all_subtitles:
                for res_dict in merged_m3u8_links.values():
                    res_dict['subtitles'] = all_subtitles

            self._update_scraper_dict(ep_no, ep)
            first_stream = next(iter(merged_m3u8_links.values()))
            self._update_scraper_dict(ep_no, {
                'streamLink': first_stream.get('downloadLink'),
                'refererLink': first_stream.get('refererLink'),
                'subtitles': all_subtitles
            })
            return ep_no, merged_m3u8_links

        return ep_no, {'error': f'Failed to extract streams for episode {ep_no}'}

    def fetch_episode_links(self, episodes, ep_ranges):
        '''
        Fetch download links for selected episodes.
        '''
        selected_eps = [ep for ep in episodes if self._is_episode_selected(ep.get('episode'), ep_ranges)]
        if not selected_eps:
            return {}

        target_links = {}
        for ep in selected_eps:
            ep_no, ep_links = self._fetch_single_episode_servers(ep)
            if ep_links and 'error' not in ep_links:
                target_links[ep_no] = ep_links
            else:
                self.logger.warning(f"Could not load streams for Episode {ep_no}: {ep_links.get('error') if isinstance(ep_links, dict) else 'Unknown error'}")

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

    def get_season_ep_ranges(self, episodes):
        '''
        Return episode ranges organized by season.
        AniSnatch groups all episodes under season 1.
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
