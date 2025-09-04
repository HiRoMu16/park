const express = require('express');
const path = require('path');
const RSSParser = require('rss-parser');

const app = express();
const port = process.env.PORT || 3000;

const parser = new RSSParser({
  headers: { 'User-Agent': 'NewsEconomics/1.0 (+https://example.local)' }
});

// RSS sources focused on business/economics
const FEEDS = [
  // Aggregated Japan business/economics
  { url: 'https://news.yahoo.co.jp/rss/categories/business.xml', label: 'Yahoo!ニュース 経済' },
  // Global business
  { url: 'https://feeds.reuters.com/reuters/businessNews', label: 'Reuters Business' }
];

// Simple in-memory cache to avoid frequent upstream requests
const CACHE_TTL_MS = 10 * 60 * 1000; // 10 minutes
let cache = { at: 0, items: [] };

function toItem(feedTitle, item) {
  const iso = item.isoDate ? new Date(item.isoDate) : (item.pubDate ? new Date(item.pubDate) : null);
  return {
    title: (item.title || '').trim(),
    link: item.link,
    source: feedTitle || 'Unknown',
    isoDate: iso ? iso.toISOString() : null
  };
}

async function fetchFeed(urlObj) {
  try {
    const feed = await parser.parseURL(urlObj.url);
    const feedTitle = feed?.title || urlObj.label || urlObj.url;
    return (feed.items || []).map((it) => toItem(feedTitle, it));
  } catch (e) {
    console.warn(`[warn] Failed to fetch RSS: ${urlObj.url} -> ${e.message}`);
    return [];
  }
}

async function loadNews(force = false) {
  const now = Date.now();
  if (!force && cache.at && now - cache.at < CACHE_TTL_MS) {
    return cache.items;
  }

  const lists = await Promise.all(FEEDS.map(fetchFeed));
  const combined = lists.flat()
    .filter((i) => i && i.title && i.link)
    .sort((a, b) => {
      const da = a.isoDate ? new Date(a.isoDate).getTime() : 0;
      const db = b.isoDate ? new Date(b.isoDate).getTime() : 0;
      return db - da;
    });

  cache = { at: now, items: combined };
  return combined;
}

// Serve static frontend
app.use(express.static(path.join(__dirname, 'public')));

// API: latest 5 news (optional keyword filter via ?q=comma,separated)
app.get('/api/news', async (req, res) => {
  try {
    const q = (req.query.q || '').toString().trim();
    const keywords = q ? q.split(',').map((s) => s.trim()).filter(Boolean) : [];
    const all = await loadNews(false);

    let items = all;
    if (keywords.length) {
      const lc = (s) => s.toLowerCase();
      items = all.filter((it) => {
        const t = lc(it.title || '');
        return keywords.some((k) => t.includes(lc(k)));
      });
    }

    res.json({
      updatedAt: new Date(cache.at || Date.now()).toISOString(),
      count: Math.min(5, items.length),
      items: items.slice(0, 5)
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to fetch news' });
  }
});

// API: health
app.get('/api/health', (req, res) => {
  res.json({ ok: true, cacheAgeMs: Date.now() - (cache.at || 0) });
});

app.listen(port, () => {
  console.log(`news-economics server on http://localhost:${port}`);
});

