# Changelog & Fixes Documentation

## Overview

This document records all fixes applied to the Media Scraper based on error logs from `@err.txt`.

---

## Fix 1: AnimePahe Domain Update
**Commit:** `8ee2f80`
**File:** `Clients/AnimePaheClient.py:11`

- Changed default `base_url` from `https://animepahe.ru/` to `https://animepahe.pw/`
- AnimePahe migrated to the new `.pw` domain; the old domain was returning Cloudflare blocks or no response.

---

## Fix 2: `request_timeout` KeyError (Anime Selection)
**Commit:** `8ee2f80`
**File:** `Clients/AnimePaheClient.py:19`

**Error in logs:**
```
Error occurred: 'request_timeout'. Check log for more details.
```

**Root cause:** `AnimePaheClient.__init__` accessed `config['request_timeout']` directly, which crashed with a `KeyError` when the configuration YAML did not include a `request_timeout` key. Other clients (e.g., `KissKhClient`) already used `config.get(...)` with a default.

**Fix:** Changed to `config.get('request_timeout', 30)` for a safe default of 30 seconds.

---

## Fix 3: `resolution_size` KeyError (Episode Display)
**Commit:** `8ee2f80`
**File:** `Clients/BaseClient.py:517`

**Error in logs:**
```
Error occurred: 'resolution_size'. Check log for more details.
```

**Root cause:** `BaseClient._show_episode_links` accessed `_vals["resolution_size"]` directly. `KissKhClient.fetch_episode_links` was producing resolution dicts that did not include a `resolution_size` key, causing a `KeyError` when displaying episode links.

**Fix:** Changed to `_vals.get("resolution_size", "NA")` for a safe fallback. Also updated `KissKhClient` to include `resolution_size` in its generated dicts for better display output.

---

## Fix 4: `downloadLink` KeyError (KissKhClient Resolution Data)
**Commit:** `8ee2f80`
**File:** `Clients/KissKhClient.py:238,242`

**Error in logs:**
```
Episode: 06 | 720P | Failed to fetch link with error ['downloadLink']
```

**Root cause:** `KissKhClient.fetch_episode_links` constructed resolution dicts with keys `file` and `type`, but `BaseClient.fetch_m3u8_links` (inherited by KissKhClient) expects keys `downloadLink` and `downloadType`. This mismatch caused a `KeyError('downloadLink')` when fetching m3u8 download links.

**Fix:** Updated `KissKhClient` dict keys to `downloadLink`, `downloadType`, and added `resolution_size` for consistent display.

**Before:**
```python
m3u8_links[quality] = {'file': quality_link, 'type': '...'}
m3u8_links = {'720': {'file': link, 'type': link_type}}
```

**After:**
```python
m3u8_links[quality] = {'downloadLink': quality_link, 'downloadType': '...', 'resolution_size': f'{quality}x0'}
m3u8_links = {'720': {'downloadLink': link, 'downloadType': link_type, 'resolution_size': '1280x720'}}
```

---

## Fix 5: Cloudflare Turnstile Challenge Handling
**Commit:** `8ee2f80`
**File:** `Clients/AnimePaheClient.py`

**Error in logs:**
```
Message: session not created: cannot connect to chrome at 127.0.0.1:52671
from session not created: This version of ChromeDriver only supports Chrome version 151
Current browser version is 150.0.7871.186
```

**Root cause:** AnimePahe now uses Cloudflare Turnstile (interactive CAPTCHA) for bot protection. The existing code used `undetected-chromedriver` to bypass basic detection but did not handle interactive Turnstile challenges.

**Fix — 3 components:**

### 5a. `_is_cloudflare_blocked` (new method)
Detects Cloudflare/Turnstile challenge responses by checking for indicators:
- `'Checking your browser'`
- `'cf-challenge'`
- `'turnstile'`
- `'Just a moment'`
- `'JavaScript is required'`
- `'__cf_duel'`

### 5b. `_get_site_cookies` (updated)
Cookie validation now:
1. Fetches the response as text (not just checking if non-empty)
2. Passes through `_is_cloudflare_blocked` to detect fake "success" responses where a CF challenge page returns HTTP 200
3. Falls through to new cookie acquisition if blocked

### 5c. `_get_new_cookies` (updated)
After page load:
1. Scans for Turnstile/Cloudflare iframes
2. Attempts to click the `cf-turnstile` widget
3. Waits for resolution (default 15 seconds)
4. Checks for `cf_clearance` cookie to verify successful challenge completion

> **Note:** The ChromeDriver/Chrome version mismatch (`v151 driver` vs `v150 browser`) is an environment issue. Users must update Chrome to v151+ or install a matching ChromeDriver.

---

## Fix 6: FFmpeg PNG Segment Rejection
**Commit:** `7d21324`
**File:** `Utils/HLSDownloader.py`

**Error in logs:**
```
URL .../639212812880698874.PNG is not in allowed_segment_extensions
Error opening input file .../uwu.m3u8
```

**Root cause:** The CDN serves HLS video segments with `.PNG` extensions — these are NOT real images, just segment files with misleading extensions. FFmpeg rejects them because `.PNG` is not in its `allowed_segment_extensions` list, even with `-allowed_extensions ALL`.

An initial fix filtered out non-media extensions, but this was too aggressive — **all** segments had `.PNG` extensions, resulting in empty playlists and a secondary "Empty segment" error.

**Fix — Rename, Don't Filter:**

### 6a. Added `_sanitize_segment_name()` helper
```python
NON_MEDIA_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.svg', '.ico'}

def _sanitize_segment_name(filename):
    name, ext = os.path.splitext(filename)
    if ext.lower() in NON_MEDIA_EXTENSIONS:
        return name + '.ts'
    return filename
```

### 6b. `_collect_ts_urls` — Collect all segments
Reverted to collecting all non-comment URLs (no filtering).

### 6c. `_download_segment` — Save with sanitized name
Segments are saved locally with `.ts` extension instead of `.png`.

### 6d. `_rewrite_m3u8_file` — Rewrite references with `.ts`
When rewriting the m3u8 with local paths, all non-media extensions are renamed to `.ts`, keeping the download file and m3u8 reference synchronized.

---

## Fix 7: Terminal Size Error in Non-Interactive Mode
**Commit:** `TBD`
**File:** `scraper.py:264`

**Error in logs:**
```
Error occurred: [Errno 25] Inappropriate ioctl for device
File "/home/themw/DEV/CLI_DOWNLOADER/scraper.py", line 264, in batch_downloader
    width = os.get_terminal_size().columns
OSError: [Errno 25] Inappropriate ioctl for device
```

**Root cause:** When stdin is piped (non-interactive mode), `os.get_terminal_size()` raises `OSError` because there's no TTY.

**Fix:** Wrap in try/except with a default fallback:
```python
try:
    width = os.get_terminal_size().columns
except OSError:
    width = 80
```

---

## Fix 8: Double `communicate()` Call in subprocess Wrapper
**Commit:** `TBD`
**File:** `Utils/commons.py:47`

**Root cause:** `exec_os_cmd` called `proc.communicate()` twice — the second call returns `(None, None)` after pipes are exhausted, causing `AttributeError` or `OSError` when `.decode()` is called on `None`.

**Fix:**
- Single `communicate()` call: `stdout, stderr = proc.communicate()`
- Added `stdin=DEVNULL` to prevent FFmpeg/TTY ioctl errors from inherited stdin

---

## Summary Table

| Issue | Commit | File(s) | Error Type |
|-------|--------|---------|------------|
| AnimePahe domain outdated | `8ee2f80` | `AnimePaheClient.py` | Site unreachable |
| `request_timeout` KeyError | `8ee2f80` | `AnimePaheClient.py` | Missing config key |
| `resolution_size` KeyError | `8ee2f80` | `BaseClient.py` | Missing dict key |
| `downloadLink` KeyError | `8ee2f80` | `KissKhClient.py` | Wrong dict keys |
| Cloudflare Turnstile block | `8ee2f80` | `AnimePaheClient.py` | Cloudflare protection |
| FFmpeg PNG segment rejection | `7d21324` | `HLSDownloader.py` | Invalid HLS segment |
| `os.get_terminal_size()` in non-interactive mode | `TBD` | `scraper.py` | TTY ioctl error |
| Double `communicate()` call | `TBD` | `commons.py` | Subprocess pipe error |
