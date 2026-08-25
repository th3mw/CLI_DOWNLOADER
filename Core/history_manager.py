import os
import sqlite3
from datetime import datetime
from Core.commons import colprint, render_box, DISPLAY_COLORS


def get_db_path():
    '''
    Return absolute path to SQLite database.
    '''
    if os.path.exists('scraper.py'):
        return os.path.abspath('history.db')
    
    config_dir = os.path.expanduser('~/.config/media-scraper')
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, 'history.db')


def get_connection():
    '''
    Open SQLite connection with row factory.
    '''
    db_path = get_db_path()
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    '''
    Initialize database schema.
    '''
    with get_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                season INTEGER DEFAULT 1,
                episode INTEGER DEFAULT 1,
                resolution TEXT,
                provider TEXT,
                content_type TEXT,
                download_type TEXT,
                target_filepath TEXT,
                download_link TEXT,
                referer_link TEXT,
                total_segments INTEGER DEFAULT 0,
                completed_segments INTEGER DEFAULT 0,
                file_size_bytes INTEGER DEFAULT 0,
                status TEXT DEFAULT 'in_progress',
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_status ON downloads(status)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_created ON downloads(created_at)')
        conn.commit()


def record_start(title, season=1, episode=1, resolution='720', provider='', content_type='', download_type='hls', target_filepath='', download_link='', referer_link='', total_segments=0) -> int:
    '''
    Record the initiation of a download task. Returns record ID.
    '''
    init_db()
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO downloads (
                    title, season, episode, resolution, provider,
                    content_type, download_type, target_filepath,
                    download_link, referer_link, total_segments,
                    completed_segments, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'in_progress', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ''', (
                title, int(season or 1), int(episode or 1), str(resolution or ''),
                provider, content_type, download_type, target_filepath,
                download_link, referer_link, int(total_segments or 0)
            ))
            conn.commit()
            return cursor.lastrowid
    except Exception:
        return 0


def update_progress(download_id: int, completed_segments: int, total_segments: int = 0, file_size_bytes: int = 0):
    '''
    Update progress checkpoint for a running download.
    '''
    if not download_id:
        return
    try:
        with get_connection() as conn:
            if total_segments > 0:
                conn.execute('''
                    UPDATE downloads
                    SET completed_segments = ?, total_segments = ?, file_size_bytes = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (completed_segments, total_segments, file_size_bytes, download_id))
            else:
                conn.execute('''
                    UPDATE downloads
                    SET completed_segments = ?, file_size_bytes = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (completed_segments, file_size_bytes, download_id))
            conn.commit()
    except Exception:
        pass


def record_complete(download_id: int, file_size_bytes: int = 0):
    '''
    Mark a download task as completed.
    '''
    if not download_id:
        return
    try:
        with get_connection() as conn:
            conn.execute('''
                UPDATE downloads
                SET status = 'completed', file_size_bytes = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (file_size_bytes, download_id))
            conn.commit()
    except Exception:
        pass


def record_failure(download_id: int, error_msg: str = ''):
    '''
    Mark a download task as failed.
    '''
    if not download_id:
        return
    try:
        with get_connection() as conn:
            conn.execute('''
                UPDATE downloads
                SET status = 'failed', error_message = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (error_msg, download_id))
            conn.commit()
    except Exception:
        pass


def get_history(limit: int = 25):
    '''
    Fetch recent download records.
    '''
    init_db()
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM downloads
                ORDER BY id DESC
                LIMIT ?
            ''', (limit,))
            return [dict(row) for row in cursor.fetchall()]
    except Exception:
        return []


def get_incomplete_downloads():
    '''
    Fetch interrupted / incomplete download records.
    '''
    init_db()
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM downloads
                WHERE status IN ('in_progress', 'paused', 'failed')
                ORDER BY id DESC
                LIMIT 50
            ''')
            rows = [dict(row) for row in cursor.fetchall()]
            # Filter out entries where target file already exists and is complete
            incomplete = []
            for r in rows:
                target_path = r.get('target_filepath')
                if not target_path or not os.path.isfile(target_path):
                    incomplete.append(r)
            return incomplete
    except Exception:
        return []


def clear_history():
    '''
    Purge all records from database.
    '''
    init_db()
    try:
        with get_connection() as conn:
            conn.execute('DELETE FROM downloads')
            conn.commit()
            return True
    except Exception:
        return False


def format_size(bytes_val: int) -> str:
    '''
    Convert bytes to human readable format.
    '''
    if not bytes_val or bytes_val <= 0:
        return 'N/A'
    mb = bytes_val / (1024 * 1024)
    if mb >= 1000:
        return f"{mb / 1024:.2f} GB"
    return f"{mb:.1f} MB"


def render_history_view(limit: int = 25):
    '''
    Display download history in a structured box.
    '''
    records = get_history(limit)
    if not records:
        print('\n' + render_box('DOWNLOAD HISTORY', ['No previous download history found.']))
        return

    lines = []
    for r in records:
        status_icon = '✔' if r['status'] == 'completed' else ('⏳' if r['status'] == 'in_progress' else '❌')
        status_color = '\033[38;5;48m' if r['status'] == 'completed' else ('\033[38;5;214m' if r['status'] == 'in_progress' else '\033[38;5;196m')
        
        ep_tag = f"S{r.get('season', 1):02d}-E{r.get('episode', 1):02d}"
        res_tag = f"{r.get('resolution', '')}P" if r.get('resolution') and not str(r.get('resolution')).endswith('P') else r.get('resolution', '')
        size_str = format_size(r.get('file_size_bytes', 0))
        date_str = (r.get('created_at') or '')[:16]
        prov = r.get('provider') or 'Unknown'
        
        title_line = f"\033[1m{r.get('title', 'Unknown')}\033[0m \033[38;5;244m({ep_tag} • {res_tag})\033[0m"
        meta_line = f"   {status_color}{status_icon} {r['status'].upper()}\033[0m | Prov: \033[38;5;39m{prov}\033[0m | Size: \033[38;5;250m{size_str}\033[0m | Date: \033[38;5;244m{date_str}\033[0m"
        
        lines.append(title_line)
        lines.append(meta_line)
        lines.append('')

    if lines and lines[-1] == '':
        lines.pop()

    print('\n' + render_box(f'DOWNLOAD HISTORY ({len(records)} recent items)', lines))


def render_incomplete_view():
    '''
    Display incomplete downloads in a structured box and return items.
    '''
    records = get_incomplete_downloads()
    if not records:
        print('\n' + render_box('INCOMPLETE DOWNLOADS', ['🎉 No pending or incomplete downloads found! All downloads complete.']))
        return []

    lines = []
    for idx, r in enumerate(records, start=1):
        ep_tag = f"S{r.get('season', 1):02d}-E{r.get('episode', 1):02d}"
        res_tag = f"{r.get('resolution', '')}P" if r.get('resolution') and not str(r.get('resolution')).endswith('P') else r.get('resolution', '')
        date_str = (r.get('created_at') or '')[:16]
        prov = r.get('provider') or 'Unknown'
        
        prog_info = ''
        if r.get('total_segments'):
            pct = int((r.get('completed_segments', 0) / r['total_segments']) * 100)
            prog_info = f" | Prog: {r.get('completed_segments', 0)}/{r['total_segments']} segs ({pct}%)"
            
        title_line = f"\033[1m[{idx}] {r.get('title', 'Unknown')}\033[0m \033[38;5;244m({ep_tag} • {res_tag})\033[0m"
        meta_line = f"    Prov: \033[38;5;39m{prov}\033[0m | Status: \033[38;5;214m{r['status'].upper()}\033[0m{prog_info} | Date: \033[38;5;244m{date_str}\033[0m"
        
        lines.append(title_line)
        lines.append(meta_line)
        lines.append('')

    if lines and lines[-1] == '':
        lines.pop()

    print('\n' + render_box('INCOMPLETE DOWNLOADS (Ready to Resume)', lines))
    return records
