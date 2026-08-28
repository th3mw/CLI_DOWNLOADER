# 🎬 Media Scraper

A powerful command-line interface (CLI) application for searching and downloading Anime, Movies, and TV Shows from multiple online providers with high performance, resolution selection, parallel link fetching, and automated HLS segment processing.

---

## 📖 Table of Contents
- [🎬 Media Scraper](#-media-scraper)
  - [📖 Table of Contents](#-table-of-contents)
  - [✨ Features](#-features)
  - [📷 Screenshots](#-screenshots)
  - [📦 Installation](#-installation)
    - [Prerequisites](#prerequisites)
    - [Global CLI Installation (Recommended)](#global-cli-installation-recommended)
      - [Option A: Using `pipx` (Recommended)](#option-a-using-pipx-recommended)
      - [Option B: Using `uv tool`](#option-b-using-uv-tool)
      - [Option C: Local Editable Install](#option-c-local-editable-install)
  - [🚀 Quick Start](#-quick-start)
  - [💻 Command Line Interface (CLI) Usage](#-command-line-interface-cli-usage)
    - [Command Line Arguments](#command-line-arguments)
    - [Example CLI Commands](#example-cli-commands)
  - [🌐 Supported Providers](#-supported-providers)
  - [⚙️ Configuration](#️-configuration)
  - [💡 Subtitle \& Media Player Notes](#-subtitle--media-player-notes)
  - [🛠️ Technical Documentation](#️-technical-documentation)
  - [📄 License](#-license)

---

## ✨ Features

- **Modern Unicode UI Engine**: Sleek bordered cards, single-line hero banners, and dynamic status indicators built for Linux, macOS, and Windows.
- **Multi-Source Scraping**: Download content seamlessly from top Anime and Movie/TV Show providers.
- **Interactive Navigation with Back Support**: Context-aware provider cards with `0. Back` to change categories on the fly.
- **Real-Time Download Dashboard**: High-precision gradient progress bars (`━╸─`) displaying speed, ETA, segment/chunk progress, and cache indicators (`[R:X F:Y]`).
- **One-Line CLI Ergonomics**: String aliases (`-s anime`, `-s movies`, `-s tv`), `--search-only` for instant lookups, `--dry-run` for link inspection, and `-q`/`--quiet` for headless scripts.
- **First-Launch Setup Wizard**: If no configuration file exists on first launch, an interactive setup wizard guides you step-by-step to create and save `config_scraper.yaml`.
- **Download Resumption**: Automatic segment/chunk caching. Interrupted downloads resume from where they left off without re-downloading existing segments.
- **Fast Parallel Fetching**: Concurrent episode link resolution (~9x speedup using multi-threaded execution).
- **Structured 2-Line Search Cards**: Rich search results displaying ratings (`★ 8.5`), genres, sub/dub availability, release year, airing status, and content types (`[TV]`, `[MOVIE]`, `[ONA]`, `[SPECIAL]`).
- **Resolution Control**: Download in your preferred video quality (360p, 720p, 1080p).
- **HLS / M3U8 Downloader**: Automated segment downloading, PNG obfuscation stripping, and FFmpeg MKV remuxing.
- **Subtitle Extraction & Conversion**: Automatic extraction and WebVTT-to-SRT conversion embedded into downloaded MKV files with default and forced subtitle flags.
- **Network Resilience**: Automatic HTTP 429 rate-limit retries, IPv4 socket enforcement, and Cloudflare Turnstile challenge solving.

---

## 📷 Screenshots

Here is the Media Scraper in action:

![Scraper Interface 1](images/1st.png)
![Scraper Interface 2](images/2nd.png)

---

## 📦 Installation

### Prerequisites
- **Python 3.10 – 3.12** *(Python 3.12 is strongly recommended for prebuilt binary wheels on Windows & macOS)*
- **FFmpeg** (installed and available in your system `PATH`)

---

### Global CLI Installation (Recommended)

Install globally from GitHub using `uv tool` (fastest & most reliable) or `pipx`:

#### Option A: Using `uv tool` (Recommended)
```bash
# Linux / macOS / Windows
uv tool install --python 3.12 git+https://github.com/th3mw/CLI_DOWNLOADER.git
```

#### Option B: Using `pipx`
```bash
# Linux / macOS
pipx install --python python3.12 git+https://github.com/th3mw/CLI_DOWNLOADER.git

# Windows (Command Prompt / PowerShell)
pipx install --python py -3.12 git+https://github.com/th3mw/CLI_DOWNLOADER.git
```

#### Option C: Local Development / Editable Install
```bash
git clone https://github.com/th3mw/CLI_DOWNLOADER.git
cd CLI_DOWNLOADER
uv sync --python 3.12
# or: pip install -e .
```

After installation, run `media-scraper` from any terminal directory:
```bash
media-scraper
```

---

### 🪟 Windows Setup & Troubleshooting Guide

If you are running on Windows, keep the following optimizations and tips in mind:

#### 1. 🐍 Python Version & C-Extension Build Errors
- **Issue**: `error: Microsoft Visual C++ 14.0 or greater is required` when installing on Python 3.13+.
- **Solution**: Install using **Python 3.12** (`--python 3.12` or `--python py -3.12`). Python 3.12 provides precompiled binary wheels for Windows, requiring zero compiler tools.
- Alternatively, install [Node.js](https://nodejs.org/) or [Bun](https://bun.sh/) on your system; `media-scraper` will automatically use your native Node/Bun engine for JavaScript decryption.

#### 2. 🎥 FFmpeg Setup on Windows
- FFmpeg is required to remux video streams and subtitles into `.mkv` containers.
- Install easily via Windows Package Manager (`winget`):
  ```powershell
  winget install Gyan.FFmpeg
  ```
  *(Or via Chocolatey: `choco install ffmpeg`)*
- Ensure a new PowerShell window is opened after installing so FFmpeg is detected in your `PATH`.

#### 3. 🛡️ PowerShell Script Execution Policy
- If running `media-scraper` returns `cannot be loaded because running scripts is disabled on this system`:
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  ```

#### 4. 💻 Recommended Terminal
- Use **[Windows Terminal](https://aka.ms/terminal)** (default in Windows 11, available via Microsoft Store on Windows 10) instead of legacy `cmd.exe` for full 24-bit ANSI color and Unicode border rendering.

#### 5. 📁 Long File Paths (Optional)
- Deeply nested series folders may exceed Windows' default 260-character path limit.
- To enable long paths in PowerShell (Run as Administrator):
  ```powershell
  New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
  ```

---

## 🚀 Quick Start

Launch the interactive CLI wizard:
```bash
media-scraper
```
(or run `python scraper.py` locally from the repository folder)

The interactive wizard will guide you through:
1. Selecting **Anime** or **Movies & Shows**
2. Searching for titles
3. Selecting episodes or season ranges
4. Choosing video resolution (360p, 720p, 1080p)
5. Starting parallel episode downloads

---

## 💻 Command Line Interface (CLI) Usage

### Command Line Arguments

```bash
python scraper.py [-h] [-c CONF] [-l LOG_FILE] [-s SERIES_TYPE] [-p PROVIDER]
                  [-n SERIES_NAME] [-S SEASONS] [-e EPISODES] [-r RESOLUTION]
                  [-d] [-dc] [-hsa [0-100]] [-dl]
```

| Flag | Long Option | Description |
|------|-------------|-------------|
| `-h` | `--help` | Display help message and options |
| `-c` | `--conf` | Custom configuration file (default: `config_scraper.yaml`) |
| `-l` | `--log-file` | Custom log file name |
| `-s` | `--series-type` | Content type: `1`/`anime`, `2`/`movies`, `3`/`tv` |
| `-p` | `--provider` | Specific provider client (`nyaa`, `anime_suge`, `anidb`, `kisskh`, `yts`, `oneshows`, `eztv`) |
| `-n` | `--series-name` | Title search query string |
| `-S` | `--seasons` | Season numbers to download (e.g. `1` or `1-3`) |
| `-e` | `--episodes` | Episode numbers to download (e.g. `1-5` or `1,3,5`) |
| `-r` | `--resolution` | Download resolution (`360`, `720`, `1080`, `2160`) |
| `-d` | `--start-download` | Start downloading immediately without prompts |
| `-dc` | `--disable-colors` | Disable ANSI colored output |
| `-q` | `--quiet` | Suppress hero banner and non-essential decoration |
| `--search-only` | | Search and display results without prompting to download |
| `--dry-run` | | Resolve streams and show pre-download inspection without downloading |
| `-tc` | `--torrent-client` | Preferred torrent engine (`aria2`, `system`, `auto`) |
| `-dl` | `--disable-looping` | Disable auto-restart loop after download completes |

### Example CLI Commands

1. **Interactive Mode**:
   ```bash
   media-scraper
   ```

2. **Download Anime Episodes (Continuous Range)**:
   ```bash
   media-scraper -s anime -p anidb -n "Solo Leveling" -e "1-5" -r 1080 -d
   ```

3. **Download Anime via Torrents (Nyaa)**:
   ```bash
   media-scraper -s anime -p nyaa -n "Solo Leveling" -e "1" -r 1080 -d
   ```

4. **Download Movie via Torrents (YTS)**:
   ```bash
   media-scraper -s movies -p yts -n "Inception" -r 1080 -d
   ```

5. **Download TV Show Season Batch (EZTV)**:
   ```bash
   media-scraper -s tv -p eztv -n "Breaking Bad" -S "1" -e "1-7" -r 1080 -d
   ```

---

## 🌐 Supported Providers

| Category | Provider Client | Engine / Type | Key Features |
|----------|-----------------|---------------|--------------|
| **Anime** | `🧲 Nyaa` (`nyaa.si`) | Torrent / `aria2c` | Kitsu API metadata, multi-resolution (1080p, 720p, 480p), Complete Season Batches |
| **Anime** | `AniDB` (`anidb.app`) | HLS Stream | Fast HLS master stream resolution, multi-language audio tracks (`jpn`, `eng`), clean API |
| **Anime** | `AnimeSuge` (`animesuge.cz`) | HLS Stream | 2-Line search cards, multi-domain dynamic embeds, multi-server fallbacks, HLS links |
| **Anime** | `KissKh` (`kisskh.co`) | HLS Stream | Anime-filtered search, episode list fetching, encrypted subtitles |
| **Movies** | `🧲 YTS / YIFY` (`yts.lt`) | Torrent / `aria2c` | IMDb metadata, 720p, 1080p, 2160p (4K), 3D torrent qualities |
| **Movies** | `1Shows` (`1shows.org`) | HTTP / WebAssembly | TMDb movie metadata, WebAssembly decryption, direct high-speed HTTP downloads |
| **Movies** | `KissKh` (`kisskh.co`) | HLS Stream | Asian Drama movies & Hollywood films |
| **TV Shows** | `🧲 EZTV` (`eztvx.to`) | Torrent / `aria2c` | TVMaze metadata, multi-season pagination, Complete Season Batch Packs (`S01 COMPLETE`) |
| **TV Shows** | `1Shows` (`1shows.org`) | HTTP / WebAssembly | TMDb series metadata, season/episode list fetching, WebAssembly decryption, direct HTTP downloads |
| **TV Shows** | `KissKh` (`kisskh.co`) | HLS Stream | Asian Drama series, season breakdowns, encrypted subtitle support |

---

## ⚙️ Configuration

Custom settings are defined in [`config_scraper.yaml`](config_scraper.yaml):

```yaml
DownloaderConfig:
  download_dir: "~/Videos"       # Root download directory
  concurrency_per_file: 6         # Parallel segment download threads
  max_parallel_downloads: 2       # Concurrent episode downloads
  torrent_client: "auto"          # Options: "aria2" (in-terminal), "system" (default desktop app), "auto"

Anime:
  download_dir: "~/Videos/Anime"  # Folder for Anime downloads

Movies:
  download_dir: "~/Videos/Movies" # Folder for Movies downloads

TV Shows:
  download_dir: "~/Videos/Series" # Folder for TV Shows / Series downloads

LoggerConfig:
  log_dir: "logs"
  log_level: "INFO"
  log_retention_days: 7
```

---

## 💡 Subtitle & Media Player Notes

Downloaded video files are saved in the **MKV (`.mkv`)** container with embedded SubRip (`.srt`) soft subtitles.

> [!TIP]
> **Automatic Subtitle Display in VLC & Media Players**:
> Soft subtitles are multiplexed with `FlagDefault=1` and `FlagForced=1` disposition flags.
> - **VLC, MPV, IINA, Plex, Jellyfin**: Automatically activate and display the subtitle track upon playback without requiring manual clicks or hotkeys.
> - **Rich Subtitle Formatting**: MKV natively supports SubRip (`.srt`) styling and fonts without compressing into basic `mov_text`.

---

## 🛠️ Documentation & Changelog

- 📜 **[Version Changelog (`CHANGELOG.md`)](CHANGELOG.md)**: Full release notes for all versions (v1.0.0 through v1.3.0).
- 👉 **[Technical Architecture Documentation (`Doc.md`)](Doc.md)**: Detailed system architecture, provider client implementation mechanics, HLS segment obfuscation stripping algorithms, and complete bug fix history.

---

## 📄 License

This project is licensed under the terms specified in [`LICENSE.md`](LICENSE.md).