import importlib
import logging

logger = logging.getLogger()

CATEGORIES = {
    1: 'Anime',
    2: 'Movies',
    3: 'TV Shows'
}

# Category Provider Registry
# Maps category name -> list of provider definitions
CATEGORY_PROVIDERS = {
    'Anime': [
        {
            'key': 'anime_suge',
            'label': 'AnimeSuge',
            'class_path': 'Content.Anime.Providers.AnimeSugeClient.AnimeSugeClient',
            'content_filter': None
        },
        {
            'key': 'anidb',
            'label': 'AniDB',
            'class_path': 'Content.Anime.Providers.AniDbClient.AniDbClient',
            'content_filter': None
        },
        {
            'key': 'kisskh',
            'label': 'KissKh (Anime Only)',
            'class_path': 'Content.Anime.Providers.KissKhClient.KissKhClient',
            'content_filter': 'anime'
        }
    ],
    'Movies': [
        {
            'key': 'yts',
            'label': 'YTS / YIFY (Movie Torrents)',
            'class_path': 'Content.Movies.Providers.YTSClient.YTSClient',
            'content_filter': 'movie'
        },
        {
            'key': 'oneshows',
            'label': '1Shows (Movies Only)',
            'class_path': 'Content.Movies.Providers.OneShowsClient.OneShowsClient',
            'content_filter': 'movie'
        },
        {
            'key': 'kisskh',
            'label': 'KissKh (Asian Drama Movies)',
            'class_path': 'Content.Movies.Providers.KissKhClient.KissKhClient',
            'content_filter': 'movie'
        }
    ],
    'TV Shows': [
        {
            'key': 'oneshows',
            'label': '1Shows (Series Only)',
            'class_path': 'Content.Series.Providers.OneShowsClient.OneShowsClient',
            'content_filter': 'tv'
        },
        {
            'key': 'kisskh',
            'label': 'KissKh (Asian Drama Series)',
            'class_path': 'Content.Series.Providers.KissKhClient.KissKhClient',
            'content_filter': 'tv'
        }
    ]
}

CATEGORY_DOWNLOADERS = {
    'Anime': {
        'hls': 'Content.Anime.Downloaders.HLSDownloader.HLSDownloader',
        'http': 'Core.BaseDownloader.BaseDownloader',
        'torrent': 'Content.Movies.Downloaders.TorrentDownloader.TorrentDownloader'
    },
    'Movies': {
        'hls': 'Content.Movies.Downloaders.MovieDownloader.MovieDownloader',
        'http': 'Content.Movies.Downloaders.MovieDownloader.MovieDownloader',
        'torrent': 'Content.Movies.Downloaders.TorrentDownloader.TorrentDownloader'
    },
    'TV Shows': {
        'hls': 'Content.Series.Downloaders.SeriesDownloader.SeriesDownloader',
        'http': 'Content.Series.Downloaders.SeriesDownloader.SeriesDownloader',
        'torrent': 'Content.Movies.Downloaders.TorrentDownloader.TorrentDownloader'
    }
}


def get_providers_for_category(category_name):
    '''Return list of available provider info dicts for a category'''
    return CATEGORY_PROVIDERS.get(category_name, [])


def get_provider_info(category_name, provider_key):
    '''Find provider info dict for a given category and provider key'''
    providers = get_providers_for_category(category_name)
    for p in providers:
        if p['key'] == provider_key:
            return p
    return None


def create_client(category_name, provider_key, category_config, hls_size_accuracy=0):
    '''
    Factory method to dynamically instantiate provider clients.
    '''
    provider_info = get_provider_info(category_name, provider_key)
    if not provider_info:
        logger.error(f"Provider '{provider_key}' not registered for category '{category_name}'")
        return None

    class_path = provider_info['class_path']
    module_name, class_name = class_path.rsplit('.', 1)

    try:
        module = importlib.import_module(module_name)
        client_cls = getattr(module, class_name)
    except Exception as e:
        logger.error(f"Failed to import client class {class_path}: {e}")
        return None

    # Inject hls_size_accuracy into category config
    category_config.update({'hls_size_accuracy': hls_size_accuracy})

    content_filter = provider_info.get('content_filter')
    logger.debug(f"Creating instance of {class_name} for category '{category_name}' with filter '{content_filter}'")

    return client_cls(category_config, series_type=category_name, content_filter=content_filter)


def get_downloader(category_name, download_type):
    '''
    Factory method to dynamically resolve the appropriate category downloader class.
    '''
    category_map = CATEGORY_DOWNLOADERS.get(category_name, CATEGORY_DOWNLOADERS['Anime'])
    class_path = category_map.get(download_type.lower(), category_map.get('hls'))
    module_name, class_name = class_path.rsplit('.', 1)
    try:
        module = importlib.import_module(module_name)
        return getattr(module, class_name)
    except Exception as e:
        logger.error(f"Failed to load downloader {class_path}: {e}")
        from Core.BaseDownloader import BaseDownloader
        return BaseDownloader
