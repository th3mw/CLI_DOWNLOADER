import html
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
from bs4 import BeautifulSoup

from Core.BaseClient import BaseClient


class MioHentaiClient(BaseClient):
    '''
    Client for scraping and streaming NSFW Anime / Hentai from MioHentai (https://miohentai.com/).
    Supports series exploration, multi-episode batching, and direct high-speed MP4 streams.
    '''
    def __init__(self, config=None, session=None, series_type='NSFW', content_filter=None):
        config = config or {}
        super().__init__(config.get('request_timeout', 30) if isinstance(config, dict) else 30, session)
        self.client_name = 'miohentai'
        self.name = 'MioHentai'
        self.provider_name = 'MioHentai'
        mio_cfg = config.get('miohentai', {}) if isinstance(config, dict) else {}
        self.base_url = mio_cfg.get('base_url', 'https://miohentai.com').rstrip('/')
        self.api_url = f"{self.base_url}/wp-json/wp/v2"
        self._target_item = {}
        self.default_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': f"{self.base_url}/"
        }

    def _clean_title(self, raw_str):
        if not raw_str:
            return ''
        unescaped = html.unescape(str(raw_str).strip())
        # Normalize dash characters
        return re.sub(r'[\u2010\u2011\u2012\u2013\u2014\u2015]', '-', unescaped).strip()

    def search(self, search_term):
        self.logger.info(f"Searching MioHentai for: {search_term}")
        query = search_term.strip()
        encoded_query = quote(query)

        results = {}
        idx = 1
        seen_series_ids = set()
        seen_urls = set()

        # 1. Search series taxonomy
        try:
            series_url = f"{self.api_url}/series?search={encoded_query}&per_page=15"
            series_resp = self._send_request(series_url, extra_headers=self.default_headers, return_type='json', silent=True)
            if isinstance(series_resp, list):
                for s in series_resp:
                    s_id = s.get('id')
                    s_name = self._clean_title(s.get('name', 'Unknown'))
                    s_count = s.get('count', 1)
                    s_link = s.get('link', '')
                    s_slug = s.get('slug', '')

                    if s_id and s_id not in seen_series_ids and s_count > 0:
                        seen_series_ids.add(s_id)
                        seen_urls.add(s_link)
                        card_title = f"{s_name} ({s_count} Ep)" if s_count > 1 else s_name
                        card_meta = f"[NSFW] • {s_count} Episode{'s' if s_count > 1 else ''} • MioHentai"

                        results[idx] = {
                            'title': card_title,
                            'raw_title': s_name,
                            'slug': s_slug,
                            'id': s_id,
                            'series_id': s_id,
                            'type': 'series',
                            'count': s_count,
                            'url': s_link,
                            'media_type': 'nsfw',
                            'card_title': card_title,
                            'card_meta': card_meta
                        }
                        idx += 1
        except Exception as e:
            self.logger.warning(f"Error querying MioHentai series API: {e}")

        # 2. Search posts
        try:
            posts_url = f"{self.api_url}/posts?search={encoded_query}&per_page=15&_embed=1"
            posts_resp = self._send_request(posts_url, extra_headers=self.default_headers, return_type='json', silent=True)
            if isinstance(posts_resp, list):
                for p in posts_resp:
                    p_id = p.get('id')
                    p_link = p.get('link', '')
                    p_series = p.get('series') or []
                    first_series_id = p_series[0] if (isinstance(p_series, list) and len(p_series) > 0) else None

                    # If this post belongs to a series we already listed, skip duplicate
                    if first_series_id and first_series_id in seen_series_ids:
                        continue
                    if p_link in seen_urls:
                        continue

                    seen_urls.add(p_link)
                    p_title = self._clean_title(p.get('title', {}).get('rendered', 'Unknown'))
                    p_slug = p.get('slug', '')

                    embedded = p.get('_embedded', {})
                    media = embedded.get('wp:featuredmedia', [])
                    cover_url = media[0].get('source_url') if media else None

                    card_title = p_title
                    card_meta = "[NSFW] • Episode • MioHentai"

                    results[idx] = {
                        'title': card_title,
                        'raw_title': p_title,
                        'slug': p_slug,
                        'id': p_id,
                        'series_id': first_series_id,
                        'type': 'post',
                        'count': 1,
                        'url': p_link,
                        'cover_url': cover_url,
                        'media_type': 'nsfw',
                        'card_title': card_title,
                        'card_meta': card_meta
                    }
                    idx += 1
        except Exception as e:
            self.logger.warning(f"Error querying MioHentai posts API: {e}")

        # 3. Fallback: Search Suggestions Endpoint if results are empty
        if not results:
            try:
                sugg_url = f"{self.base_url}/wp-admin/admin-ajax.php?action=se-search-suggestions&term={encoded_query}"
                sugg_resp = self._send_request(sugg_url, extra_headers=self.default_headers, return_type='json', silent=True)
                if isinstance(sugg_resp, dict) and sugg_resp.get('items'):
                    for item in sugg_resp['items']:
                        item_url = item.get('url', '')
                        if item_url in seen_urls:
                            continue
                        seen_urls.add(item_url)
                        item_title = self._clean_title(item.get('title', 'Unknown'))
                        item_id = item.get('id')
                        item_studio = item.get('studio', '')
                        item_year = item.get('year', '')

                        meta_parts = ['[NSFW]']
                        if item_year:
                            meta_parts.append(f"Year: {item_year}")
                        if item_studio:
                            meta_parts.append(f"Studio: {item_studio}")
                        meta_parts.append('MioHentai')

                        card_meta = " • ".join(meta_parts)
                        results[idx] = {
                            'title': item_title,
                            'raw_title': item_title,
                            'slug': item_url.strip('/').split('/')[-1] if item_url else '',
                            'id': item_id,
                            'series_id': None,
                            'type': 'post',
                            'count': 1,
                            'url': item_url,
                            'cover_url': item.get('thumbnail'),
                            'media_type': 'nsfw',
                            'card_title': item_title,
                            'card_meta': card_meta
                        }
                        idx += 1
            except Exception as e:
                self.logger.warning(f"Error querying MioHentai search suggestions: {e}")

        if not results:
            self.logger.warning(f"No results found on MioHentai for '{search_term}'")
            return None

        return results

    def fetch_episodes_list(self, target):
        self._target_item = target
        item_type = target.get('type')
        series_id = target.get('series_id')
        slug = target.get('slug', '')
        raw_name = target.get('raw_title') or target.get('title', 'NSFW')

        episodes = []

        # If target has a series taxonomy, resolve all episodes belonging to this series
        if series_id:
            try:
                ep_api_url = f"{self.api_url}/posts?series={series_id}&per_page=100&orderby=title&order=asc"
                posts_data = self._send_request(ep_api_url, extra_headers=self.default_headers, return_type='json', silent=True)
                if isinstance(posts_data, list) and len(posts_data) > 0:
                    for p in posts_data:
                        ep_title = self._clean_title(p.get('title', {}).get('rendered', ''))
                        m = re.search(r'(?:episode|ep\.?)\s*(\d+)', ep_title, re.IGNORECASE)
                        ep_num = int(m.group(1)) if m else 1
                        episodes.append({
                            'episode': ep_num,
                            'episodeName': self._windows_safe_string(ep_title),
                            'raw_name': ep_title,
                            'url': p.get('link'),
                            'id': p.get('id'),
                            'slug': p.get('slug'),
                            'season': 1
                        })
            except Exception as e:
                self.logger.warning(f"Could not load series episodes from API for series {series_id}: {e}")

        # Fallback: scrape series archive page if API returned nothing
        if not episodes and item_type == 'series' and slug:
            try:
                series_page_url = f"{self.base_url}/series/{slug}/"
                html_text = self._send_request(series_page_url, extra_headers=self.default_headers, return_type='text', silent=True)
                if html_text:
                    soup = BeautifulSoup(html_text, 'html.parser')
                    articles = soup.find_all('article')
                    for a in articles:
                        link_tag = a.find('a', href=True)
                        h3_tag = a.find('h3') or a.find('h2')
                        ep_title = self._clean_title(h3_tag.get_text(strip=True) if h3_tag else (link_tag.get('title') if link_tag else ''))
                        if not ep_title:
                            continue
                        m = re.search(r'(?:episode|ep\.?)\s*(\d+)', ep_title, re.IGNORECASE)
                        ep_num = int(m.group(1)) if m else 1
                        direct_url = a.find('a', attrs={'data-video-url': True})
                        data_video_url = direct_url['data-video-url'] if direct_url else None
                        episodes.append({
                            'episode': ep_num,
                            'episodeName': self._windows_safe_string(ep_title),
                            'raw_name': ep_title,
                            'url': link_tag['href'] if link_tag else '',
                            'data_video_url': data_video_url,
                            'season': 1
                        })
            except Exception as e:
                self.logger.warning(f"Could not scrape series page {slug}: {e}")

        # Single post fallback
        if not episodes:
            clean_name = self._clean_title(raw_name)
            m = re.search(r'(?:episode|ep\.?)\s*(\d+)', clean_name, re.IGNORECASE)
            ep_num = int(m.group(1)) if m else 1
            episodes.append({
                'episode': ep_num,
                'episodeName': self._windows_safe_string(clean_name),
                'raw_name': clean_name,
                'url': target.get('url'),
                'id': target.get('id'),
                'slug': slug,
                'season': 1
            })

        # Sort episodes by episode number ascending
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
        video_url = ep_data.get('data_video_url')
        page_url = ep_data.get('url')

        if not video_url and page_url:
            try:
                html_text = self._send_request(page_url, extra_headers=self.default_headers, return_type='text', silent=True)
                if html_text:
                    # 1. Match data-video-src on <video> tag
                    src_match = re.search(r'data-video-src=[\"\']([^\"\']+)[\"\']', html_text)
                    if not src_match:
                        # 2. Match videoSrc in window.videoPlayerBootConfig
                        src_match = re.search(r'videoSrc[\"\']?\s*:\s*[\"\']([^\"\']+)[\"\']', html_text)
                    if not src_match:
                        # 3. Match data-video-url on thumbnail
                        src_match = re.search(r'data-video-url=[\"\']([^\"\']+)[\"\']', html_text)
                    if src_match:
                        video_url = html.unescape(src_match.group(1).replace(r'\/', '/'))
            except Exception as e:
                self.logger.warning(f"Error fetching MioHentai episode page for ep {ep_no}: {e}")

        if not video_url:
            return ep_no, {'error': f"Failed to extract video stream for episode {ep_no}"}

        # Format stream dictionary
        stream_entry = {
            'resolution_size': '1280x720',
            'downloadLink': video_url,
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
        # Strip trailing episode markers from series folder/prefix
        clean_title = re.sub(r'\s*[-–]\s*(?:Episode|Ep\.?)\s*\d+.*$', '', title, flags=re.IGNORECASE).strip()
        clean_title = re.sub(r'\s*\(\d+\s*Ep(?:isodes?)?\)$', '', clean_title, flags=re.IGNORECASE).strip()
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
