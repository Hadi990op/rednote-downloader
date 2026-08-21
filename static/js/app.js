/* RedNote Video Downloader — Frontend JS */
(function() {
  'use strict';

  const input = document.getElementById('url-input');
  const fetchBtn = document.getElementById('fetch-btn');
  const results = document.getElementById('results');
  const statusMsg = document.getElementById('status-msg');
  const errorMsg = document.getElementById('error-msg');
  const warnBanner = document.getElementById('warn-banner');

  let selectedFormat = 'direct/bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best';
  let currentUrl = '';
  let currentTitle = '';

  // Check auth status on load
  fetch('api/status')
    .then(r => r.json())
    .then(data => {
      if (!data.auth_configured && warnBanner) {
        warnBanner.style.display = 'block';
      }
    })
    .catch(() => {});

  // Fetch video info
  function fetchInfo() {
    const url = input.value.trim();
    if (!url) {
      input.focus();
      return;
    }

    fetchBtn.disabled = true;
    fetchBtn.textContent = 'Fetching...';
    results.classList.remove('show');
    errorMsg.style.display = 'none';
    statusMsg.style.display = 'block';
    statusMsg.innerHTML = '<span class="spinner"></span> Fetching video info...';

    fetch('api/info', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: url }),
    })
      .then(r => r.json())
      .then(data => {
        statusMsg.style.display = 'none';
        fetchBtn.disabled = false;
        fetchBtn.textContent = 'Get Video';

        if (data.error) {
          showError(data.error);
          return;
        }

        currentUrl = data.url;
        currentTitle = data.title;
        renderResults(data);
        results.classList.add('show');
      })
      .catch(err => {
        statusMsg.style.display = 'none';
        fetchBtn.disabled = false;
        fetchBtn.textContent = 'Get Video';
        showError('Network error. Please try again.');
      });
  }

  function renderResults(data) {
    let durationStr = '';
    if (data.duration) {
      const m = Math.floor(data.duration / 60);
      const s = data.duration % 60;
      durationStr = `${m}:${s.toString().padStart(2, '0')}`;
    }

    let html = `
      <div class="video-info">
        <h3>${escapeHtml(data.title)}</h3>
        <div class="video-meta">
          ${data.uploader ? `<span>👤 ${escapeHtml(data.uploader)}</span>` : ''}
          ${durationStr ? `<span>⏱ ${durationStr}</span>` : ''}
          <span>📦 ${data.formats.length - 1} quality options</span>
        </div>
      </div>
      <div class="formats-list" id="formats-list">
    `;

    data.formats.forEach((f, i) => {
      const selected = i === 0 ? 'selected' : '';
      const isLive = f.format_id && f.format_id.startsWith('live_');
      const icon = f.is_best ? '🎬' : (isLive ? '📸' : (f.height && f.height >= 2160 ? '4K' : '📹'));
      const meta = isLive
        ? '📸 Live Photo · Video only · No audio'
        : (f.has_audio ? '✅ With audio' : '⚠️ Video only (needs merge)');
      html += `
        <div class="format-card ${selected}" data-format-id="${escapeAttr(f.format_id)}">
          <div class="format-left">
            <div class="format-icon">${icon}</div>
            <div>
              <div class="format-label">${escapeHtml(f.label)}</div>
              <div class="format-meta">${meta} · ${f.ext.toUpperCase()}</div>
            </div>
          </div>
          <div class="format-size">${escapeHtml(f.filesize_str)}</div>
        </div>
      `;
    });

    html += '</div>';
    html += `<button class="btn-primary" id="download-btn" style="width:100%;margin-top:20px;">⬇ Download Video</button>`;

    results.innerHTML = html;

    // Format selection
    document.querySelectorAll('.format-card').forEach(card => {
      card.addEventListener('click', function() {
        document.querySelectorAll('.format-card').forEach(c => c.classList.remove('selected'));
        this.classList.add('selected');
        selectedFormat = this.dataset.formatId;
      });
    });

    // Download button
    document.getElementById('download-btn').addEventListener('click', downloadVideo);
  }

  function downloadVideo() {
    const dlBtn = document.getElementById('download-btn');
    dlBtn.disabled = true;
    dlBtn.textContent = 'Downloading on server, please wait...';

    fetch('api/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: currentUrl,
        format_id: selectedFormat,
        title: currentTitle,
      }),
    })
      .then(response => {
        if (!response.ok) {
          return response.json().then(d => { throw new Error(d.error || 'Download failed'); });
        }
        return response.blob();
      })
      .then(blob => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = (currentTitle || 'rednote_video') + '.mp4';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        dlBtn.disabled = false;
        dlBtn.textContent = '⬇ Download Video';
      })
      .catch(err => {
        dlBtn.disabled = false;
        dlBtn.textContent = '⬇ Download Video';
        showError(err.message || 'Download failed.');
      });
  }

  function showError(msg) {
    errorMsg.textContent = msg;
    errorMsg.style.display = 'block';
    results.classList.remove('show');
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
  }

  function escapeAttr(str) {
    return (str || '').replace(/"/g, '&quot;');
  }

  // Event listeners
  if (fetchBtn) fetchBtn.addEventListener('click', fetchInfo);
  if (input) {
    input.addEventListener('keypress', function(e) {
      if (e.key === 'Enter') fetchInfo();
    });
  }
})();
