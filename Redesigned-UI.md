# 🎨 CLI & Interactive UI Redesign Specification (`Redesigned-UI.md`)

> **Objective**: Modernize and unify the CLI and Interactive User Experience for the Media Scraper & Downloader across all platforms (Linux, macOS, Windows).
> Built following modern CLI design principles: *Clarity, Human-Centric Visual Hierarchy, Progressive Disclosure, Unicode Box Drawing, Dynamic Spinners, and POSIX One-Line Ergonomics*.

---

## 📑 Table of Contents
1. [Design Philosophy & System Foundation](#1-design-philosophy--system-foundation)
2. [Section 1: Hero Banner & Session Header](#section-1-hero-banner--session-header)
3. [Section 2: First-Launch Setup Wizard](#section-2-first-launch-setup-wizard)
4. [Section 3: Category & Provider Navigation (with Back option)](#section-3-category--provider-navigation)
5. [Section 4: Search & Interactive Result Cards](#section-4-search--interactive-result-cards)
6. [Section 5: Episode & Season Selection Grid](#section-5-episode--season-selection-grid)
7. [Section 6: Quality & Resolution Selector](#section-6-quality--resolution-selector)
8. [Section 7: Parallel Link Resolution & Animated Spinners](#section-7-parallel-link-resolution--animated-spinners)
9. [Section 8: Pre-Download Inspection & Cache Resumption Prompt](#section-8-pre-download-inspection--cache-resumption-prompt)
10. [Section 9: Live Download Dashboard & Multi-Metric Progress Bar](#section-9-live-download-dashboard--multi-metric-progress-bar)
11. [Section 10: Post-Download Receipt & Session Summary](#section-10-post-download-receipt--session-summary)
12. [Section 11: One-Line CLI Usage & Flag Ergonomics](#section-11-one-line-cli-usage--flag-ergonomics)
13. [Section 12: Terminal Adaptation & Accessibility](#section-12-terminal-adaptation--accessibility)

---

## 1. Design Philosophy & System Foundation

### 🎨 Color Palette & Typography
| Role | ANSI Code | Color | Purpose |
|------|-----------|-------|---------|
| **Brand Primary** | `\033[38;5;39m` | Electric Blue | Borders, Card Headers, Primary Accents |
| **Brand Secondary** | `\033[38;5;141m` | Soft Purple | Hero Titles, Provider Badges, Highlights |
| **Success** | `\033[38;5;82m` | Bright Green | Completed downloads, skips, valid inputs |
| **Warning / Prompt** | `\033[38;5;214m` | Warm Amber | Input prompts, warnings, cache notifications |
| **Error** | `\033[38;5;196m` | Crimson Red | Fatal errors, failed chunks, rate limits |
| **Metadata / Muted** | `\033[38;5;244m` | Cool Slate Gray | IDs, timestamps, secondary notes, debug |
| **Bold Emphasis** | `\033[1m` | Bold White | Key titles, active episode numbers, totals |

### 🔣 Unicode Box Characters & Icons
- **Box Borders**: `╭`, `╮`, `╰`, `╯`, `│`, `─`, `├`, `┤`, `┬`, `┴`, `┼`
- **Double Borders**: `╔`, `╗`, `╚`, `╝`, `║`, `═`
- **Bullets & Arrows**: `▸`, `➜`, `•`, `›`, `»`, `✓`, `✖`, `⚠`, `ℹ`, `⚡`, `💾`, `🎬`, `⏳`
- **Spinners**: Braille set `['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']`

---

## Section 1: Hero Banner & Session Header

### Interactive Output:
```text
╭────────────────────────────────────────────────────────────────────╮
│  🎬  CLI MEDIA SCRAPER & DOWNLOADER  v1.2                         │
│  Anime • Asian Dramas • Movies • TV Shows                          │
╰────────────────────────────────────────────────────────────────────╯
```

### Key Enhancements:
- Compact, elegant rounded single-line container instead of loud multi-line ASCII art.
- Displays version and active provider capabilities cleanly.
- Suppressed automatically in `--quiet` or non-TTY piped environments.

---

## Section 2: First-Launch Setup Wizard

When `config_scraper.yaml` is missing, the setup wizard runs with clear step indicators:

```text
╭────────────────── FIRST LAUNCH CONFIGURATION ──────────────────╮
│ Step 1 of 3: Download Directory Setup                          │
╰────────────────────────────────────────────────────────────────╯
➜ Default Download Directory [~/Videos/MediaScraper]: 

╭────────────────── FIRST LAUNCH CONFIGURATION ──────────────────╮
│ Step 2 of 3: Network & Performance Concurrency                │
╰────────────────────────────────────────────────────────────────╯
➜ Max Parallel Segment Downloads [1-8, default: 4]: 4

╭────────────────── FIRST LAUNCH CONFIGURATION ──────────────────╮
│ Step 3 of 3: Preferred Video Format                           │
╰────────────────────────────────────────────────────────────────╯
  [1] MKV (.mkv - Recommended: Soft Subs + Forced Flags)
  [2] MP4 (.mp4 - Universal compatibility)
➜ Select container [default: 1]: 1

✔ Configuration saved successfully to: ./config_scraper.yaml
```

---

## Section 3: Category & Provider Navigation

### Category Selection Menu:
```text
╭───── SELECT CONTENT TYPE ─────╮
│  [1]  🎬  Anime               │
│  [2]  🍿  Movies              │
│  [3]  📺  TV Shows            │
│  [0]  🚪  Exit                │
╰───────────────────────────────╯
➜ Enter choice [1-3, 0=Exit]: 1
```

### Provider Selection Menu (Context-Aware):
```text
╭─────── SELECT ANIME PROVIDER ───────╮
│  [1]  ⚡  AnimeSuge (Fast Streams)  │
│  [2]  🌐  AniDB (Multi-Audio + HLS) │
│  [3]  🎌  KissKh (Anime Only)       │
│  [0]  ‹   Back to Content Types     │
╰─────────────────────────────────────╯
➜ Enter choice [1-3, 0=Back]: 2
```

---

## Section 4: Search & Interactive Result Cards

### Rich 2-Line Search Result Cards:
```text
🔍 Searching AniDB for: "Solo Leveling" ...

╭── Search Results (3 matches) ──────────────────────────────────────╮
│                                                                    │
│  [1] Solo Leveling                                                 │
│      Rating: ★ 8.1  •  Year: 2024  •  Format: [TV]  •  Eps: 12     │
│      Genres: Action, Fantasy  •  Audio: JPN (Sub) / ENG (Dub)      │
│                                                                    │
│  [2] Solo Leveling Season 2: Arise from the Shadow                 │
│      Rating: ★ 8.5  •  Year: 2025  •  Format: [TV]  •  Eps: 13     │
│      Genres: Action, Fantasy  •  Audio: JPN (Sub)                  │
│                                                                    │
│  [3] Solo Leveling: How to Get Stronger                            │
│      Rating: ★ 6.4  •  Year: 2024  •  Format: [RECAP] • Eps: 1     │
│                                                                    │
│  [0] 🔍 Search again with a different title                        │
╰────────────────────────────────────────────────────────────────────╯
➜ Select series [1-3, 0=New Search]: 1
```

---

## Section 5: Episode & Season Selection Grid

### Compact Episode Range Overview:
```text
╭── Episodes Available: Solo Leveling ───────────────────────────────╮
│  Total Episodes: 12 (1 - 12)                                       │
│  Summary: [Ep 1] ... [Ep 12]                                       │
╰────────────────────────────────────────────────────────────────────╯
➜ Select episode range (e.g. 1-4, 1,3,5 or Enter for all 1-12): 1-3
```

---

## Section 6: Quality & Resolution Selector

```text
╭── Available Resolutions ───────────────────────────────────────────╮
│  [1]  1080P  (Full HD  •  ~350 MB/ep  •  Recommended)             │
│  [2]  720P   (HD       •  ~180 MB/ep)                              │
│  [3]  360P   (SD       •  ~65 MB/ep)                               │
╰────────────────────────────────────────────────────────────────────╯
➜ Select download resolution [default: 1080]: 1080
```

---

## Section 7: Parallel Link Resolution & Animated Spinners

```text
⠋ Resolving video streams & subtitle tracks [3/3 episodes]
  ✔ Ep 01: 1080P HLS Stream Found (Audio: JPN • Subs: English [Default+Forced])
  ✔ Ep 02: 1080P HLS Stream Found (Audio: JPN • Subs: English [Default+Forced])
  ✔ Ep 03: 1080P HLS Stream Found (Audio: JPN • Subs: English [Default+Forced])
```

---

## Section 8: Pre-Download Inspection & Cache Resumption Prompt

### Target Directory & Existing File Check:
```text
╭── Pre-Download Checklist ──────────────────────────────────────────╮
│ Series:     Solo Leveling                                          │
│ Save Path:  /home/th3mw/Videos/Anime/Solo Leveling                 │
│ Resolution: 1080P (MKV with Forced English Subtitles)              │
│ Target:     Episodes 1 - 3 (3 episodes queued)                     │
│                                                                    │
│ Status Scan:                                                       │
│   [✓] Episode 1 - 1080P.mkv already exists (342.1 MB) -> Skipping │
│   [!] Episode 2: Partial cache found (148/210 segments)            │
│   [ ] Episode 3: Ready to download (212 segments)                  │
╰────────────────────────────────────────────────────────────────────╯
➜ Partial cache detected for Episode 2: [C]ontinue download / [W]ipe cache [default: C]: C
➜ Proceed to download remaining 2 episode(s)? (Y/n): Y
```

---

## Section 9: Live Download Dashboard & Multi-Metric Progress Bar

```text
Downloading: Solo Leveling

[1/2] Episode 2 - 1080P.mkv
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸ 92% • 193/210 seg • 8.4 MB/s • ETA 00:02 [R:148 F:0]

[2/2] Episode 3 - 1080P.mkv
(Waiting in queue...)
```

### Metrics Highlighted in Progress Bar:
1. **Modern Smooth Gradient Bar**: `━` and `╸` characters with high precision.
2. **Percentage**: Direct percentage calculation.
3. **Count**: `193/210 segments` (or `45.2 / 48.0 MiB` for chunks).
4. **Real-Time Speed**: `8.4 MB/s` with rolling window smoothing.
5. **Accurate ETA**: Remaining seconds in `MM:SS`.
6. **Cache Indicator**: `R:148` (Reused segments from cache), `F:0` (Failed/Retried segments).

---

## Section 10: Post-Download Receipt & Session Summary

```text
╭────────────────────── DOWNLOAD SUMMARY ──────────────────────╮
│  Series:   Solo Leveling                                     │
│  Saved To: /home/th3mw/Videos/Anime/Solo Leveling/           │
│                                                              │
│  Status:                                                     │
│    ✔ Episode 1: Skipped (Already downloaded)                 │
│    ✔ Episode 2: Completed in 00m 18s (1080P • 348.4 MB)      │
│    ✔ Episode 3: Completed in 00m 42s (1080P • 351.2 MB)      │
│                                                              │
│  Total Downloaded: 699.6 MB in 01m 00s (Avg: 11.6 MB/s)      │
╰──────────────────────────────────────────────────────────────╯
🎉 All tasks completed successfully!
```

---

## Section 11: One-Line CLI Usage & Flag Ergonomics

### Modern Command Syntax:
```bash
# Standard Non-Interactive Download:
python scraper.py -s anime -p anidb -n "Solo Leveling" -e "1-3" -r 1080 -d

# Flexible Category Aliases:
python scraper.py -s 1            # Numeric alias
python scraper.py -s anime        # String alias
python scraper.py -s movies       # Movies
python scraper.py -s tv           # TV Shows

# New Helpful One-Line Flags:
--search-only      # Quick lookup: print matching series and exit without downloading
--dry-run          # Inspect link resolution and file plan without downloading
--quiet / -q       # Suppress banners and decorative headers (script/cron friendly)
--no-color         # Standard POSIX flag to disable all ANSI color codes
```

---

## Section 12: Terminal Adaptation & Accessibility

1. **TTY Detection**: Automatically strip ANSI escape codes and decorative box characters when output is piped (`python scraper.py ... | tee log.txt` or `> output.txt`).
2. **Terminal Resize Adaptation**: Dynamic width calculation (`min(shutil.get_terminal_size().columns, 80)`) so borders never wrap or distort on narrow mobile SSH/Termux screens.
3. **Environment Support**: Respect `NO_COLOR=1` and `TERM=dumb` standards automatically.
