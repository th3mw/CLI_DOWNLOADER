import os
from Core.BaseDownloader import BaseDownloader
from Content.Anime.Downloaders.HLSDownloader import HLSDownloader
from Content.Movies.Downloaders.MovieDownloader import MovieDownloader


class SeriesDownloader(BaseDownloader):
    '''
    Dedicated downloader for multi-episode TV shows and Asian Dramas.
    Automatically handles HLS m3u8 streams and direct HTTP downloads per episode.
    '''
    def __init__(self, dl_config, ep_details, session=None):
        super().__init__(dl_config, ep_details, session)

    def start_download(self, dl_link):
        dl_type = getattr(self, 'download_type', None) or self.ep_details.get('downloadType') or ('hls' if '.m3u8' in str(dl_link).lower() else 'mp4')
        is_hls = (dl_type == 'hls') or ('.m3u8' in str(dl_link).lower())
        forward_config = dict(self.dl_config)
        if is_hls:
            hls_dl = HLSDownloader(forward_config, self.ep_details, session=self.req_session)
            return hls_dl.start_download(dl_link)
        else:
            movie_dl = MovieDownloader(forward_config, self.ep_details, session=self.req_session)
            return movie_dl.start_download(dl_link)
