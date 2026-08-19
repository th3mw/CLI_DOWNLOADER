import io
import os
import platform
import shutil
import tarfile
import tempfile
import urllib.request
import zipfile

from Core.commons import colprint, ProgressBar

# Official & verified static standalone binary releases
STATIC_ARIA2_URLS = {
    'Linux_x86_64': 'https://github.com/dmesg00/aria2-static-builds/releases/download/v1.37.0/aria2-1.37.0-linux-gnu-64bit-build1.tar.bz2',
    'Linux_i386': 'https://github.com/dmesg00/aria2-static-builds/releases/download/v1.37.0/aria2-1.37.0-linux-gnu-32bit-build1.tar.bz2',
    'Linux_i686': 'https://github.com/dmesg00/aria2-static-builds/releases/download/v1.37.0/aria2-1.37.0-linux-gnu-32bit-build1.tar.bz2',
    'Linux_aarch64': 'https://github.com/dmesg00/aria2-static-builds/releases/download/v1.37.0/aria2-1.37.0-linux-gnu-arm-rbpi-build1.tar.bz2',
    'Linux_armv7l': 'https://github.com/dmesg00/aria2-static-builds/releases/download/v1.37.0/aria2-1.37.0-linux-gnu-arm-rbpi-build1.tar.bz2',
    'Windows_x86_64': 'https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0-win-64bit-build1.zip',
    'Windows_AMD64': 'https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0-win-64bit-build1.zip',
    'Windows_x86': 'https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0-win-32bit-build1.zip',
}


def get_local_bin_dir():
    '''Returns standard path for user local binaries: ~/.local/share/media-scraper/bin'''
    bin_dir = os.path.expanduser('~/.local/share/media-scraper/bin')
    os.makedirs(bin_dir, exist_ok=True)
    return bin_dir


def get_aria2_path(auto_provision=True):
    '''
    Resolves the executable path for aria2c.
    1. Checks system PATH.
    2. Checks ~/.local/share/media-scraper/bin/
    3. Auto-provisions static binary for current platform if missing and auto_provision=True.
    '''
    # 1. System PATH
    sys_path = shutil.which('aria2c')
    if sys_path:
        return sys_path

    # 2. Local provisioned binary
    bin_dir = get_local_bin_dir()
    exe_name = 'aria2c.exe' if platform.system() == 'Windows' else 'aria2c'
    local_path = os.path.join(bin_dir, exe_name)

    if os.path.isfile(local_path) and os.access(local_path, os.X_OK):
        return local_path

    if not auto_provision:
        return None

    # 3. Auto-provision static binary
    return provision_aria2c()


def provision_aria2c():
    '''Downloads and extracts static aria2c standalone binary for the host OS/architecture'''
    sys_name = platform.system()
    arch_name = platform.machine()
    key = f"{sys_name}_{arch_name}"

    url = STATIC_ARIA2_URLS.get(key)
    if not url:
        # Fallback to 64bit if Linux
        if sys_name == 'Linux':
            url = STATIC_ARIA2_URLS.get('Linux_x86_64')
        elif sys_name == 'Windows':
            url = STATIC_ARIA2_URLS.get('Windows_x86_64')

    if not url:
        return None

    bin_dir = get_local_bin_dir()
    exe_name = 'aria2c.exe' if sys_name == 'Windows' else 'aria2c'
    dest_path = os.path.join(bin_dir, exe_name)

    colprint('header', f"\n  ➜ Auto-provisioning bundled standalone aria2c for {sys_name} ({arch_name})...")

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            total_size = int(resp.headers.get('Content-Length', 0))
            downloaded = 0
            chunk_size = 65536
            data = io.BytesIO()

            pbar = ProgressBar(100, f"Downloading aria2c", unit='%') if total_size > 0 else None

            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                data.write(chunk)
                downloaded += len(chunk)
                if pbar and total_size > 0:
                    pct = min(100, int((downloaded / total_size) * 100))
                    pbar.update(pct)

            if pbar:
                pbar.complete()

            data.seek(0)

        # Extract archive in-memory or via tempfile
        if url.endswith('.tar.bz2'):
            with tarfile.open(fileobj=data, mode='r:bz2') as tar:
                for member in tar.getmembers():
                    if os.path.basename(member.name) == 'aria2c':
                        extracted_f = tar.extractfile(member)
                        with open(dest_path, 'wb') as out_f:
                            out_f.write(extracted_f.read())
                        break
        elif url.endswith('.zip'):
            with zipfile.ZipFile(data) as zf:
                for name in zf.namelist():
                    if os.path.basename(name).lower() == 'aria2c.exe':
                        with zf.open(name) as zf_file, open(dest_path, 'wb') as out_f:
                            out_f.write(zf_file.read())
                        break

        if os.path.isfile(dest_path):
            os.chmod(dest_path, 0o755)
            colprint('success', f"  [✓] Bundled aria2c successfully configured at: {dest_path}\n")
            return dest_path
    except Exception as e:
        colprint('error', f"  [✗] Failed to auto-provision aria2c: {e}\n")

    return None
