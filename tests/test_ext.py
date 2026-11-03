import os
import unittest
from unittest.mock import MagicMock, patch

from Content.Movies.Downloaders.TorrentDownloader import TorrentDownloader
from Content.Series.Providers.ExtClient import ExtClient
from Core.provider_factory import create_client, get_providers_for_category


class TestExtClient(unittest.TestCase):

    def setUp(self):
        self.client = ExtClient()

    def test_provider_registration(self):
        providers = get_providers_for_category('TV Shows')
        self.assertTrue(len(providers) > 0)
        first_prov = providers[0]
        self.assertEqual(first_prov['key'], 'ext')
        self.assertEqual(first_prov['name'], 'Ext.to')
        self.assertEqual(first_prov['type'], 'torrent')

        created = create_client('TV Shows', 'ext', {})
        self.assertIsNotNone(created)
        self.assertEqual(created.name, 'Ext.to')

    def test_cookie_initialization(self):
        self.assertIn('cf_clearance', self.client._cookies)
        self.assertIn('PHPSESSID', self.client._cookies)
        headers = self.client._get_headers(referer='https://ext.to/')
        self.assertIn('User-Agent', headers)
        self.assertIn('Referer', headers)

    def test_parse_selected_indices(self):
        td = TorrentDownloader({'download_dir': '/tmp'}, {})
        self.assertIsNone(td._parse_selected_indices('all', 10))
        self.assertIsNone(td._parse_selected_indices('', 10))
        self.assertIsNone(td._parse_selected_indices('1-10', 10))
        self.assertEqual(td._parse_selected_indices('1-3', 10), '1,2,3')
        self.assertEqual(td._parse_selected_indices('1, 3, 5', 10), '1,3,5')
        self.assertEqual(td._parse_selected_indices('1-2, 5, 8-10', 10), '1,2,5,8,9,10')

    def test_search_parsing(self):
        mock_html = '''
        <html>
            <body>
                <a href="/breaking-bad-s2743/">Breaking Bad</a>
                <a href="/better-call-saul-s3128/">Better Call Saul</a>
            </body>
        </html>
        '''
        mock_resp = MagicMock()
        mock_resp.text = mock_html
        mock_resp.status_code = 200

        with patch.object(self.client, '_request', return_value=mock_resp):
            results = self.client.search('Breaking Bad')
            self.assertIsNotNone(results)
            self.assertIn(1, results)
            self.assertEqual(results[1]['raw_title'], 'Breaking Bad')
            self.assertEqual(results[1]['show_slug'], 'breaking-bad-s2743')

    def test_fetch_episodes_list_as_seasons(self):
        mock_hub_html = '''
        <html>
            <body>
                <a href="/breaking-bad-s2743/?s=1">7 episodes</a>
                <a href="/breaking-bad-s2743/?s=2">13 episodes</a>
                <a href="/breaking-bad-s2743/?s=3">13 episodes</a>
            </body>
        </html>
        '''
        mock_resp = MagicMock()
        mock_resp.text = mock_hub_html
        mock_resp.status_code = 200

        target = {'raw_title': 'Breaking Bad', 'show_slug': 'breaking-bad-s2743'}
        with patch.object(self.client, '_request', return_value=mock_resp):
            seasons = self.client.fetch_episodes_list(target)
            self.assertEqual(len(seasons), 3)
            self.assertEqual(seasons[0]['season'], 1)
            self.assertTrue(seasons[0]['is_season_pack'])
            self.assertIn('Season 01 Complete Pack', seasons[0]['episodeName'])

    def test_fetch_season_packs_and_resolution_ranking(self):
        mock_torrents_html = '''
        <html>
            <body>
                <div class="torrent-row">
                    <a href="/breaking-bad-s01-complete-1080p-717634/">Breaking Bad S01 Complete 1080p BluRay</a>
                    <div>seeders: 400 leechers: 50</div>
                    <div>Size 4.2 GB Files 8 Age 2 years ago</div>
                </div>
                <div class="torrent-row">
                    <a href="/breaking-bad-s01-pack-1080p-999999/">Breaking Bad S01 1080p WebRip</a>
                    <div>seeders: 150 leechers: 20</div>
                    <div>Size 5.1 GB Files 8 Age 1 year ago</div>
                </div>
            </body>
        </html>
        '''
        mock_resp = MagicMock()
        mock_resp.text = mock_torrents_html
        mock_resp.status_code = 200

        with patch.object(self.client, '_request', return_value=mock_resp):
            packs = self.client.fetch_season_packs('breaking-bad-s2743', 1)
            self.assertIn('1080p', packs)
            p_list = packs['1080p']
            self.assertEqual(len(p_list), 2)
            # Must be ranked by seeders descending
            self.assertGreater(p_list[0]['seeds'], p_list[1]['seeds'])
            self.assertEqual(p_list[0]['seeds'], 400)
            self.assertEqual(p_list[0]['size'], '4.2 GB')

    def test_fetch_torrent_magnet_and_files(self):
        mock_detail_html = '''
        <html>
            <head>
                <meta name="csrf-token" content="test_csrf_token_123">
            </head>
            <body>
                <script>
                    var pageToken = "test_page_token_456";
                </script>
                <table>
                    <tr>
                        <td>Breaking.Bad.S01E01.Pilot.1080p.mkv</td>
                        <td>MKV</td>
                        <td>928.3 MB</td>
                    </tr>
                    <tr>
                        <td>Breaking.Bad.S01E02.Cats.In.The.Bag.1080p.mkv</td>
                        <td>MKV</td>
                        <td>600.0 MB</td>
                    </tr>
                </table>
            </body>
        </html>
        '''
        mock_detail_resp = MagicMock()
        mock_detail_resp.text = mock_detail_html
        mock_detail_resp.status_code = 200

        mock_post_resp = MagicMock()
        mock_post_resp.json.return_value = {
            'success': True,
            'url': 'magnet:?xt=urn:btih:TESTHASH1234567890&dn=Breaking+Bad+S01'
        }

        def mock_request(url, method='get', **kwargs):
            if 'getTorrentMagnet.php' in url:
                return mock_post_resp
            return mock_detail_resp

        with patch.object(self.client, '_request', side_effect=mock_request):
            res = self.client.fetch_torrent_magnet_and_files('https://ext.to/breaking-bad-s01-717634/')
            self.assertIsNotNone(res)
            self.assertTrue(res['magnet'].startswith('magnet:?xt=urn:btih:'))
            self.assertEqual(len(res['files']), 2)
            self.assertEqual(res['files'][0]['name'], 'Breaking.Bad.S01E01.Pilot.1080p.mkv')
            self.assertEqual(res['files'][0]['size'], '928.3 MB')
            self.assertEqual(res['files'][1]['name'], 'Breaking.Bad.S01E02.Cats.In.The.Bag.1080p.mkv')

    def test_detect_resolution_and_dead_torrent_filtering(self):
        self.assertEqual(self.client._detect_resolution('Show S01 2160p UHD HDR'), '2160p')
        self.assertEqual(self.client._detect_resolution('Show S01 4K BluRay'), '2160p')
        self.assertEqual(self.client._detect_resolution('Show S01 1080p BluRay x264'), '1080p')
        self.assertEqual(self.client._detect_resolution('Show S01 720p HDTV'), '720p')
        self.assertEqual(self.client._detect_resolution('Show S01 DVDRip XviD'), '480p')

        mock_multi_res_html = '''
        <html>
            <body>
                <div class="torrent-row">
                    <a href="/show-s01-1080p-alive-111111/">Show S01 1080p BluRay</a>
                    <div>seeders: 50 leechers: 5</div>
                    <div>Size 4.0 GB</div>
                </div>
                <div class="torrent-row">
                    <a href="/show-s01-1080p-dead-222222/">Show S01 1080p WebRip</a>
                    <div>seeders: 0 leechers: 0</div>
                    <div>Size 3.5 GB</div>
                </div>
                <div class="torrent-row">
                    <a href="/show-s01-720p-alive-333333/">Show S01 720p HDTV</a>
                    <div>seeders: 20 leechers: 2</div>
                    <div>Size 2.0 GB</div>
                </div>
            </body>
        </html>
        '''
        mock_resp = MagicMock()
        mock_resp.text = mock_multi_res_html
        mock_resp.status_code = 200

        with patch.object(self.client, '_request', return_value=mock_resp):
            packs = self.client.fetch_season_packs('test-show-s123', 1)
            self.assertIn('1080p', packs)
            self.assertIn('720p', packs)
            # Dead torrent (0 seeds) should be filtered out because a healthy 1080p torrent exists
            self.assertEqual(len(packs['1080p']), 1)
            self.assertEqual(packs['1080p'][0]['torrent_id'], 111111)
            self.assertEqual(packs['1080p'][0]['seeds'], 50)
            self.assertEqual(packs['1080p'][0]['leeches'], 5)
            self.assertEqual(len(packs['720p']), 1)
            self.assertEqual(packs['720p'][0]['torrent_id'], 333333)
            self.assertEqual(packs['720p'][0]['seeds'], 20)
            self.assertEqual(packs['720p'][0]['leeches'], 2)

    def test_table_cell_leech_parsing(self):
        mock_table_html = '''
        <html>
            <body>
                <table>
                    <tr><th>TORRENT NAME</th><th>SIZE</th><th>FILES</th><th>AGE</th><th>SEED</th><th>LEECH</th></tr>
                    <tr>
                        <td><a href="/see-s01-1080p-12345/">See S01 1080p</a></td>
                        <td>Size 11 GB</td>
                        <td>Files 8</td>
                        <td>Age 1 year</td>
                        <td>Seed 71</td>
                        <td>Leech 63</td>
                    </tr>
                </table>
            </body>
        </html>
        '''
        mock_resp = MagicMock()
        mock_resp.text = mock_table_html
        mock_resp.status_code = 200

        with patch.object(self.client, '_request', return_value=mock_resp):
            packs = self.client.fetch_season_packs('see-s4954', 1)
            self.assertIn('1080p', packs)
            self.assertEqual(len(packs['1080p']), 1)
            p = packs['1080p'][0]
            self.assertEqual(p['seeds'], 71)
            self.assertEqual(p['leeches'], 63)

    def test_render_table_formatting_and_wrapping(self):
        from Core.commons import render_table, visible_len
        cols = [
            {'key': 'index', 'title': '#', 'width': 6, 'align': 'center'},
            {'key': 'title', 'title': 'RELEASE NAME', 'wrap': True, 'align': 'left'},
            {'key': 'size', 'title': 'SIZE', 'width': 10, 'align': 'center'},
            {'key': 'seeds', 'title': 'SEEDS', 'width': 8, 'align': 'center'},
        ]
        rows = [
            {
                'index': '[1]',
                'title': 'Very Long Release Name That Wraps Over Multiple Lines Inside Table Cell',
                'size': '11 GB',
                'seeds': '71',
                'is_default': True
            }
        ]
        footer = [{'index': '[0]', 'title': 'Back', 'size': '', 'seeds': ''}]
        rendered = render_table('TEST TABLE', cols, rows, max_width=80, footer_rows=footer)
        self.assertIn('TEST TABLE', rendered)
        self.assertIn('[1]', rendered)
        self.assertIn('[0]', rendered)
        self.assertIn('11 GB', rendered)
        self.assertIn('RELEASE NAME', rendered)


if __name__ == '__main__':
    unittest.main()
