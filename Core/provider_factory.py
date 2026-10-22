import importlib
import logging

logger = logging.getLogger()

CATEGORIES = {
    1: 'Anime',
    2: 'Movies',
    3: 'TV Shows',
    4: 'Hentai (NSFW)'
}

# Category Provider Registry
# Maps category name -> list of provider definitions
CATEGORY_PROVIDERS = {
    'Anime': [
        {
            'key': 'anikoto',
            'name': 'AniKoto',
            'desc': 'HD Anime Streams',
            'label': 'AniKoto (HD Anime)',
            'class_path': 'Content.Anime.Providers.AnikotoClient.AnikotoClient',
            'content_filter': None,
            'type': 'direct'
        },
        {
            'key': 'anime_suge',
            'name': 'AnimeSuge',
            'desc': 'Fast Direct Streams',
            'label': 'AnimeSuge (Fast Streams)',
            'class_path': 'Content.Anime.Providers.AnimeSugeClient.AnimeSugeClient',
            'content_filter': None,
            'type': 'direct'
        },
        {
            'key': 'anisnatch',
            'name': 'AniSnatch',
            'desc': 'Direct Anime Streams',
            'label': 'AniSnatch (Direct Anime)',
            'class_path': 'Content.Anime.Providers.AniSnatchClient.AniSnatchClient',
            'content_filter': None,
            'type': 'direct'
        },
        {
            'key': 'kisskh',
            'name': 'KissKh',
            'desc': 'Anime & Asian Dramas',
            'label': 'KissKh (Anime Only)',
            'class_path': 'Content.Anime.Providers.KissKhClient.KissKhClient',
            'content_filter': 'anime',
            'type': 'direct'
        },
        {
            'key': 'nyaa',
            'name': 'Nyaa',
            'desc': 'Anime Swarms & Torrents',
            'label': 'Nyaa (Anime Torrents)',
            'class_path': 'Content.Anime.Providers.NyaaClient.NyaaClient',
            'content_filter': 'anime',
            'type': 'torrent'
        }
    ],
    'Movies': [
        {
            'key': 'yts',
            'name': 'YTS / YIFY',
            'desc': '720p • 1080p • 4K Movie Torrents',
            'label': 'YTS / YIFY (Movie Torrents)',
            'class_path': 'Content.Movies.Providers.YTSClient.YTSClient',
            'content_filter': 'movie',
            'type': 'torrent'
        },
        {
            'key': 'tgx',
            'name': 'TorrentGalaxy',
            'desc': 'High Quality Movie Swarms',
            'label': 'TorrentGalaxy (Movies Torrents)',
            'class_path': 'Content.Movies.Providers.TGxClient.TGxClient',
            'content_filter': 'movie',
            'type': 'torrent'
        },
        {
            'key': 'oneshows',
            'name': '1Shows',
            'desc': 'Direct Movie Streams',
            'label': '1Shows (Direct Movies)',
            'class_path': 'Content.Movies.Providers.OneShowsClient.OneShowsClient',
            'content_filter': 'movie',
            'type': 'direct'
        },
        {
            'key': 'kisskh',
            'name': 'KissKh',
            'desc': 'Asian Movies & Cinema',
            'label': 'KissKh (Asian Movies)',
            'class_path': 'Content.Movies.Providers.KissKhClient.KissKhClient',
            'content_filter': 'movie',
            'type': 'direct'
        }
    ],
    'TV Shows': [
        {
            'key': 'eztv',
            'name': 'EZTV',
            'desc': 'TV Torrents & Episodes',
            'label': 'EZTV (TV Torrents)',
            'class_path': 'Content.Series.Providers.EZTVClient.EZTVClient',
            'content_filter': 'tv',
            'type': 'torrent'
        },
        {
            'key': 'tgx',
            'name': 'TorrentGalaxy',
            'desc': 'TV Show Swarms & Packs',
            'label': 'TorrentGalaxy (TV Shows Torrents)',
            'class_path': 'Content.Series.Providers.TGxClient.TGxClient',
            'content_filter': 'tv',
            'type': 'torrent'
        },
        {
            'key': 'oneshows',
            'name': '1Shows',
            'desc': 'Direct TV Streams',
            'label': '1Shows (Direct TV Shows)',
            'class_path': 'Content.Series.Providers.OneShowsClient.OneShowsClient',
            'content_filter': 'tv',
            'type': 'direct'
        },
        {
            'key': 'kisskh',
            'name': 'KissKh',
            'desc': 'Asian Dramas & TV Series',
            'label': 'KissKh (Asian Dramas & TV)',
            'class_path': 'Content.Series.Providers.KissKhClient.KissKhClient',
            'content_filter': 'tv',
            'type': 'direct'
        }
    ],
    'Hentai (NSFW)': [
        {
            'key': 'hanime',
            'name': 'Hanime',
            'desc': 'Adult Anime & Hentai Streams',
            'label': 'Hanime (Hentai & NSFW Anime)',
            'class_path': 'Content.NSFW.Providers.HanimeClient.HanimeClient',
            'content_filter': 'nsfw',
            'type': 'direct'
        },
        {
            'key': 'miohentai',
            'name': 'MioHentai',
            'desc': 'Free HD Hentai Videos & Episodes',
            'label': 'MioHentai (HD Adult Anime)',
            'class_path': 'Content.NSFW.Providers.MioHentaiClient.MioHentaiClient',
            'content_filter': 'nsfw',
            'type': 'direct'
        },
        {
            'key': 'hentaihaven',
            'name': 'HentaiHaven',
            'desc': 'Classic & New HD Hentai Streams',
            'label': 'HentaiHaven (HD Hentai & HLS)',
            'class_path': 'Content.NSFW.Providers.HentaiHavenClient.HentaiHavenClient',
            'content_filter': 'nsfw',
            'type': 'direct'
        },
        {
            'key': 'trixhentai',
            'name': 'TrixHentai',
            'desc': 'Direct MP4 Hentai Videos & Episodes',
            'label': 'TrixHentai (Direct MP4 Hentai)',
            'class_path': 'Content.NSFW.Providers.TrixHentaiClient.TrixHentaiClient',
            'content_filter': 'nsfw',
            'type': 'direct'
        }
    ],
    'NSFW': [
        {
            'key': 'hanime',
            'name': 'Hanime',
            'desc': 'Adult Anime & Hentai Streams',
            'label': 'Hanime (Hentai & NSFW Anime)',
            'class_path': 'Content.NSFW.Providers.HanimeClient.HanimeClient',
            'content_filter': 'nsfw',
            'type': 'direct'
        },
        {
            'key': 'miohentai',
            'name': 'MioHentai',
            'desc': 'Free HD Hentai Videos & Episodes',
            'label': 'MioHentai (HD Adult Anime)',
            'class_path': 'Content.NSFW.Providers.MioHentaiClient.MioHentaiClient',
            'content_filter': 'nsfw',
            'type': 'direct'
        },
        {
            'key': 'hentaihaven',
            'name': 'HentaiHaven',
            'desc': 'Classic & New HD Hentai Streams',
            'label': 'HentaiHaven (HD Hentai & HLS)',
            'class_path': 'Content.NSFW.Providers.HentaiHavenClient.HentaiHavenClient',
            'content_filter': 'nsfw',
            'type': 'direct'
        },
        {
            'key': 'trixhentai',
            'name': 'TrixHentai',
            'desc': 'Direct MP4 Hentai Videos & Episodes',
            'label': 'TrixHentai (Direct MP4 Hentai)',
            'class_path': 'Content.NSFW.Providers.TrixHentaiClient.TrixHentaiClient',
            'content_filter': 'nsfw',
            'type': 'direct'
        }
    ],
    'NSFW / Hentai': [
        {
            'key': 'hanime',
            'name': 'Hanime',
            'desc': 'Adult Anime & Hentai Streams',
            'label': 'Hanime (Hentai & NSFW Anime)',
            'class_path': 'Content.NSFW.Providers.HanimeClient.HanimeClient',
            'content_filter': 'nsfw',
            'type': 'direct'
        },
        {
            'key': 'miohentai',
            'name': 'MioHentai',
            'desc': 'Free HD Hentai Videos & Episodes',
            'label': 'MioHentai (HD Adult Anime)',
            'class_path': 'Content.NSFW.Providers.MioHentaiClient.MioHentaiClient',
            'content_filter': 'nsfw',
            'type': 'direct'
        },
        {
            'key': 'hentaihaven',
            'name': 'HentaiHaven',
            'desc': 'Classic & New HD Hentai Streams',
            'label': 'HentaiHaven (HD Hentai & HLS)',
            'class_path': 'Content.NSFW.Providers.HentaiHavenClient.HentaiHavenClient',
            'content_filter': 'nsfw',
            'type': 'direct'
        },
        {
            'key': 'trixhentai',
            'name': 'TrixHentai',
            'desc': 'Direct MP4 Hentai Videos & Episodes',
            'label': 'TrixHentai (Direct MP4 Hentai)',
            'class_path': 'Content.NSFW.Providers.TrixHentaiClient.TrixHentaiClient',
            'content_filter': 'nsfw',
            'type': 'direct'
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
    },
    'Hentai (NSFW)': {
        'hls': 'Content.Anime.Downloaders.HLSDownloader.HLSDownloader',
        'http': 'Content.Movies.Downloaders.MovieDownloader.MovieDownloader',
        'mp4': 'Content.Movies.Downloaders.MovieDownloader.MovieDownloader',
        'torrent': 'Content.Movies.Downloaders.TorrentDownloader.TorrentDownloader'
    },
    'NSFW': {
        'hls': 'Content.Anime.Downloaders.HLSDownloader.HLSDownloader',
        'http': 'Content.Movies.Downloaders.MovieDownloader.MovieDownloader',
        'mp4': 'Content.Movies.Downloaders.MovieDownloader.MovieDownloader',
        'torrent': 'Content.Movies.Downloaders.TorrentDownloader.TorrentDownloader'
    },
    'NSFW / Hentai': {
        'hls': 'Content.Anime.Downloaders.HLSDownloader.HLSDownloader',
        'http': 'Content.Movies.Downloaders.MovieDownloader.MovieDownloader',
        'mp4': 'Content.Movies.Downloaders.MovieDownloader.MovieDownloader',
        'torrent': 'Content.Movies.Downloaders.TorrentDownloader.TorrentDownloader'
    }
}


def get_providers_for_category(category_name):
    '''Return list of available provider info dicts for a category'''
    if category_name in CATEGORY_PROVIDERS:
        return CATEGORY_PROVIDERS[category_name]
    alias_map = {
        'nsfw': 'Hentai (NSFW)',
        'hentai': 'Hentai (NSFW)',
        '4': 'Hentai (NSFW)',
        4: 'Hentai (NSFW)'
    }
    canonical = alias_map.get(str(category_name).lower(), category_name)
    return CATEGORY_PROVIDERS.get(canonical, [])


def get_provider_info(category_name, provider_key):
    '''Find provider info dict for a given category and provider key'''
    providers = get_providers_for_category(category_name)
    for p in providers:
        if p['key'] == provider_key:
            return p
    return None


def create_client(category_name, provider_key, category_config, hls_size_accuracy=0, audio_preference='sub'):
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
        import traceback
        logger.error(traceback.format_exc())
        return None

    # Inject hls_size_accuracy and audio_preference into category config
    category_config.update({
        'hls_size_accuracy': hls_size_accuracy,
        'audio_preference': audio_preference
    })

    content_filter = provider_info.get('content_filter')
    logger.debug(f"Creating instance of {class_name} for category '{category_name}' with filter '{content_filter}'")

    try:
        return client_cls(category_config, series_type=category_name, content_filter=content_filter)
    except Exception as e:
        logger.error(f"Failed to instantiate client {class_name}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


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
