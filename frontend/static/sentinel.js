// ── KeySentinel — Sentinel mode JS ──────────────────────────────────

// ── State ──────────────────────────────────────────────────────────
 let _selectedUserId   = null;
let _selectedUserName = null;
let _selectedSessionId = null;
let _replayLoadedFor  = null;
let _liveSessionId    = null;  // session currently watched live
let _liveSince        = 0;     // timestamp cursor for incremental fetch
let _liveTimer        = null;  // setInterval handle
let _liveKbCounts      = {};   // key heatmap for live tab
let _liveRecentPresses = [];  // {ts} for sliding-window WPM/KPS
let _liveRecentMoves   = [];  // {ts, x, y} for mouse speed
let _liveCharts        = null;
let _liveKbLastPress  = {};    // Date.now() of most recent press per key
let _liveTotalKeys    = 0;
let _liveTotalClicks  = 0;
let _liveTotalMoves   = 0;
let _liveStartedAt    = null;

// ── Tab helpers ────────────────────────────────────────────────────
function switchTab(name) {
  if (name === 'live' && !_liveTimer && !_liveSessionId) {
    const row = _selectedSessionId != null
      ? document.querySelector(`.session-row[data-sid="${_selectedSessionId}"]`)
      : null;
    if (row?.dataset.ongoing === '1') { openLive(_selectedSessionId); return; }
  }
  ['users', 'sessions', 'metrics', 'replay', 'live'].forEach(t => {
    document.getElementById(`tab-${t}`)?.classList.toggle('hidden', t !== name);
    const btn = document.getElementById(`tab-${t}-btn`);
    if (btn) btn.classList.toggle('active', t === name);
  });
  if (name === 'replay' && _selectedSessionId !== null && _replayLoadedFor !== _selectedSessionId) {
    loadReplay(_selectedSessionId);
  }
}

// ── Activity badge ─────────────────────────────────────────────────
const ACTIVITY_CSS = {
  coding:  'badge-coding',
  writing: 'badge-writing',
  gaming:  'badge-gaming',
  train:   'badge-train',
};
function activityBadge(label) {
  if (!label) return '<span class="badge-unknown px-2 py-0.5 rounded text-xs">—</span>';
  const css = ACTIVITY_CSS[label] || 'badge-unknown';
  return `<span class="${css} px-2 py-0.5 rounded text-xs font-bold uppercase">${label}</span>`;
}

// ── Format helpers ─────────────────────────────────────────────────
function fmtTs(ts) {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString('fr-FR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}
function fmtDuration(secs) {
  if (secs == null) return '—';
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = Math.floor(secs % 60);
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}
function fmtMs(ms) {
  if (ms == null) return '—';
  return ms.toFixed(1) + ' ms';
}
function fmtMinutes(min) {
  if (min == null || min === 0) return '0 min';
  return min.toFixed(1) + ' min';
}

// ── Users tab ──────────────────────────────────────────────────────
async function loadUsers() {
  show('users-loading'); hide('users-error'); hide('users-table'); hide('users-empty');
  try {
    const res  = await fetch('/api/sentinel/users');
    const data = await res.json();
    hide('users-loading');
    if (data.error) { showError('users-error', data.error); return; }
    if (!data.length) { show('users-empty'); return; }
    renderUsers(data);
    show('users-table');
  } catch (e) {
    hide('users-loading');
    showError('users-error', 'Impossible de contacter le serveur.' + e);
  }
}

function renderUsers(users) {
  const tbody = document.getElementById('users-tbody');
  tbody.innerHTML = '';
  users.forEach(u => {
    const dot = u.is_on_line
      ? '<span class="inline-block w-2 h-2 rounded-full dot-on mr-2"></span>En ligne'
      : '<span class="inline-block w-2 h-2 rounded-full dot-off mr-2"></span>Hors ligne';
    const tr = document.createElement('tr');
    tr.className = 'user-row border-b border-gray-800/50' + (u.id === _selectedUserId ? ' selected' : '');
    tr.dataset.uid = u.id;
    tr.dataset.uname = u.name;
    tr.innerHTML = `
      <td class="px-4 py-3 text-xs">${dot}</td>
      <td class="px-4 py-3 font-semibold">${esc(u.name)}</td>
      <td class="px-4 py-3">${activityBadge(u.on_going_activity)}</td>
      <td class="px-4 py-3 text-right text-gray-400">${u.session_count}</td>
      <td class="px-4 py-3 text-right">
        <button class="text-xs text-blue-400 hover:text-blue-300"
                onclick="selectUser(${u.id}, '${esc(u.name)}')">
          Voir sessions →
        </button>
      </td>`;
    tr.onclick = () => selectUser(u.id, u.name);
    tbody.appendChild(tr);
  });
}

function selectUser(uid, uname) {
  _selectedUserId   = uid;
  _selectedUserName = uname;
  document.querySelectorAll('.user-row').forEach(r => {
    r.classList.toggle('selected', parseInt(r.dataset.uid) === uid);
  });
  loadSessions(uid, uname);
  switchTab('sessions');
}

async function _checkUserLiveBanner(uid) {
  hide('users-live-banner');
  if (!uid) return;
  try {
    const res  = await fetch(`/api/sentinel/sessions?user_id=${uid}`);
    const data = await res.json();
    const live = data.find(s => s.ending_at == null);
    if (!live) return;
    show('users-live-banner');
    document.getElementById('users-live-activity').innerHTML = activityBadge(live.activity);
    document.getElementById('users-live-since').textContent  = 'depuis ' + fmtTs(live.started_at);
    const btn = document.getElementById('users-live-btn');
    btn.onclick = () => openLive(live.id);
  } catch (_) {}
}

// ── Sessions tab ───────────────────────────────────────────────────
async function loadSessions(uid, uname) {
  document.getElementById('sessions-user-label').textContent =
    uname ? `— ${uname}` : '';
  show('sessions-loading');
  hide('sessions-error'); hide('sessions-table'); hide('sessions-empty');
  document.getElementById('sessions-loading').textContent = 'Chargement…';

  const url = uid != null
    ? `/api/sentinel/sessions?user_id=${uid}`
    : '/api/sentinel/sessions';
  try {
    const res  = await fetch(url);
    const data = await res.json();
    hide('sessions-loading');
    if (data.error) { showError('sessions-error', data.error); return; }
    if (!data.length) { show('sessions-empty'); return; }
    renderSessions(data);
    show('sessions-table');
  } catch(e) {
    hide('sessions-loading');
    showError('sessions-error', 'Impossible de contacter le serveur.');
  }
}

function reloadSessions() {
  if (_selectedUserId != null) loadSessions(_selectedUserId, _selectedUserName);
  else loadSessions(null, null);
}

function renderSessions(sessions) {
  const tbody = document.getElementById('sessions-tbody');
  tbody.innerHTML = '';
  sessions.forEach(s => {
    const ongoing = s.ending_at == null;
    const tr = document.createElement('tr');
    tr.className = 'session-row border-b border-gray-800/50' +
      (s.id === _selectedSessionId ? ' selected' : '') +
      (ongoing ? ' bg-green-950/20' : '');
    tr.dataset.sid = s.id;
    tr.dataset.ongoing = ongoing ? '1' : '0';

    const durationCell = ongoing
      ? '<span class="inline-flex items-center gap-1 text-xs text-green-400"><span class="inline-block w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse"></span>En cours</span>'
      : fmtDuration(s.duration_s);

    const actionCell = ongoing
      ? `<div class="flex gap-3 justify-end">
           <button class="text-xs text-purple-400 hover:text-purple-300"
                   onclick="event.stopPropagation();selectSession(${s.id})">Métriques →</button>
           <button class="text-xs text-green-400 hover:text-green-300 font-semibold"
                   onclick="event.stopPropagation();openLive(${s.id})">&#128994; Live →</button>
         </div>`
      : `<div class="flex gap-3 justify-end">
           <button class="text-xs text-purple-400 hover:text-purple-300"
                   onclick="event.stopPropagation();selectSession(${s.id})">Métriques →</button>
           <button class="text-xs text-blue-400 hover:text-blue-300"
                   onclick="event.stopPropagation();openReplay(${s.id})">Replay →</button>
         </div>`;

    tr.innerHTML = `
      <td class="px-4 py-3 text-xs text-gray-400">${fmtTs(s.started_at)}</td>
      <td class="px-4 py-3">${activityBadge(s.activity)}</td>
      <td class="px-4 py-3 text-right text-gray-300">${durationCell}</td>
      <td class="px-4 py-3 text-right text-gray-400">${s.keyboard_events.toLocaleString()}</td>
      <td class="px-4 py-3 text-right text-gray-400">${s.mouse_events.toLocaleString()}</td>
      <td class="px-4 py-3 text-right">${actionCell}</td>`;
    tr.onclick = () => selectSession(s.id);
    tbody.appendChild(tr);
  });
}

function selectSession(sid) {
  _selectedSessionId = sid;
  _replayLoadedFor   = null;
  document.querySelectorAll('.session-row').forEach(r => {
    r.classList.toggle('selected', parseInt(r.dataset.sid) === sid);
  });
  const row = document.querySelector(`.session-row[data-sid="${sid}"]`);
  const liveBtn = document.getElementById('tab-live-btn');
  if (liveBtn) liveBtn.classList.toggle('hidden', row?.dataset.ongoing !== '1' && _liveSessionId !== sid);
  loadMetrics(sid);
  switchTab('metrics');
}

// ── Metrics tab ────────────────────────────────────────────────────
async function loadMetrics(sid) {
  document.getElementById('metrics-session-label').textContent = `#${sid}`;
  hide('metrics-empty'); show('metrics-loading');
  hide('metrics-error'); hide('metrics-content');
  try {
    const res = await fetch(`/api/sentinel/session/${sid}/stats`);
    const d   = await res.json();
    hide('metrics-loading');
    if (d.error) { showError('metrics-error', d.error); return; }
    renderMetrics(d);
    show('metrics-content');
  } catch(e) {
    hide('metrics-loading');
    showError('metrics-error', 'Impossible de contacter le serveur.');
  }
}

function renderMetrics(d) {
  set('m-duration', fmtDuration(d.duration_s));
  set('m-kb',      (d.keyboard_events || 0).toLocaleString());
  set('m-mouse',   (d.mouse_events    || 0).toLocaleString());
  set('m-clicks',  (d.click_count     || 0).toLocaleString());
  set('m-dwell',   fmtMs(d.avg_dwell_ms));
  set('m-flight',  fmtMs(d.avg_flight_ms));
  set('m-speed',   d.avg_mouse_speed_px_s != null ? d.avg_mouse_speed_px_s + ' px/s' : '—');
  set('m-uuid',    d.uuid || '—');

  const total = (d.coding_time || 0) + (d.writing_time || 0) + (d.gaming_time || 0);
  const pct = (v) => total > 0 ? ((v / total) * 100).toFixed(1) : 0;

  set('m-coding-val',  fmtMinutes(d.coding_time));
  set('m-writing-val', fmtMinutes(d.writing_time));
  set('m-gaming-val',  fmtMinutes(d.gaming_time));
  document.getElementById('m-coding-bar' ).style.width = pct(d.coding_time  || 0) + '%';
  document.getElementById('m-writing-bar').style.width = pct(d.writing_time || 0) + '%';
  document.getElementById('m-gaming-bar' ).style.width = pct(d.gaming_time  || 0) + '%';
}

// ── DOM helpers ────────────────────────────────────────────────────
function show(id) { document.getElementById(id)?.classList.remove('hidden'); }
function hide(id) { document.getElementById(id)?.classList.add('hidden'); }
function set(id, val) { const el = document.getElementById(id); if (el) el.textContent = val; }
function showError(id, msg) { const el = document.getElementById(id); if (el) { el.textContent = msg; el.classList.remove('hidden'); } }
function esc(s) { return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

// ═══════════════════════════════════════════════════════════════════
// REPLAY ENGINE
// ═══════════════════════════════════════════════════════════════════

// ── Key parsers ────────────────────────────────────────────────────
function _parseKeyChar(raw) {
  // Format A — pynput str(KeyCode): "'a'" (with surrounding quotes)
  const m = raw.match(/^'([\s\S]*)'$/);
  if (m) return m[1];
  // Format B — pynput key.char (no quotes): plain single character "a"
  if (!raw.startsWith('Key.') && raw.length === 1) return raw;
  // Special keys
  if (raw === 'Key.space'  || raw === 'space')  return ' ';
  if (raw === 'Key.enter'  || raw === 'enter')  return '\n';
  if (raw === 'Key.tab'    || raw === 'tab')    return '\t';
  return null;
}

function _parseKeyId(raw) {
  const m = raw.match(/^'([\s\S]*)'$/);
  if (m) return m[1].toLowerCase();
  if (raw.startsWith('Key.')) return raw.slice(4).replace(/_[lr]$/, '').toLowerCase();
  return raw.toLowerCase();
}

// ── Replay data & player state ─────────────────────────────────────
let _RP = null;          // { events[], duration, activity, bbox }
let _scrubbing = false;  // true while user drags scrubber
const _PL = { playing: false, speed: 1, playhead: 0, lastWall: null, rafId: null, evIdx: 0 };

// ── Visual state ───────────────────────────────────────────────────
let _textBuf   = [];
let _kbCounts  = {};
let _kbPressed = new Set();
let _mousePts  = [];
let _mousePos  = null;
let _allClicks = [];

function _resetVisual() {
  _textBuf = []; _kbCounts = {}; _kbPressed = new Set();
  _mousePts = []; _mousePos = null; _allClicks = [];
}

// ── Apply one event to visual state ───────────────────────────────
// Handles both DB spellings: 'key_press'/'key_release' (schema) and
// 'press'/'release' (agent _key_str path).
function _applyEvent(ev) {
  const isPress   = ev.k === 'key_press'   || ev.k === 'press';
  const isRelease = ev.k === 'key_release' || ev.k === 'release';
  if (isPress) {
    if (ev.key === 'Key.backspace' || ev.key === 'backspace') { _textBuf.pop(); }
    else { const ch = _parseKeyChar(ev.key); if (ch !== null) _textBuf.push(ch); }
    const kid = _parseKeyId(ev.key);
    _kbCounts[kid] = (_kbCounts[kid] || 0) + 1;
    _kbPressed.add(kid);
  } else if (isRelease) {
    _kbPressed.delete(_parseKeyId(ev.key));
  } else if (ev.k === 'move') {
    _mousePos = { x: ev.x, y: ev.y };
    _mousePts.push({ x: ev.x, y: ev.y });
    if (_mousePts.length > 1500) _mousePts.shift();
  } else if (ev.k === 'click') {
    _mousePos = { x: ev.x, y: ev.y };
    _allClicks.push({ x: ev.x, y: ev.y, button: ev.button });
  }
}

// ── Render: text areas ─────────────────────────────────────────────
function _renderText() {
  const text = _textBuf.join('');
  const act  = _RP?.activity;
  if      (act === 'writing') { const el = document.getElementById('replay-writing-area'); if (el) el.textContent = text; }
  else if (act === 'coding')  { const el = document.getElementById('replay-coding-area');  if (el) el.textContent = text; }
}

// ── Keyboard DOM — AZERTY ISO (français) ──────────────────────────
const _KB_DEF = [
  [['²',1],['&',1],['é',1],['"',1],["'",1],['(',1],['-',1],['è',1],['_',1],['ç',1],['à',1],[')',1],['=',1],['backspace',2]],
  [['tab',1.5],['a',1],['z',1],['e',1],['r',1],['t',1],['y',1],['u',1],['i',1],['o',1],['p',1],['^',1],['$',1],['enter',1.5]],
  [['caps_lock',1.75],['q',1],['s',1],['d',1],['f',1],['g',1],['h',1],['j',1],['k',1],['l',1],['m',1],['ù',1],['enter',2.25]],
  [['shift',1.25],['<',1],['w',1],['x',1],['c',1],['v',1],['b',1],['n',1],[',',1],[';',1],[':',1],['!',1],['shift',2.75]],
  [['ctrl',1.25],['alt',1.25],['space',6.25],['alt_gr',1.25],['ctrl',1.25]],
];
const _KB_LBL = {
  backspace: '⌫', tab: 'Tab', caps_lock: '⇪', enter: '↵',
  shift: '⇧', ctrl: 'Ctrl', alt: 'Alt', alt_gr: 'AltGr',
  space: 'Espace', '²': '²', up: '↑', down: '↓', left: '←', right: '→',
};
const _KU = 30;

function _buildKeyboardDOM(containerId) {
  const parent = document.getElementById(containerId);
  if (!parent) return;
  parent.innerHTML = '';
  const wrap = document.createElement('div');
  wrap.className = 'inline-flex flex-col gap-1';
  const makeRow = (keys) => {
    const row = document.createElement('div');
    row.className = 'flex gap-1';
    for (const [kid, units] of keys) {
      const el = document.createElement('div');
      el.className = 'kb-key rounded select-none overflow-hidden';
      el.style.cssText = `width:${Math.round(_KU*units)}px;min-width:${Math.round(_KU*units)}px;height:28px;display:flex;flex-direction:column;align-items:center;justify-content:center;font-size:10px;border:1px solid #30363d;background:#21262d;color:#484f58`;
      el.dataset.kid = kid;
      el.innerHTML = `<span class="font-medium">${esc(_KB_LBL[kid] || kid.toUpperCase().slice(0,5))}</span><span class="kb-cnt" style="font-size:7px;line-height:1"></span>`;
      row.appendChild(el);
    }
    return row;
  };
  for (const r of _KB_DEF) wrap.appendChild(makeRow(r));
  const arrWrap = document.createElement('div');
  arrWrap.className = 'flex flex-col gap-1 mt-1';
  const arrTop = makeRow([['up',1]]);
  arrTop.style.paddingLeft = `${_KU + 2}px`;
  arrWrap.appendChild(arrTop);
  arrWrap.appendChild(makeRow([['left',1],['down',1],['right',1]]));
  wrap.appendChild(arrWrap);
  parent.appendChild(wrap);
}

function _renderKeyboard() {
  const container = document.getElementById('replay-kb-container');
  if (!container) return;
  const max = Math.max(1, ...Object.values(_kbCounts));
  container.querySelectorAll('.kb-key').forEach(el => {
    const kid = el.dataset.kid, count = _kbCounts[kid] || 0;
    const heat = count / max, pressed = _kbPressed.has(kid);
    const cntEl = el.querySelector('.kb-cnt');
    if (cntEl) cntEl.textContent = count > 0 ? (count > 9999 ? Math.round(count/1000)+'k' : count) : '';
    if (pressed) {
      el.style.background = '#3d1a6e'; el.style.color = '#d2a8ff';
      el.style.borderColor = '#8957e5';
      el.style.boxShadow   = '0 0 8px rgba(188,140,255,.85),inset 0 0 6px rgba(188,140,255,.3)';
    } else if (count > 0) {
      const r = Math.round(13+heat*75), g = Math.round(42+heat*124), b = Math.round(95+heat*160);
      el.style.background = `rgb(${r},${g},${b})`; el.style.color = heat>.6?'#0d1117':'#c9d1d9';
      el.style.borderColor = `rgb(${r},${g},${b})`; el.style.boxShadow = 'none';
    } else {
      el.style.background = '#21262d'; el.style.color = '#484f58';
      el.style.borderColor = '#30363d'; el.style.boxShadow = 'none';
    }
  });
}

// ── Mouse canvas ───────────────────────────────────────────────────
function _getActiveCanvas() {
  const act = _RP?.activity;
  if (act === 'writing') return document.getElementById('replay-mouse-writing');
  if (act === 'coding')  return document.getElementById('replay-mouse-coding');
  return document.getElementById('replay-mouse-gaming');
}

function _drawMouseCanvas() {
  const canvas = _getActiveCanvas();
  if (!canvas || !_RP?.bbox) return;
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  const { minX, maxX, minY, maxY } = _RP.bbox;
  const pad = 20;
  const norm = (x, y) => ({
    cx: pad + ((x - minX) / ((maxX - minX) || 1)) * (W - 2*pad),
    cy: pad + ((y - minY) / ((maxY - minY) || 1)) * (H - 2*pad),
  });
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = '#0d1117'; ctx.fillRect(0, 0, W, H);
  if (!_mousePts.length && !_allClicks.length && !_mousePos) {
    ctx.fillStyle = '#6e7681'; ctx.font = '12px monospace'; ctx.textAlign = 'center';
    ctx.fillText('Aucun mouvement enregistré', W/2, H/2); return;
  }
  if (_mousePts.length > 1) {
    ctx.beginPath();
    const p0 = norm(_mousePts[0].x, _mousePts[0].y); ctx.moveTo(p0.cx, p0.cy);
    for (let i = 1; i < _mousePts.length; i++) {
      const p = norm(_mousePts[i].x, _mousePts[i].y); ctx.lineTo(p.cx, p.cy);
    }
    ctx.strokeStyle = 'rgba(88,166,255,0.22)'; ctx.lineWidth = 1; ctx.stroke();
  }
  for (const c of _allClicks) {
    const { cx, cy } = norm(c.x, c.y);
    const col = (!c.button || c.button.includes('left')) ? '#3fb950' : '#f85149';
    ctx.beginPath(); ctx.arc(cx, cy, 4, 0, Math.PI*2); ctx.fillStyle = col+'cc'; ctx.fill();
    ctx.beginPath(); ctx.arc(cx, cy, 7, 0, Math.PI*2); ctx.strokeStyle = col+'88'; ctx.lineWidth=1; ctx.stroke();
  }
  if (_mousePos) {
    const { cx, cy } = norm(_mousePos.x, _mousePos.y);
    ctx.save();
    ctx.fillStyle = '#bc8cff'; ctx.strokeStyle = '#0d1117'; ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(cx,    cy    );
    ctx.lineTo(cx,    cy+14 );
    ctx.lineTo(cx+4,  cy+10 );
    ctx.lineTo(cx+7,  cy+16 );
    ctx.lineTo(cx+9,  cy+15 );
    ctx.lineTo(cx+6,  cy+9  );
    ctx.lineTo(cx+11, cy+9  );
    ctx.closePath(); ctx.fill(); ctx.stroke();
    ctx.restore();
  }
  ctx.fillStyle = '#484f58'; ctx.font = '9px monospace'; ctx.textAlign = 'left';
  ctx.fillText(`${minX},${minY}→${maxX},${maxY}`, 4, H-4);
}

// ── Time / scrubber sync ───────────────────────────────────────────
function _fmtTime(s) {
  return `${Math.floor(s/60)}:${String(Math.floor(s%60)).padStart(2,'0')}`;
}
function _syncUI() {
  const dur = _RP?.duration || 0, pos = _PL.playhead;
  set('rp-time-cur', _fmtTime(pos));
  set('rp-time-dur', _fmtTime(dur));
  if (!_scrubbing) {
    const s = document.getElementById('rp-scrubber');
    if (s) s.value = dur > 0 ? Math.round((pos/dur)*10000) : 0;
  }
}
function _updatePlayBtn() {
  const btn = document.getElementById('replay-play-btn');
  if (btn) btn.textContent = _PL.playing ? '⏸ Pause' : '▶ Lire';
}

// ── Replay charts ──────────────────────────────────────────────────
let _rpCharts   = null;
let _rpChartIdx = -1;

function _computeReplayTimeSeries(events, duration) {
  const WIN = 10, STEP = 5;
  const series = [];
  for (let end = WIN; end <= duration + STEP; end += STEP) {
    const start = end - WIN;
    const win = events.filter(e => e.t >= start && e.t < end);
    // WPM: printable chars / 5 chars-per-word / (WIN/60 min)
    const chars = win.filter(e =>
      (e.k === 'key_press' || e.k === 'press') && _parseKeyChar(e.key) !== null
    ).length;
    const wpm = Math.round((chars / 5) / (WIN / 60));
    // Keys/s
    const presses = win.filter(e => e.k === 'key_press' || e.k === 'press').length;
    const kps = Math.round((presses / WIN) * 10) / 10;
    // Mouse speed from consecutive move events
    const moves = win.filter(e => e.k === 'move');
    let mouseSpeed = 0;
    if (moves.length >= 2) {
      let totalDist = 0, totalTime = 0;
      for (let i = 1; i < moves.length; i++) {
        const dx = moves[i].x - moves[i-1].x, dy = moves[i].y - moves[i-1].y;
        const dt = moves[i].t - moves[i-1].t;
        if (dt > 0 && dt < 1) {
          totalDist += Math.sqrt(dx*dx + dy*dy);
          totalTime += dt;
        }
      }
      mouseSpeed = totalTime > 0 ? Math.round(totalDist / totalTime) : 0;
    }
    series.push({ t: end, label: _fmtTime(end), wpm, kps, mouseSpeed });
  }
  return series;
}

function _makeRpChart(id, color, label) {
  const canvas = document.getElementById(id);
  if (!canvas) return null;
  return new Chart(canvas.getContext('2d'), {
    type: 'line',
    data: { labels: [], datasets: [{ label, data: [], borderColor: color,
      backgroundColor: color + '22', borderWidth: 2, pointRadius: 2, tension: 0.4, fill: true }] },
    options: {
      animation: false, responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { display: false },
        y: { min: 0, grid: { color: '#21262d' }, ticks: { color: '#8b949e', font: { size: 10 } } }
      }
    }
  });
}

function _initReplayCharts() {
  if (_rpCharts) { Object.values(_rpCharts).forEach(c => c?.destroy()); }
  _rpCharts = {
    wpm:   _makeRpChart('rp-chart-wpm',   '#58a6ff', 'WPM'),
    kps:   _makeRpChart('rp-chart-kps',   '#d2a8ff', 'Touches/s'),
    mouse: _makeRpChart('rp-chart-mouse', '#2dd4bf', 'Vitesse souris'),
  };
  _rpChartIdx = -1;
}

function _updateReplayCharts(playhead) {
  if (!_rpCharts || !_RP?.timeSeries) return;
  const visible = _RP.timeSeries.filter(p => p.t <= playhead + 1);
  const newIdx  = visible.length;
  if (newIdx === _rpChartIdx) return;
  _rpChartIdx = newIdx;
  const labels    = visible.map(p => p.label);
  const wpmData   = visible.map(p => p.wpm);
  const kpsData   = visible.map(p => p.kps);
  const mouseData = visible.map(p => p.mouseSpeed);
  if (_rpCharts.wpm)   { _rpCharts.wpm.data.labels   = labels; _rpCharts.wpm.data.datasets[0].data   = wpmData;   _rpCharts.wpm.update('none'); }
  if (_rpCharts.kps)   { _rpCharts.kps.data.labels   = labels; _rpCharts.kps.data.datasets[0].data   = kpsData;   _rpCharts.kps.update('none'); }
  if (_rpCharts.mouse) { _rpCharts.mouse.data.labels = labels; _rpCharts.mouse.data.datasets[0].data = mouseData; _rpCharts.mouse.update('none'); }
  // Update stat numbers
  if (visible.length > 0) {
    const last = visible[visible.length - 1];
    set('rp-stat-wpm', last.wpm);
    set('rp-stat-kps', last.kps.toFixed(1));
    const mouseEl = document.getElementById('rp-stat-mouse');
    if (mouseEl) mouseEl.innerHTML = `${last.mouseSpeed} <span class="text-xs">px/s</span>`;
  } else {
    set('rp-stat-wpm', '—'); set('rp-stat-kps', '—');
    const mouseEl = document.getElementById('rp-stat-mouse');
    if (mouseEl) mouseEl.innerHTML = `— <span class="text-xs">px/s</span>`;
  }
}

// ── RAF tick ───────────────────────────────────────────────────────
function _tick(wallNow) {
  if (!_PL.playing || !_RP) return;
  const dt = (wallNow - _PL.lastWall) / 1000 * _PL.speed;
  _PL.lastWall = wallNow;
  _PL.playhead = Math.min(_PL.playhead + dt, _RP.duration);
  let textDirty = false, kbDirty = false, mouseDirty = false;
  while (_PL.evIdx < _RP.events.length && _RP.events[_PL.evIdx].t <= _PL.playhead) {
    const ev = _RP.events[_PL.evIdx++];
    _applyEvent(ev);
    const isKP = ev.k === 'key_press' || ev.k === 'press';
    const isKR = ev.k === 'key_release' || ev.k === 'release';
    if      (isKP) { textDirty = true; kbDirty = true; }
    else if (isKR) { kbDirty = true; }
    else           { mouseDirty = true; }
  }
  if (textDirty)  _renderText();
  if (kbDirty)    _renderKeyboard();
  if (mouseDirty) _drawMouseCanvas();
  _syncUI();
  _updateReplayCharts(_PL.playhead);
  if (_PL.playhead >= _RP.duration) { _PL.playing = false; _updatePlayBtn(); return; }
  _PL.rafId = requestAnimationFrame(_tick);
}

// ── Seek (instant — replays all events up to target time) ─────────
function _seek(seconds) {
  const wasPlaying = _PL.playing;
  if (_PL.rafId) { cancelAnimationFrame(_PL.rafId); _PL.rafId = null; }
  _PL.playing  = false;
  _PL.playhead = Math.max(0, Math.min(seconds, _RP.duration));
  _resetVisual();
  let idx = 0;
  for (; idx < _RP.events.length; idx++) {
    if (_RP.events[idx].t > _PL.playhead) break;
    _applyEvent(_RP.events[idx]);
  }
  _PL.evIdx = idx;
  _renderText(); _renderKeyboard(); _drawMouseCanvas(); _syncUI();
  _updateReplayCharts(_PL.playhead);
  if (wasPlaying && _PL.playhead < _RP.duration) {
    _PL.playing = true; _PL.lastWall = performance.now();
    _PL.rafId = requestAnimationFrame(_tick);
    _updatePlayBtn();
  }
}

// ── Public controls ────────────────────────────────────────────────
function playerToggle() {
  if (!_RP) return;
  if (_PL.playing) {
    _PL.playing = false;
    if (_PL.rafId) { cancelAnimationFrame(_PL.rafId); _PL.rafId = null; }
  } else {
    if (_PL.playhead >= _RP.duration) _seek(0);
    _PL.playing = true; _PL.lastWall = performance.now();
    _PL.rafId = requestAnimationFrame(_tick);
  }
  _updatePlayBtn();
}
function playerReset() {
  if (!_RP) return;
  _PL.playing = false;
  if (_PL.rafId) { cancelAnimationFrame(_PL.rafId); _PL.rafId = null; }
  _seek(0); _updatePlayBtn();
}
function playerScrub(val) {
  if (!_RP) return;
  _seek((_RP.duration * parseInt(val)) / 10000);
}
function setSpeed(s) {
  _PL.speed = s;
  document.querySelectorAll('.rspd').forEach(b => b.classList.toggle('active', parseInt(b.dataset.speed) === s));
}

// ── Load replay data ───────────────────────────────────────────────
async function loadReplay(sid) {
  if (!sid) return;
  _replayLoadedFor = sid;
  if (_PL.rafId) { cancelAnimationFrame(_PL.rafId); _PL.rafId = null; }
  _PL.playing = false;
  document.getElementById('replay-session-label').textContent = `#${sid}`;
  hide('replay-empty'); show('replay-loading'); hide('replay-error'); hide('replay-container');
  ['replay-view-writing','replay-view-coding','replay-view-gaming'].forEach(v => {
    const el = document.getElementById(v); if (el) el.style.display = 'none';
  });
  try {
    const res  = await fetch(`/api/sentinel/session/${sid}/events`);
    const data = await res.json();
    hide('replay-loading');
    if (data.error) { showError('replay-error', data.error); return; }
    document.getElementById('replay-activity-badge').innerHTML = activityBadge(data.activity);

    // Merge & sort all events, translate field names for engine
    const events = [];
    for (const e of (data.keyboard || [])) events.push({ t: e.ts_offset, k: e.type,  key: e.key });
    for (const e of (data.mouse    || [])) events.push({ t: e.ts_offset, k: e.type,  x: e.x, y: e.y, button: e.button });
    events.sort((a, b) => a.t - b.t);

    // Bounding box for mouse normalisation
    const mevs = events.filter(e => e.k === 'move' || e.k === 'click');
    let bbox = { minX: 0, maxX: 1, minY: 0, maxY: 1 };
    if (mevs.length) {
      const xs = mevs.map(e => e.x), ys = mevs.map(e => e.y);
      bbox = { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };
    }

    const dur = data.duration ?? (events.length ? events[events.length-1].t : 0);
    _RP = { events, activity: data.activity, duration: Math.max(dur, 0.1), bbox };
    _RP.timeSeries = _computeReplayTimeSeries(events, _RP.duration);
    _PL.playing = false; _PL.playhead = 0; _PL.evIdx = 0; _PL.lastWall = null;
    _resetVisual();

    // Show the right view
    const act = data.activity;
    const viewId = act === 'writing' ? 'replay-view-writing'
                 : act === 'coding'  ? 'replay-view-coding'
                 : 'replay-view-gaming';
    const el = document.getElementById(viewId);
    if (el) el.style.display = (act === 'writing' || act === 'coding') ? 'grid' : 'block';

    if (act !== 'writing' && act !== 'coding') _buildKeyboardDOM('replay-kb-container');

    _renderText(); _renderKeyboard(); _drawMouseCanvas(); _syncUI(); _updatePlayBtn();
    show('replay-container');
    _initReplayCharts();
    _updateReplayCharts(0);
  } catch(e) {
    hide('replay-loading');
    showError('replay-error', 'Impossible de charger les événements : ' + e);
  }
}

function openReplay(sid) {
  _selectedSessionId = sid;
  _replayLoadedFor   = null;
  document.querySelectorAll('.session-row').forEach(r =>
    r.classList.toggle('selected', parseInt(r.dataset.sid) === sid)
  );
  switchTab('replay');
}

// ═══════════════════════════════════════════════════════════════════
// LIVE ENGINE
// ═══════════════════════════════════════════════════════════════════

const _LIVE_FEED_MAX = 120;

const _LIVE_FEED_COLORS = {
  key_press:   'text-blue-400',
  key_release: 'text-gray-600',
  click:       'text-purple-400',
  move:        'text-gray-700',
};

// ── Live charts ────────────────────────────────────────────────────
const _LIVE_WIN_S       = 10;   // sliding window width in seconds
const _LIVE_CHART_MAX   = 30;   // max chart points kept

function _initLiveCharts() {
  if (_liveCharts) { Object.values(_liveCharts).forEach(c => c?.destroy()); }
  const make = (id, color, label) => {
    const canvas = document.getElementById(id);
    if (!canvas) return null;
    return new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: { labels: [], datasets: [{ label, data: [], borderColor: color,
        backgroundColor: color + '22', borderWidth: 2, pointRadius: 2, tension: 0.4, fill: true }] },
      options: {
        animation: false, responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          x: { display: false },
          y: { min: 0, grid: { color: '#21262d' }, ticks: { color: '#8b949e', font: { size: 10 } } }
        }
      }
    });
  };
  _liveCharts = {
    wpm:   make('live-chart-wpm',   '#58a6ff', 'WPM'),
    kps:   make('live-chart-kps',   '#d2a8ff', 'Touches/s'),
    mouse: make('live-chart-mouse', '#2dd4bf', 'Vitesse souris'),
  };
}

function _pushLiveChartPoint(nowTs) {
  if (!_liveCharts) return;
  const cutoff = nowTs - _LIVE_WIN_S;

  // Trim buffers to keep only the last WIN seconds
  while (_liveRecentPresses.length && _liveRecentPresses[0].ts < cutoff) _liveRecentPresses.shift();
  while (_liveRecentMoves.length   && _liveRecentMoves[0].ts   < cutoff) _liveRecentMoves.shift();

  // WPM: printable presses / 5 chars-per-word / (WIN/60 min)
  const chars = _liveRecentPresses.length;
  const wpm   = Math.round((chars / 5) / (_LIVE_WIN_S / 60));

  // KPS
  const kps = Math.round((_liveRecentPresses.length / _LIVE_WIN_S) * 10) / 10;

  // Mouse speed
  let mouseSpeed = 0;
  if (_liveRecentMoves.length >= 2) {
    let totalDist = 0, totalTime = 0;
    for (let i = 1; i < _liveRecentMoves.length; i++) {
      const dx = _liveRecentMoves[i].x - _liveRecentMoves[i-1].x;
      const dy = _liveRecentMoves[i].y - _liveRecentMoves[i-1].y;
      const dt = _liveRecentMoves[i].ts - _liveRecentMoves[i-1].ts;
      if (dt > 0 && dt < 2) { totalDist += Math.sqrt(dx*dx + dy*dy); totalTime += dt; }
    }
    mouseSpeed = totalTime > 0 ? Math.round(totalDist / totalTime) : 0;
  }

  // Update stat numbers
  set('live-stat-wpm', wpm);
  set('live-stat-kps', kps.toFixed(1));
  const mouseEl = document.getElementById('live-stat-mouse-speed');
  if (mouseEl) mouseEl.innerHTML = `${mouseSpeed} <span class="text-xs">px/s</span>`;

  // Push to charts
  const label = new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const pushChart = (c, val) => {
    if (!c) return;
    c.data.labels.push(label);
    c.data.datasets[0].data.push(val);
    if (c.data.labels.length > _LIVE_CHART_MAX) { c.data.labels.shift(); c.data.datasets[0].data.shift(); }
    c.update('none');
  };
  pushChart(_liveCharts.wpm,   wpm);
  pushChart(_liveCharts.kps,   kps);
  pushChart(_liveCharts.mouse, mouseSpeed);
}

// ═══════════════════════════════════════════════════════════════════
function openLive(sid) {
  stopLive();
  _liveSessionId   = sid;
  _liveSince       = 0;
  _liveKbCounts    = {};
  _liveKbLastPress  = {};
  _liveTotalKeys     = 0;
  _liveTotalClicks   = 0;
  _liveTotalMoves    = 0;
  _liveStartedAt     = Date.now();
  _liveRecentPresses = [];
  _liveRecentMoves   = [];

  set('live-session-label', `#${sid}`);
  set('live-stat-keys',     '0');
  set('live-stat-clicks',   '0');
  set('live-stat-moves',    '0');
  set('live-stat-duration', '0s');
  document.getElementById('live-feed').innerHTML =
    '<div class="text-gray-600 italic">En attente d\'événements…</div>';
  hide('live-stopped'); show('live-container');
  hide('live-ended-badge'); show('live-pulse');

  // Show Live tab button
  document.getElementById('tab-live-btn')?.classList.remove('hidden');

  // Build keyboard heatmap
  _buildKeyboardDOM('live-kb-container');

  // Build charts
  _initLiveCharts();

  switchTab('live');

  // Fetch activity label for badge
  fetch(`/api/sentinel/sessions?user_id=`)
    .catch(() => {});
  fetch(`/api/sentinel/session/${sid}/stats`)
    .then(r => r.json())
    .then(d => {
      document.getElementById('live-activity-badge').innerHTML = activityBadge(d.activity || null);
    }).catch(() => {});

  _liveTimer = setInterval(_livePoll, 1000);
  _livePoll();
}

async function _livePoll() {
  if (!_liveSessionId) return;
  try {
    const res  = await fetch(`/api/sentinel/session/${_liveSessionId}/live?since=${_liveSince}`);
    const data = await res.json();
    if (data.error) return;

    _liveSince = data.since;

    // Update ongoing state
    if (!data.ongoing) {
      hide('live-pulse');
      show('live-ended-badge');
      stopLive(/* keepUI */ true);
    }

    // Feed sliding-window buffers (ts is epoch float in seconds)
    const nowTs = data.since || (Date.now() / 1000);
    for (const e of data.keyboard) {
      if (e.type === 'key_press') _liveRecentPresses.push({ ts: e.ts });
    }
    for (const e of data.mouse) {
      if (e.type === 'move') _liveRecentMoves.push({ ts: e.ts, x: e.x, y: e.y });
    }
    _pushLiveChartPoint(nowTs);

    // Accumulate counts
    const presses = data.keyboard.filter(e => e.type === 'key_press');
    _liveTotalKeys   += presses.length;
    _liveTotalClicks += data.mouse.filter(e => e.type === 'click').length;
    _liveTotalMoves  += data.mouse.filter(e => e.type === 'move').length;

    // Update keyboard heatmap
    const now = Date.now();
    for (const e of presses) {
      const kid = _parseKeyId(e.key);
      _liveKbCounts[kid]    = (_liveKbCounts[kid] || 0) + 1;
      _liveKbLastPress[kid] = now;
    }
    _renderLiveKeyboard();

    // Update stats
    set('live-stat-keys',   _liveTotalKeys.toLocaleString());
    set('live-stat-clicks', _liveTotalClicks.toLocaleString());
    set('live-stat-moves',  _liveTotalMoves.toLocaleString());

    const elapsed = Math.round((Date.now() - _liveStartedAt) / 1000);
    set('live-stat-duration', fmtDuration(elapsed));

    const total = _liveTotalKeys + _liveTotalClicks + _liveTotalMoves;
    set('live-event-count', `${total.toLocaleString()} événements`);

    // Append to feed
    const newEvents = [
      ...data.keyboard.map(e => ({
        ts: e.ts, time: e.time,
        device: 'keyboard', etype: e.type, detail: e.key,
      })),
      ...data.mouse.filter(e => e.type !== 'move').map(e => ({
        ts: e.ts, time: new Date(e.ts * 1000).toLocaleTimeString('fr-FR'),
        device: 'mouse', etype: e.type,
        detail: e.type === 'click' ? `${e.button || ''} (${e.x},${e.y})` : `dy=${e.dy} (${e.x},${e.y})`,
      })),
    ].sort((a, b) => a.ts - b.ts);

    if (newEvents.length) _appendLiveFeed(newEvents);

  } catch (_) {}
}

function _appendLiveFeed(events) {
  const feed = document.getElementById('live-feed');
  const placeholder = feed.querySelector('.italic');
  if (placeholder) placeholder.remove();

  const ICONS = { keyboard: '⌨️', mouse: '🖱️' };
  for (const ev of events) {
    const div = document.createElement('div');
    const color = _LIVE_FEED_COLORS[ev.etype] || 'text-gray-400';
    div.className = `flex gap-2 py-0.5 px-1 rounded ${color}`;
    div.innerHTML =
      `<span class="text-gray-600 w-20 shrink-0">${ev.time}</span>` +
      `<span class="w-4">${ICONS[ev.device] || '📡'}</span>` +
      `<span class="w-20 shrink-0">${ev.etype}</span>` +
      `<span class="text-gray-400">${esc(ev.detail || '')}</span>`;
    feed.prepend(div);
  }
  while (feed.children.length > _LIVE_FEED_MAX) feed.lastChild.remove();
}

const _LIVE_KB_DECAY_S = 2; // seconds until a key fully fades

function _renderLiveKeyboard() {
  const container = document.getElementById('live-kb-container');
  if (!container) return;
  const now = Date.now();
  container.querySelectorAll('.kb-key').forEach(el => {
    const kid   = el.dataset.kid;
    const count = _liveKbCounts[kid] || 0;
    const cntEl = el.querySelector('.kb-cnt');
    // Always show count when > 0
    if (cntEl) cntEl.textContent = count > 0 ? (count > 9999 ? Math.round(count/1000)+'k' : count) : '';
    if (count > 0) {
      const age  = (now - (_liveKbLastPress[kid] || 0)) / 1000;
      const heat = Math.max(0, 1 - age / _LIVE_KB_DECAY_S);
      if (heat > 0) {
        const r = Math.round(13+heat*75), g = Math.round(42+heat*124), b = Math.round(95+heat*160);
        el.style.background  = `rgb(${r},${g},${b})`;
        el.style.color       = heat > 0.6 ? '#0d1117' : '#c9d1d9';
        el.style.borderColor = `rgb(${r},${g},${b})`;
      } else {
        // Fully decayed: dark bg, dim text so the count remains readable
        el.style.background  = '#21262d';
        el.style.color       = '#6e7681';
        el.style.borderColor = '#30363d';
      }
    } else {
      el.style.background  = '#21262d';
      el.style.color       = '#484f58';
      el.style.borderColor = '#30363d';
    }
    el.style.boxShadow = 'none';
  });
}

function clearLiveFeed() {
  document.getElementById('live-feed').innerHTML =
    '<div class="text-gray-600 italic">Vidé.</div>';
}

function stopLive(keepUI = false) {
  if (_liveTimer) { clearInterval(_liveTimer); _liveTimer = null; }
  if (!keepUI) {
    _liveSessionId = null;
    hide('live-container'); show('live-stopped');
    document.getElementById('tab-live-btn')?.classList.add('hidden');
    switchTab('sessions');
  }
}

// ── Auto-refresh (15s) ────────────────────────────────────────────
const _AUTO_REFRESH_S = 5;

function _autoRefresh() {
  const active = ['users','sessions','metrics','replay'].find(t =>
    !document.getElementById(`tab-${t}`)?.classList.contains('hidden')
  );
  if (!active) return;
  const selectedOngoing = _selectedSessionId != null &&
    document.querySelector(`.session-row[data-sid="${_selectedSessionId}"]`)?.dataset.ongoing === '1';
  if (active === 'users') {
    loadUsers();
  } else if (active === 'sessions') {
    reloadSessions();
  } else if (active === 'metrics' && selectedOngoing) {
    loadMetrics(_selectedSessionId);
  } else if (active === 'replay' && selectedOngoing && !_PL.playing) {
    loadReplay(_selectedSessionId);
  }
}

// ── Init ──────────────────────────────────────────────────────────
loadUsers();
setInterval(_autoRefresh, _AUTO_REFRESH_S * 1000);
