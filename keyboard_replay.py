"""
Keyboard replay — generates a self-contained HTML page and opens it in the browser.

Usage:
    uv run keyboard_replay.py                        # uses keyboard_events.parquet
    uv run keyboard_replay.py --file my_session.parquet
    uv run keyboard_replay.py --no-open             # generate HTML without opening
"""

import argparse
import http.server
import json
import os
import threading
import webbrowser
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser()
parser.add_argument("--file", default="keyboard_events.parquet")
parser.add_argument(
    "--no-open", action="store_true", help="Don't auto-open the browser"
)
parser.add_argument(
    "--port", type=int, default=0, help="HTTP port (0 = pick a free one)"
)
args = parser.parse_args()

parquet_path = Path(args.file)
if not parquet_path.is_absolute():
    parquet_path = Path(__file__).parent / parquet_path

# ---------------------------------------------------------------------------
# Load + prepare data
# ---------------------------------------------------------------------------
df = pd.read_parquet(parquet_path).sort_values("elapsed_s").reset_index(drop=True)

events = df[["elapsed_s", "event", "key"]].to_dict(orient="records")

presses = df[df["event"] == "press"]
duration = float(df["elapsed_s"].iloc[-1] - df["elapsed_s"].iloc[0])
char_presses = presses[~presses["key"].str.startswith("Key.")]
wpm = (len(char_presses) / 5) / max(duration / 60, 0.001)

stats = {
    "total_events": len(df),
    "presses": int(len(presses)),
    "duration_s": round(duration, 2),
    "wpm": round(wpm, 1),
    "unique_keys": int(presses["key"].nunique()),
}

# ---------------------------------------------------------------------------
# HTML template  (EVENTS_JSON and STATS_JSON are placeholder tokens)
# ---------------------------------------------------------------------------
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>⌨️ Keyboard Replay</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #0d1117; color: #c9d1d9;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    min-height: 100vh;
    display: flex; flex-direction: column; align-items: center;
    padding: 2rem 1rem; gap: 1.5rem;
  }
  h1 { font-size: 1.6rem; color: #58a6ff; }

  /* Stats */
  .stats { display: flex; gap: 1rem; flex-wrap: wrap; justify-content: center; }
  .stat-card {
    background: #161b22; border: 1px solid #30363d; border-radius: 10px;
    padding: 0.8rem 1.4rem; text-align: center; min-width: 100px;
  }
  .stat-card .val { font-size: 1.6rem; font-weight: 700; color: #58a6ff; }
  .stat-card .lbl { font-size: 0.72rem; color: #8b949e; margin-top: 2px;
                    text-transform: uppercase; letter-spacing: .05em; }

  /* Text display */
  .text-box {
    width: 100%; max-width: 760px;
    background: #161b22; border: 1px solid #30363d; border-radius: 10px;
    padding: 1.2rem 1.4rem; min-height: 130px;
    font-family: 'Courier New', Courier, monospace;
    font-size: 1.3rem; line-height: 1.85;
    white-space: pre-wrap; word-break: break-word;
  }
  .cursor {
    display: inline-block; width: 2px; height: 1.1em;
    background: #58a6ff; vertical-align: middle; margin-left: 1px;
    animation: blink 1s step-end infinite;
  }
  @keyframes blink { 50% { opacity: 0; } }
  .new-char  { background: #1f6feb; color: #fff; border-radius: 3px; padding: 0 2px; }
  .del-char  { background: #b91c1c; color: #fff; border-radius: 3px; padding: 0 2px;
               text-decoration: line-through; }

  /* Held-keys row */
  .keys-area {
    width: 100%; max-width: 760px; min-height: 44px;
    display: flex; flex-wrap: wrap; align-items: center; gap: 6px;
  }
  .key-badge {
    font-family: 'Courier New', monospace; font-size: 0.8rem; font-weight: 700;
    padding: 4px 10px; border-radius: 6px; border: 1px solid rgba(255,255,255,.12);
    animation: pop .12s ease-out;
  }
  @keyframes pop { from { transform: scale(1.35); } to { transform: scale(1); } }
  .key-char     { background: #1f6feb; color: #fff; }
  .key-modifier { background: #7c3aed; color: #fff; }
  .key-special  { background: #0d9488; color: #fff; }
  .key-delete   { background: #b91c1c; color: #fff; }
  .no-keys-msg  { color: #444; font-size: 0.82rem; }

  /* Timeline scrubber */
  .timeline-row {
    width: 100%; max-width: 760px;
    display: flex; align-items: center; gap: 10px;
  }
  #timeline {
    flex: 1; height: 6px; accent-color: #1f6feb;
    cursor: pointer;
  }
  .time-label {
    font-size: 0.78rem; color: #8b949e; white-space: nowrap;
    min-width: 90px; text-align: right; font-family: 'Courier New', monospace;
  }

  /* Controls */
  .controls {
    display: flex; gap: 0.75rem; align-items: center;
    flex-wrap: wrap; justify-content: center;
  }
  button {
    padding: .55rem 1.4rem; border-radius: 8px;
    border: 1px solid #30363d; background: #21262d;
    color: #c9d1d9; font-size: .95rem; cursor: pointer;
    transition: background .15s;
  }
  button:hover    { background: #30363d; }
  button.primary  { background: #1f6feb; border-color: #1f6feb; color: #fff; }
  button.primary:hover { background: #388bfd; }
  button:disabled { opacity: .4; cursor: not-allowed; }
  label { font-size: .88rem; color: #8b949e; }
  input[type=range] { accent-color: #1f6feb; width: 110px; }
  #speed-val { color: #58a6ff; font-weight: 600; min-width: 32px; display: inline-block; }
  .status { font-size: .82rem; color: #8b949e; min-height: 18px; }

  /* Countdown overlay */
  #countdown {
    display: none; font-size: 5rem; font-weight: 900; color: #58a6ff;
    position: fixed; top: 50%; left: 50%; transform: translate(-50%,-50%);
    animation: pop .4s ease-out; pointer-events: none;
  }
</style>
</head>
<body>

<h1>⌨️ Keyboard Replay</h1>

<div class="stats" id="stats"></div>

<div class="text-box" id="text-box"><span class="cursor"></span></div>

<div class="keys-area" id="keys-area">
  <span class="no-keys-msg">No keys held …</span>
</div>

<div class="timeline-row">
  <input type="range" id="timeline" min="0" max="1" step="0.001" value="0"
    oninput="onTimelineDrag(this)" onchange="onTimelineRelease(this)">
  <span class="time-label" id="time-label">0.00s / 0.00s</span>
</div>
<div class="status" id="status">Ready — press Replay to start.</div>

<div class="controls">
  <button class="primary" id="btn-play"  onclick="startReplay()">▶ Replay</button>
  <button id="btn-pause" onclick="togglePause()" disabled>⏸ Pause</button>
  <button id="btn-reset" onclick="resetAll()">↺ Reset</button>
  <label>Speed
    <input type="range" id="speed" min="0.25" max="8" step="0.25" value="1"
      oninput="onSpeedChange(this)">
    <span id="speed-val">1x</span>
  </label>
</div>

<div id="countdown"></div>

<script>
const EVENTS = EVENTS_JSON;
const STATS  = STATS_JSON;

const MODIFIERS = new Set([
  'Key.shift','Key.ctrl','Key.ctrl_l','Key.ctrl_r',
  'Key.alt','Key.alt_l','Key.alt_r','Key.alt_gr',
  'Key.cmd','Key.cmd_l','Key.cmd_r','Key.caps_lock'
]);
const DELETE_KEYS = new Set(['Key.backspace','Key.delete']);
const SPECIAL_LABELS = {
  'Key.space':'SPACE','Key.enter':'ENTER ↵','Key.tab':'TAB →',
  'Key.esc':'ESC','Key.end':'END','Key.home':'HOME',
  'Key.up':'↑','Key.down':'↓','Key.left':'←','Key.right':'→',
  'Key.page_up':'PG↑','Key.page_down':'PG↓',
  'Key.shift':'SHIFT','Key.ctrl':'CTRL','Key.ctrl_l':'CTRL','Key.ctrl_r':'CTRL',
  'Key.alt':'ALT','Key.alt_l':'ALT','Key.alt_r':'ALT','Key.alt_gr':'ALTGR',
  'Key.cmd':'⌘','Key.caps_lock':'CAPS','Key.backspace':'⌫ BKSP','Key.delete':'DEL',
  'Key.f1':'F1','Key.f2':'F2','Key.f3':'F3','Key.f4':'F4',
  'Key.f5':'F5','Key.f6':'F6','Key.f7':'F7','Key.f8':'F8',
  'Key.f9':'F9','Key.f10':'F10','Key.f11':'F11','Key.f12':'F12',
};

// Render stats cards
(function(){
  const s = STATS;
  document.getElementById('stats').innerHTML = [
    [s.presses,                'Key Presses'],
    [s.duration_s.toFixed(1)+'s', 'Duration'],
    [s.wpm.toFixed(0),         '~WPM'],
    [s.unique_keys,            'Unique Keys'],
    [s.total_events,           'Total Events'],
  ].map(([v,l]) =>
    `<div class="stat-card"><div class="val">${v}</div><div class="lbl">${l}</div></div>`
  ).join('');
})();

// ---- helpers ----
function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function keyCategory(k) {
  if (DELETE_KEYS.has(k))    return 'delete';
  if (MODIFIERS.has(k))      return 'modifier';
  if (k.startsWith('Key.'))  return 'special';
  return 'char';
}
function keyLabel(k) { return SPECIAL_LABELS[k] || k.replace('Key.','').toUpperCase(); }

// ---- render text ----
let _delFlashTimer = null;
function renderText(highlight, deleting, deletedChar) {
  const box = document.getElementById('text-box');
  let body = esc(textBuf).replace(/\n/g,'<br>');

  if (deleting && deletedChar) {
    box.innerHTML = body + `<span class="del-char">${esc(deletedChar)}</span><span class="cursor"></span>`;
    if (_delFlashTimer) clearTimeout(_delFlashTimer);
    _delFlashTimer = setTimeout(() => renderText(false, false, null), 110);
    return;
  }
  if (highlight && textBuf.length > 0) {
    // wrap last char in highlight span
    const last = body.endsWith(';') ? '' : body.slice(-1);
    if (last && last !== '>') body = body.slice(0,-1) + `<span class="new-char">${last}</span>`;
  }
  box.innerHTML = body + '<span class="cursor"></span>';
}

function renderHeldKeys() {
  const area = document.getElementById('keys-area');
  if (held.size === 0) { area.innerHTML = '<span class="no-keys-msg">No keys held …</span>'; return; }
  area.innerHTML = [...held].sort().map(k =>
    `<span class="key-badge key-${keyCategory(k)}">${esc(keyLabel(k))}</span>`
  ).join('');
}

function setStatus(msg) { document.getElementById('status').textContent = msg; }

// ---- countdown ----
function countdown(n, cb) {
  const el = document.getElementById('countdown');
  el.style.display = 'block';
  let i = n;
  (function tick() {
    if (i < 1) { el.style.display = 'none'; cb(); return; }
    el.textContent = i--;
    el.style.animation = 'none'; void el.offsetWidth; el.style.animation = 'pop .4s ease-out';
    setTimeout(tick, 1000);
  })();
}

// ---- state ----
let textBuf = '', held = new Set();
let timer = null, paused = false;
let eventIdx = 0, replayStart = 0, pausedAt = 0, speed = 1;
let started = false;  // true once replay has begun at least once
const TOTAL_DURATION = EVENTS.length ? EVENTS[EVENTS.length-1].elapsed_s : 1;

// Initialise timeline max once EVENTS are known
document.getElementById('timeline').max = TOTAL_DURATION;
document.getElementById('timeline').step = TOTAL_DURATION / 1000;

// ---- clock tick: keeps timeline & time-label updating during silent gaps ----
function clockTick() {
  if (started && !paused && !_isDragging) {
    const nowElapsed = Math.min(
      (performance.now() - replayStart) / 1000 * speed,
      TOTAL_DURATION
    );
    document.getElementById('timeline').value = nowElapsed;
    document.getElementById('time-label').textContent =
      `${nowElapsed.toFixed(2)}s / ${TOTAL_DURATION.toFixed(2)}s`;
  }
  requestAnimationFrame(clockTick);
}
requestAnimationFrame(clockTick);
document.getElementById('time-label').textContent = `0.00s / ${TOTAL_DURATION.toFixed(2)}s`;

// ---- seek: rebuild state up to targetElapsed instantly ----
function seekTo(targetElapsed) {
  // find the first event index at or after targetElapsed
  let newIdx = EVENTS.findIndex(e => e.elapsed_s > targetElapsed);
  if (newIdx === -1) newIdx = EVENTS.length;

  // fast-replay all press events up to newIdx to rebuild text & held
  let buf = '', heldSet = new Set();
  for (let i = 0; i < newIdx; i++) {
    const {key, event} = EVENTS[i];
    if (event === 'press') {
      heldSet.add(key);
      if (key.length === 1)         buf += key;
      else if (key === 'Key.space') buf += ' ';
      else if (key === 'Key.enter') buf += '\n';
      else if (DELETE_KEYS.has(key) && buf.length > 0) buf = buf.slice(0,-1);
    } else {
      heldSet.delete(key);
    }
  }

  textBuf  = buf;
  held     = heldSet;
  eventIdx = newIdx;

  // recalibrate the virtual clock so scheduleNext fires at the right delay
  replayStart = performance.now() - targetElapsed * 1000 / speed;

  renderText(false, false, null);
  renderHeldKeys();

  const frac = TOTAL_DURATION > 0 ? targetElapsed / TOTAL_DURATION : 0;
  document.getElementById('timeline').value = targetElapsed;
  document.getElementById('time-label').textContent =
    `${targetElapsed.toFixed(2)}s / ${TOTAL_DURATION.toFixed(2)}s`;
  setStatus(`Seeked to ${targetElapsed.toFixed(2)}s — Event ${newIdx} / ${EVENTS.length}`);
}

// ---- timeline drag / release handlers ----
let _wasPaused = false;
let _isDragging = false;
function onTimelineDrag(el) {
  if (!_isDragging) {
    // first tick of this drag — snapshot whether we were already paused
    _wasPaused  = paused;
    _isDragging = true;
    // pause playback for the duration of the drag
    if (started && !paused) {
      paused = true;
      if (timer) clearTimeout(timer);
    }
  }
  const t = parseFloat(el.value);
  document.getElementById('time-label').textContent =
    `${t.toFixed(2)}s / ${TOTAL_DURATION.toFixed(2)}s`;
}
function onTimelineRelease(el) {
  _isDragging = false;
  const t = parseFloat(el.value);
  if (!started) {
    // replay not started yet — seek and begin playing from this position
    speed = parseFloat(document.getElementById('speed').value);
    document.getElementById('btn-play').disabled  = true;
    document.getElementById('btn-pause').disabled = false;
    started = true;
    paused  = false;
    seekTo(t);
    scheduleNext();
    return;
  }
  seekTo(t);
  if (!_wasPaused) {
    // was playing before drag — resume
    paused = false;
    document.getElementById('btn-pause').textContent = '\u23f8 Pause';
    scheduleNext();
  }
}

function onSpeedChange(el) {
  const newSpeed = parseFloat(el.value);
  document.getElementById('speed-val').textContent = newSpeed + 'x';
  if (!started) { speed = newSpeed; return; }
  // Use pausedAt as reference when paused so position doesn't drift
  const refNow = paused ? pausedAt : performance.now();
  const currentElapsed = (refNow - replayStart) / 1000 * speed;
  speed = newSpeed;
  replayStart = refNow - currentElapsed * 1000 / speed;
  if (paused) {
    // Reset pausedAt so togglePause's compensation accounts only for future pause time
    pausedAt = performance.now();
  } else {
    if (timer) clearTimeout(timer);
    scheduleNext();
  }
}

function scheduleNext() {
  if (paused || eventIdx >= EVENTS.length) return;
  const target = EVENTS[eventIdx].elapsed_s / speed;
  const now    = (performance.now() - replayStart) / 1000;
  timer = setTimeout(processEvent, Math.max(0, (target - now) * 1000));
}

function processEvent() {
  if (paused || eventIdx >= EVENTS.length) return;
  const {key, event, elapsed_s} = EVENTS[eventIdx];
  let highlight = false, deleting = false, deletedChar = null;

  if (event === 'press') {
    held.add(key);
    if (key.length === 1)         { textBuf += key;    highlight = true; }
    else if (key === 'Key.space') { textBuf += ' ';    highlight = true; }
    else if (key === 'Key.enter') { textBuf += '\n';   highlight = true; }
    else if (DELETE_KEYS.has(key) && textBuf.length > 0) {
      deletedChar = textBuf.slice(-1);
      textBuf     = textBuf.slice(0, -1);
      deleting    = true;
    }
  } else {
    held.delete(key);
  }

  renderText(highlight, deleting, deletedChar);
  renderHeldKeys();
  setStatus(`Event ${eventIdx + 1} / ${EVENTS.length}  (${elapsed_s.toFixed(2)}s)`);

  eventIdx++;
  if (eventIdx < EVENTS.length) {
    scheduleNext();
  } else {
    setStatus('✅ Replay complete!');
    document.getElementById('btn-pause').disabled = true;
    document.getElementById('btn-play').disabled  = false;
    held.clear(); renderHeldKeys();
  }
}

function resetAll() {
  if (timer) clearTimeout(timer);
  textBuf = ''; held = new Set(); eventIdx = 0; paused = false;
  renderText(false, false, null);
  renderHeldKeys();
  document.getElementById('timeline').value = 0;
  document.getElementById('time-label').textContent = `0.00s / ${TOTAL_DURATION.toFixed(2)}s`;
  document.getElementById('btn-pause').disabled  = true;
  document.getElementById('btn-pause').textContent = '⏸ Pause';
  document.getElementById('btn-play').disabled   = false;
  started = false;
  setStatus('Ready — press Replay to start.');
}

function startReplay() {
  resetAll();
  speed = parseFloat(document.getElementById('speed').value);
  document.getElementById('btn-play').disabled  = true;
  document.getElementById('btn-pause').disabled = false;
  countdown(3, () => { replayStart = performance.now(); started = true; scheduleNext(); });
}

function togglePause() {
  const btn = document.getElementById('btn-pause');
  if (!paused) {
    paused = true; pausedAt = performance.now();
    if (timer) clearTimeout(timer);
    btn.textContent = '▶ Resume'; setStatus('Paused.');
  } else {
    paused = false; replayStart += performance.now() - pausedAt;
    btn.textContent = '⏸ Pause'; scheduleNext();
  }
}
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Inject data and write
# ---------------------------------------------------------------------------
events_json = json.dumps(events, ensure_ascii=False)
stats_json = json.dumps(stats, ensure_ascii=False)
html_out = HTML_TEMPLATE.replace("EVENTS_JSON", events_json).replace(
    "STATS_JSON", stats_json
)

out_path = Path(__file__).parent / "keyboard_replay.html"
out_path.write_text(html_out, encoding="utf-8")
print(f"Generated: {out_path}")

# ---------------------------------------------------------------------------
# Serve over HTTP so the browser doesn't close / block file:// access
# ---------------------------------------------------------------------------
serve_dir = str(out_path.parent)
handler = http.server.SimpleHTTPRequestHandler


class QuietHandler(handler):
    def log_message(self, *_):
        pass  # suppress request noise


server = http.server.HTTPServer(("127.0.0.1", args.port), QuietHandler)
port = server.server_address[1]
url = f"http://127.0.0.1:{port}/keyboard_replay.html"

thread = threading.Thread(target=server.serve_forever, daemon=True)
os.chdir(serve_dir)
thread.start()

print(f"Serving at:  {url}")
print("Press Ctrl+C to stop.\n")

if not args.no_open:
    webbrowser.open(url)

try:
    thread.join()
except KeyboardInterrupt:
    print("\nServer stopped.")
    server.shutdown()
