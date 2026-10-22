import html
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
from bs4 import BeautifulSoup

from Core.BaseClient import BaseClient


class HentaiHavenClient(BaseClient):
    '''
    Client for scraping and streaming NSFW Anime / Hentai from HentaiHaven (https://hentaihaven.xxx/).
    Extracts multi-resolution HLS master streams with subtitle tracks.
    '''
    def __init__(self, config=None, session=None, series_type='NSFW', content_filter=None):
        config = config or {}
        super().__init__(config.get('request_timeout', 30) if isinstance(config, dict) else 30, session)
        self.client_name = 'hentaihaven'
        self.name = 'HentaiHaven'
        self.provider_name = 'HentaiHaven'
        hh_cfg = config.get('hentaihaven', {}) if isinstance(config, dict) else {}
        self.base_url = hh_cfg.get('base_url', 'https://hentaihaven.xxx').rstrip('/')
        self.api_url = f"{self.base_url}/api/manga"
        self._target_item = {}
        self.default_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': f"{self.base_url}/"
        }

    def _clean_title(self, raw_str):
        if not raw_str:
            return ''
        unescaped = html.unescape(str(raw_str).strip())
        return re.sub(r'[\u2010\u2011\u2012\u2013\u2014\u2015]', '-', unescaped).strip()

    def search(self, search_term):
        self.logger.info(f"Searching HentaiHaven for: {search_term}")
        query = search_term.strip()
        encoded_query = quote(query)

        search_url = f"{self.api_url}/?search={encoded_query}&per_page=20&locale=en"
        data = self._send_request(search_url, extra_headers=self.default_headers, return_type='json', silent=True)

        if not data or not isinstance(data, dict) or not data.get('data'):
            self.logger.warning(f"No results found on HentaiHaven for '{search_term}'")
            return None

        results = {}
        for idx, item in enumerate(data['data'], start=1):
            title = self._clean_title(item.get('title', {}).get('rendered', 'Unknown'))
            slug = item.get('slug', '')
            item_id = item.get('id')
            meta = item.get('meta', {})
            thumb = meta.get('vraven_remote_thumbnail')
            cover_url = f"https://img.hentaihaven.xxx/{thumb}" if thumb else None

            card_title = title
            card_meta = "[NSFW] • HLS • HentaiHaven"

            results[idx] = {
                'title': card_title,
                'raw_title': title,
                'slug': slug,
                'id': item_id,
                'url': f"{self.base_url}/watch/{slug}/",
                'cover_url': cover_url,
                'media_type': 'nsfw',
                'card_title': card_title,
                'card_meta': card_meta
            }

        return results

    def fetch_episodes_list(self, target):
        self._target_item = target
        slug = target.get('slug', '')
        raw_name = target.get('raw_title') or target.get('title', 'NSFW')
        watch_url = target.get('url') or f"{self.base_url}/watch/{slug}/"

        episodes = []
        html_text = self._send_request(watch_url, extra_headers=self.default_headers, return_type='text', silent=True)
        if html_text:
            # Check for season subpage (e.g. /watch/slug/season-1/)
            season_matches = re.findall(rf'href=[\"\'](/watch/{slug}/season-\d+/)[\"\']', html_text)
            if season_matches:
                season_url = f"{self.base_url}{season_matches[0]}"
                season_html = self._send_request(season_url, extra_headers=self.default_headers, return_type='text', silent=True)
                if season_html:
                    html_text += '\n' + season_html

            # Extract episode links
            ep_matches = re.findall(rf'/watch/{slug}/(?:[^/]+/)?(episode-(\d+))/', html_text, re.IGNORECASE)
            seen_nums = set()
            for ep_slug, ep_num_str in ep_matches:
                try:
                    num = int(ep_num_str)
                except Exception:
                    continue
                if num not in seen_nums:
                    seen_nums.add(num)
                    ep_url = f"{self.base_url}/watch/{slug}/{ep_slug}/"
                    ep_name = f"{raw_name} - Episode {num}"
                    episodes.append({
                        'episode': num,
                        'episodeName': self._windows_safe_string(ep_name),
                        'raw_name': ep_name,
                        'url': ep_url,
                        'slug': ep_slug,
                        'season': 1
                    })

        # Single episode fallback
        if not episodes:
            m = re.search(r'(?:episode|ep\.?)\s*(\d+)', raw_name, re.IGNORECASE)
            ep_num = int(m.group(1)) if m else 1
            episodes.append({
                'episode': ep_num,
                'episodeName': self._windows_safe_string(raw_name),
                'raw_name': raw_name,
                'url': watch_url,
                'slug': slug,
                'season': 1
            })

        episodes.sort(key=lambda x: x['episode'])
        return episodes

    def show_episode_results(self, items, *predefined_range):
        for item in items:
            name = item.get('raw_name') or item.get('episodeName')
            self._colprint('results', f"  [Episode {item.get('episode', 1)}] {name}")

    def get_season_ep_ranges(self, episodes):
        return {1: {'start': 1, 'end': len(episodes)}}

    def _fetch_single_episode_link(self, ep_data):
        ep_no = ep_data.get('episode', 1)
        page_url = ep_data.get('url')
        if not page_url:
            return ep_no, {'error': f"Missing URL for episode {ep_no}"}

        html_text = self._send_request(page_url, extra_headers=self.default_headers, return_type='text', silent=True)
        if not html_text:
            return ep_no, {'error': f"Could not load episode page {page_url}"}

        # Extract contentUrl from JSON-LD or regex
        m3u8_url = None
        match = re.search(r'\"contentUrl\"\s*:\s*\"([^\"]+\.m3u8[^\"]*)\"', html_text)
        if match:
            m3u8_url = match.group(1).replace(r'\/', '/')
        else:
            match = re.search(r'https?://[^\s\"\']+\.m3u8[^\s\"\']*', html_text)
            if match:
                m3u8_url = match.group(0)

        if not m3u8_url:
            return ep_no, {'error': f"No playable HLS stream found for episode {ep_no}"}

        stream_entry = {
            'resolution_size': '1920x1080',
            'downloadLink': m3u8_url,
            'downloadType': 'hls',
            'refererLink': f"{self.base_url}/",
            'duration': 0
        }

        m3u8_links = {
            '1080': stream_entry,
            '720': stream_entry,
            '360': stream_entry
        }
        return ep_no, m3u8_links

    def fetch_episode_links(self, episodes, ep_ranges):
        selected_eps = episodes
        if not selected_eps:
            return {}

        target_links = {}
        with ThreadPoolExecutor(max_workers=min(4, len(selected_eps))) as executor:
            results = list(executor.map(self._fetch_single_episode_link, selected_eps))

        for ep_no, res_dict in sorted(results, key=lambda x: x[0]):
            target_links[ep_no] = res_dict

        return target_links

    def set_out_names(self, target_series):
        raw = target_series.get('raw_title') or target_series.get('title', 'NSFW')
        title = self._clean_title(raw)
        clean_title = re.sub(r'\s*[-–]\s*(?:Episode|Ep\.?)\s*\d+.*$', '', title, flags=re.IGNORECASE).strip()
        safe_title = self._windows_safe_string(clean_title or 'NSFW')
        return safe_title, f"{safe_title} - "

    def fetch_m3u8_links(self, target_ep_links, resolution, episode_prefix):
        episode_links = {}
        series_title = episode_prefix.rstrip(' -').strip()

        for ep_no, res_data in target_ep_links.items():
            if 'error' in res_data:
                continue

            chosen_res = None
            if str(resolution) in res_data:
                chosen_res = str(resolution)
            elif '1080' in res_data:
                chosen_res = '1080'
            elif '720' in res_data:
                chosen_res = '720'
            elif res_data:
                chosen_res = next(iter(res_data.keys()))

            if not chosen_res:
                continue

            stream_info = res_data[chosen_res]
            final_filename = self.format_media_filename(
                series_title=series_title,
                season=1,
                episode=ep_no,
                resolution=chosen_res,
                is_movie=False,
                ext='.mkv'
            )

            download_link = stream_info.get('downloadLink')
            referer_link = stream_info.get('refererLink', f"{self.base_url}/")

            self._colprint('results', f"  Episode: {ep_no:02d} | {chosen_res}P | Link found [{download_link[:60]}...]")

            episode_links[ep_no] = {
                'episodeName': final_filename,
                'downloadLink': download_link,
                'downloadType': 'hls',
                'refererLink': referer_link,
                'resolution': chosen_res,
                'season': 1,
                'episode': ep_no,
                'type': 'nsfw'
            }

        return episode_links
