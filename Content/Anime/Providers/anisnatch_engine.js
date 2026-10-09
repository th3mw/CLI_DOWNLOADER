#!/usr/bin/env node
/**
 * AniSnatch Backend Protocol Engine
 * Handles encrypted session negotiation, search, episode listing, server scraping, and stream extraction.
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

class AniSnatchEngine {
    constructor() {
        this.baseUrl = 'https://anisnatch.top';
        this.sessionToken = null;
        this.siteMeta = null;
        this.ctx = null;
        this.sandbox = null;
        this.scriptCache = {};
    }

    async getScript(scriptPath) {
        if (this.scriptCache[scriptPath]) return this.scriptCache[scriptPath];
        const localPath = path.join(__dirname, path.basename(scriptPath));
        if (fs.existsSync(localPath)) {
            const content = fs.readFileSync(localPath, 'utf8');
            this.scriptCache[scriptPath] = content;
            return content;
        }
        const fullUrl = scriptPath.startsWith('http') ? scriptPath : `${this.baseUrl}/${scriptPath.replace(/^\//, '')}`;
        const res = await fetch(fullUrl, {
            headers: {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': `${this.baseUrl}/`
            }
        });
        if (!res.ok) throw new Error(`Failed to fetch script ${fullUrl}: ${res.status}`);
        const content = await res.text();
        this.scriptCache[scriptPath] = content;
        return content;
    }

    async init() {
        if (this.sessionToken && this.sandbox) return this.sessionToken;

        const res = await fetch(`${this.baseUrl}/home`, {
            headers: {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': `${this.baseUrl}/`
            }
        });
        const html = await res.text();
        const tokenMatch = html.match(/<meta\s+name=["\x27]token["\x27]\s+content=["\x27]([^"\x27]+)["\x27]/i);
        if (!tokenMatch) throw new Error('AniSnatch token meta tag missing from homepage');
        const metaToken = tokenMatch[1];

        const domainMatch = html.match(/domain\s*=\s*[\x27"]([^"\x27]+)[\x27"]/);
        const versionMatch = html.match(/version\s*=\s*[\x27"]([^"\x27]+)[\x27"]/);
        const siteNameMatch = html.match(/siteName\s*=\s*[\x27"]([^"\x27]+)[\x27"]/);
        const configTokenMatch = html.match(/configToken\s*=\s*[\x27"]([^"\x27]+)[\x27"]/);
        const serverTimeMatch = html.match(/serverTime\s*=\s*(\d+)/);

        const domain = domainMatch ? domainMatch[1] : `${this.baseUrl}/`;
        const version = versionMatch ? versionMatch[1] : '1.4.5';
        const siteName = siteNameMatch ? siteNameMatch[1] : 'AniSnatch';
        const configToken = configTokenMatch ? configTokenMatch[1] : '';
        const serverTime = serverTimeMatch ? parseInt(serverTimeMatch[1]) : Math.floor(Date.now() / 1000);

        this.siteMeta = { metaToken, domain, version, siteName, configToken, serverTime };

        const [pakoCode, initCode, ajaxCode] = await Promise.all([
            this.getScript(`assets/script/pako.min.js?v${version}`),
            this.getScript(`assets/script/init.min.js?v${version}`),
            this.getScript(`assets/script/ajax.min.js?v${version}`)
        ]);

        const noop = () => {};
        const sandbox = {
            console, fetch, Date, Math, JSON, String, Array, Uint8Array, parseInt,
            btoa: (str) => Buffer.from(str, 'binary').toString('base64'),
            atob: (b64) => Buffer.from(b64, 'base64').toString('binary'),
            unescape, escape, encodeURIComponent, decodeURIComponent,
            domain, dlServer: 'https://dl.anisnatch.top/', version, siteName, configToken, serverTime,
            addEventListener: noop, removeEventListener: noop,
            document: {
                querySelector: (sel) => {
                    if (sel === 'meta[name="token"]' || sel === "meta[name='token']") {
                        return { content: metaToken };
                    }
                    return null;
                },
                addEventListener: noop, removeEventListener: noop,
                createElement: () => ({ setAttribute: noop, appendChild: noop, style: {} }),
                head: { appendChild: noop }
            },
            navigator: {
                onLine: true,
                userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
        };
        sandbox.window = sandbox;
        sandbox.self = sandbox;

        sandbox.XMLHttpRequest = class {
            constructor() {
                this.headers = {};
                this.status = 0;
                this.response = null;
            }
            open(method, url) {
                this.method = method;
                this.url = url;
            }
            setRequestHeader(k, v) {
                this.headers[k] = v;
            }
            send(body) {
                const url = this.url.startsWith('http') ? this.url : domain + this.url;
                fetch(url, {
                    method: this.method,
                    headers: {
                        ...this.headers,
                        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Referer': `${this.baseUrl}/home`,
                        'Origin': this.baseUrl
                    },
                    body: body
                }).then(async (res) => {
                    this.status = res.status;
                    const buf = await res.arrayBuffer();
                    this.response = buf;
                    if (this.onload) this.onload();
                }).catch(err => {
                    if (this.onerror) this.onerror(err);
                });
            }
        };

        this.ctx = vm.createContext(sandbox);
        vm.runInContext(pakoCode, this.ctx);
        vm.runInContext(initCode, this.ctx);
        vm.runInContext(ajaxCode.replace('const xhrAjax =', 'window.xhrAjax ='), this.ctx);
        this.sandbox = sandbox;

        const initRes = await this.sandbox.xhrAjax(domain + 'api/init', JSON.stringify({ token: null })).promise;
        if (!initRes || !initRes.token) {
            throw new Error(`AniSnatch init handshake failed: ${JSON.stringify(initRes)}`);
        }
        this.sessionToken = initRes.token;
        return this.sessionToken;
    }

    async search(keyword, page = 1) {
        await this.init();
        const res = await this.sandbox.xhrAjax(
            this.siteMeta.domain + 'api/search',
            JSON.stringify({ keyword, page: parseInt(page) || 1 })
        ).promise;
        return res;
    }

    async getEpisodes(animeId) {
        await this.init();
        const res = await this.sandbox.xhrAjax(
            this.siteMeta.domain + 'api/loadEPs',
            JSON.stringify({ id: parseInt(animeId), token: this.sessionToken })
        ).promise;
        return res;
    }

    async getServers(animeId, ep) {
        await this.init();
        const res = await this.sandbox.xhrAjax(
            this.siteMeta.domain + 'api/loadSVs',
            JSON.stringify({ id: parseInt(animeId), ep: parseInt(ep), token: this.sessionToken })
        ).promise;
        return res;
    }

    async extractStream(source) {
        await this.init();
        const videoUrl = this.siteMeta.domain + 'video/' + source;
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 6000);

            const res = await fetch(videoUrl, {
                headers: {
                    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Referer': `${this.baseUrl}/`
                },
                signal: controller.signal
            });
            clearTimeout(timeoutId);

            const html = await res.text();
            const iframeMatch = html.match(/<iframe[^>]+src=["\x27]([^"\x27]+)["\x27]/i);
            if (!iframeMatch) return null;

            let playerUrl = iframeMatch[1];
            if (!playerUrl.startsWith('http')) {
                playerUrl = this.siteMeta.domain.replace(/\/+$/, '') + '/' + playerUrl.replace(/^\/+/, '');
            }

            const pController = new AbortController();
            const pTimeout = setTimeout(() => pController.abort(), 6000);

            const pRes = await fetch(playerUrl, {
                headers: {
                    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Referer': `${this.baseUrl}/`
                },
                signal: pController.signal
            });
            clearTimeout(pTimeout);

            const pHtml = await pRes.text();

            const sourceMatch = pHtml.match(/const\s+source\s*=\s*({[\s\S]*?});/);
            if (sourceMatch) {
                try {
                    const srcObj = vm.runInContext('(' + sourceMatch[1] + ')', vm.createContext({}));
                    return {
                        playerUrl,
                        m3u8: srcObj.src ? (srcObj.src.url || srcObj.src.file) : null,
                        subtitles: srcObj.subtitles || [],
                        skips: srcObj.skips || []
                    };
                } catch (e) {}
            }

            const m3u8Match = pHtml.match(/["\x27](https?:\/\/[^"\x27]+\.m3u8[^"\x27]*)["\x27]/i);
            if (m3u8Match) {
                return {
                    playerUrl,
                    m3u8: m3u8Match[1],
                    subtitles: [],
                    skips: []
                };
            }
        } catch (err) {
            return null;
        }

        return null;
    }

    async getFastStreams(animeId, ep, audioPreference = 'sub') {
        const srvRes = await this.getServers(animeId, ep);
        if (!srvRes || !srvRes.success || !srvRes.server) {
            return { success: false, error: 'No servers found' };
        }

        const serverCategories = srvRes.server;
        const tasks = [];
        let serverIdx = 1;

        const categories = audioPreference === 'dub'
            ? ['dub', 'soft-sub', 'sub']
            : ['soft-sub', 'sub', 'dub'];

        for (const cat of categories) {
            const list = serverCategories[cat] || [];
            // Take top 3 candidate servers per category
            for (const s of list.slice(0, 3)) {
                if (!s.source) continue;
                const idx = serverIdx++;
                const srvTitle = s.title || s.server || `Server ${idx}`;
                const srvType = cat === 'sub' ? 'Hardsub' : (cat === 'soft-sub' ? 'Soft Sub' : 'Dub');

                tasks.push(
                    (async () => {
                        const stream = await this.extractStream(s.source);
                        if (stream && stream.m3u8) {
                            return {
                                serverIdx: idx,
                                serverName: `Server ${idx} (${srvTitle})`,
                                serverType: srvType,
                                serverId: s.source,
                                stream
                            };
                        }
                        return null;
                    })()
                );
            }
        }

        const extracted = (await Promise.all(tasks)).filter(Boolean);
        return { success: true, streams: extracted };
    }
}

// CLI Interface for Python Subprocess / Runner
async function runCli() {
    const args = process.argv.slice(2);
    const action = args[0];
    const engine = new AniSnatchEngine();

    try {
        if (action === 'search') {
            const query = args[1] || '';
            const page = args[2] || 1;
            const res = await engine.search(query, page);
            console.log(JSON.stringify(res));
        } else if (action === 'episodes') {
            const animeId = args[1];
            const res = await engine.getEpisodes(animeId);
            console.log(JSON.stringify(res));
        } else if (action === 'servers') {
            const animeId = args[1];
            const ep = args[2] || 1;
            const res = await engine.getServers(animeId, ep);
            console.log(JSON.stringify(res));
        } else if (action === 'fast_streams') {
            const animeId = args[1];
            const ep = args[2] || 1;
            const audio = args[3] || 'sub';
            const res = await engine.getFastStreams(animeId, ep, audio);
            console.log(JSON.stringify(res));
        } else if (action === 'extract') {
            const source = args[1];
            const res = await engine.extractStream(source);
            console.log(JSON.stringify(res));
        } else {
            console.error(JSON.stringify({ error: `Unknown action: ${action}` }));
            process.exit(1);
        }
    } catch (err) {
        console.error(JSON.stringify({ error: err.message, stack: err.stack }));
        process.exit(1);
    }
}

if (require.main === module) {
    runCli();
}

module.exports = AniSnatchEngine;
