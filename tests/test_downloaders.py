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
        'episodeName': 'Test Show - S01 - E01.mkv',
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
        'episodeName': 'Take Charge of My Heart (2026) - S01 - E01 - 720P.mkv',
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
        'episodeName': 'Direct Show - S01 - E01 - 720P.mp4',
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
