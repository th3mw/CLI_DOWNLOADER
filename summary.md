# CLI Downloader - Implementation Summary

## What Was Done

### 1. AnimeSuge Provider Integration

Added a new anime provider `anime_suge` (animesuge.cz) to the scraper alongside `kisskh` and `oneshows`.

**Files Created:**
- `Clients/AnimeSugeClient.py` - New client for AnimeSuge

**Files Modified:**
- `scraper.py` - Added provider registry pattern, `--provider` (`-p`) CLI flag
- `config_scraper.yaml` - Added AnimeSuge provider config section
- `Clients/BaseClient.py` - Added `refererLink` to m3u8 link dicts in `_parse_m3u8_links` and `fetch_m3u8_links`
- `Utils/HLSDownloader.py` - Fixed `_sanitize_segment_name` to handle segments without extensions

### 2. VRF Token Algorithm

Ported the JavaScript VRF token generation algorithm to Python. This is required by AnimeSuge's AJAX endpoints.

**Algorithm:**
1. RC4 cipher with key `"ysJhV6U27FVIjjuk"`
2. Base64 encoding
3. Character code shifting (mod 8 pattern with offsets: -3, +3, -4, +2, -2, +5, +4, +5)
4. Base64 encoding again
5. ROT13 cipher

### 3. Provider Registry Pattern

Implemented a provider registry in `Utils/provider_factory.py`:

```python
CATEGORY_PROVIDERS = {
    'Anime': [
        {'key': 'anime_suge', 'label': 'AnimeSuge', 'class_path': 'Clients.AnimeSugeClient.AnimeSugeClient'},
        {'key': 'kisskh', 'label': 'KissKh (Anime Only)', 'class_path': 'Clients.KissKhClient.KissKhClient'}
    ],
    ...
}
```

CLI usage: `python3 scraper.py -p anime_suge -n "anime name"`

---

## How AnimeSuge Scraper Works

### Overview

AnimeSuge (animesuge.cz) is an anime streaming site that uses vidtube.site as its video CDN. The scraper works by:

1. Searching for anime via the filter page
2. Fetching episode lists via AJAX endpoints (requires VRF token)
3. Fetching server lists for each episode
4. Getting stream URLs from servers
5. Extracting m3u8 links from vidtube embed pages
6. Downloading HLS streams

### Step-by-Step Flow

#### 1. Search (`search` method)

- URL: `https://animesuge.cz/filter?keyword={query}`
- Parses HTML for anime cards containing:
  - `data-tip="{anime_id}"` - numeric ID for API calls
  - `href="/anime/{slug}/ep-{num}"` - anime URL
  - `data-jp="{title}"` - Japanese title
- Returns dict of search results

#### 2. Fetch Episode List (`fetch_episodes_list` method)

- Requires VRF token computed from `anime_id`
- URL: `https://animesuge.cz/ajax/episode/list/{anime_id}?vrf={token}`
- Response is JSON with HTML content
- Parses HTML for episode links containing:
  - `data-id="{data_id}"` - episode data ID
  - `data-slug="{ep_number}"` - episode number
  - `data-sub="{0|1}"` - subtitle available
  - `data-dub="{0|1}"` - dub available
  - `data-ids="{base64_ids}"` - encoded IDs for server list

#### 3. Fetch Server List (`_get_server_list` method)

- URL: `https://animesuge.cz/ajax/server/list?servers={encoded_data_ids}`
- **Critical:** Base64 `+` characters must be URL-encoded as `%2B`
- Response is JSON with HTML containing server elements
- Parses HTML for:
  - `data-type="sub|hsub|dub"` - server type
  - `data-link-id="{link_id}"` - link ID for stream URL

#### 4. Get Stream URL (`_get_stream_url` method)

- URL: `https://animesuge.cz/ajax/server?get={encoded_link_id}`
- **Critical:** Base64 `+` characters must be URL-encoded as `%2B`
- Response is JSON with `result.url` containing vidtube embed URL

#### 5. Get M3U8 from VidTube (`_get_m3u8_from_vidtube` method)

- Fetches vidtube embed page
- Extracts `data-id="{vidtube_id}"` from HTML
- Calls vidtube API: `https://vidtube.site/stream/getSourcesNew?id={vidtube_id}&type={sub|dub}`
- Returns m3u8 URL from `sources.file` in response

#### 6. Parse M3U8 Links (`_parse_m3u8_links` in BaseClient)

- Fetches master m3u8 file
- **Critical:** Referer must be `https://vidtube.site/` (with trailing slash)
- Parses for resolution variants
- Returns dict of resolution → download link

### Key Technical Details

#### VRF Token Generation

The VRF token is required for episode list AJAX calls. The algorithm uses:
- RC4 encryption with a fixed key
- Base64 encoding
- Character shifting in a repeating 8-character pattern
- ROT13 final encoding

#### Referer Requirements

- AnimeSuge AJAX calls: `https://animesuge.cz/anime`
- VidTube m3u8 files: `https://vidtube.site/` (trailing slash required!)
- Without correct referer: 403 Forbidden

#### URL Encoding

Base64-encoded values containing `+` must be URL-encoded as `%2B` when used in URLs. Failure to do this results in incorrect API responses.

### Error Handling

The client handles various error states:
- 403 errors from missing/incorrect referer
- Empty server lists (no sub/dub available)
- Failed stream URL extraction
- Failed m3u8 link extraction

### Configuration

```yaml
Anime:
  download_dir: "/home/themw/Videos/Anime"
  providers:
    anime_suge:
      base_url: "https://animesuge.cz"
      search_url: "/filter"
      preferred_server_types:
        - sub
        - hsub
        - dub
```

### CLI Arguments

```
-p anime_suge          # Provider selection
-n "search term"       # Search keyword
-s 1                   # Series type (1=Anime)
-r 720                 # Resolution
-e 1-6                 # Episode range
-d                     # Start download immediately
```

### Dependencies

- `requests` - HTTP client
- `beautifulsoup4` - HTML parsing (imported as needed)
- `PyCryptodome` - For other clients (not used by AnimeSuge)
- `undetected-chromedriver` - For other clients (not used by AnimeSuge)

---

## Known Issues

1. **Segment Extensions:** Some vidtube segments don't have `.ts` extension. Fixed in `_sanitize_segment_name` to add extension when missing.

2. **M3U8 Referer:** The vidtube CDN requires exact referer `https://vidtube.site/` (with trailing slash) or returns 403.

3. **Server Parsing:** The server HTML structure requires careful regex matching due to nested div elements.

---

## Testing

Basic test command:
```bash
python3 scraper.py -s 1 -n "Jobless" -r 720 -d -p anime_suge
```

With episode selection:
```bash
python3 scraper.py -s 1 -n "Jobless" -r 360 -e 1-1 -d -p anime_suge
```
