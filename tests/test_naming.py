import pytest
from Core.BaseClient import BaseClient
from Content.Anime.Providers.AnikotoClient import AnikotoClient
from Content.Anime.Providers.KissKhClient import KissKhClient as AnimeKissKh
from Content.Anime.Providers.NyaaClient import NyaaClient
from Content.Movies.Providers.YTSClient import YTSClient
from Content.Movies.Providers.TGxClient import TGxClient as TGxMovies
from Content.Series.Providers.TGxClient import TGxClient as TGxSeries
from Content.Series.Providers.EZTVClient import EZTVClient
from Content.Series.Providers.OneShowsClient import OneShowsClient


def test_base_client_format_media_filename_series():
    client = BaseClient()
    # No provider passed, no provider on client
    res = client.format_media_filename("Mashle", season=1, episode=1, resolution="1080P")
    assert res == "Mashle - E01 - 1080P.mkv"
    assert "S01" not in res

    # Explicit provider passed
    res_prov = client.format_media_filename("Mashle", season=1, episode=1, resolution="1080P", provider="AniKoto")
    assert res_prov == "Mashle - E01 - 1080P [AniKoto].mkv"
    assert "S01" not in res_prov


def test_base_client_format_media_filename_multipart():
    client = BaseClient()
    res = client.format_media_filename("Solo Leveling", season=1, episode=1, number2=2, resolution="1080", provider="AniKoto")
    assert res == "Solo Leveling - E01-E02 - 1080P [AniKoto].mkv"
    assert "S01" not in res


def test_base_client_format_media_filename_movie():
    client = BaseClient()
    res = client.format_media_filename("Inception", is_movie=True, resolution="1080", provider="1Shows")
    assert res == "Inception - 1080P [1Shows].mkv"

    # Movie without resolution
    res_no_res = client.format_media_filename("Inception", is_movie=True, provider="1Shows")
    assert res_no_res == "Inception [1Shows].mkv"


def test_provider_client_automatic_provider_tag():
    # Test that client inheriting BaseClient automatically populates its name in format_media_filename
    client = BaseClient()
    client.name = "KissKh"
    res = client.format_media_filename("Take Charge of My Heart (2026)", season=1, episode=1, resolution="720P")
    assert res == "Take Charge of My Heart (2026) - E01 - 720P [KissKh].mkv"
    assert "S01" not in res


def test_nyaa_naming_format():
    client = NyaaClient({'request_timeout': 10})
    target_ep_links = {
        1: {
            '1080': {
                'downloadLink': 'magnet:?xt=urn:btih:test',
                'torrent_info': {'seeds': 10, 'peers': 5, 'size': '1.2 GB'}
            }
        }
    }
    ep_links = client.fetch_m3u8_links(target_ep_links, '1080P', 'Frieren - ')
    ep1 = ep_links[1]
    assert ep1['episodeName'] == "Frieren - E01 - 1080P [Nyaa].mkv"
    assert "S01" not in ep1['episodeName']


def test_yts_naming_format():
    client = YTSClient({'request_timeout': 10})
    target_ep_links = {
        1: {
            '1080P': {
                'downloadLink': 'magnet:?xt=urn:btih:test',
                'quality': '1080P',
                'torrent_info': {'seeds': 50, 'peers': 20, 'size': '2.1 GB'}
            }
        }
    }
    ep_links = client.fetch_m3u8_links(target_ep_links, '1080P', 'Interstellar (2014) - ')
    movie = ep_links[1]
    assert movie['episodeName'] == "Interstellar (2014) - 1080P [YTS].mkv"
    assert "S01" not in movie['episodeName']


def test_eztv_naming_format():
    client = EZTVClient({'request_timeout': 10})
    client._episodes_by_idx[1] = {'season': 2, 'ep_no': 5, 'raw_name': 'Episode 5'}
    target_ep_links = {
        1: {
            '1080': {
                'downloadLink': 'magnet:?xt=urn:btih:test',
                'torrent_info': {'seeds': 30, 'peers': 10, 'size': '800 MB'}
            }
        }
    }
    ep_links = client.fetch_m3u8_links(target_ep_links, '1080', 'The Boys - ')
    ep5 = ep_links[1]
    assert ep5['episodeName'] == "The Boys - E05 - 1080P [EZTV].mkv"
    assert "S02" not in ep5['episodeName']


def test_tgx_naming_format():
    client_movies = TGxMovies({'request_timeout': 10})
    target_m_links = {
        1: {
            '1080P': {
                'downloadLink': 'magnet:?xt=urn:btih:test',
                'quality': '1080P',
                'torrent_info': {'seeds': 10, 'peers': 5, 'size': '2 GB'}
            }
        }
    }
    m_links = client_movies.fetch_m3u8_links(target_m_links, '1080P', 'Dune (2021) - ')
    assert m_links[1]['episodeName'] == "Dune (2021) - 1080P [TorrentGalaxy].mkv"

    client_series = TGxSeries({'request_timeout': 10})
    client_series._episodes_by_idx[1] = {'season': 1, 'ep_no': 3}
    target_s_links = {
        1: {
            '1080': {
                'downloadLink': 'magnet:?xt=urn:btih:test',
                'torrent_info': {'seeds': 10, 'peers': 5, 'size': '1 GB'}
            }
        }
    }
    s_links = client_series.fetch_m3u8_links(target_s_links, '1080', 'Severance - ')
    assert s_links[1]['episodeName'] == "Severance - E03 - 1080P [TorrentGalaxy].mkv"
    assert "S01" not in s_links[1]['episodeName']


def test_legacy_file_detection_candidates(tmp_path):
    import re
    import os

    ep_name = "Mashle - E01 - 1080P [AniKoto].mkv"
    ep_out_dir = str(tmp_path)
    base_without_ext = ep_name.rsplit('.', 1)[0]
    candidate_files = [
        os.path.join(ep_out_dir, ep_name),
        os.path.join(ep_out_dir, f"{base_without_ext}.mkv"),
        os.path.join(ep_out_dir, f"{base_without_ext}.mp4"),
    ]
    clean_no_prov = re.sub(r'\s*\[.*?\]\s*$', '', base_without_ext).strip()
    if clean_no_prov != base_without_ext:
        candidate_files.append(os.path.join(ep_out_dir, f"{clean_no_prov}.mkv"))
        candidate_files.append(os.path.join(ep_out_dir, f"{clean_no_prov}.mp4"))

    season_num = 1
    if ' - E' in clean_no_prov:
        legacy_s_name = clean_no_prov.replace(' - E', f" - S{season_num:02d} - E", 1)
        candidate_files.append(os.path.join(ep_out_dir, f"{legacy_s_name}.mkv"))
        candidate_files.append(os.path.join(ep_out_dir, f"{legacy_s_name}.mp4"))

    # Simulate a legacy file on disk with S01
    legacy_file = os.path.join(ep_out_dir, "Mashle - S01 - E01 - 1080P.mkv")
    with open(legacy_file, 'wb') as f:
        f.write(b'0' * (2 * 1024 * 1024))  # 2MB

    found = None
    for cand in candidate_files:
        if os.path.isfile(cand) and os.path.getsize(cand) > 1024 * 1024:
            found = cand
            break

    assert found == legacy_file

