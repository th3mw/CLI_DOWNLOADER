# Changelog

All notable changes to the **Media Scraper & Downloader** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [v2.0.0] - Planned Milestone (Interactive TUI Dashboard)

### 🎯 Planned Features
- **Full Textual Terminal User Interface (TUI)**:
  - Multi-screen dashboard with split-pane layout, mouse & keyboard navigation (`Vim` keys / arrow keys).
  - **Live Search & Catalog Browser**: Real-time debounced fuzzy search results with metadata drawers and genre badges.
  - **Interactive Episode Picker**: Visual multi-select checkboxes with one-key batch toggling (`Space` to select, `A` for All).
  - **Live Download Center**: Animated progress gauges, real-time speed charts, and active queue management (Pause / Resume / Cancel).
  - **Dual Execution Modes**: Launch full TUI with `media-scraper --tui` while retaining zero-dependency headless CLI mode for automated scripts.

## [v1.5.0] - 2026-08-25

### 🚀 Added
- **Hanime.tv NSFW Provider (`HanimeClient`)**:
  - Reverse-engineered Hanime API v11 cryptographic handshake protocol with AES-256-GCM token encryption and WASM signature generation.
  - Lightning-fast in-memory fuzzy search across Hanime's complete 3,500+ title catalog with studio branding, release year, like counts, and view metrics.
  - Direct HLS master stream resolution with multi-resolution selection (1080p, 720p, 480p, 360p).
  - Registered as `[4] 🔞 NSFW / Hentai` in category selector.
- **Audio Preference System (Sub & Dub Options)**:
  - Added `-a / --audio {sub, dub, dual, all}` CLI option and `AudioPreference.default_audio` configuration setting.
  - Automatically prioritizes English Dubbed audio tracks and servers on `AnimeSugeClient`, `AniDbClient`, `KissKhClient`, and `NyaaClient` when `dub` is selected.
- **SQLite Download History & Incomplete Resumption Manager (`history_manager.py`)**:
  - Embedded zero-dependency SQLite task ledger (`~/.config/media-scraper/history.db`).
  - Added CLI inspection flags: `--history` (`-H`), `--incomplete` (`-I`), and `--clear-history`.
  - Added interactive `[5] 📜 Download History & Task Manager` in the Main Menu with one-key resume for interrupted downloads.
- **Hardware-Accelerated Video Compression (`compressor.py`)**:
  - Integrated post-download video compression using high-efficiency HEVC/AV1 encoding.
  - Auto-detects GPU hardware acceleration (`hevc_nvenc`, `hevc_vaapi`, `hevc_qsv`, `hevc_amf`) with seamless CPU fallback (`libx265`).
  - Re-encodes video streams with perceptual losslessness (CRF 23) while preserving all audio and subtitle streams intact, reducing file sizes by 50–70%.
  - Configurable via `--compress` (`-cmp`) CLI flag or `PostProcessing.auto_compress` in `config_scraper.yaml`.
- **Automatic Config Version Migration**:
  - Auto-detects outdated `config_scraper.yaml` versions (<1.5.0) and upgrades them seamlessly upon first launch while preserving all user custom directory paths and settings.
- **Standardized Search Badges & Provider Branding**:
  - Search result cards across all providers now render clean, standardized badges (`[TV Series]`, `[Movie]`, `[OVA]`, `[Special]`, `[NSFW]`, episode counts, dub/sub availability, ratings, and release year).
  - Fixed breadcrumb navigation to accurately reflect active provider name (e.g. `📍 Location: Anime › Nyaa › Solo Leveling › Select Episodes`).

---

## [v1.4.0] - 2026-08-21

### 🚀 Added
- **Single-Screen Step-by-Step Clean UX**:
  - Implemented `clear_screen` and `render_step_header` to clear the terminal between interactive steps while keeping the top Hero Header persistent.
  - Added dynamic breadcrumb navigation trails (e.g. `📍 Location: Anime › Nyaa › Solo Leveling › Select Episodes`).
- **Standardized Media Library File Naming**:
  - Automated Plex/Jellyfin/Kodi compliant naming: `{Series Title} - S{season:02d} - E{episode:02d}.mkv` across all Anime, TV Shows, and Movie providers.
  - Handled multi-part episodes (`- E01-E02.mkv`) and movie releases (`{Movie Title}.mkv`).
- **Numbered Resolution Selection & Robust Validation**:
  - Rendered clean numbered choices (`[1] 1080P • Full HD (Recommended) [default]`, `[2] 720P`, etc.) in the `AVAILABLE RESOLUTIONS` card.
  - Supported selecting by index number (`1`, `2`, `3`), by typing resolution string (`1080`, `720p`, `360`), or by pressing Enter for default.
  - Added robust input validation re-prompting with contextual error messages upon invalid user entries.
- **In-Place Concurrent Progress Dashboard**:
  - Eliminated loose pre-download printing tags (`➜ Downloading: ...`) outside the progress manager.
  - Multi-slot progress bars now manage their lines completely in place with dedicated episode descriptors (`S01-E01`, `S01-E02`).

### ⚡ Performance
- **Instant Resolution Discovery & Streamlined Link Resolution**:
  - Decoupled resolution probing from whole-queue episode link resolution: Interactive sessions now probe available resolutions using only 1 sample episode in <1s (or bypass probing instantly when predefined via `-r`), eliminating the 30–60s freeze on large episode queues.
  - Optimized `AnimeSugeClient` to terminate server probing immediately upon receiving working master playlist qualities from the primary server.
  - Scaled parallel worker pools and added direct fallback queries in `NyaaClient` and `AniDbClient`.

### 🛠️ Changed
- **Direct Episode Selection Workflow**:
  - Completely eliminated the redundant intermediate `Enter episodes range to display (ex: 1-16)` prompt for series with many episodes (>24).
  - Replaced with a concise `AVAILABLE EPISODES` overview box and an immediate prompt for the episodes to download in a single step.

### 🐛 Fixed
- **KissKh Provider v1.4 Modernization**: Updated `KissKhClient` across Anime, Movies, and TV Series to return proper `(series_dir, episode_prefix)` tuples in `set_out_names`, format standardized `{Series Title} - S01 - E01 - {res}P.mkv` filenames, support dictionary episode range filtering, and wrap individual episode requests in error-containment blocks.
- **AnimeSuge HTTP 429 Rate Limit Crash**: Implemented progressive backoff, adaptive server `Retry-After` header parsing, silent error suppression for optional mirror probes, and controlled concurrency to eliminate HTTP 429 crashes during batch episode link resolution.
- **Missing `re` Module Import in `BaseDownloader`**: Resolved `NameError` in `_get_display_prefix` when parsing standardized episode tokens.
- **Global `max_parallel_downloads` Scope in Downloader**: Added defensive retrieval of `max_parallel_downloads` from download configuration inside worker routines.

---

## [v1.3.0] - 2026-08-20

### 🚀 Added
- **Modern Unicode UI Engine**:
  - Hero header banners and clean bordered container cards (`render_box`) for search results, menus, and pre-download inspection receipts.
  - Multi-line, non-overlapping concurrent download dashboard using dynamic ANSI vertical cursor positioning (`\033[NA`).
  - High-precision gradient progress bars (`━╸─`) displaying speed, ETA, segment/chunk completion, and cache ratios (`[R:X F:Y]`).
  - Standardized `🧲` magnet icon across all torrent providers (`Nyaa`, `YTS`, `EZTV`).
- **Nyaa Anime Torrent Provider (`NyaaClient`)**:
  - Integrated Kitsu API metadata with multi-mirror Nyaa RSS feed parsers (`nyaa.si`, `nyaa.land`, `nyaa.net`).
  - Multi-resolution quality aggregation (1080p, 720p, 480p) with complete batch/season pack detection.
- **EZTV TV Shows Torrent Provider (`EZTVClient`)**:
  - Integrated TVMaze API metadata with EZTV and Apibay multi-mirror indexers.
  - Complete season batch detection (`S01 COMPLETE 1080p/720p`) and selective episode unchecking/cherry-picking (e.g. `1,3,5` or `1-4,7`).
- **Autonomous `aria2c` Provisioning & Torrent Dispatcher**:
  - Zero-friction automated static binary provisioning for Linux and Windows.
  - User-configurable `torrent_client` modes (`aria2`, `system`, `auto`) with desktop client dispatching via `xdg-open` / `os.startfile` / `open`.

### 🐛 Fixed
- **Multi-Episode Parallel Progress Overlap**: Fixed concurrent download threads overwriting the same line by implementing an active bar registry and multi-slot ANSI cursor manager.
- **Self-Deadlock on 100% Download Completion**: Replaced non-reentrant `threading.Lock()` with `threading.RLock()` in `ProgressBar`, resolving thread hangs during `__exit__` cleanup.
- **FFmpeg Subprocess Hangs**: Added `-nostdin` flag to all FFmpeg muxing commands and 300s timeout protection in `exec_os_cmd`.
- **HTTP Connection Pool Discards**: Configured `requests.adapters.HTTPAdapter(pool_connections=64, pool_maxsize=64)` to handle high-concurrency requests without dropped connections.
- **Missing `ProgressBar` Import in Provisioner**: Corrected `ProgressBar` import path in `aria2_provisioner.py`.

---

## [v1.2.0] - 2026-08-19

### 🚀 Added
- **Domain-Driven Content Architecture & Provider Factory**:
  - Refactored monolith into modular domain packages (`Content/Anime`, `Content/Movies`, `Content/Series`, `Core/`).
  - Extensible `ProviderFactory` supporting dynamic registration of content providers and download engines.
  - Unified `TorrentDownloader` bridging magnet links to `aria2c` or native desktop clients.
- **CLI Ergonomics & Inspection Modes**:
  - Added `--dry-run` flag to resolve stream manifests and inspect metadata without writing video files to disk.
  - Added `--search-only` flag for instant query inspection.
  - Added `--quiet` (`-q`) and `--no-color` (`-dc`) flags for scripted environments.
  - Added interactive first-launch setup wizard for `config_scraper.yaml`.
- **Download Resumption & Caching**:
  - Automatic segment and chunk caching in isolated per-episode temporary folders with automatic directory cleanup.

### 🛠️ Changed
- Reorganized provider modules into dedicated subpackages with distinct client and downloader classes.
- Enhanced subtitle processing to automatically prioritize and extract English tracks as default forced tracks.

---

## [v1.1.0] - 2026-08-18

### 🚀 Added
- **Movies Content Domain & Streaming Providers**:
  - Added OneShows movie search and HLS/MP4 extraction.
  - Added YTS / YIFY torrent integration for movies with 720p, 1080p, 2160p (4K), and 3D resolution selection.
- **Multi-Resolution Aggregation**:
  - Unified multi-resolution selector allowing users to choose stream quality per title.

### 🛠️ Changed
- Extended configuration schema to support separate root download directories for movies and TV series.

---

## [v1.0.0] - 2026-08-04

### 🚀 Added
- **Initial Release of Media Scraper CLI**:
  - Anime and Asian Dramas / Korean TV series search and downloading.
  - Supported initial providers: **KissKH**, **AnimeSuge**, and **AniDB**.
  - Multi-threaded HLS segment downloading with AES-128 decryption.
  - WebVTT subtitle extraction and conversion to SubRip (SRT).
  - Automated FFmpeg audio/video remuxing into MKV/MP4 containers.
