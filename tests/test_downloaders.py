import os
from unittest.mock import patch, MagicMock
import pytest
from Core.BaseDownloader import BaseDownloader
from Content.Series.Downloaders.SeriesDownloader import SeriesDownloader
from Content.Movies.Downloaders.MovieDownloader import MovieDownloader
from Content.Anime.Downloaders.HLSDownloader import HLSDownloader


def test_base_downloader_attributes():
    dl_cfg = {'download_dir': '/tmp/test_base', 'concurrency_per_file': 4, 'request_timeout': 15}
    ep_details = {
        'episodeName': 'Test Show - E01.mkv',
        'type': 'tv',
        'season': 1,
        'episode': 1,
        'downloadType': 'hls',
        'refererLink': 'https://kisskh.co'
    }
    base = BaseDownloader(dl_cfg, ep_details)
    assert base.dl_config == dl_cfg
    assert base.download_type == 'hls'
    assert base.referer_link == 'https://kisskh.co'
    assert base.out_dir == f"/tmp/test_base{os.sep}Season-1"


def test_series_downloader_hls_forwarding():
    dl_cfg = {'download_dir': '/tmp/test_series', 'concurrency_per_file': 4}
    ep_details = {
        'episodeName': 'Take Charge of My Heart (2026) - E01 - 720P [KissKh].mkv',
        'type': 'tv',
        'season': 1,
        'episode': 1,
        'downloadType': 'hls',
        'downloadLink': 'https://example.com/stream.m3u8',
        'refererLink': 'https://kisskh.co'
    }

    s_dl = SeriesDownloader(dl_cfg, ep_details)
    assert s_dl.download_type == 'hls'
    assert s_dl.referer_link == 'https://kisskh.co'

    with patch.object(HLSDownloader, 'start_download', return_value=(0, None)) as mock_hls:
        res = s_dl.start_download(ep_details['downloadLink'])
        assert res == (0, None)
        assert mock_hls.called


def test_series_downloader_movie_forwarding():
    dl_cfg = {'download_dir': '/tmp/test_series_direct', 'concurrency_per_file': 4}
    ep_details = {
        'episodeName': 'Direct Show - E01 - 720P.mp4',
        'type': 'tv',
        'season': 1,
        'episode': 1,
        'downloadType': 'mp4',
        'downloadLink': 'https://example.com/direct.mp4',
        'refererLink': 'https://kisskh.co'
    }

    s_dl = SeriesDownloader(dl_cfg, ep_details)
    assert s_dl.download_type == 'mp4'

    with patch.object(MovieDownloader, 'start_download', return_value=(0, None)) as mock_movie:
        res = s_dl.start_download(ep_details['downloadLink'])
        assert res == (0, None)
        assert mock_movie.called


def test_movie_downloader_hls_and_direct():
    dl_cfg = {'download_dir': '/tmp/test_movie', 'concurrency_per_file': 4}
    ep_hls = {
        'episodeName': 'Movie (2026) - 1080P.mkv',
        'type': 'movie',
        'downloadType': 'hls',
        'downloadLink': 'https://example.com/movie.m3u8',
        'refererLink': 'https://example.com'
    }

    m_dl_hls = MovieDownloader(dl_cfg, ep_hls)
    assert m_dl_hls.download_type == 'hls'
    with patch.object(HLSDownloader, 'start_download', return_value=(0, None)) as mock_hls:
        res = m_dl_hls.start_download(ep_hls['downloadLink'])
        assert res == (0, None)
        assert mock_hls.called

    ep_direct = {
        'episodeName': 'Movie (2026) - 1080P.mp4',
        'type': 'movie',
        'downloadType': 'mp4',
        'downloadLink': 'https://example.com/movie.mp4',
        'refererLink': 'https://example.com'
    }
    m_dl_direct = MovieDownloader(dl_cfg, ep_direct)
    assert m_dl_direct.download_type == 'mp4'
    with patch.object(MovieDownloader, '_download_direct_stream', return_value=True), \
         patch.object(MovieDownloader, '_create_out_dirs'), \
         patch.object(MovieDownloader, '_remove_out_dirs'):
        res = m_dl_direct.start_download(ep_direct['downloadLink'])
        assert res == (0, None)


def test_base_downloader_display_prefix():
    dl_cfg = {'download_dir': '/tmp/test_prefix'}
    
    # 1. Standard E-format
    ep1 = {'episodeName': 'Mashle - E01 - 720P [AniSnatch].mkv', 'type': 'anime'}
    b1 = BaseDownloader(dl_cfg, ep1)
    assert b1._get_display_prefix() == 'E01'

    # 2. Multi-episode
    ep2 = {'episodeName': 'Mashle - E01-E02 - 720P [AniSnatch].mkv', 'type': 'anime'}
    b2 = BaseDownloader(dl_cfg, ep2)
    assert b2._get_display_prefix() == 'E01-E02'

    # 3. S01 - E05
    ep3 = {'episodeName': 'Show - S01 - E05 - 1080P.mkv', 'type': 'tv'}
    b3 = BaseDownloader(dl_cfg, ep3)
    assert b3._get_display_prefix() == 'S01-E05'

    # 4. Movie
    ep4 = {'episodeName': 'Mashle Movie - 1080P.mkv', 'type': 'movie'}
    b4 = BaseDownloader(dl_cfg, ep4)
    assert b4._get_display_prefix() == 'Movie'

    # 5. Fallback via ep_details episode number
    ep5 = {'episodeName': 'NonStandardNaming.mkv', 'type': 'tv', 'episode': 7}
    b5 = BaseDownloader(dl_cfg, ep5)
    assert b5._get_display_prefix() == 'E07'

    # 6. Fallback default - must never be 'Downloading'
    ep6 = {'episodeName': 'UnknownName.mkv', 'type': 'unknown'}
    b6 = BaseDownloader(dl_cfg, ep6)
    assert b6._get_display_prefix() == 'Episode'
    assert b6._get_display_prefix() != 'Downloading'


def test_batch_downloader_timing_and_ordering():
    from scraper import batch_downloader
    import time

    def mock_download_fn(link, cfg):
        time.sleep(0.01)
        return {
            'status': 'success',
            'file': link['episodeName'],
            'log': f"Done {link['episodeName']}",
            'error': None,
            'time': '00m 01s',
            'duration_sec': 1
        }

    links = {
        1: {'episodeName': 'Mashle - E01.mkv'},
        2: {'episodeName': 'Mashle - E02.mkv'},
        3: {'episodeName': 'Mashle - E03.mkv'},
    }
    cfg = {'download_dir': '/tmp/test'}

    # Test concurrent execution preserves index order and computes session time
    summary = batch_downloader(mock_download_fn, links, cfg, max_parallel_downloads=3)
    assert summary['total'] == 3
    assert summary['success'] == 3
    assert 'total_time' in summary
    assert 'results' in summary
    assert len(summary['results']) == 3
    # Check that order is preserved
    assert summary['results'][0]['file'] == 'Mashle - E01.mkv'
    assert summary['results'][1]['file'] == 'Mashle - E02.mkv'
    assert summary['results'][2]['file'] == 'Mashle - E03.mkv'
    assert summary['results'][0]['time'] == '00m 01s'

