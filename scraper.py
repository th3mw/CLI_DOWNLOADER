import argparse
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import os, sys

# Ensure UTF-8 stdout/stderr and ANSI support on Windows
if sys.platform == 'win32' or os.name == 'nt':
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
    os.system('')  # Enable VT100 / ANSI escape sequences in Windows terminal

from time import time
import traceback

# Note: For optimization, custom modules are imported as required
from Core.commons import colprint_init, colprint, PRINT_THEMES, ExitException, render_box, clear_screen, render_step_header
from Core.commons import create_logger, load_yaml, pretty_time, strip_ansi, threaded, delete_old_logs
from Core.provider_factory import CATEGORIES, CATEGORY_PROVIDERS, get_providers_for_category, create_client, get_downloader
from Core import history_manager, compressor

args = None
series_type = None
config = None
logger = None
client = None
hls_size_accuracy = 0
disable_colors = False
disable_looping = False
config_file = 'config_scraper.yaml'
log_file_name = None
get_current_time = lambda fmt='%F %T': datetime.now().strftime(fmt)

def get_provider(category_name, predefined_provider=None):
    '''
    Show provider selection menu for the given category categorized into Direct Streams & Torrents.
    Returns the selected provider key or 'BACK'.
    '''
    providers = get_providers_for_category(category_name)
    if not providers:
        logger.error(f'No providers available for category: {category_name}')
        raise ExitException(0)

    if predefined_provider is None and (args is None or not getattr(args, 'quiet', False)):
        clear_screen()
        render_step_header(breadcrumbs=[category_name, 'Select Provider'])

    direct_provs = [p for p in providers if p.get('type') == 'direct']
    torrent_provs = [p for p in providers if p.get('type') == 'torrent']

    menu_lines = []
    choices = {}
    current_idx = 1

    # Order sections intuitively by content type (Torrents first for Movies/TV, Direct first for Anime/NSFW)
    groups = []
    if category_name in ('Movies', 'TV Shows'):
        if torrent_provs: groups.append(('🧲  BITTORRENT SWARMS & MAGNETS', torrent_provs))
        if direct_provs: groups.append(('⚡  DIRECT STREAMS & CDN', direct_provs))
    else:
        if direct_provs: groups.append(('⚡  DIRECT STREAMS & CDN', direct_provs))
        if torrent_provs: groups.append(('🧲  BITTORRENT SWARMS & MAGNETS', torrent_provs))

    max_name_len = max(len(p.get('name') or p.get('label', p['key'])) for p in providers)

    for group_title, prov_list in groups:
        if menu_lines:
            menu_lines.append("")
        menu_lines.append(f"  \033[1m\033[38;5;39m{group_title}\033[0m")
        for prov in prov_list:
            prov_name = prov.get('name') or prov.get('label', prov['key'])
            prov_desc = prov.get('desc', '')
            name_padded = prov_name.ljust(max_name_len)
            if prov_desc:
                line = f"    \033[1m[{current_idx}]\033[0m  {name_padded}  \033[38;5;244m•  {prov_desc}\033[0m"
            else:
                line = f"    \033[1m[{current_idx}]\033[0m  {name_padded}"
            menu_lines.append(line)
            choices[current_idx] = prov['key']
            current_idx += 1

    menu_lines.append("")
    menu_lines.append(f"    \033[38;5;244m[0]  ‹ Back to Content Types\033[0m")
    choices[0] = 'BACK'

    print('\n' + render_box(f'SELECT {category_name.upper()} PROVIDER', menu_lines))

    if predefined_provider is not None:
        colprint('predefined', f'\n  Using Predefined Provider: {predefined_provider}')
        if predefined_provider not in [p['key'] for p in providers]:
            logger.error(f'Invalid provider: {predefined_provider}')
            raise ExitException(0)
        return predefined_provider
    else:
        choice = colprint('user_input', f'\n  ➜ Select provider [1-{len(choices)-1}, 0=Back]: ', input_type='recurring', input_dtype='int', input_options=choices, allow_empty_input=False)
        return choices[choice]

def parse_task_selection(user_input: str, total_tasks: int) -> list:
    '''
    Parse task selection input supporting single numbers, comma-separated lists, ranges, or 'all'.
    Examples:
      '1' -> [1]
      '1,3' -> [1, 3]
      '1-3' -> [1, 2, 3]
      '1, 3-5, 8' -> [1, 3, 4, 5, 8]
      'a', 'all' -> [1, 2, ..., total_tasks]
      '0', 'q', 'exit' -> []
    Returns list of 1-based task indices (sorted and unique).
    '''
    if not user_input or not str(user_input).strip():
        return []
    s = str(user_input).strip().lower()
    if s in ('0', 'q', 'exit', 'cancel', 'back'):
        return []
    if s in ('a', 'all'):
        return list(range(1, total_tasks + 1))

    selected = set()
    parts = [p.strip() for p in s.split(',') if p.strip()]
    for part in parts:
        if '-' in part:
            sub = [x.strip() for x in part.split('-')]
            if len(sub) == 2 and sub[0].isdigit() and sub[1].isdigit():
                start = max(1, int(sub[0]))
                end = min(total_tasks, int(sub[1]))
                if start <= end:
                    selected.update(range(start, end + 1))
                else:
                    selected.update(range(end, start + 1))
        elif part.isdigit():
            val = int(part)
            if 1 <= val <= total_tasks:
                selected.add(val)
    return sorted(list(selected))

def get_audio_preference(category_name, predefined_audio=None):
    '''
    Show audio selection menu (Sub vs Dub) for Anime in interactive mode.
    Sub (Original Japanese Audio) is preferred by default.
    '''
    if predefined_audio is not None:
        colprint('predefined', f'\n  Using Predefined Audio: {predefined_audio}')
        return predefined_audio.lower()

    default_pref = (config.get('AudioPreference', {}).get('default_audio', 'sub') if config else 'sub').lower()
    default_idx = 2 if default_pref in ('dub', 'english') else 1

    menu_lines = [
        f"  \033[1m[1]\033[0m  🇯🇵  Sub         \033[38;5;244m•  Original Japanese Audio + English Subtitles\033[0m \033[38;5;39m[default]\033[0m",
        f"  \033[1m[2]\033[0m  🇺🇸  Dub         \033[38;5;244m•  English Voice Acting\033[0m",
        f"  \033[1m[3]\033[0m  🌐  Dual Audio  \033[38;5;244m•  Multi-Audio (Japanese + English Track)\033[0m",
    ]
    print('\n' + render_box('AUDIO LANGUAGE PREFERENCE', menu_lines))
    choice = colprint('user_input', f'\n  ➜ Select Audio [1=Sub, 2=Dub, 3=Dual Audio] [default={default_idx}]: ', input_type='recurring', input_options=['1', '2', '3', 'sub', 'dub', 'dual', 's', 'd', 1, 2, 3], allow_empty_input=True)
    if choice is None or choice == '':
        return 'sub'

    choice_str = str(choice).strip().lower()
    if choice_str in ('2', 'dub', 'd'):
        return 'dub'
    elif choice_str in ('3', 'dual'):
        return 'dual'
    else:
        return 'sub'

def get_client(provider_key=None):
    '''Return a client instance based on the selected provider.'''
    global series_type, config, logger, hls_size_accuracy, args

    # Resolve provider key if not explicitly provided
    if provider_key is None:
        provider_key = get_provider(series_type)
        if provider_key == 'BACK':
            return None

    audio_pref = getattr(args, 'audio', None) or (config.get('AudioPreference', {}).get('default_audio', 'sub') if config else 'sub')

    category_config = config.setdefault(series_type, {})
    client_inst = create_client(series_type, provider_key, category_config, hls_size_accuracy, audio_preference=audio_pref)
    if not client_inst:
        logger.error(f'Failed to create client for category={series_type}, provider={provider_key}')
        raise ExitException(1)
    return client_inst

def get_os_safe_path(tmp_path):
    '''Returns OS corrected path with expanded home directory'''
    # First expand the home directory if path starts with ~
    if tmp_path.startswith('~'):
        tmp_path = os.path.expanduser(tmp_path)
        
    if os.sep == '\\' and '/mnt/' in tmp_path:
        # platform is Windows and path is Linux, then convert to Windows path
        logger.debug('Platform is Windows but Paths are Linux. Converting paths to Windows paths')
        tmp_path = tmp_path.split('/')[2:]
        tmp_path[0] = tmp_path[0].upper() + ':'
        tmp_path = '\\'.join(tmp_path)
    elif os.sep == '/' and ':\\' in tmp_path:
        # platform is Linux and path is Windows, then convert to Linux path
        logger.debug('Platform is Linux but Paths are Windows. Converting paths to Linux paths')
        tmp_path = tmp_path.split('\\')
        tmp_path[0] = tmp_path[0].lower().replace(':', '')
        tmp_path = '/mnt/' + '/'.join(tmp_path)
    else:
        tmp_path = tmp_path.replace('/', os.sep).replace('\\', os.sep) # make sure the separator is correct

    return tmp_path

def check_if_exists(path):
    logger.debug(f'Validating/creating download path [{path}]')
    try:
        os.makedirs(path, exist_ok=True)
        logger.debug('Download path exists/created successfully')
    except Exception as e:
        raise Exception(f'Failed to create download path [{path}]. Error: {e}')

def resume_task(record, config_data):
    '''
    Resume an incomplete download record from SQLite database.
    '''
    rec_id = record.get('id')
    title = record.get('title', 'Unknown')
    season = int(record.get('season') or 1)
    episode = int(record.get('episode') or 1)
    resolution = str(record.get('resolution') or '720').rstrip('pP')
    content_type = record.get('content_type') or 'Anime'
    download_type = record.get('download_type') or 'hls'
    target_filepath = record.get('target_filepath')
    download_link = record.get('download_link')
    referer_link = record.get('referer_link', '')
    provider_name = record.get('provider', '')

    if not target_filepath:
        base_dir = config_data.get(content_type, {}).get('download_dir') or config_data.get('DownloaderConfig', {}).get('download_dir', '~/Videos')
        out_dir = os.path.expanduser(base_dir)
        out_file = f"{title}.mkv"
        target_filepath = os.path.join(out_dir, out_file)
    else:
        out_dir = os.path.dirname(target_filepath)
        out_file = os.path.basename(target_filepath)

    check_if_exists(out_dir)

    if os.path.isfile(target_filepath) and os.path.getsize(target_filepath) > 0:
        colprint('success', f"\n  [✓] {out_file} is already complete on disk! (Size: {history_manager.format_size(os.path.getsize(target_filepath))})")
        history_manager.record_complete(rec_id, os.path.getsize(target_filepath))
        return True

    colprint('header', f"\n  🔄 Resuming download: {out_file} [{provider_name}]...")
    history_manager.record_resumed(rec_id)

    dl_config = config_data.get('DownloaderConfig', {}).copy()
    dl_config['download_dir'] = out_dir
    dl_config['max_parallel_downloads'] = 1

    ep_details = {
        'series_title': title,
        'season': season,
        'episode': episode,
        'episodeName': out_file,
        'resolution': resolution,
        'downloadType': download_type,
        'downloadLink': download_link,
        'refererLink': referer_link,
        'type': 'tv' if content_type == 'TV Shows' else ('movie' if content_type == 'Movies' else 'anime')
    }

    downloader_cls = get_downloader(content_type, download_type)
    dlClient = downloader_cls(dl_config, ep_details)

    success = False
    error_msg = ''
    try:
        if download_link:
            res = dlClient.start_download(download_link)
            if isinstance(res, tuple) and res[0] != 0:
                error_msg = res[1] or 'Download failed'
            else:
                success = True
        else:
            error_msg = 'No download link in record'
    except Exception as e:
        error_msg = str(e)

    # If direct resumption failed with stored link, try re-fetching fresh stream link
    if not success and provider_name:
        colprint('warning', f"  ⚠️ Stored link expired or failed ({error_msg}). Re-resolving via {provider_name}...")
        try:
            prov_key = provider_name.lower().replace(' ', '').replace('/', '_')
            for p in get_providers_for_category(content_type):
                if p['key'] in prov_key or prov_key in p['key'] or p['label'].lower().find(prov_key) != -1:
                    prov_key = p['key']
                    break

            cat_cfg = config_data.get(content_type, {})
            client_inst = create_client(content_type, prov_key, cat_cfg)
            if client_inst:
                clean_title = re.sub(r'\s*-\s*S\d+.*$', '', title).strip()
                search_results = client_inst.search(clean_title)
                if search_results:
                    match_item = search_results[0] if isinstance(search_results, list) else list(search_results.values())[0]
                    eps_list = client_inst.fetch_episodes_list(match_item)
                    if eps_list:
                        ep_links = client_inst.fetch_episode_links(eps_list, {'start': episode, 'end': episode})
                        if ep_links:
                            fresh_links = client_inst.fetch_m3u8_links(ep_links, str(resolution), f"{clean_title} - ")
                            if fresh_links:
                                fresh_item = list(fresh_links.values())[0] if isinstance(fresh_links, dict) else fresh_links[0]
                                fresh_url = fresh_item.get('downloadLink')
                                if fresh_url:
                                    colprint('success', f"  ✔ Fresh link obtained! Resuming stream download...")
                                    ep_details['downloadLink'] = fresh_url
                                    ep_details['refererLink'] = fresh_item.get('refererLink', referer_link)
                                    dlClient = downloader_cls(dl_config, ep_details)
                                    res = dlClient.start_download(fresh_url)
                                    if isinstance(res, tuple) and res[0] != 0:
                                        error_msg = res[1] or 'Download failed'
                                    else:
                                        success = True
        except Exception as refetch_err:
            error_msg = f"{error_msg} | Refetch error: {refetch_err}"

    if success and os.path.isfile(target_filepath) and os.path.getsize(target_filepath) > 0:
        file_size = os.path.getsize(target_filepath)
        history_manager.record_complete(rec_id, file_size)

        # Video compression if requested
        if (args and getattr(args, 'compress', False)) or (config_data and config_data.get('PostProcessing', {}).get('auto_compress', False)):
            post_cfg = config_data.get('PostProcessing', {}) if config_data else {}
            compressor.compress_video(
                target_filepath,
                codec=post_cfg.get('codec', 'hevc'),
                crf=post_cfg.get('crf', 23),
                preset=post_cfg.get('preset', 'slow')
            )
            file_size = os.path.getsize(target_filepath)
            history_manager.record_complete(rec_id, file_size)

        colprint('success', f"\n  ✔ Resumed download completed successfully! ({out_file})\n")
        return True
    else:
        history_manager.record_failure(rec_id, error_msg)
        colprint('error', f"\n  ✗ Resumption failed for {out_file}: {error_msg}\n")
        return False

def handle_history_menu():
    global config, config_file
    if not config:
        config = load_yaml(config_file)
    while True:
        clear_screen()
        render_step_header(step_title='Download History & Tasks')
        lines = [
            "  \033[1m[1]\033[0m  📜  View Download History       \033[38;5;244m•  Recent completed & active downloads\033[0m",
            "  \033[1m[2]\033[0m  🔄  Resume Incomplete Downloads  \033[38;5;244m•  Pick up paused or failed tasks\033[0m",
            "  \033[1m[3]\033[0m  🗑   Clear Download History       \033[38;5;244m•  Purge local task database records\033[0m",
            "",
            "  \033[38;5;244m[0]  ‹   Back to Main Menu\033[0m"
        ]
        print('\n' + render_box('HISTORY & TASK MANAGER', lines))
        c = colprint('user_input', '\n  ➜ Enter choice [1-3, 0=Back]: ', input_type='recurring', input_dtype='int', input_options=[0, 1, 2, 3])
        if c == 1:
            history_manager.render_history_view(30)
            input('\n  ➜ Press Enter to continue...')
        elif c == 2:
            records = history_manager.render_incomplete_view()
            if records:
                try:
                    sel = input(f'\n  ➜ Enter task #(s) to resume (e.g. 1,3 or 1-2, A=All, 0=Cancel): ').strip()
                except (EOFError, KeyboardInterrupt):
                    sel = '0'
                selected_indices = parse_task_selection(sel, len(records))
                if selected_indices:
                    colprint('header', f"\n  ⚡ Resuming {len(selected_indices)} selected task(s)...\n")
                    for idx in selected_indices:
                        rec = records[idx - 1]
                        resume_task(rec, config)
            input('\n  ➜ Press Enter to continue...')
        elif c == 3:
            history_manager.clear_history()
            colprint('success', '\n  ✔ History cleared successfully.')
            input('\n  ➜ Press Enter to continue...')
        else:
            break

def get_series_type(keys, predefined_input=None):
    logger.debug('Selecting the series type')
    type_aliases = {
        '1': 'Anime', 'anime': 'Anime',
        '2': 'Movies', 'movies': 'Movies', 'movie': 'Movies',
        '3': 'TV Shows', 'tv': 'TV Shows', 'tvshows': 'TV Shows', 'tv_shows': 'TV Shows', 'series': 'TV Shows',
        '4': 'Hentai (NSFW)', 'nsfw': 'Hentai (NSFW)', 'hentai': 'Hentai (NSFW)', 'hanime': 'Hentai (NSFW)', 'nsfw / hentai': 'Hentai (NSFW)', 'hentai (nsfw)': 'Hentai (NSFW)'
    }
    if predefined_input is not None:
        pre_str = str(predefined_input).lower().strip()
        if pre_str in type_aliases:
            colprint('predefined', f'\n  Using Predefined Content Type: {type_aliases[pre_str]}')
            return type_aliases[pre_str]

    while True:
        if args is None or not getattr(args, 'quiet', False):
            clear_screen()
            render_step_header(step_title='Select Content Category')

        menu_lines = [
            f"  \033[1m[1]\033[0m  🎬  Anime          \033[38;5;244m•  TV Series, Movies & OVAs\033[0m",
            f"  \033[1m[2]\033[0m  🍿  Movies         \033[38;5;244m•  Blockbusters & Cinema\033[0m",
            f"  \033[1m[3]\033[0m  📺  TV Shows       \033[38;5;244m•  Series, Seasons & Episodes\033[0m",
            f"  \033[1m[4]\033[0m  🔞  Hentai (NSFW)  \033[38;5;244m•  Adult Anime & Content\033[0m",
            "",
            f"  \033[1m[5]\033[0m  📜  History        \033[38;5;244m•  Download Tasks & Manager\033[0m",
            f"  \033[38;5;244m[0]  🚪  Exit\033[0m"
        ]
        print('\n' + render_box('SELECT CONTENT TYPE', menu_lines))
        choice = colprint('user_input', '\n  ➜ Enter choice [1-5, 0=Exit]: ', input_type='recurring', input_dtype='int', input_options=[0, 1, 2, 3, 4, 5], allow_empty_input=False)
        if choice == 0:
            raise ExitException(0)
        elif choice == 5:
            handle_history_menu()
            continue

        series_type_selected = keys[choice - 1]
        logger.debug(f'Series type selected: {series_type_selected}')
        return series_type_selected

def search_and_select_series(predefined_search_input=None, search_only=False):
    while True:
        logger.debug("Search and select series")
        # get search keyword from user input
        if predefined_search_input:
            colprint('predefined', f'\n  🔍 Using Predefined Input for search: {predefined_search_input}')
            keyword = predefined_search_input
        else:
            if args is None or not getattr(args, 'quiet', False):
                clear_screen()
                prov_name = getattr(client, 'name', '') or str(series_type)
                render_step_header(breadcrumbs=[str(series_type), prov_name, 'Search'])
            keyword = colprint('user_input', "\n  🔍 Enter series/movie name: ")

        colprint('header', f"\n  Searching for '{keyword}'...")
        logger.info(f'Searching with keyword: {keyword}')
        search_results = client.search(keyword) # pyright: ignore[reportOptionalMemberAccess]
        logger.info('Search Results Found')
        logger.debug(f'Search Results: {search_results}')

        if search_results is None or len(search_results) == 0:
            logger.error('No matches found. Try with different keyword')
            if predefined_search_input is None:
                continue
            else:
                raise ExitException(0)

        # Format 2-line search result cards
        card_lines = []
        for idx, (res_no, res_item) in enumerate(search_results.items()):
            title = res_item.get('card_title') or res_item.get('title', 'Unknown')
            line1 = f"  \033[1m[{res_no}]\033[0m  \033[38;5;39m{title}\033[0m"

            if res_item.get('card_meta'):
                line2 = f"       \033[38;5;244m{res_item['card_meta']}\033[0m"
            else:
                rating = res_item.get('rating', 'N/A')
                year = res_item.get('year', '')
                format_tag = res_item.get('type', '') or res_item.get('media_type', '')
                eps = res_item.get('episodes_count', '') or res_item.get('episodes', '')
                meta = []
                if rating != 'N/A' and rating: meta.append(f"\033[38;5;220m★ {rating}\033[0m")
                if year and year != 'XXXX': meta.append(f"Year: {year}")
                if format_tag: meta.append(f"\033[38;5;141m[{str(format_tag).upper()}]\033[0m")
                if eps: meta.append(f"Eps: {eps}")
                line2 = "       " + " \033[38;5;244m•\033[0m ".join(meta)

            genres = res_item.get('genres', '')
            card_lines.append(line1)
            card_lines.append(line2)
            if genres:
                card_lines.append(f"       \033[38;5;244mGenres: {genres}\033[0m")
            if idx < len(search_results) - 1:
                card_lines.append("")

        if not search_only:
            card_lines.append("")
            card_lines.append("  \033[38;5;244m[0]  🔍 Search again with a different title\033[0m")

        print('\n' + render_box(f'Search Results ({len(search_results)} matches)', card_lines))

        if search_only:
            raise ExitException(0)

        # get user selection for the search results
        option = colprint('user_input', f"\n  ➜ Select series [1-{len(search_results)}, 0=New Search]: ", input_type='recurring', input_dtype='int', input_options=list(range(len(search_results)+1)), allow_empty_input=False)
        logger.debug(f'Selected option: {option}')

        if option == 0:
            continue
        else:
            break

    return search_results[option]

def get_resolutions(items):
    '''
    Generator function to yield the resolutions of available episodes
    '''
    for item in items:
        yield [ i for i in item.keys() if i not in ('error', 'original') ]

def get_ep_range(default_ep_range, mode='Enter', _episodes_predef=None, type='episodes'):
    '''
    Get the seasons/episodes range from user input.
    Returns dict of start:float, end:float, specific_no:list.
    '''
    if _episodes_predef:
        colprint('predefined', f'\n  Using Predefined Input for {type} to download: {_episodes_predef}')
        ep_user_input = _episodes_predef
    else:
        ep_user_input = colprint('user_input', f"\n  ➜ {mode} {type} to download (ex: 1-16) [default={default_ep_range}]: ", input_type='recurring', input_dtype='range') or "all"
        if str(ep_user_input).lower() == 'all':
            ep_user_input = default_ep_range

    logger.debug(f'Selected {type} range ({mode = }): {ep_user_input = }')

    # keep track of user input ranges
    if ep_user_input.count('-') > 1:
        logger.error('Invalid input! You must specify only one range.')
        return get_ep_range(default_ep_range, mode, _episodes_predef)

    ep_start, ep_end, specific_eps = 0, 0, []
    for ep_range in ep_user_input.split(','):
        if '-' in ep_range:                             # process the range if '-' is found
            ep_range = ep_range.split('-')
            if ep_range[0] == '':
                ep_range[0] = default_ep_range.split('-')[0]    # set start to default start number, if not set
            if ep_range[1] == '':
                ep_range[1] = default_ep_range.split('-')[1]    # set end to default end number, if not set

            ep_start, ep_end = map(float, ep_range)
        else:
            specific_eps.append(float(ep_range))        # if it is a number and not range, add it to the list

    return {'start': ep_start, 'end': ep_end, 'specific_no': specific_eps}

def get_ep_range_multiple(season_ep_ranges, episodes, seasons_predef=None, episodes_predef=None):
    '''
    Get episode ranges per season
    '''
    min_ss = min(season_ep_ranges.keys()) if season_ep_ranges else 1
    max_ss = max(season_ep_ranges.keys()) if season_ep_ranges else 1
    selected_seasons = get_ep_range(f"{min_ss}-{max_ss}", 'Enter', seasons_predef, type='seasons')
    logger.debug(f'Selected seasons: {selected_seasons}')
    # filter out selected seasons only if available
    selected_seasons = { k:v for k,v in season_ep_ranges.items() if (k >= selected_seasons['start'] and k <= selected_seasons['end']) or k in selected_seasons['specific_no'] }
    logger.debug(f'Selected seasons filtered: {selected_seasons}')
    if episodes_predef:
        dl_entire_season = 'n'
    else:
        dl_entire_season = colprint('user_input', f"\n  ➜ Download entire season(s) (y|n)? ", input_type='recurring', input_options=['y', 'n', 'Y', 'N']).lower() or 'y'

    # return entire season range
    if dl_entire_season == 'y':
        return selected_seasons

    # get user input for episode ranges per season
    selected_eps = {}
    for k, v in selected_seasons.items():
        selected_eps_per_season = get_ep_range(f"{v['start']}-{v['end']}", f'Enter Season-{k}', episodes_predef)
        selected_eps[k] = selected_eps_per_season

    return selected_eps

def downloader(ep_details, dl_config):
    '''
    Download function where Download Client initialization and download happens.
    Accepts two dicts: download config, episode details. Returns download status.
    '''
    # load color themes
    error_clr = PRINT_THEMES['error'] if not disable_colors else ''
    success_clr = PRINT_THEMES['results'] if not disable_colors else ''
    skipped_clr = PRINT_THEMES['predefined'] if not disable_colors else ''
    reset_clr = PRINT_THEMES['reset'] if not disable_colors else ''

    start = get_current_time()
    start_epoch = int(time())

    out_file = ep_details['episodeName']
    max_parallel_downloads = dl_config.get('max_parallel_downloads', 1)

    if 'downloadLink' not in ep_details:
        return f'{error_clr}[{start}] Download skipped for {out_file}, due to error: {ep_details.get("error", "Unknown")}{reset_clr}'

    download_type = ep_details['downloadType']
    # set output directory based on series type
    out_dir = dl_config['download_dir']
    if ep_details.get('type', '') == 'tv':
        out_dir = f"{out_dir}{os.sep}Season-{ep_details['season']}"     # add extra folder for season

    # create download client for the episode based on category and download type
    logger.debug(f'Creating download client with {ep_details = }, {dl_config = }')

    downloader_cls = get_downloader(series_type, download_type)
    logger.debug(f'Resolved downloader {downloader_cls.__name__} for category {series_type} [{download_type}]')
    dlClient = downloader_cls(dl_config, ep_details)

    full_target_path = os.path.join(out_dir, out_file)
    prov_name = getattr(client, 'provider_name', None) or getattr(client, 'name', '') or str(series_type)
    dl_id = history_manager.record_start(
        title=ep_details.get('series_title') or out_file,
        season=ep_details.get('season', 1),
        episode=ep_details.get('episode', 1),
        resolution=ep_details.get('resolution', ''),
        provider=prov_name,
        content_type=series_type,
        download_type=download_type,
        target_filepath=full_target_path,
        download_link=ep_details.get('downloadLink', ''),
        referer_link=ep_details.get('refererLink', '')
    )

    logger.info(f'Download started for {out_file}...')
    if max_parallel_downloads <= 1:
        colprint('header', f"\n  ➜ Downloading: {out_file}")

    if os.path.isfile(full_target_path) and os.path.getsize(full_target_path) > 0:
        # skip file if already exists
        colprint('predefined', f"  [✓] {out_file} already exists -> Skipping")
        history_manager.record_complete(dl_id, os.path.getsize(full_target_path))
        return {
            'status': 'skipped',
            'file': out_file,
            'log': f'{skipped_clr}[{start}] Download skipped for {out_file}. File already exists!{reset_clr}',
            'error': None
        }
    else:
        try:
            res = dlClient.start_download(ep_details['downloadLink'])
            if isinstance(res, tuple) and len(res) == 2:
                status, msg = res
            else:
                status, msg = 0, ''
        except Exception as e:
            status, msg = 1, str(e)

        # remove target dirs if no files are downloaded
        dlClient._cleanup_out_dirs()

        end = get_current_time()
        if status != 0:
            history_manager.record_failure(dl_id, str(msg))
            colprint('error', f"  [✗] Failed: {out_file} ({msg})\n")
            return {
                'status': 'failed',
                'file': out_file,
                'log': f'{error_clr}[{end}] Download failed for {out_file}, with error: {msg}{reset_clr}',
                'error': str(msg)
            }

        # Successful download
        file_size = os.path.getsize(full_target_path) if os.path.isfile(full_target_path) else 0
        history_manager.record_complete(dl_id, file_size)

        # Video compression if requested
        if (args and getattr(args, 'compress', False)) or (config and config.get('PostProcessing', {}).get('auto_compress', False)):
            post_cfg = config.get('PostProcessing', {}) if config else {}
            compressor.compress_video(
                full_target_path,
                codec=post_cfg.get('codec', 'hevc'),
                crf=post_cfg.get('crf', 23),
                preset=post_cfg.get('preset', 'slow')
            )
            new_size = os.path.getsize(full_target_path) if os.path.isfile(full_target_path) else file_size
            history_manager.record_complete(dl_id, new_size)

        end_epoch = int(time())
        download_time = pretty_time(end_epoch-start_epoch, fmt='h m s')
        if max_parallel_downloads <= 1:
            colprint('results', f"  [✓] Completed: {out_file} ({download_time})\n")
        return {
            'status': 'success',
            'file': out_file,
            'log': f'{success_clr}[{end}] Download completed for {out_file} in {download_time}!{reset_clr}',
            'error': None,
            'time': download_time
        }

def batch_downloader(download_fn, links, dl_config, max_parallel_downloads):
    raw_results = []
    total_items = len(links)

    if max_parallel_downloads <= 1 or total_items <= 1:
        for link in links.values():
            res = download_fn(link, dl_config)
            raw_results.append(res)
    else:
        colprint('header', f"\n  ⚡ Starting Simultaneous Download of {total_items} item(s) (Concurrency: {max_parallel_downloads})...\n")
        with ThreadPoolExecutor(max_workers=max_parallel_downloads) as executor:
            future_to_link = {executor.submit(download_fn, link, dl_config): link for link in links.values()}
            for future in as_completed(future_to_link):
                try:
                    res = future.result()
                    raw_results.append(res)
                except Exception as e:
                    raw_results.append({
                        'status': 'failed',
                        'file': 'Unknown',
                        'log': f"Download failed with exception: {e}",
                        'error': str(e)
                    })

    log_lines = [r['log'] if isinstance(r, dict) and 'log' in r else str(r) for r in raw_results]
    logger.info(strip_ansi('\n'.join(log_lines)))

    successes = [r for r in raw_results if isinstance(r, dict) and r.get('status') == 'success']
    failures = [r for r in raw_results if isinstance(r, dict) and r.get('status') == 'failed']
    skipped = [r for r in raw_results if isinstance(r, dict) and r.get('status') == 'skipped']

    return {
        'total': total_items,
        'success': len(successes),
        'failed': len(failures),
        'skipped': len(skipped),
        'failures': failures,
        'successes': successes,
        'skipped_items': skipped
    }

def close_handlers():
    '''
    Close handlers properly to ensure rotation works without issues
    '''
    try:
        if logger is None:
            return
        for handler in logger.handlers:
            handler.close()
            logger.removeHandler(handler)
    except Exception as e:
        if 'not defined' in str(e): return   # ignore if logger itself is not defined
        print(f'Error while closing log handlers: {e}')


def main():
    global series_type, config, logger, client, hls_size_accuracy, disable_colors, disable_looping, config_file, log_file_name
    client = None
    logger = None
    skip_restart = False
    try:
        # Initialize required variables

        # parse cli arguments
        parser = argparse.ArgumentParser(
            description='🎬 Media scraper and downloader for Anime, Movies and TV Shows.',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog='''
Examples:
  Interactive Mode:
    python scraper.py
  
  One-Line Direct Downloads:
    python scraper.py -s anime -p anisnatch -n "Solo Leveling" -e "1-3" -r 1080 -d
    python scraper.py -s movies -p oneshows -n "Inception" -r 1080 -d
    python scraper.py -s tv -p kisskh -n "Vincenzo" -S "1" -e "1-5" -r 720 -d

  Quick Search Only (no download):
    python scraper.py -s anime -p anisnatch -n "Jobless" --search-only

  Dry Run Inspection (resolve links without downloading):
    python scraper.py -s anime -p anisnatch -n "Solo Leveling" -e "1" --dry-run
'''
        )
        parser.add_argument('-c', '--conf', default='config_scraper.yaml',
                         help='configuration file (default: config_scraper.yaml)')
        parser.add_argument('-l', '--log-file', help='custom file name for logging (default: scraper_{YYYYMMDDHHMMSS}.log)')
        parser.add_argument('-s', '--series-type', type=str, help='type of content (1/anime, 2/movies, 3/tv)')
        all_provider_keys = list(dict.fromkeys([p['key'] for cat_providers in CATEGORY_PROVIDERS.values() for p in cat_providers]))
        parser.add_argument('-p', '--provider', choices=all_provider_keys, help='provider to use for downloading')
        parser.add_argument('-n', '--series-name', help='name of the series to search')
        parser.add_argument('-S', '--seasons', action='append', help='seasons number to download (only applicable for TV Shows)')
        parser.add_argument('-e', '--episodes', action='append', help='episodes number to download (e.g. 1-12, 1,3,5)')
        parser.add_argument('-r', '--resolution', type=str, help='resolution to download the episodes (e.g. 1080, 720, 360)')
        parser.add_argument('-d', '--start-download', action='store_true', help='start download immediately without prompt')
        parser.add_argument('-dc', '--disable-colors', '--no-color', dest='disable_colors', default=False, action='store_true', help='disable colored ANSI output')
        parser.add_argument('-q', '--quiet', default=False, action='store_true', help='suppress hero banner and non-essential decoration')
        parser.add_argument('-a', '--audio', choices=['sub', 'dub', 'dual', 'all'], help='preferred audio language (sub: Subtitled, dub: English Dubbed)')
        parser.add_argument('-H', '--history', action='store_true', help='view recent download history')
        parser.add_argument('-I', '--incomplete', action='store_true', help='view and resume incomplete/interrupted downloads')
        parser.add_argument('--clear-history', action='store_true', help='clear all download history from database')
        parser.add_argument('-cmp', '--compress', action='store_true', help='compress downloaded video with high-efficiency HEVC/AV1 encoding')
        parser.add_argument('--search-only', default=False, action='store_true', help='search and display results without prompting to download')
        parser.add_argument('--dry-run', default=False, action='store_true', help='resolve streams and show pre-download inspection without downloading')
        parser.add_argument('-hsa', '--hls-size-accuracy', default=0, type=int, choices=range(0, 101), metavar='[0-100]',
                         help='accuracy to display the file size of hls files (0-100)')
        parser.add_argument('-tc', '--torrent-client', choices=['aria2', 'system', 'auto'], help='preferred torrent engine (aria2 for in-terminal, system for desktop app, auto for automatic)')
        parser.add_argument('-dl', '--disable-looping', default=False, action='store_true', help='disable auto-restart')

        global args
        args = parser.parse_args()

        config_file = args.conf
        log_file_name = args.log_file
        if log_file_name is None:
            log_file_name = f"scraper_{get_current_time('%Y%m%d%H%M%S')}.log"
        elif not log_file_name.endswith('.log'):
            log_file_name = f'{log_file_name}.log'
        series_type_predef = args.series_type
        series_name_predef = args.series_name
        seasons_predef = '-'.join(args.seasons) if args.seasons else None
        episodes_predef = '-'.join(args.episodes) if args.episodes else None
        resolution_predef = args.resolution
        # convert bool to y/n
        start_download_predef = 'y' if args.start_download else None

        # global settings
        disable_colors = args.disable_colors
        hls_size_accuracy = args.hls_size_accuracy
        disable_looping = args.disable_looping or args.search_only or args.dry_run

        # initialize color printer
        colprint_init(disable_colors)

        # load config from yaml to dict using yaml
        config = load_yaml(config_file)
        downloader_config = config['DownloaderConfig']
        if args.torrent_client:
            downloader_config['torrent_client'] = args.torrent_client
        max_parallel_downloads = downloader_config['max_parallel_downloads']

        # create logger
        config['LoggerConfig']['log_file_name'] = log_file_name
        logger = create_logger(**config['LoggerConfig'])
        logger.info('-------------------------------- NEW SCRAPER SESSION --------------------------------')

        logger.info(f'CLI options: {args}')

        # Handle standalone history flags
        if args.history:
            history_manager.render_history_view(35)
            sys.exit(0)
        if args.clear_history:
            history_manager.clear_history()
            colprint('success', '\n  ✔ Download history successfully purged.\n')
            sys.exit(0)
        if args.incomplete:
            records = history_manager.render_incomplete_view()
            if records:
                if args.start_download:
                    colprint('header', f"\n  ⚡ Automatically resuming all {len(records)} incomplete download(s)...\n")
                    for rec in records:
                        resume_task(rec, config)
                else:
                    try:
                        sel = input(f'\n  ➜ Enter task #(s) to resume (e.g. 1,3 or 1-2, A=All, 0=Exit): ').strip()
                    except (EOFError, KeyboardInterrupt):
                        sel = '0'
                    selected_indices = parse_task_selection(sel, len(records))
                    if selected_indices:
                        colprint('header', f"\n  ⚡ Resuming {len(selected_indices)} selected task(s)...\n")
                        for idx in selected_indices:
                            rec = records[idx - 1]
                            resume_task(rec, config)
            sys.exit(0)

        # Display hero banner
        if not args.quiet and series_type_predef is not None:
            hero_box = render_box('', [
                '\033[38;5;39m\033[1m🎬  CLI MEDIA SCRAPER & DOWNLOADER  v1.7.0\033[0m',
                '\033[38;5;244mAnime • Asian Dramas • Movies • TV Shows • NSFW\033[0m'
            ], center=True)
            print(f'\n{hero_box}\n')

        # remove older log files
        delete_old_logs(config['LoggerConfig']['log_dir'], config['LoggerConfig'].get('log_retention_days', 7), config['LoggerConfig'].get('log_backup_count', 3))

        # get series type / category and provider with Back navigation support
        while True:
            category_names = list(CATEGORIES.values())
            series_type = get_series_type(category_names, series_type_predef)
            logger.info(f'Selected Series type: {series_type}')

            # get provider key from CLI if specified
            provider_predef = args.provider if hasattr(args, 'provider') else None

            # create client (with provider selection if not predefined via CLI)
            client = get_client(provider_predef)
            if client is None:
                if series_type_predef is not None:
                    raise ExitException(0)
                continue

            logger.info(f'Client: {client}')
            break

        # set client specific download configurations
        if series_type in ('Movies', 'TV Shows'):
            downloader_config['use_http_client'] = True

        # set respective download dir if present
        if series_type in config and isinstance(config[series_type], dict) and 'download_dir' in config[series_type]:
            logger.debug(f'Setting download dir to [{config[series_type]["download_dir"]}] from series specific configuration')
            downloader_config['download_dir'] = config[series_type]['download_dir']
        elif series_type in ('Hentai (NSFW)', 'NSFW / Hentai', 4, '4', 'nsfw', 'hentai'):
            nsfw_cfg = config.get('Hentai (NSFW)') or config.get('NSFW / Hentai') or config.get('NSFW') or {}
            if 'download_dir' in nsfw_cfg:
                downloader_config['download_dir'] = nsfw_cfg['download_dir']
            elif 'Anime' in config and 'download_dir' in config['Anime']:
                downloader_config['download_dir'] = os.path.join(config['Anime']['download_dir'], 'Hentai (NSFW)')

        # modify path based on the platform OS
        downloader_config['download_dir'] = get_os_safe_path(downloader_config['download_dir'])
        # check if download path exists
        check_if_exists(downloader_config['download_dir'])

        # search in an infinite loop till you get your series
        target_series = search_and_select_series(series_name_predef, search_only=args.search_only)
        logger.info(f'Selected series: {target_series}')

        # fetch episode links
        logger.info(f'Fetching episodes list')
        episodes = client.fetch_episodes_list(target_series)

        if len(episodes) == 0:
            logger.error('No episodes found in selected series!')
            raise ExitException(1)

        if not args.quiet and not episodes_predef:
            clear_screen()
            prov_name = getattr(client, 'name', '') or str(series_type)
            render_step_header(breadcrumbs=[str(series_type), prov_name, target_series.get('title', 'Unknown'), 'Select Episodes'])

        ep_overview = [
            f"\033[1mSeries:\033[0m \033[38;5;39m{target_series.get('title', 'Unknown')}\033[0m",
            f"\033[1mTotal Episodes Available:\033[0m \033[38;5;82m{len(episodes)}\033[0m (1 - {len(episodes)})"
        ]
        print('\n' + render_box('AVAILABLE EPISODES', ep_overview))
        client.show_episode_results(episodes, seasons_predef, episodes_predef)

        # get user input for episodes range and parse start and end number
        season_ranges = client.get_season_ep_ranges(episodes)
        if series_type in (3, '3', 'TV Shows', 'tv') and len(season_ranges) > 1:
            selected_eps = get_ep_range_multiple(season_ranges, episodes, seasons_predef, episodes_predef)
        elif len(episodes) == 1 or series_type in ('Movies', 2, '2', 'movies'):
            ep_start = episodes[0]['episode']
            ep_end = episodes[-1]['episode']
            selected_eps = {'start': ep_start, 'end': ep_end, 'specific_no': [ep_start]}
        else:
            selected_eps = get_ep_range(f"{episodes[0]['episode']}-{episodes[-1]['episode']}", 'Enter', episodes_predef)

        # set output names & make it windows safe
        logger.debug(f'Set output names based on {target_series}')
        series_title, episode_prefix = client.set_out_names(target_series)
        logger.debug(f'{series_title = }, {episode_prefix = }')

        # set target output dir
        downloader_config['download_dir'] = os.path.join(f"{downloader_config['download_dir']}", f"{series_title}")
        logger.debug(f"Final download dir: {downloader_config['download_dir']}")

        # 1. Fast Resolution Discovery (Probe 1 sample episode if resolution not predefined)
        target_ep_links = {}
        if resolution_predef:
            resolution = resolution_predef
            colprint('predefined', f'\nUsing Predefined Input for resolution: {resolution_predef}')
        else:
            sample_ep = episodes[0]
            if isinstance(selected_eps, dict):
                first_sel_num = selected_eps.get('start') or (selected_eps.get('specific_no', [None])[0])
                if first_sel_num:
                    for ep in episodes:
                        if ep.get('episode') == first_sel_num:
                            sample_ep = ep
                            break

            colprint('header', "\nProbing Available Releases & Resolutions...")
            sample_links = client.fetch_episode_links([sample_ep], {'start': sample_ep.get('episode', 1), 'end': sample_ep.get('episode', 1), 'specific_no': [sample_ep.get('episode', 1)]})
            if sample_links:
                target_ep_links.update(sample_links)

            sample_ep_links = next(iter(sample_links.values()), {}) if sample_links else {}
            # Filter out error keys and failed probe dicts
            clean_sample_links = {}
            if isinstance(sample_ep_links, dict):
                for k, v in sample_ep_links.items():
                    if str(k).lower() == 'error' or (isinstance(k, str) and 'error' in k.lower()):
                        continue
                    if isinstance(v, dict) and 'error' in v and len(v) == 1:
                        continue
                    clean_sample_links[k] = v
            sample_ep_links = clean_sample_links

            # Check if options contain actual torrent release details / file sizes (e.g. 1.2 GB, magnet)
            has_release_sizes = any(
                isinstance(v, dict) and (v.get('size') or v.get('magnet') or (v.get('downloadType') == 'torrent'))
                for v in sample_ep_links.values()
            )

            # Check if options have server groupings (multi-server anime)
            has_servers = any(isinstance(v, dict) and v.get('server_name') for v in sample_ep_links.values())

            # Sort options: 2160 -> 1080 -> 720 -> 480 -> 360, and by seeds descending
            def sort_res_option(entry):
                opt_k, opt_d = entry
                q_raw = (opt_d.get('quality') if isinstance(opt_d, dict) else None) or opt_k
                q = str(q_raw).upper().replace('P', '')
                seeds = int(opt_d.get('seeds') or (opt_d.get('torrent_info', {}).get('seeds', 0) if isinstance(opt_d, dict) else 0)) if isinstance(opt_d, dict) else 0
                q_score = 300000 if q == '2160' else (200000 if q == '1080' else (100000 if q == '720' else (50000 if q == '480' else (25000 if q in ('360', '682') else 0))))
                return q_score + seeds

            # Deduplicate entries: if has_servers, use srv-prefixed entries to keep all servers
            if has_servers:
                filtered_sample_options = [(k, v) for k, v in sample_ep_links.items() if str(k).startswith('srv')]
                if not filtered_sample_options:
                    filtered_sample_options = list(sample_ep_links.items())
            else:
                filtered_sample_options = list(sample_ep_links.items())

            # Group by server if has_servers
            servers_grouped = {}
            if has_servers:
                for opt_k, opt_d in filtered_sample_options:
                    srv_title = opt_d.get('server_name', 'Default Server')
                    if opt_d.get('server_type'):
                        srv_title += f" [{opt_d.get('server_type')}]"
                    servers_grouped.setdefault(srv_title, []).append((opt_k, opt_d))
                for srv_t in servers_grouped:
                    servers_grouped[srv_t].sort(key=sort_res_option, reverse=True)
            else:
                sorted_options = sorted(filtered_sample_options, key=sort_res_option, reverse=True)

            if not args.quiet:
                clear_screen()
                prov_name = getattr(client, 'name', '') or str(series_type)
                box_header_title = 'Select Torrent Release' if has_release_sizes else 'Select Resolution'
                render_step_header(breadcrumbs=[str(series_type), prov_name, target_series.get('title', 'Unknown'), box_header_title])

            res_lines = []
            res_map = {}
            default_choice_idx = "1"
            has_1080_default = False
            current_choice_num = 1

            if has_servers:
                for srv_title, srv_opts in servers_grouped.items():
                    if res_lines:
                        res_lines.append("")
                    res_lines.append(f"  \033[1m\033[38;5;39m🖥️  {srv_title}\033[0m")
                    for opt_k, opt_d in srv_opts:
                        q_raw = (opt_d.get('quality') if isinstance(opt_d, dict) else None) or opt_k
                        q = str(q_raw).upper().replace('P', '')
                        if not q or q.lower() in ('error', 'none'):
                            continue

                        idx_str = str(current_choice_num)
                        res_map[idx_str] = opt_k
                        if q not in res_map:
                            res_map[q] = opt_k
                            res_map[f"{q}p"] = opt_k
                            res_map[f"{q}P"] = opt_k
                            if q == '2160':
                                res_map['4k'] = opt_k
                                res_map['4K'] = opt_k

                        is_default = False
                        if q == '1080' and not has_1080_default:
                            default_choice_idx = idx_str
                            has_1080_default = True
                            is_default = True

                        def_tag = ' \033[38;5;39m[default]\033[0m' if is_default else ''
                        label = '4K UHD' if q == '2160' else ('Full HD (Recommended)' if q == '1080' else ('HD' if q in ('720', '682') else ('SD' if q in ('480', '360') else 'Stream')))
                        res_lines.append(f"    \033[1m[{idx_str}]\033[0m  \033[1m{q}P\033[0m  \033[38;5;244m•  {label}\033[0m{def_tag}")
                        current_choice_num += 1
            else:
                for idx, (opt_k, opt_d) in enumerate(sorted_options, start=1):
                    q_raw = (opt_d.get('quality') if isinstance(opt_d, dict) else None) or opt_k
                    q = str(q_raw).upper().replace('P', '')
                    if not q or q.lower() in ('error', 'none'):
                        continue
                    res_map[str(idx)] = opt_k
                    if q not in res_map:
                        res_map[q] = opt_k
                        res_map[f"{q}p"] = opt_k
                        res_map[f"{q}P"] = opt_k
                        if q == '2160':
                            res_map['4k'] = opt_k
                            res_map['4K'] = opt_k

                    is_default = False
                    if q == '1080' and not has_1080_default:
                        default_choice_idx = str(idx)
                        has_1080_default = True
                        is_default = True

                    def_tag = ' \033[38;5;39m[default]\033[0m' if is_default else ''

                    is_torrent = isinstance(opt_d, dict) and (opt_d.get('size') or opt_d.get('magnet') or opt_d.get('downloadType') == 'torrent')
                    if is_torrent:
                        size_meta = f"{opt_d.get('size', 'Ready')} • Seeds: {opt_d.get('seeds', 0)}"
                        res_lines.append(f"  \033[1m[{idx}]\033[0m  \033[1m{q}P\033[0m  \033[38;5;244m•  {size_meta}\033[0m{def_tag}")
                    else:
                        label = '4K UHD' if q == '2160' else ('Full HD (Recommended)' if q == '1080' else ('HD' if q in ('720', '682') else ('SD' if q in ('480', '360') else 'Stream')))
                        res_lines.append(f"  \033[1m[{idx}]\033[0m  \033[1m{q}P\033[0m  \033[38;5;244m•  {label}\033[0m{def_tag}")

            if not res_lines:
                ordered_res = ['1080', '720', '480', '360']
                for idx, r in enumerate(ordered_res, start=1):
                    res_map[str(idx)] = r
                    res_map[r] = r
                    label = 'Full HD (Recommended)' if r == '1080' else ('HD' if r == '720' else 'SD')
                    def_tag = ' \033[38;5;39m[default]\033[0m' if r == '1080' else ''
                    res_lines.append(f"  \033[1m[{idx}]\033[0m  \033[1m{r}P\033[0m  \033[38;5;244m•  {label}\033[0m{def_tag}")

            card_title = 'AVAILABLE TORRENT RELEASES' if has_release_sizes else 'AVAILABLE RESOLUTIONS'
            print('\n' + render_box(card_title, res_lines))

            default_val = res_map.get(default_choice_idx, list(res_map.values())[0])

            while True:
                try:
                    prompt_label = 'Select release' if has_release_sizes else 'Select resolution'
                    raw_input_val = input(f"\n  ➜ {prompt_label} [1-{len(res_lines)} or quality, default={default_choice_idx}]: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    raise ExitException(0)

                if not raw_input_val:
                    resolution = default_val
                    break

                cleaned = raw_input_val.lower().replace('p', '').strip()
                if raw_input_val in res_map:
                    resolution = res_map[raw_input_val]
                    break
                elif cleaned in res_map:
                    resolution = res_map[cleaned]
                    break
                else:
                    print(f"\033[38;5;196m  ❌ Invalid selection '{raw_input_val}'. Please enter a number (1-{len(res_lines)}) or resolution quality.\033[0m")

        logger.info(f'Selected download resolution: {resolution}')

        # 2. Fetch episode links for selected episodes
        logger.info(f'Fetching episodes based on {selected_eps = }')
        colprint('header', "\nFetching Episode links:")
        all_fetched_links = client.fetch_episode_links(episodes, selected_eps)
        if target_ep_links:
            target_ep_links.update(all_fetched_links)
        else:
            target_ep_links = all_fetched_links

        if len(target_ep_links) == 0:
            logger.error("No episodes are available for download!")
            raise ExitException(1)

        # 3. Format final m3u8 download links for specified resolution
        target_dl_links = client.fetch_m3u8_links(target_ep_links, resolution, episode_prefix)

        # Check for already downloaded episodes in the target download directory
        missing_dl_links = {}
        already_downloaded_count = 0
        for ep_key, ep_val in target_dl_links.items():
            if not ep_val or not ep_val.get('downloadLink'):
                missing_dl_links[ep_key] = ep_val
                continue

            ep_name = ep_val.get('episodeName', '')
            ep_out_dir = downloader_config['download_dir']
            if ep_val.get('type') == 'tv':
                ep_out_dir = os.path.join(ep_out_dir, f"Season-{ep_val.get('season', 1)}")

            target_file_path = os.path.join(ep_out_dir, ep_name)
            base_without_ext = ep_name.rsplit('.', 1)[0]
            alt_mkv = os.path.join(ep_out_dir, f"{base_without_ext}.mkv")
            alt_mp4 = os.path.join(ep_out_dir, f"{base_without_ext}.mp4")

            candidate_files = [target_file_path, alt_mkv, alt_mp4]

            # Detect legacy files without provider tag or with legacy Sxx token
            clean_no_prov = re.sub(r'\s*\[.*?\]\s*$', '', base_without_ext).strip()
            if clean_no_prov != base_without_ext:
                candidate_files.append(os.path.join(ep_out_dir, f"{clean_no_prov}.mkv"))
                candidate_files.append(os.path.join(ep_out_dir, f"{clean_no_prov}.mp4"))

            season_num = ep_val.get('season', 1)
            try:
                s_int = int(season_num)
            except Exception:
                s_int = 1
            if ' - E' in clean_no_prov:
                legacy_s_name = clean_no_prov.replace(' - E', f" - S{s_int:02d} - E", 1)
                candidate_files.append(os.path.join(ep_out_dir, f"{legacy_s_name}.mkv"))
                candidate_files.append(os.path.join(ep_out_dir, f"{legacy_s_name}.mp4"))

            existing_file = None
            for cand in candidate_files:
                if os.path.isfile(cand) and os.path.getsize(cand) > 1024 * 1024:
                    existing_file = cand
                    break

            if existing_file:
                size_mb = round(os.path.getsize(existing_file) / (1024 * 1024), 1)
                colprint('results', f"  [✓] {os.path.basename(existing_file)} already exists ({size_mb} MB) -> Skipping")
                already_downloaded_count += 1
            else:
                missing_dl_links[ep_key] = ep_val

        target_dl_links = missing_dl_links
        available_dl_count = len([ k for k, v in target_dl_links.items() if v.get('downloadLink') is not None ])
        logger.debug(f'{target_dl_links = }, {available_dl_count = }')

        if available_dl_count == 0 and already_downloaded_count > 0:
            colprint('results', f'\nAll {already_downloaded_count} selected episode(s) are already downloaded! Nothing to download.')
            return

        if len(target_dl_links) == 0:
            logger.error('No episodes available to download! Exiting.')
            raise ExitException(1)

        # Display Pre-Download Checklist Card
        if not args.quiet and not start_download_predef:
            clear_screen()
            prov_name = getattr(client, 'name', '') or str(series_type)
            render_step_header(breadcrumbs=[str(series_type), prov_name, series_title, 'Download Inspection'])

        audio_pref_val = getattr(client, 'audio_preference', None) or 'sub'
        audio_label = '🇺🇸 English Dubbed (Dub)' if audio_pref_val == 'dub' else ('🌐 Dual Audio / Multi-Audio' if audio_pref_val == 'dual' else '🇯🇵 Sub (Original Japanese)')
        first_dl = next(iter(target_dl_links.values()), {}) if target_dl_links else {}
        raw_res = first_dl.get('resolution') or str(resolution)
        clean_res = re.sub(r'^srv\d+_', '', str(raw_res), flags=re.IGNORECASE)
        res_display = f"{clean_res.upper()}P" if not clean_res.upper().endswith('P') else clean_res.upper()

        checklist_lines = [
            f"  \033[1mSeries:\033[0m      \033[38;5;39m{series_title}\033[0m",
            f"  \033[1mSave Path:\033[0m   \033[38;5;244m{downloader_config['download_dir']}\033[0m",
            f"  \033[1mResolution:\033[0m  \033[38;5;220m{res_display}\033[0m \033[38;5;244m(MKV with Forced English Subtitles)\033[0m",
            f"  \033[1mAudio:\033[0m       \033[38;5;39m{audio_label}\033[0m",
            f"  \033[1mQueued:\033[0m      {available_dl_count} episode(s) ready to download"
        ]
        if already_downloaded_count > 0:
            checklist_lines.append(f"  \033[38;5;82m✔  {already_downloaded_count} existing episode(s) skipped\033[0m")
        print('\n' + render_box('PRE-DOWNLOAD INSPECTION', checklist_lines))

        if args.dry_run:
            colprint('results', '\n[DRY RUN] Inspection complete. Exiting without downloading video files.')
            return

        if start_download_predef:
            colprint('predefined', f'Using Predefined Input for start download: {start_download_predef}')
            proceed = 'y'
        else:
            proceed = colprint('user_input', f"\n  ➜ Proceed to download (Y|n)? ", input_type='recurring', input_options=['y', 'n', 'Y', 'N', 'e']).lower() or 'y'

        if proceed == 'y':
            pass
        elif proceed == 'e':
            # option for user to edit his choices
            new_selected_eps = get_ep_range(f"{selected_eps['start']}-{selected_eps['end']}", 'Edit')
            new_ep_start, new_ep_end = new_selected_eps['start'], new_selected_eps['end']
            # filter target download links based on new range
            target_dl_links = { k:v for k,v in target_dl_links.items() if (k >= new_ep_start and k <= new_ep_end) or k in new_selected_eps['specific_no'] }
            logger.debug(f'Edited {target_dl_links = }')
            colprint('yellow', f'Proceeding to download as per edited range [{new_ep_start} - {new_ep_end}]...')
        else:
            logger.error("Download halted on user input")
            raise ExitException(1)

        # start downloading...
        msg = f"Downloading {available_dl_count} episode(s) to {downloader_config['download_dir']}..."
        logger.info(msg)
        # invoke downloader using a threadpool
        logger.info(f'Invoking batch downloader with {max_parallel_downloads = }')
        summary = batch_downloader(downloader, target_dl_links, downloader_config, max_parallel_downloads)

        # Post-download receipt card
        receipt_lines = [
            f"  \033[1mSeries:\033[0m    \033[38;5;39m{series_title}\033[0m",
            f"  \033[1mSaved To:\033[0m  \033[38;5;244m{downloader_config['download_dir']}\033[0m",
            f"  \033[1mEpisodes:\033[0m  {summary['total']} processed ({summary['success']} succeeded, {summary['skipped']} skipped, {summary['failed']} failed)"
        ]

        if summary['failed'] > 0:
            receipt_lines.append("")
            if summary['success'] > 0:
                receipt_lines.append(f"\033[38;5;220m⚠ Download session completed with {summary['failed']} failure(s)!\033[0m")
            else:
                receipt_lines.append(f"\033[38;5;196m✗ Download session failed ({summary['failed']} of {summary['total']} item(s) failed)!\033[0m")

            receipt_lines.append("")
            receipt_lines.append("\033[1mFailure Details:\033[0m")
            for item in summary['failures']:
                err_text = item.get('error') or 'Unknown error'
                first_line = err_text.strip().splitlines()[0] if err_text else 'Unknown error'
                receipt_lines.append(f"  \033[38;5;196m•\033[0m \033[1m{item.get('file', 'Unknown')}\033[0m: {first_line[:80]}")
        else:
            receipt_lines.append("")
            receipt_lines.append(f"\033[38;5;82m✔ Download session completed successfully! ({summary['success']} downloaded, {summary['skipped']} skipped)\033[0m")

        card_title = 'DOWNLOAD SUMMARY [FAILED]' if summary['failed'] == summary['total'] else ('DOWNLOAD SUMMARY [PARTIAL]' if summary['failed'] > 0 else 'DOWNLOAD SUMMARY')
        print('\n' + render_box(card_title, receipt_lines))

    except SystemExit as se:
        # propagate the exit from argparse after printing help or on parse error
        skip_restart = True

    except KeyboardInterrupt as ki:
        logger.error('User interrupted')

    except ExitException as ee:
        # skip restart only if exit code is 0
        if int(str(ee)) == 0: skip_restart = True

    except Exception as e:
        if logger:
            logger.error(f'Error occurred: {e}. Check log for more details.')
            logger.warning(f'Stacktrace: {traceback.format_exc()}')
        else:
            colprint('error', f'Error occurred: {e}')

    finally:
        # Perform any cleanup tasks
        if client: client.cleanup()
        # Ensure to close handlers at the end of the script or before rotating
        close_handlers()
        # Auto-start a new instance
        if skip_restart or disable_looping: exit(0)
        try:
            continuation_prompt = colprint('user_input', '\n  ➜ Ready for one more? Start new download (y|n)? ', input_type='recurring', input_options=['y', 'n', 'Y', 'N']).lower() or 'y'
            if continuation_prompt == 'y':
                os.system(f'{sys.executable} {sys.argv[0]} -c {config_file} -l {log_file_name}')
            else:
                colprint('results', "Download completed. Thanks for using the scraper!\n")

        except KeyboardInterrupt:
            exit(0)


if __name__ == '__main__':
    main()
