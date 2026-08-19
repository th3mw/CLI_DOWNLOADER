import os
from Core.BaseDownloader import BaseDownloader
from Anime.Downloaders.HLSDownloader import HLSDownloader
from Movies.Downloaders.MovieDownloader import MovieDownloader


class SeriesDownloader(BaseDownloader):
    '''
    Dedicated downloader for multi-episode TV shows and Asian Dramas.
    Automatically handles HLS m3u8 streams and direct HTTP downloads per episode.
    '''
    def __init__(self, dl_config, ep_details):
        super().__init__(dl_config, ep_details)

    def start_download(self, dl_link):
        is_hls = (self.download_type == 'hls') or ('.m3u8' in dl_link.lower())
        if is_hls:
            hls_dl = HLSDownloader({
                'download_dir': self.out_dir,
                'temp_dir': self.parent_temp_dir,
                'concurrency_per_file': self.concurrency,
                'request_timeout': self.request_timeout,
                'use_http_client': self.use_http_client
            }, self.ep_details)
            hls_dl.start_download(dl_link)
        else:
            movie_dl = MovieDownloader({
                'download_dir': self.out_dir,
                'temp_dir': self.parent_temp_dir,
                'concurrency_per_file': self.concurrency,
                'request_timeout': self.request_timeout,
                'use_http_client': self.use_http_client
            }, self.ep_details)
            movie_dl.start_download(dl_link)
