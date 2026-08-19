# Media Scraper - Technical Documentation

Comprehensive architecture, provider implementation details, downloader mechanics, and technical changelog for the Media Scraper codebase.

---

## 1. System Architecture

The Media Scraper is designed around a modular, object-oriented architecture separating CLI orchestration, provider-specific web scraping, network resilience, and media downloading/remuxing engines.

```mermaid
flowchart TD
    CLI[scraper.py - CLI & UI Loop] --> Factory[provider_factory.py]
    Factory --> ClientChoice{Category & Provider Selection}
    ClientChoice -->|Anime| AniDb[AniDbClient]
    ClientChoice -->|Anime| AnimeSuge[AnimeSugeClient]
    ClientChoice -->|Anime / Drama| KissKh[KissKhClient]
    ClientChoice -->|Movies / TV| OneShows[OneShowsClient]
    
    AniDb --> BaseClient[BaseClient]
    AnimeSuge --> BaseClient
    KissKh --> BaseClient
    OneShows --> BaseClient

    CLI --> DownloaderChoice{Download Type}
    DownloaderChoice -->|Direct HTTP Chunks| BaseDownloader[BaseDownloader]
    DownloaderChoice -->|HLS / M3U8 Streams| HLSDownloader[HLSDownloader]
    
    HLSDownloader --> BaseDownloader
    HLSDownloader --> FFmpeg[FFmpeg Muxer Engine]
    BaseDownloader --> FFmpeg
```

### Core Directory Layout
- **`scraper.py`**: CLI entry point, argument parsing (`argparse`), interactive prompts, menu loops, and batch downloader dispatching.
- **`Clients/`**: Provider implementations inheriting from `BaseClient`.
  - [`BaseClient.py`](file:///home/th3mw/DEV/CLI_DOWNLOADER/Clients/BaseClient.py): Abstract base class, HTTP request wrapper with session pooling, parallel link fetching manager, search results display formatter.
  - [`AniDbClient.py`](file:///home/th3mw/DEV/CLI_DOWNLOADER/Clients/AniDbClient.py): AniDB provider scraper (`anidb.app`).
  - [`AnimeSugeClient.py`](file:///home/th3mw/DEV/CLI_DOWNLOADER/Clients/AnimeSugeClient.py): AnimeSuge provider scraper (`animesuge.cz`).
  - [`KissKhClient.py`](file:///home/th3mw/DEV/CLI_DOWNLOADER/Clients/KissKhClient.py): KissKh provider scraper (Anime, Asian Drama, Movies & TV Shows).
  - [`OneShowsClient.py`](file:///home/th3mw/DEV/CLI_DOWNLOADER/Clients/OneShowsClient.py): 1Shows provider scraper (Movies & TV Shows with WASM decryption).
- **`Utils/`**: Downloader and shared utility modules.
  - [`provider_factory.py`](file:///home/th3mw/DEV/CLI_DOWNLOADER/Utils/provider_factory.py): Dynamic provider registry and factory instantiation.
  - [`BaseDownloader.py`](file:///home/th3mw/DEV/CLI_DOWNLOADER/Utils/BaseDownloader.py): Direct MP4 downloader, multi-threaded chunk pool (4MiB chunks), subtitle downloader & converter.
  - [`HLSDownloader.py`](file:///home/th3mw/DEV/CLI_DOWNLOADER/Utils/HLSDownloader.py): HLS `.m3u8` playlist parser, obfuscated TS segment header stripper, local m3u8 playlist rewriter, FFmpeg remuxing engine.
  - [`commons.py`](file:///home/th3mw/DEV/CLI_DOWNLOADER/Utils/commons.py): Retry decorators, multi-engine JS runtime runner (`exec_js`), subprocess execution, terminal coloring utilities.

---

## 2. Provider Implementations & Mechanics

### AniDB Client (`Clients/AniDbClient.py`)
- **API & Browse Scraping**: Scrapes search cards from `/browse?q={query}` (with fallback to `/search/suggestions?q=`), parsing anime title, type (`[TV]`, `[MOVIE]`, `[SPECIAL]`), rating, and slug IDs.
- **Frontend REST APIs**: Directly queries `/api/frontend/anime/{id}/episodes` to retrieve full episode lists and `/api/frontend/episode/{id}/languages` to resolve multi-language audio streams (`jpn`, `eng`, `kor`).
- **HLS Stream Parsing**: Extracts JWPlayer `master.m3u8` streams and parses multi-bitrate resolution tiers (`1080p`, `720p`, `360p`).
- **Segment Sanitization**: Downloads `.xls` MPEG-TS segments and sanitizes extensions to `.ts` for FFmpeg remuxing.

### AnimeSuge Client (`Clients/AnimeSugeClient.py`)
- **VRF Token Algorithm**: Implements a 5-stage verification token generator required by AnimeSuge AJAX endpoints:
  1. RC4 cipher with key `"ysJhV6U27FVIjjuk"`
  2. Base64 encoding
  3. Character shifting in a repeating mod 8 pattern (`-3, +3, -4, +2, -2, +5, +4, +5`)
  4. Base64 encoding
  5. ROT13 cipher
- **Search & Card Formatting**: Scrapes HTML search results and concurrently queries `/ajax/anime/tooltip/{id}` using `ThreadPoolExecutor` to extract status (`Finished Airing` / `Currently Airing`), release year, content type (`[TV]`, `[MOVIE]`, `[ONA]`), and sub/dub episode breakdowns (`24 (Sub: 24, Dub: 12)`). Formats results into structured 2-line cards matching KissKh display styles.
- **VidTube Embed Scraper**: Parses iframe embeds (`https://vidtube.site/e/{id}`), calls `getSourcesNew`, extracts quality `.m3u8` playlists, and parses `tracks` JSON arrays for WebVTT (`.vtt`) subtitle tracks.
- **Concurrent Link Resolution**: Uses `ThreadPoolExecutor(max_workers=min(10, len(selected_eps)))` to resolve episode links in parallel, reducing fetch times by ~9x.

### KissKh Client (`Clients/KissKhClient.py`)
- **API Endpoints**: Communicates directly with KissKh JSON REST APIs (`/api/DramaList/Search`, `/api/DramaList/Drama`, `/api/DramaList/Episode`).
- **Dynamic JavaScript Token Generation**: Employs `exec_js` from `Utils.commons` to execute `common.js` and evaluate `_0x54b991` for `kkey` generation across available JS runtimes (`bun`, `node`, `deno`, or `quickjs`).
- **Encrypted Subtitles & Video Payloads**: Decrypts AES-encrypted subtitle payloads (`.txt` / `.txt1`) and video streams using custom AES-CBC key/IV pairs.
- **Null Safety & Resilience**: Implements `None` guards around search/series responses to prevent crashes during API rate limiting or temporary outages.

### OneShows Client (`Clients/OneShowsClient.py`)
- **TMDb Search API**: Direct querying of TMDb endpoints (`/api/search/query`, `/api/tv/`) for high-fidelity movie and TV series metadata.
- **WebAssembly Payload Decryption**: Downloads `makimaDL-manifest.json` and `makimaDL.wasm`, decrypting AES-GCM stream payloads via the JS runtime runner (`exec_js`).
- **Variety Selection & Mirror Resolution**: Presents available download varieties (Source + Resolution + Size) and resolves intermediate mirrors (PixelDrain, GoodStream) into direct download links.

---

## 3. Downloader Engine & Network Resilience

### HLS Downloader (`Utils/HLSDownloader.py`)
1. **Segment Renaming (`_sanitize_segment_name`)**: CDNs frequently serve HLS video segments with misleading extensions (`.png`, `.jpg`) or without extensions. The downloader renames all non-media extensions to `.ts` so FFmpeg's HLS demuxer accepts them without throwing `not in allowed_segment_extensions` errors.
2. **Obfuscation Stripping (`_strip_png_header`)**: Certain CDNs (e.g. VidTube) prepend fake 8-byte PNG headers (`0x89PNG\r\n\x1a\n`) to MPEG-TS streams. The downloader scans for the first 188-byte aligned TS sync byte (`0x47`) and strips the leading fake header bytes before writing segment files.
3. **Local Playlist Rewriting (`_rewrite_m3u8_file`)**: Rewrites the `.m3u8` playlist file to reference local downloaded `.ts` segment files and encryption keys.
4. **FFmpeg Remuxing (`_convert_to_mp4`)**: Executes FFmpeg with `-y` (overwrite), `-allowed_extensions ALL`, stream mapping (`-map 0:v -map 0:a -map {i}`), ISO 639-2 language tags (`-metadata:s:{stream_idx} language=eng`), and disposition flags (`-disposition:{stream_idx} default+forced`).

### Network & Transport Layer
- **IPv4 Socket Enforcement**: `urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET` forces IPv4 to avoid IPv6 connection drops on Linux.
- **Encoding Headers**: Standardized `Accept-Encoding: gzip, deflate` across HTTP sessions to prevent unhandled raw Brotli compression payloads.
- **Rate Limit Backoff**: `@retry()` decorator in `BaseClient._send_request()` handles HTTP 429 rate limit responses with exponential backoff (`time.sleep(2)`).
- **Multi-Engine JS Runner**: `exec_js()` automatically detects CLI runtimes (`bun`, `node`, `deno`, `qjs`) or falls back to the embedded `quickjs` Python module.

---

## 4. Subtitle Subsystem & MKV Auto-Activation

### VTT to SRT Conversion (`Utils/BaseDownloader.py`)
When subtitle tracks are downloaded in WebVTT (`.vtt`) format, `_download_subtitles()` automatically converts them to SubRip (`.srt`) format using FFmpeg:
```bash
ffmpeg -y -loglevel warning -i "sub_file.vtt" "sub_file.srt"
```

### MKV Subtitle Multiplexing (`FlagDefault` & `FlagForced`)
- **Default Container (`.mkv`)**: All downloaded video files with soft subtitles are packaged as Matroska (`.mkv`) files.
- **Native SubRip Encoding (`-c:s srt`)**: Subtitles are stored in native SubRip format rather than being compressed to MP4's limited `mov_text`.
- **Automatic Display in VLC & Media Players**: FFmpeg applies `-disposition:s:{idx} default+forced` which writes Matroska `FlagDefault=1` and `FlagForced=1` header flags.
- **Player Compatibility**: VLC, MPV, IINA, Celluloid, Kodi, Plex, and Jellyfin immediately auto-render the subtitle track on startup without requiring manual track selection or hotkey presses.

---

## 5. Technical Changelog & Historical Bug Fixes

| Issue | Commit / File | Summary & Fix |
|-------|---------------|---------------|
| **1Shows Movie WASM Decryption & Auto-Selection** | `Clients/OneShowsClient.py`, `Clients/BaseClient.py`, `scraper.py` | Fixed WASM bytes download in payload decryption, formatted variety selection menu in Unicode cards, and auto-selected single movies without redundant episode range prompts. |
| **`KissKhClient` `get_season_ep_ranges` Missing Attribute** | `Clients/BaseClient.py` | Implemented `get_season_ep_ranges` on `BaseClient` so all providers inherit season/episode extraction. |
| **Purged Duplicate Raw Search Output** | `AniDbClient.py`, `AnimeSugeClient.py`, `KissKhClient.py`, `OneShowsClient.py` | Removed raw `_colprint` in client `search()` methods so only the formatted Unicode card is rendered. |
| **Terminal Margin Indentation & Breathing Room** | `Utils/commons.py`, `scraper.py`, `BaseDownloader.py` | Added 2-space left margin to cards (`render_box`), user prompts, and live progress bars so UI isn't glued to the terminal edge. |
| **Download List Progress Bar Overlapping Fix** | `scraper.py`, `Utils/BaseDownloader.py` | Enabled clean sequential episode downloading with per-episode progress bars, line clearing (`\033[K`), and discrete completion receipts. |
| **Modern CLI & Interactive UI Overhaul** | `scraper.py`, `Utils/commons.py`, `Utils/BaseDownloader.py` | Complete visual overhaul with `render_box` Unicode cards, smooth gradient progress bars (`━╸─`), `--search-only`, `--dry-run`, `-q`, and `--no-color`. |
| **Provider Menu `0. Back` Navigation** | `scraper.py` | Added `0. Back` navigation across all provider menus to easily return to content type selection. |
| **Auto-Skip Existing Episodes** | `scraper.py` | Detects completed files (>1MB) in target output directory and skips re-downloading them. |
| **`episodes` Undefined Variable Fix** | `scraper.py` | Passed `episodes` into `get_ep_range_multiple` and restricted multi-season prompts to TV Shows with >1 seasons. |
| **English Subtitle Default Priority** | `HLSDownloader.py`, `BaseDownloader.py` | Sorted subtitle tracks so English is always stream 0 with `default+forced` flags. |
| **Incomplete Download Cache Resumption** | `HLSDownloader.py`, `BaseDownloader.py` | Detected cached segments on startup and seamlessly resumed remaining segments without duplicating cache. |
| **HLS Query Params & Extension Rejection Fix** | `Utils/HLSDownloader.py` | Upgraded `_sanitize_segment_name` to strip query strings (`.jpg?mod=1`) and rewritten playlists to enforce `.ts` segments for FFmpeg. |
| **AniDB `show_episode_results` Signature Fix** | `Clients/AniDbClient.py` | Added `*predefined_range` variadic argument support to `show_episode_results` matching `scraper.py` dispatcher. |
| **MKV Container with Forced Subtitles** | `BaseClient.py`, `HLSDownloader.py`, `BaseDownloader.py` | Transitioned output container to MKV (`.mkv`) with SubRip (`srt`) and `default+forced` flags for auto-activation in VLC. |
| **AniDB Provider Integration** | `Clients/AniDbClient.py`, `Utils/provider_factory.py` | Added AniDB (`anidb.app`) provider client with multi-language HLS streams and `.xls` segment sanitization. |
| **AnimeSuge Embed 404 Fix** | `Clients/AnimeSugeClient.py` | Added dynamic domain origin extraction (`getSourcesNew` / `getSources`) and multi-server fallback. |
| **`tqdm` Missing Module Fallback** | `Utils/BaseDownloader.py` | Added lightweight self-contained progress bar fallback when `tqdm` is not installed. |
| **`NoneType` block_size Crash** | `Clients/BaseClient.py` | Added safe fallback `self.bs = AES.block_size if AES is not None else 16` and AES availability guards. |
| **`quickjs` Import Failure** | `Clients/KissKhClient.py`, `Utils/commons.py` | Built universal `exec_js` runner with auto-detection for `bun`, `node`, `deno`, and optional `quickjs`. |
| **WASM Decryption in 1Shows** | `Clients/OneShowsClient.py` | Integrated `exec_js` for WASM decryption supporting Bun/Node/Deno runtimes. |
| **Purged AnimePahe Provider** | Full Repository | Removed AnimePahe client, pycache, and documentation remnants. |
| **`resolution_size` KeyError** | `Clients/BaseClient.py` | Added safe `.get('resolution_size', 'NA')` fallbacks. |
| **`downloadLink` KeyError** | `Clients/KissKhClient.py` | Standardized resolution dict keys to `downloadLink` and `downloadType`. |
| **FFmpeg PNG Segment Rejection** | `Utils/HLSDownloader.py` | Implemented `_sanitize_segment_name()` to map misleading `.png` extensions to `.ts`. |
| **Fake PNG Header Obfuscation** | `Utils/HLSDownloader.py` | Implemented `_strip_png_header()` to locate `0x47` sync bytes and strip PNG headers. |
| **Non-Interactive TTY Error** | `scraper.py` | Added `try/except` around `os.get_terminal_size()` with fallback width `80`. |
| **KissKh 429 Rate Limit Crash** | `Clients/BaseClient.py`, `KissKhClient.py` | Fixed `Accept-Encoding`, enforced IPv4 sockets, added 429 retry backoff and null response guards. |
| **AnimeSuge Structured 2-Line Cards** | `Clients/AnimeSugeClient.py` | Extracted status, year, sub/dub counts, and formatted 2-line UI cards. |
| **Parallel Link Fetching** | `AnimeSugeClient.py`, `KissKhClient.py`, `OneShowsClient.py` | Added `ThreadPoolExecutor` concurrent link resolution (~9x speedup). |
| **VTT to SRT Conversion** | `Utils/BaseDownloader.py` | Added automatic VTT -> SRT conversion prior to MP4 remuxing. |
