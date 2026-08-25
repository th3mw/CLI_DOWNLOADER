import logging
import os
import re
import requests
import shutil
import subprocess
import sys
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from functools import wraps
from time import sleep
from logging.handlers import RotatingFileHandler
from subprocess import Popen, PIPE, DEVNULL


# color themes
PRINT_THEMES = {
    'default': '\033[1m',
    'blurred': '\033[38;5;244m',
    'header': '\033[38;5;39m\033[1m',
    'results': '\033[38;5;82m',
    'predefined': '\033[38;5;214m',
    'user_input': '\033[38;5;220m\033[1m',
    'yellow': '\033[38;5;220m',
    'success': '\033[38;5;82m',
    'error': '\033[38;5;196m',
    'primary': '\033[38;5;39m',
    'secondary': '\033[38;5;141m',
    'warning': '\033[38;5;214m',
    'muted': '\033[38;5;244m',
    'bold': '\033[1m',
    'blinking': '\033[5m',
    'reset': '\033[0m'
}
DISPLAY_COLORS = True

# strip ANSI characters
strip_ansi = lambda text: re.sub(r'\x1b\[[0-9;]*m', '', str(text)) if text is not None else ''

def visible_len(text):
    '''Calculate visible display length of string ignoring ANSI codes'''
    return len(strip_ansi(text))

def render_box(title, lines, max_width=76, indent=2, center=False):
    '''
    Render a clean Unicode bordered card container.
    Adapts dynamically to terminal width without line overflow.
    Includes left indentation margin for clean breathing room.
    '''
    try:
        term_cols = shutil.get_terminal_size((80, 24)).columns
    except Exception:
        term_cols = 80
    term_width = min(term_cols - (indent * 2), max_width)
    inner_width = max(term_width - 4, 30)
    pad_left = ' ' * indent

    c_border = PRINT_THEMES['primary'] if DISPLAY_COLORS else ''
    c_title = (PRINT_THEMES['secondary'] + PRINT_THEMES['bold']) if DISPLAY_COLORS else ''
    c_reset = PRINT_THEMES['reset'] if DISPLAY_COLORS else ''

    title_str = f' {c_title}{title}{c_reset}{c_border} ' if title else ''
    title_vlen = visible_len(title) + 2 if title else 0
    dash_count = max(inner_width - title_vlen, 2)

    out = [f'{pad_left}{c_border}╭──{title_str}' + ('─' * dash_count) + f'╮{c_reset}']
    for line in lines:
        vlen = visible_len(line)
        if vlen > inner_width:
            line_str = line[:inner_width]
            vlen = inner_width
        else:
            line_str = line
        pad = max(0, inner_width - vlen)
        if center:
            pad_l = ' ' * (pad // 2)
            pad_r = ' ' * (pad - len(pad_l))
            out.append(f'{pad_left}{c_border}│{c_reset} {pad_l}{line_str}{pad_r} {c_border}│{c_reset}')
        else:
            out.append(f'{pad_left}{c_border}│{c_reset} {line_str}' + (' ' * pad) + f' {c_border}│{c_reset}')

    out.append(f'{pad_left}{c_border}╰' + ('─' * (inner_width + 2)) + f'╯{c_reset}')
    return '\n'.join(out)

def clear_screen(disable_clear=False):
    '''Clear terminal screen buffer while preserving cross-platform compatibility'''
    if disable_clear or os.environ.get('NO_CLEAR') or not sys.stdout.isatty():
        return
    sys.stdout.write('\033[2J\033[H')
    sys.stdout.flush()

def render_step_header(breadcrumbs=None, step_title=None):
    '''Render persistent top hero header and dynamic breadcrumb trail'''
    c_blue = PRINT_THEMES['header'] if DISPLAY_COLORS else ''
    c_muted = PRINT_THEMES['muted'] if DISPLAY_COLORS else ''
    c_reset = PRINT_THEMES['reset'] if DISPLAY_COLORS else ''
    c_green = PRINT_THEMES['results'] if DISPLAY_COLORS else ''
    c_yellow = PRINT_THEMES['user_input'] if DISPLAY_COLORS else ''

    banner = render_box('', [
        f'{c_blue}🎬  CLI MEDIA SCRAPER & DOWNLOADER  v1.5{c_reset}',
        f'{c_muted}Anime • Asian Dramas • Movies • TV Shows • NSFW{c_reset}'
    ], max_width=76, indent=0, center=True)
    print(f'\n{banner}\n')
    if breadcrumbs:
        trail = f' {c_muted}›{c_reset} '.join(f'{c_green}{b}{c_reset}' for b in breadcrumbs if b)
        print(f"  {c_muted}📍 Location:{c_reset} {trail}\n")
    elif step_title:
        print(f"  {c_yellow}➜ {step_title}{c_reset}\n")

class ExitException(Exception):
    '''
    Custom exception which forces UDB to exit. Requires status code as argument.
    - =0 means direct exit without prompting for new session.
    - >0 prompts for new session.
    '''
    pass

def exec_os_cmd(cmd, timeout=300):
    '''
    Execute any OS commands
    Args: command to be executed
    Returns: output of executed command
    '''
    proc = Popen(cmd, stdout=PIPE, stderr=PIPE, shell=True, stdin=DEVNULL)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except Exception as e:
        proc.kill()
        raise Exception(f"Command timed out after {timeout}s: {e}")
    msg = stdout.decode("utf-8", errors="ignore")
    std_err = stderr.decode("utf-8", errors="ignore")
    rc = proc.returncode
    if rc != 0:
        raise Exception(f"Error occurred: {std_err}")
    return msg


def get_js_runtime():
    '''Detect available JavaScript CLI runtimes (bun, node, deno, qjs)'''
    for bin_name in ['bun', 'node', 'deno', 'qjs']:
        path = shutil.which(bin_name)
        if path:
            if bin_name == 'deno':
                return [path, 'eval']
            return [path, '-e']
    return None


def exec_js(js_code):
    '''
    Execute JavaScript code across multiple available engines:
    1. CLI JS runtime (bun, node, deno, qjs)
    2. Embedded quickjs Python C-extension
    Raises RuntimeError if no JavaScript engine is available or execution fails.
    '''
    runtime_cmd = get_js_runtime()
    if runtime_cmd:
        res = subprocess.run(runtime_cmd + [js_code], capture_output=True, text=True)
        if res.returncode == 0:
            return res.stdout.strip()
        else:
            raise RuntimeError(f"JS execution failed via {runtime_cmd[0]}: {res.stderr.strip()}")

    try:
        import quickjs
        ctx = quickjs.Context()
        out = []
        ctx.add_callable("__log_print__", lambda *args: out.append(" ".join(str(a) for a in args)))
        ctx.eval("var console = { log: __log_print__, error: __log_print__, warn: __log_print__ };")
        res = ctx.eval(js_code)
        if out:
            return "\n".join(out).strip()
        return str(res) if res is not None else ""
    except ImportError:
        pass

    raise RuntimeError(
        "No JavaScript engine found. Please install 'bun' (recommended: https://bun.sh), 'node', 'deno', or the 'quickjs' package."
    )


# display seconds in hh mm ss format
def pretty_time(sec: int, fmt='hh:mm:ss'):
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 3600 % 60
    if fmt == 'hh:mm:ss':
        return '{:02d}:{:02d}:{:02d}'.format(h,m,s)
    else:
        return '{:02d}h {:02d}m {:02d}s'.format(h,m,s) if h > 0 else '{:02d}m {:02d}s'.format(m,s)

# initialize colored printing
def colprint_init(disable_colors=False):
    global DISPLAY_COLORS
    if disable_colors or bool(os.environ.get('NO_COLOR')) or os.environ.get('TERM') == 'dumb':
        DISPLAY_COLORS = False
    else:
        DISPLAY_COLORS = True
        if os.name == 'nt':
            os.system('')   # required to enable ANSI output in Windows terminals

# custom stdout printer
def colprint(theme, text, **kwargs):
    '''Colorful print function.

    Args:
    - theme: color theme to be applied
    - text: data to print
    '''
    if DISPLAY_COLORS:
        c_strt, c_end = PRINT_THEMES.get(theme, '\033[1m'), PRINT_THEMES["reset"]
    else:
        c_strt, c_end = '', ''

    # parse the additional arguments
    line_end = kwargs.get('end')
    input_type = kwargs.get('input_type')
    input_dtype = kwargs.get('input_dtype')
    input_options = kwargs.get('input_options')
    allow_empty_input = kwargs.get('allow_empty_input', True)
    indent = kwargs.get('indent', 2)

    def _indent_text(t, ind=2):
        if not t or ind <= 0:
            return t
        prefix = ' ' * ind
        lines = str(t).split('\n')
        indented = []
        for l in lines:
            if not l.strip():
                indented.append(l)
            elif l.startswith(prefix):
                indented.append(l)
            else:
                indented.append(prefix + l)
        return '\n'.join(indented)

    def _get_input_(msg, input_type='once', input_dtype=None, input_options=[], allow_empty_input=True):
        user_input = input(f'{msg}').strip()
        # do not return till valid input is entered
        if input_type == 'recurring':
            try:
                # data type check
                try:
                    if user_input == '' and allow_empty_input:
                        return user_input       # if it is empty, it means default value
                    elif input_dtype == 'int':
                        user_input = int(user_input)
                    elif input_dtype == 'float':
                        user_input = float(user_input)
                    elif input_dtype == 'range':
                        # special case for range inputs. check if the values in range are int / float. allow empty value.
                        temp_inputs = [ float(i) if '.' in i else int(i) for i in user_input.replace('-', ',').split(',') if i ]
                except ValueError:
                    raise ValueError('Invalid input! Please enter a valid input.')

                # valid input check
                if input_options and not user_input in input_options:
                    raise ValueError('Invalid option selected! Please select an option from above.')

            except ValueError as ve:
                logging.error(ve)
                return _get_input_(msg, input_type, input_dtype, input_options, allow_empty_input)

        return user_input

    formatted_text = _indent_text(text, indent)

    if 'input' in theme:
        return _get_input_(f'{c_strt}{formatted_text}{c_end}', input_type, input_dtype, input_options, allow_empty_input)
    else:
        print(f'{c_strt}{formatted_text}{c_end}', end=line_end)

# custom decorator for retring of a function
def retry(exceptions=(Exception,), tries=4, delay=1.5, backoff=1.8, print_errors=False):
    """
    Retry Decorator
    Retries the wrapped function/method `times` times if the exceptions listed
    in ``exceptions`` are thrown
    :param Exceptions: Lists of exceptions that trigger a retry attempt
    :type Exceptions: Tuple of Exceptions
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt, mdelay = 0, delay
            while attempt < tries:
                try:
                    return_status = func(*args, **kwargs)
                    if type(return_status) == tuple and return_status[1] == 0:
                        raise Exception(return_status)
                    return return_status
                except exceptions as e:
                    attempt += 1
                    if attempt >= tries:
                        if kwargs.get('silent', False):
                            return None
                        if print_errors:
                            colprint('error', f'{e} | Final Attempt: {attempt} / {tries}')
                        raise e
                    sleep(mdelay)
                    mdelay *= backoff
            return func(*args, **kwargs)
        return wrapper
    return decorator

# custom decorator to make any function multi-threaded
def threaded(max_parallel=None, thread_name_prefix='scraper-', print_status=False):
    '''
    make any function multi-threaded by adding this decorator
    '''
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # If first argument is 'self' keyword, value will be like <xxx object at xxx>, then it is called from a class
            called_from_class = True if str(args[0]).startswith('<') and str(args[0]).endswith('>') and 'object at' in str(args[0]) else False
            final_status = []
            results = {}
            # Using a with statement to ensure threads are cleaned up promptly
            with ThreadPoolExecutor(max_workers=max_parallel, thread_name_prefix=thread_name_prefix) as executor:

                if called_from_class:
                    # If caller is a class, need to provide first argument (i.e., self) separately
                    futures = { executor.submit(func, args[0], i, *args[2:], **kwargs): idx for idx, i in enumerate(args[1]) }
                else:
                    futures = { executor.submit(func, i, *args[1:], **kwargs): idx for idx, i in enumerate(args[0]) }

                for future in as_completed(futures):
                    i = futures[future]
                    try:
                        # store result
                        data = future.result()
                        # if 'completed' not in data:
                        #     print(data)
                        if print_status: print(f"\033[F\033[K\r{data}")
                        results[i] = data
                    except Exception as e:
                        colprint('error', f'{e}')

            # sort the results in same order as received
            for idx, status in sorted(results.items()):
                final_status.append(status)

            return final_status
        return wrapper
    return decorator

CURRENT_CONFIG_VERSION = "1.5.0"


def migrate_config(config, config_file):
    '''
    Automatically migrate older YAML configurations to the latest schema while preserving custom paths.
    '''
    if not isinstance(config, dict):
        config = {}

    old_ver = config.get('version', '1.0.0')
    config['version'] = CURRENT_CONFIG_VERSION

    # Ensure DownloaderConfig exists
    if 'DownloaderConfig' not in config:
        config['DownloaderConfig'] = {
            'download_dir': '~/Videos',
            'max_parallel_downloads': 2,
            'torrent_client': 'auto'
        }

    # Ensure AudioPreference exists
    if 'AudioPreference' not in config:
        config['AudioPreference'] = {
            'default_audio': 'sub'
        }

    # Ensure Anime section exists
    if 'Anime' not in config:
        base_dir = config.get('DownloaderConfig', {}).get('download_dir', '~/Videos')
        config['Anime'] = {
            'download_dir': f"{base_dir.rstrip('/')}/Anime",
            'providers': {
                'nyaa': {'base_url': 'https://nyaa.si'},
                'anime_suge': {
                    'base_url': 'https://animesuge.cz',
                    'search_url': '/filter',
                    'preferred_server_types': ['sub', 'hsub', 'dub']
                },
                'anidb': {
                    'base_url': 'https://anidb.app',
                    'search_url': 'https://anidb.app/browse?q='
                },
                'kisskh': {'base_url': 'https://kisskh.co'}
            }
        }

    # Ensure Movies section exists
    if 'Movies' not in config:
        base_dir = config.get('DownloaderConfig', {}).get('download_dir', '~/Videos')
        config['Movies'] = {
            'download_dir': f"{base_dir.rstrip('/')}/Movies",
            'providers': {
                'yts': {'base_url': 'https://yts.lt'},
                'oneshows': {'base_url': 'https://www.1shows.org'},
                'kisskh': {'base_url': 'https://kisskh.co'}
            }
        }

    # Ensure TV Shows section exists
    if 'TV Shows' not in config:
        base_dir = config.get('DownloaderConfig', {}).get('download_dir', '~/Videos')
        config['TV Shows'] = {
            'download_dir': f"{base_dir.rstrip('/')}/Series",
            'providers': {
                'eztv': {'base_url': 'https://eztvx.to'},
                'oneshows': {'base_url': 'https://www.1shows.org'},
                'kisskh': {'base_url': 'https://kisskh.co'}
            }
        }

    # Ensure NSFW section exists
    if 'NSFW' not in config:
        base_dir = config.get('DownloaderConfig', {}).get('download_dir', '~/Videos')
        config['NSFW'] = {
            'download_dir': f"{base_dir.rstrip('/')}/NSFW",
            'providers': {
                'hanime': {
                    'base_url': 'https://hanime.tv',
                    'search_url': 'https://search.htv-services.com'
                }
            }
        }

    # Ensure PostProcessing section exists
    if 'PostProcessing' not in config:
        config['PostProcessing'] = {
            'auto_compress': False,
            'codec': 'hevc',
            'crf': 23,
            'preset': 'slow'
        }

    # Ensure LoggerConfig exists
    if 'LoggerConfig' not in config:
        config['LoggerConfig'] = {
            'log_dir': 'logs',
            'log_level': 'INFO',
            'log_retention_days': 7,
            'log_backup_count': 3
        }

    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, sort_keys=False, default_flow_style=False)
        colprint('success', f"\n✓ Configuration automatically updated to v{CURRENT_CONFIG_VERSION} at '{config_file}' (preserved existing download paths)\n")
    except Exception as e:
        logging.warning(f"Could not persist migrated config to {config_file}: {e}")

    return config


def run_config_wizard(config_file, existing_config=None):
    '''
    Interactive setup wizard to create or update YAML configuration file.
    '''
    if existing_config:
        colprint('header', f"\n\033[96m╭────────────────── CONFIGURATION UPDATE (v{CURRENT_CONFIG_VERSION}) ──────────────────╮\033[0m")
        colprint('header', f"\033[96m│ An outdated configuration was detected at '{config_file}'.          │\033[0m")
        colprint('header', f"\033[96m│ Let's configure your new v{CURRENT_CONFIG_VERSION} settings & review your setup!         │\033[0m")
        colprint('header', f"\033[96m╰──────────────────────────────────────────────────────────────────╯\033[0m\n")
    else:
        colprint('header', f"\n\033[96m╭────────────────── CONFIGURATION WIZARD ──────────────────╮\033[0m")
        colprint('header', f"\033[96m│ No configuration file found at '{config_file}'.          │\033[0m")
        colprint('header', f"\033[96m│ Let's quickly create your setup configuration!           │\033[0m")
        colprint('header', f"\033[96m╰──────────────────────────────────────────────────────────╯\033[0m\n")

    ex_dl = (existing_config or {}).get('DownloaderConfig', {})
    ex_anime = (existing_config or {}).get('Anime', {})
    ex_movies = (existing_config or {}).get('Movies', {})
    ex_shows = (existing_config or {}).get('TV Shows', {})
    ex_nsfw = (existing_config or {}).get('Hentai (NSFW)') or (existing_config or {}).get('NSFW / Hentai') or (existing_config or {}).get('NSFW', {})
    ex_audio = (existing_config or {}).get('AudioPreference', {})
    ex_post = (existing_config or {}).get('PostProcessing', {})
    ex_logger = (existing_config or {}).get('LoggerConfig', {})

    default_base_dir = ex_dl.get('download_dir') or "~/Videos"
    base_dir = colprint('user_input', f"Main download directory [default={default_base_dir}]: ", input_type='once') or default_base_dir

    default_anime_dir = ex_anime.get('download_dir') or f"{base_dir.rstrip('/')}/Anime"
    anime_dir = colprint('user_input', f"Anime download directory [default={default_anime_dir}]: ", input_type='once') or default_anime_dir

    default_movies_dir = ex_movies.get('download_dir') or f"{base_dir.rstrip('/')}/Movies"
    movies_dir = colprint('user_input', f"Movies download directory [default={default_movies_dir}]: ", input_type='once') or default_movies_dir

    default_shows_dir = ex_shows.get('download_dir') or f"{base_dir.rstrip('/')}/Series"
    shows_dir = colprint('user_input', f"TV Shows download directory [default={default_shows_dir}]: ", input_type='once') or default_shows_dir

    default_nsfw_dir = ex_nsfw.get('download_dir') or f"{anime_dir.rstrip('/')}/Hentai (NSFW)"
    nsfw_dir = colprint('user_input', f"Hentai (NSFW) download directory [default={default_nsfw_dir}]: ", input_type='once') or default_nsfw_dir

    default_audio_choice = 2 if ex_audio.get('default_audio') == 'dub' else 1
    audio_choice = colprint('user_input', f"Preferred Audio Language [1. Sub/Original, 2. English Dubbed] [default={default_audio_choice}]: ", input_type='recurring', input_dtype='int', input_options=[1, 2], allow_empty_input=True) or default_audio_choice
    selected_audio = 'dub' if int(audio_choice) == 2 else 'sub'

    default_max_parallel = ex_dl.get('max_parallel_downloads', 2)
    max_parallel = colprint('user_input', f"Max parallel episode downloads (1-10) [default={default_max_parallel}]: ", input_type='recurring', input_dtype='int', input_options=list(range(1, 11)), allow_empty_input=True) or default_max_parallel

    default_tor_choice = 1 if ex_dl.get('torrent_client') == 'aria2' else (2 if ex_dl.get('torrent_client') == 'system' else 3)
    torrent_choice = colprint('user_input', f"Preferred Torrent Mode [1. In-Terminal (aria2c), 2. Default App (e.g. FDM, qBittorrent), 3. Auto] [default={default_tor_choice}]: ", input_type='recurring', input_dtype='int', input_options=[1, 2, 3], allow_empty_input=True) or default_tor_choice
    torrent_client = 'aria2' if int(torrent_choice) == 1 else ('system' if int(torrent_choice) == 2 else 'auto')

    default_compress_choice = 'y' if ex_post.get('auto_compress') else 'n'
    compress_input = colprint('user_input', f"Auto-compress completed downloads with HEVC/AV1? (y/n) [default={default_compress_choice}]: ", input_type='recurring', input_options=['y', 'n', 'yes', 'no', 'Y', 'N'], allow_empty_input=True) or default_compress_choice
    auto_compress = str(compress_input).lower().startswith('y')

    default_log_lvl = ex_logger.get('log_level', 'INFO')
    log_level = colprint('user_input', f"Logging level (DEBUG|INFO|WARNING|ERROR) [default={default_log_lvl}]: ", input_type='recurring', input_options=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'debug', 'info', 'warning', 'error'], allow_empty_input=True).upper() or default_log_lvl

    config = {
        'version': CURRENT_CONFIG_VERSION,
        'DownloaderConfig': {
            'download_dir': base_dir,
            'max_parallel_downloads': int(max_parallel),
            'torrent_client': torrent_client,
        },
        'AudioPreference': {
            'default_audio': selected_audio,
        },
        'Anime': {
            'download_dir': anime_dir,
            'providers': ex_anime.get('providers') or {
                'nyaa': {
                    'base_url': 'https://nyaa.si'
                },
                'anime_suge': {
                    'base_url': 'https://animesuge.cz',
                    'search_url': '/filter',
                    'preferred_server_types': ['sub', 'hsub', 'dub']
                },
                'anidb': {
                    'base_url': 'https://anidb.app',
                    'search_url': 'https://anidb.app/browse?q='
                },
                'kisskh': {
                    'base_url': 'https://kisskh.co'
                }
            }
        },
        'Movies': {
            'download_dir': movies_dir,
            'providers': ex_movies.get('providers') or {
                'yts': {
                    'base_url': 'https://yts.lt'
                },
                'oneshows': {
                    'base_url': 'https://www.1shows.org'
                },
                'kisskh': {
                    'base_url': 'https://kisskh.co'
                }
            }
        },
        'TV Shows': {
            'download_dir': shows_dir,
            'providers': ex_shows.get('providers') or {
                'eztv': {
                    'base_url': 'https://eztvx.to'
                },
                'oneshows': {
                    'base_url': 'https://www.1shows.org'
                },
                'kisskh': {
                    'base_url': 'https://kisskh.co'
                }
            }
        },
        'Hentai (NSFW)': {
            'download_dir': nsfw_dir,
            'providers': ex_nsfw.get('providers') or {
                'hanime': {
                    'base_url': 'https://hanime.tv',
                    'search_url': 'https://search.htv-services.com'
                }
            }
        },
        'PostProcessing': {
            'auto_compress': auto_compress,
            'codec': ex_post.get('codec', 'hevc'),
            'crf': ex_post.get('crf', 23),
            'preset': ex_post.get('preset', 'slow')
        },
        'LoggerConfig': {
            'log_dir': ex_logger.get('log_dir', os.path.expanduser('~/.local/share/media-scraper/logs') if not os.path.exists('scraper.py') else 'logs'),
            'log_level': log_level,
            'log_retention_days': ex_logger.get('log_retention_days', 7),
            'log_backup_count': ex_logger.get('log_backup_count', 3)
        }
    }

    try:
        parent_dir = os.path.dirname(config_file)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        with open(config_file, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, sort_keys=False, default_flow_style=False)

        colprint('success', f"\n✓ Configuration saved successfully to '{config_file}'!\n")
    except Exception as e:
        colprint('error', f"\nFailed to save configuration file '{config_file}': {e}")
        raise ExitException(0)

    return config


# load yaml config into dict
def load_yaml(config_file):
    xdg_config = os.path.expanduser('~/.config/media-scraper/config_scraper.yaml')
    target_path = None

    if os.path.isfile(config_file):
        target_path = config_file
    elif os.path.isfile(xdg_config):
        target_path = xdg_config
    else:
        save_target = config_file if os.path.exists('scraper.py') else xdg_config
        return run_config_wizard(save_target)

    with open(target_path, "r", encoding="utf-8") as stream:
        try:
            config = yaml.safe_load(stream)
            if not isinstance(config, dict):
                config = {}
            if config.get('version') != CURRENT_CONFIG_VERSION or ('Hentai (NSFW)' not in config and 'NSFW / Hentai' not in config and 'NSFW' not in config) or 'PostProcessing' not in config:
                return run_config_wizard(target_path, existing_config=config)
            return config
        except yaml.YAMLError as exc:
            colprint('error', f"Error occured while reading yaml file: {exc}")
            raise ExitException(0)

# custom logging formatter to highlight error messages
class CustomLogFormatter(logging.Formatter):
    '''A Formatter to highlight error log level messages in red'''
    def __init__(self, fmt=None, datefmt=None, style='%', validate=True):
        super().__init__(fmt, datefmt, style, validate)

    def format(self, record):
        if record.levelname == 'ERROR' and DISPLAY_COLORS:
            record.msg = f'{PRINT_THEMES["error"]}{record.msg}{PRINT_THEMES["reset"]}'
        return super().format(record)

# custom logger function
def create_logger(**logger_config):
    '''Create a logging handler

    Args: logging configuration as a dictionary [Allowed keys: log_level, log_dir, log_file_name, max_log_size_in_kb, log_backup_count]
    Returns: a logging handler'''
    # human-readable log-level to logging.* mapping
    log_levels = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR
    }

    # format the log entries
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(funcName)s:%(lineno)s - %(message)s')
    stdout_formatter = CustomLogFormatter()
    # get root logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # create logging directory
    os.makedirs(logger_config.get('log_dir', 'logs'), exist_ok=True)

    # create logging handler for stdout
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(stdout_formatter)
    stdout_handler.setLevel(logging.ERROR)

    # add rotating file handler to rotate log file when size crosses a threshold
    file_handler = RotatingFileHandler(
        os.path.join(logger_config.get('log_dir', 'logs'), logger_config.get('log_file_name', 'scraper.log')),
        maxBytes = logger_config.get('max_log_size_in_kb', 1000) * 1000,  # KB to Bytes
        backupCount = logger_config.get('log_backup_count', 3),
        encoding='utf-8',
        delay=True
    )
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(log_levels.get(logger_config.get('log_level', 'INFO').upper()))

    logger.addHandler(file_handler)     # print to file
    logger.addHandler(stdout_handler)   # print only error to stdout

    return logger

# delete old log files
def delete_old_logs(directory='logs', days_threshold=7, max_file_count=3):
    '''
    Delete files older than `days_threshold` days and greater than `max_file_count` in the specified directory.
    '''
    logging.debug(f'Deleting log files older than {days_threshold} days and greater than {max_file_count}...')
    ndays = datetime.now().timestamp() - days_threshold * 86400

    # Get list of files to delete. If you encapsulate this in () brackets, it'll be a generator :)
    files_with_mtime = [ (f, os.stat(f).st_mtime) for f in ( os.path.join(directory, i) for i in os.listdir(directory) ) if os.path.isfile(f) and os.stat(f).st_mtime < ndays ]
    files_to_delete = sorted(files_with_mtime, key=lambda x: x[1])[:-max_file_count]

    logging.debug(f'Found {len(files_to_delete)} files to delete!')
    failure_cnt = 0
    for f in files_to_delete:
        try:
            logging.debug(f'Deleting file: {f[0]}')
            os.remove(f[0])
        except:
            failure_cnt += 1
    
    if failure_cnt > 0:
        logging.error(f'Failed to delete {failure_cnt}/{len(files_to_delete)} log files older than {days_threshold} days.')
    else:
        logging.debug(f'Deleted {len(files_to_delete)} files.')
