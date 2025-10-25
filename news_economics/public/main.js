async function fetchNews() {
  const statusEl = document.getElementById('status');
  const listEl = document.getElementById('news');
  statusEl.textContent = '読み込み中...';
  listEl.innerHTML = '';

  try {
    const res = await fetch('/api/news');
    if (!res.ok) throw new Error('サーバーからの取得に失敗しました');
    const data = await res.json();

    if (!data.items || data.items.length === 0) {
      statusEl.textContent = '表示できるニュースが見つかりませんでした。';
      return;
    }

    statusEl.textContent = '';
    const fmt = new Intl.DateTimeFormat('ja-JP', { dateStyle: 'medium', timeStyle: 'short' });
    data.items.forEach((it) => {
      const card = document.createElement('article');
      card.className = 'news-card';

      const a = document.createElement('a');
      a.href = it.link;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.textContent = it.title;
      a.className = 'news-title';

      const meta = document.createElement('div');
      meta.className = 'news-meta';
      const d = it.isoDate ? new Date(it.isoDate) : null;
      meta.textContent = `${it.source || '提供元不明'} ・ ${d ? fmt.format(d) : ''}`;

      card.appendChild(a);
      card.appendChild(meta);
      listEl.appendChild(card);
    });
  } catch (err) {
    console.error(err);
    statusEl.textContent = 'ニュースの取得でエラーが発生しました。時間をおいて再度お試しください。';
  }
}

document.getElementById('refreshBtn').addEventListener('click', () => {
  // Force refresh by adding a cache-buster param (server has its own cache TTL)
  fetchNews();
});

// Initial load
fetchNews();

