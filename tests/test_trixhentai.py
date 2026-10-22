import pytest
from unittest.mock import patch
from Core.provider_factory import get_providers_for_category, create_client, get_downloader
from Content.NSFW.Providers.TrixHentaiClient import TrixHentaiClient
from Content.Movies.Downloaders.MovieDownloader import MovieDownloader


def test_trixhentai_registration():
    providers = get_providers_for_category('Hentai (NSFW)')
    keys = [p['key'] for p in providers]
    assert 'trixhentai' in keys

    client = create_client('Hentai (NSFW)', 'trixhentai', {})
    assert isinstance(client, TrixHentaiClient)
    assert client.provider_name == 'TrixHentai'
    assert client.client_name == 'trixhentai'

    dl_cls = get_downloader('Hentai (NSFW)', 'mp4')
    assert dl_cls == MovieDownloader


def test_trixhentai_search():
    client = TrixHentaiClient({})

    fake_search_html = '''
    <div class="item">
        <a href="https://www.trixhentai.com/video/overflow-episode-7/" title="Overflow – Épisode 7">
            <img src="https://www.trixhentai.com/thumb.jpg" />
            <h2>Overflow – Épisode 7</h2>
        </a>
    </div>
    '''

    with patch.object(client, '_send_request', return_value=fake_search_html):
        results = client.search('overflow')
        assert len(results) == 1
        assert results[1]['raw_title'] == 'Overflow - Épisode 7'
        assert results[1]['slug'] == 'overflow-episode-7'
        assert '[NSFW]' in results[1]['card_meta']


def test_trixhentai_episodes_and_links():
    client = TrixHentaiClient({})

    target = {
        'slug': 'overflow-episode-7',
        'raw_title': 'Overflow – Épisode 7',
        'url': 'https://www.trixhentai.com/video/overflow-episode-7/'
    }

    episodes = client.fetch_episodes_list(target)
    assert len(episodes) == 1
    assert episodes[0]['episode'] == 7

    # Test stream resolution
    fake_video_html = '''
    <script>
    const player = jwplayer('playerjw').setup({
        file: 'https://www.trixhentai.com/wp-content/uploads/2020/03/129-Overflow-Ep7.mp4'
    });
    </script>
    '''

    with patch.object(client, '_send_request', return_value=fake_video_html):
        ep_no, res_dict = client._fetch_single_episode_link({'episode': 7, 'url': target['url']})
        assert ep_no == 7
        assert '720' in res_dict
        assert res_dict['720']['downloadLink'] == 'https://www.trixhentai.com/wp-content/uploads/2020/03/129-Overflow-Ep7.mp4'
        assert res_dict['720']['downloadType'] == 'mp4'

    # Test filename formatting
    final_links = client.fetch_m3u8_links({7: res_dict}, '720', 'Overflow - ')
    assert 7 in final_links
    assert 'Overflow - E07 - 720P [TrixHentai].mp4' in final_links[7]['episodeName']
