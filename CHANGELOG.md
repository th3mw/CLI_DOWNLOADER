# Changelog

All notable changes to the **Media Scraper & Downloader** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
