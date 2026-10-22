import pytest
from unittest.mock import patch
from Core.provider_factory import get_providers_for_category, create_client, get_downloader
from Content.NSFW.Providers.HentaiHavenClient import HentaiHavenClient
from Content.Anime.Downloaders.HLSDownloader import HLSDownloader


def test_hentaihaven_registration():
    providers = get_providers_for_category('Hentai (NSFW)')
    keys = [p['key'] for p in providers]
    assert 'hentaihaven' in keys

    client = create_client('Hentai (NSFW)', 'hentaihaven', {})
    assert isinstance(client, HentaiHavenClient)
    assert client.provider_name == 'HentaiHaven'
    assert client.client_name == 'hentaihaven'

    dl_cls = get_downloader('Hentai (NSFW)', 'hls')
    assert dl_cls == HLSDownloader


def test_hentaihaven_search():
    client = HentaiHavenClient({})

    mock_search_data = {
        'data': [
            {
                'id': 1234,
                'slug': 'test-anime',
                'title': {'rendered': 'Test Anime &#8211; The Animation'},
                'meta': {'vraven_remote_thumbnail': 'images/test.jpg'}
            }
        ]
    }

    with patch.object(client, '_send_request', return_value=mock_search_data):
        results = client.search('Test Anime')
        assert len(results) == 1
        assert results[1]['raw_title'] == 'Test Anime - The Animation'
        assert results[1]['slug'] == 'test-anime'
        assert '[NSFW]' in results[1]['card_meta']


def test_hentaihaven_episodes_and_links():
    client = HentaiHavenClient({})

    target = {
        'slug': 'test-anime',
        'raw_title': 'Test Anime',
        'url': 'https://hentaihaven.xxx/watch/test-anime/'
    }

    fake_watch_html = '''
    <a href="/watch/test-anime/episode-1/">Episode 1</a>
    <a href="/watch/test-anime/episode-2/">Episode 2</a>
    '''

    with patch.object(client, '_send_request', return_value=fake_watch_html):
        episodes = client.fetch_episodes_list(target)
        assert len(episodes) == 2
        assert episodes[0]['episode'] == 1
        assert episodes[1]['episode'] == 2

    # Test single episode stream resolution
    fake_ep_html = '''
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"VideoObject","contentUrl":"https://octopusmanifest.org/stream/playlist.m3u8"}
    </script>
    '''

    with patch.object(client, '_send_request', return_value=fake_ep_html):
        ep_no, res_dict = client._fetch_single_episode_link({'episode': 1, 'url': 'https://hentaihaven.xxx/watch/test-anime/episode-1/'})
        assert ep_no == 1
        assert '1080' in res_dict
        assert res_dict['1080']['downloadLink'] == 'https://octopusmanifest.org/stream/playlist.m3u8'
        assert res_dict['1080']['downloadType'] == 'hls'

    # Test filename formatting
    final_links = client.fetch_m3u8_links({1: res_dict}, '1080', 'Test Anime - ')
    assert 1 in final_links
    assert 'Test Anime - E01 - 1080P [HentaiHaven].mkv' in final_links[1]['episodeName']
