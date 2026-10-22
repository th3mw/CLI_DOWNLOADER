import pytest
from unittest.mock import patch, MagicMock
from Core.provider_factory import get_providers_for_category, create_client, get_downloader
from Content.NSFW.Providers.MioHentaiClient import MioHentaiClient
from Content.Movies.Downloaders.MovieDownloader import MovieDownloader


def test_miohentai_registration():
    providers = get_providers_for_category('Hentai (NSFW)')
    keys = [p['key'] for p in providers]
    assert 'miohentai' in keys

    client = create_client('Hentai (NSFW)', 'miohentai', {})
    assert isinstance(client, MioHentaiClient)
    assert client.provider_name == 'MioHentai'
    assert client.client_name == 'miohentai'

    # Downloader resolution for mp4
    dl_cls = get_downloader('Hentai (NSFW)', 'mp4')
    assert dl_cls == MovieDownloader


def test_miohentai_search_series_and_posts():
    client = MioHentaiClient({})

    mock_series_response = [
        {
            'id': 100,
            'name': 'Test Series &amp; More',
            'count': 3,
            'link': 'https://miohentai.com/series/test-series/',
            'slug': 'test-series'
        }
    ]
    mock_posts_response = [
        {
            'id': 501,
            'title': {'rendered': 'Standalone Video &#8211; Episode 1'},
            'link': 'https://miohentai.com/standalone-video-episode-1/',
            'slug': 'standalone-video-episode-1',
            'series': []
        }
    ]

    with patch.object(client, '_send_request') as mock_send:
        def side_effect(url, **kwargs):
            if '/series?' in url:
                return mock_series_response
            if '/posts?' in url:
                return mock_posts_response
            return None

        mock_send.side_effect = side_effect
        results = client.search('Test')

        assert len(results) == 2
        assert results[1]['type'] == 'series'
        assert results[1]['raw_title'] == 'Test Series & More'
        assert results[1]['count'] == 3
        assert '[NSFW]' in results[1]['card_meta']

        assert results[2]['type'] == 'post'
        assert results[2]['raw_title'] == 'Standalone Video - Episode 1'


def test_miohentai_fetch_episodes_list():
    client = MioHentaiClient({})

    # 1. Target with series_id
    series_target = {
        'type': 'series',
        'series_id': 100,
        'raw_title': 'Test Series',
        'slug': 'test-series'
    }

    mock_episodes_response = [
        {'id': 2, 'title': {'rendered': 'Test Series &#8211; Episode 2'}, 'link': 'https://miohentai.com/ep2/', 'slug': 'ep2'},
        {'id': 1, 'title': {'rendered': 'Test Series &#8211; Episode 1'}, 'link': 'https://miohentai.com/ep1/', 'slug': 'ep1'},
    ]

    with patch.object(client, '_send_request', return_value=mock_episodes_response):
        episodes = client.fetch_episodes_list(series_target)
        assert len(episodes) == 2
        # Verified sorted by episode number
        assert episodes[0]['episode'] == 1
        assert episodes[0]['raw_name'] == 'Test Series - Episode 1'
        assert episodes[1]['episode'] == 2

    # 2. Standalone target
    post_target = {
        'type': 'post',
        'raw_title': 'Single OVA &#8211; Episode 1',
        'url': 'https://miohentai.com/single-ova/',
        'id': 999
    }
    single_eps = client.fetch_episodes_list(post_target)
    assert len(single_eps) == 1
    assert single_eps[0]['episode'] == 1
    assert single_eps[0]['raw_name'] == 'Single OVA - Episode 1'


def test_miohentai_links_and_naming():
    client = MioHentaiClient({})

    # set_out_names
    target_series = {'raw_title': 'Overflow &#8211; Episode 1'}
    dir_name, prefix = client.set_out_names(target_series)
    assert dir_name == 'Overflow'
    assert prefix == 'Overflow - '

    # fetch_episode_links
    ep_data = {'episode': 1, 'url': 'https://miohentai.com/ep1/'}
    fake_html = '<video id="video-player" data-video-src="https://cdn.miohentai.com/index.php?data=abc123xyz"></video>'

    with patch.object(client, '_send_request', return_value=fake_html):
        ep_no, res_dict = client._fetch_single_episode_link(ep_data)
        assert ep_no == 1
        assert '720' in res_dict
        assert res_dict['720']['downloadLink'] == 'https://cdn.miohentai.com/index.php?data=abc123xyz'
        assert res_dict['720']['downloadType'] == 'mp4'

    # fetch_m3u8_links
    target_ep_links = {1: res_dict}
    final_links = client.fetch_m3u8_links(target_ep_links, '720', 'Overflow - ')
    assert 1 in final_links
    ep1_info = final_links[1]
    assert ep1_info['downloadType'] == 'mp4'
    assert 'Overflow - E01 - 720P [MioHentai].mp4' in ep1_info['episodeName']
