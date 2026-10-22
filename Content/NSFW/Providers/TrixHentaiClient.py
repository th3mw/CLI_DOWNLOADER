import html
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
from bs4 import BeautifulSoup

from Core.BaseClient import BaseClient


class TrixHentaiClient(BaseClient):
    '''
    Client for scraping and streaming NSFW Anime / Hentai from TrixHentai (https://www.trixhentai.com/).
    Direct high-speed MP4 downloads with age-gate verification bypass.
    '''
    def __init__(self, config=None, session=None, series_type='NSFW', content_filter=None):
        config = config or {}
        super().__init__(config.get('request_timeout', 30) if isinstance(config, dict) else 30, session)
        self.client_name = 'trixhentai'
        self.name = 'TrixHentai'
        self.provider_name = 'TrixHentai'
        trix_cfg = config.get('trixhentai', {}) if isinstance(config, dict) else {}
        self.base_url = trix_cfg.get('base_url', 'https://www.trixhentai.com').rstrip('/')
        self._target_item = {}
        self.default_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': f"{self.base_url}/"
        }
        # Age gate bypass cookie
        self.cookies = {'age_gate': '1'}
        if self.req_session:
            self.req_session.cookies.set('age_gate', '1', domain='.trixhentai.com')

    def _clean_title(self, raw_str):
        if not raw_str:
            return ''
        unescaped = html.unescape(str(raw_str).strip())
        return re.sub(r'[\u2010\u2011\u2012\u2013\u2014\u2015]', '-', unescaped).strip()

    def search(self, search_term):
        self.logger.info(f"Searching TrixHentai for: {search_term}")
        query = search_term.strip()
        encoded_query = quote(query)

        search_url = f"{self.base_url}/?s={encoded_query}"
        html_text = self._send_request(search_url, extra_headers=self.default_headers, return_type='text', silent=True)

        if not html_text:
            self.logger.warning(f"No response from TrixHentai for '{search_term}'")
            return None

        soup = BeautifulSoup(html_text, 'html.parser')
        items = soup.find_all(['div', 'article'], class_=lambda c: c and 'item' in c)

        results = {}
        idx = 1
        seen_urls = set()

        for it in items:
            link_tag = it.find('a', href=lambda h: h and '/video/' in h)
            if not link_tag:
                continue
            v_url = link_tag['href']
            if v_url in seen_urls:
                continue
            seen_urls.add(v_url)

            h_tag = it.find(['h2', 'h3', 'h1', 'p'])
            raw_title = h_tag.get_text(strip=True) if h_tag else (link_tag.get('title') or link_tag.get_text(strip=True))
            if not raw_title:
                continue

            title = self._clean_title(raw_title)
            img_tag = it.find('img')
            cover_url = img_tag.get('src') if img_tag else None

            # Detect episode if present
            ep_match = re.search(r'(?:[eé]pisode|ep\.?)\s*(\d+)', title, re.IGNORECASE)
            ep_str = f"Ep {ep_match.group(1)}" if ep_match else "Video"

            card_title = title
            card_meta = f"[NSFW] • {ep_str} • MP4 • TrixHentai"

            results[idx] = {
                'title': card_title,
                'raw_title': title,
                'url': v_url,
                'slug': v_url.strip('/').split('/')[-1],
                'cover_url': cover_url,
                'media_type': 'nsfw',
                'card_title': card_title,
                'card_meta': card_meta
            }
            idx += 1

        if not results:
            self.logger.warning(f"No results found on TrixHentai for '{search_term}'")
            return None

        return results

    def fetch_episodes_list(self, target):
        self._target_item = target
        raw_name = target.get('raw_title') or target.get('title', 'NSFW')
        clean_name = self._clean_title(raw_name)
        v_url = target.get('url')

        m = re.search(r'(?:[eé]pisode|ep\.?)\s*(\d+)', clean_name, re.IGNORECASE)
        ep_num = int(m.group(1)) if m else 1

        return [{
            'episode': ep_num,
            'episodeName': self._windows_safe_string(clean_name),
            'raw_name': clean_name,
            'url': v_url,
            'slug': target.get('slug', ''),
            'season': 1
        }]

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

        # 1. Match jwplayer file: '...mp4'
        mp4_url = None
        match = re.search(r'file\s*:\s*[\"\']([^\"\']+\.mp4[^\"]*)[\"\']', html_text)
        if match:
            mp4_url = match.group(1)
        else:
            # 2. Match HTML5 source tag
            match = re.search(r'<source[^>]+src=[\"\']([^\"\']+\.mp4[^\"]*)[\"\']', html_text)
            if match:
                mp4_url = match.group(1)

        if not mp4_url:
            return ep_no, {'error': f"No direct MP4 stream found for episode {ep_no}"}

        stream_entry = {
            'resolution_size': '1280x720',
            'downloadLink': mp4_url,
            'downloadType': 'mp4',
            'refererLink': f"{self.base_url}/",
            'duration': 0
        }

        m3u8_links = {
            '720': stream_entry,
            '1080': stream_entry
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
        clean_title = re.sub(r'\s*[-–]\s*(?:[eé]pisode|ep\.?)\s*\d+.*$', '', title, flags=re.IGNORECASE).strip()
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
            elif '720' in res_data:
                chosen_res = '720'
            elif '1080' in res_data:
                chosen_res = '1080'
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
                ext='.mp4'
            )

            download_link = stream_info.get('downloadLink')
            referer_link = stream_info.get('refererLink', f"{self.base_url}/")

            self._colprint('results', f"  Episode: {ep_no:02d} | {chosen_res}P | Link found [{download_link[:60]}...]")

            episode_links[ep_no] = {
                'episodeName': final_filename,
                'downloadLink': download_link,
                'downloadType': 'mp4',
                'refererLink': referer_link,
                'resolution': chosen_res,
                'season': 1,
                'episode': ep_no,
                'type': 'nsfw'
            }

        return episode_links
