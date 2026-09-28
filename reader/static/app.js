"use strict";

// ------------------------------------------------------------ tien ich
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

const prefs = {
  get(key, fallback) {
    try {
      const raw = localStorage.getItem("reader." + key);
      return raw === null ? fallback : JSON.parse(raw);
    } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem("reader." + key, JSON.stringify(value)); } catch { /* bo qua */ }
  },
};

async function api(path, opts = {}) {
  const init = { method: opts.method || (opts.body !== undefined || opts.raw !== undefined ? "POST" : "GET"), headers: {} };
  if (opts.raw !== undefined) init.body = opts.raw;
  else if (opts.body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(opts.body);
  }
  let res;
  try { res = await fetch("/api/" + path, init); }
  catch { throw new Error("Không kết nối được Trợ lý đọc. Hãy mở lại bằng file Start Doc Reader.cmd."); }
  let data = null;
  try { data = await res.json(); } catch { /* khong phai json */ }
  if (!res.ok) throw new Error((data && data.error) || `Lỗi ${res.status}`);
  return data;
}

function toast(message, isError = false, ms = 3200) {
  const node = el("div", { class: "toast" + (isError ? " err" : "") }, message);
  $("#toasts").append(node);
  setTimeout(() => node.remove(), isError ? ms + 2500 : ms);
  return node;
}

function shortTime(text) {
  if (!text) return "";
  const [date, time] = text.split(" ");
  const today = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const todayText = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`;
  if (date === todayText) return time;
  const [, m, d] = date.split("-");
  return `${d}/${m} ${time}`;
}

function minutesText(seconds) {
  if (seconds < 60) return "dưới 1 phút";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} phút`;
  return `${Math.floor(minutes / 60)} giờ ${minutes % 60} phút`;
}

// ------------------------------------------------------------ trang thai
const CHARS_PER_SECOND = 14;
const state = {
  library: [],
  notesDir: "",
  doc: null,
  idx: 0,
  playing: false,
  speed: prefs.get("speed", 1),
  voice: prefs.get("voice", "vi-VN-NamMinhNeural"),
  talk: prefs.get("talk", true),
  natural: prefs.get("natural", true),
  justImported: null,
  en: prefs.get("en", true),
  resume: prefs.get("resume", true),
  follow: prefs.get("follow", true),
  skipLists: prefs.get("skipLists", false),
  autoDictate: prefs.get("autoDictate", false),
  fontSize: prefs.get("font", 20),
  theme: prefs.get("theme", "auto"),
  filter: "all",
  composer: null,
  wasPlaying: false,
  selection: null,
};
let sentenceEls = [];
let remainingChars = [];
let lastUserScroll = 0;

// ------------------------------------------------------------ thu vien
async function loadLibrary() {
  const data = await api("library");
  state.library = data.items;
  state.notesDir = data.notes_dir;
  renderLibrary();
}

function renderLibrary() {
  const list = $("#libList");
  list.innerHTML = "";
  $("#libCount").textContent = state.library.length ? String(state.library.length) : "";
  if (!state.library.length) {
    list.append(el("div", { class: "lib-empty" }, "Chưa có tài liệu nào. Mở file hoặc dán nội dung để bắt đầu."));
    return;
  }
  for (const item of state.library) {
    const pct = item.total > 1 ? Math.round((item.position / (item.total - 1)) * 100) : 0;
    const meta = [
      el("span", {}, pct >= 99 ? "Đã nghe hết" : `${pct}%`),
      el("span", {}, minutesText(item.chars / CHARS_PER_SECOND)),
      item.notes ? el("span", { class: "badge n" }, `${item.notes} ghi chú`) : null,
      item.open_questions ? el("span", { class: "badge q" }, `${item.open_questions} câu hỏi`) : null,
    ];
    const button = el("button", {
      class: "lib-item" + (state.doc && state.doc.id === item.id ? " on" : ""),
      title: item.source || item.title,
      onclick: () => openDoc(item.id),
    },
      el("div", { class: "lib-title" }, item.title),
      el("div", { class: "lib-meta" }, meta),
      el("div", { class: "lib-bar" }, el("i", { style: `width:${pct}%` })),
    );
    const del = el("span", {
      class: "lib-del", role: "button", tabindex: "0", title: "Xoá khỏi thư viện", "aria-label": "Xoá khỏi thư viện",
      onclick: (event) => { event.stopPropagation(); removeDoc(item); },
    });
    del.innerHTML = '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>';
    button.append(del);
    list.append(button);
  }
}

async function removeDoc(item) {
  if (!confirm(`Xoá "${item.title}" khỏi thư viện?\n\nFile ghi chú Markdown của tài liệu này vẫn được giữ lại.`)) return;
  try {
    await api(`doc/${item.id}`, { method: "DELETE" });
    if (state.doc && state.doc.id === item.id) closeDoc();
    await loadLibrary();
  } catch (err) { toast(err.message, true); }
}

// ------------------------------------------------------------ mo tai lieu
async function openDoc(id) {
  try {
    showDoc(await api(`doc/${id}?${segQuery()}&natural=${state.natural ? 1 : 0}`));
  } catch (err) {
    toast(err.message, true);
    if (location.hash.includes(id)) history.replaceState(null, "", location.pathname);
  }
}

function showDoc(doc) {
  stopPlayback();
  state.doc = doc;
  remainingChars = new Array(doc.sentences.length + 1);
  remainingChars[doc.sentences.length] = 0;
  for (let i = doc.sentences.length - 1; i >= 0; i--) {
    remainingChars[i] = remainingChars[i + 1] + doc.sentences[i].t.length;
  }
  state.idx = Math.min(doc.position || 0, doc.sentences.length - 1);
  closeComposer();
  $("#docTitle").textContent = doc.title;
  document.title = `${doc.title} · Trợ lý đọc`;
  const sourceLabel = { file: "File", url: "Link", upload: "File tải lên", text: "Văn bản dán vào" }[doc.source_type] || "";
  $("#docSource").textContent = [sourceLabel, doc.source && doc.source_type !== "text" ? doc.source : ""].filter(Boolean).join(": ");
  $("#docActions").hidden = false;
  $("#btnSource").hidden = !["file", "url"].includes(doc.source_type);
  $("#btnReload").hidden = !["file", "url"].includes(doc.source_type);
  $("#notesFoot").hidden = false;
  history.replaceState(null, "", `#doc=${doc.id}`);
  prefs.set("lastDoc", doc.id);
  renderDoc();
  renderNotes();
  setCurrent(state.idx, { force: true, save: false });
  loadSegments().catch(() => {});
  // font web tai xong lam doi bo cuc, can lai cho cau dang doc nam giua man hinh
  if (document.fonts) document.fonts.ready.then(() => { if (state.doc === doc && sentenceEls[state.idx]) keepVisible(sentenceEls[state.idx], true); });
  const known = state.library.find((item) => item.id === doc.id);
  if (!known) loadLibrary(); else renderLibrary();
  document.getElementById("app").classList.remove("show-lib");
  if ("mediaSession" in navigator) {
    navigator.mediaSession.metadata = new MediaMetadata({ title: doc.title, artist: "Trợ lý đọc" });
  }
}

function closeDoc() {
  stopPlayback();
  state.doc = null;
  sentenceEls = [];
  remainingChars = [];
  $("#doc").innerHTML = "";
  $("#doc").append(emptyTemplate.cloneNode(true));
  $("#docTitle").textContent = "Chưa mở tài liệu";
  $("#docSource").textContent = "";
  $("#docActions").hidden = true;
  $("#notesFoot").hidden = true;
  document.title = "Trợ lý đọc";
  history.replaceState(null, "", location.pathname);
  renderNotes();
  updateStatus();
}

function renderDoc() {
  const doc = state.doc;
  const root = $("#doc");
  root.innerHTML = "";
  sentenceEls = new Array(doc.sentences.length);
  if (doc.reloaded) {
    root.append(el("div", { class: "doc-banner" }, el("b", {}, "Đã cập nhật nội dung mới"), ` lúc ${shortTime(doc.reloaded)}. Ghi chú cũ được gắn lại vào đúng câu nếu câu đó vẫn còn.`));
  }
  let list = null;
  doc.blocks.forEach((block) => {
    let node;
    if (block.type === "li") {
      if (!list) { list = el("ul"); root.append(list); }
      node = el("li");
      list.append(node);
    } else {
      list = null;
      const tag = block.type === "quote" ? "blockquote" : block.type === "code" ? "pre" : block.type.startsWith("h") ? block.type : "p";
      node = el(tag);
      root.append(node);
    }
    for (let i = block.start; i < block.end; i++) {
      const span = el("span", { class: "s", "data-i": i }, doc.sentences[i].t);
      sentenceEls[i] = span;
      node.append(span);
      if (i < block.end - 1) node.append(" ");
    }
  });
  decorateNotes();
}

function sortedNotes() {
  return (state.doc ? state.doc.notes : []).slice().sort((a, b) => a.i - b.i || a.created.localeCompare(b.created));
}

function decorateNotes() {
  $$(".note-pin", $("#doc")).forEach((pin) => pin.remove());
  $$(".s.noted", $("#doc")).forEach((span) => span.classList.remove("noted", "q-open"));
  const marks = $("#progressMarks");
  marks.innerHTML = "";
  if (!state.doc) return;
  const total = Math.max(1, state.doc.sentences.length);
  sortedNotes().forEach((note) => {
    const span = sentenceEls[note.i];
    const openQ = note.kind === "question" && !note.done;
    marks.append(el("i", { class: openQ ? "q" : "", style: `left:${(note.i / total) * 100}%` }));
    if (!span) return;
    span.classList.add("noted");
    if (openQ) span.classList.add("q-open");
    const pin = el("button", {
      class: "note-pin" + (note.kind === "question" ? " q" : ""),
      title: (note.kind === "question" ? "Câu hỏi: " : "Ghi chú: ") + (note.text || note.quote).slice(0, 140),
      onclick: (event) => { event.stopPropagation(); focusNoteCard(note.id); },
    }, note.kind === "question" ? "?" : "✎");
    span.after(pin);
  });
}

// ------------------------------------------------------------ vi tri doc
function speakable(i) {
  const doc = state.doc;
  const block = doc.blocks[doc.sentences[i].b];
  if (block.type === "code") return false;
  if (state.skipLists && block.type === "li") return false;
  return true;
}

function nextSpeakable(i, dir = 1) {
  const n = state.doc.sentences.length;
  while (i >= 0 && i < n && !speakable(i)) i += dir;
  return i >= 0 && i < n ? i : -1;
}

let savePositionTimer = 0;
function setCurrent(i, { force = false, save = true } = {}) {
  if (!state.doc) return;
  i = Math.max(0, Math.min(i, state.doc.sentences.length - 1));
  const prev = sentenceEls[state.idx];
  if (prev) prev.classList.remove("cur");
  state.idx = i;
  const cur = sentenceEls[i];
  if (cur) {
    cur.classList.add("cur");
    if (force || (state.follow && Date.now() - lastUserScroll > 5000)) keepVisible(cur, force);
  }
  $$(".note").forEach((card) => card.classList.toggle("cur", Number(card.dataset.i) === i));
  updateStatus();
  if (save) {
    clearTimeout(savePositionTimer);
    const docId = state.doc.id;
    savePositionTimer = setTimeout(async () => {
      try {
        const summary = await api(`doc/${docId}/position`, { body: { i } });
        const index = state.library.findIndex((item) => item.id === docId);
        if (index >= 0) { state.library[index] = summary; renderLibrary(); }
      } catch { /* mat ket noi tam thoi, lan sau luu lai */ }
    }, 900);
  }
}

function keepVisible(node, force) {
  const box = $("#docScroll").getBoundingClientRect();
  const rect = node.getBoundingClientRect();
  const top = box.top + box.height * 0.18;
  const bottom = box.top + box.height * 0.72;
  if (force || rect.top < top || rect.bottom > bottom) {
    node.scrollIntoView({ block: "center", behavior: force ? "auto" : "smooth" });
  }
}

function updateStatus() {
  const doc = state.doc;
  if (!doc) {
    $("#statusPos").textContent = "Chưa mở tài liệu";
    $("#statusLeft").textContent = "";
    $(".dot-sep").hidden = true;
    $("#progressFill").style.width = "0";
    return;
  }
  const total = doc.sentences.length;
  const chars = remainingChars[state.idx] || 0;
  $(".dot-sep").hidden = false;
  $("#statusPos").textContent = `Câu ${state.idx + 1}/${total}`;
  $("#statusLeft").textContent = `còn khoảng ${minutesText(chars / (CHARS_PER_SECOND * state.speed))}`;
  $("#progressFill").style.width = `${total > 1 ? (state.idx / (total - 1)) * 100 : 100}%`;
}

// ------------------------------------------------------------ phat am thanh
const audioPool = new Map();
let current = null;
let playToken = 0;
let retried = new Set();
const WAIT_MAX_TRIES = 60; // thu lai moi 5 giay, toi da 5 phut
let waitTries = 0;
let retryWait = null;

function clearRetryWait() {
  if (!retryWait) return;
  clearTimeout(retryWait.timer);
  window.removeEventListener("online", retryWait.resume);
  retryWait = null;
}

function ttsUrl(i, bust = "") {
  // che do doc lien: cau le chi la tam thoi, khong can may chu tao truoc cac cau sau
  const ahead = state.natural ? "&ahead=0" : "";
  return `/api/tts/${state.doc.id}/${i}?voice=${encodeURIComponent(state.voice)}&en=${state.en ? 1 : 0}${ahead}${bust}`;
}

function audioKey(i) { return `${state.doc.id}|${i}|${state.voice}|${state.en}`; }

function getAudio(i) {
  const key = audioKey(i);
  let audio = audioPool.get(key);
  if (!audio) {
    audio = new Audio();
    audio.preload = "auto";
    audio.src = ttsUrl(i);
    audio.dataset.i = String(i);
    audioPool.set(key, audio);
  }
  return audio;
}

function trimPool(center) {
  for (const [key, audio] of audioPool) {
    const i = Number(audio.dataset.i);
    if (audio !== current && (i < center - 1 || i > center + 4 || !key.startsWith(state.doc.id + "|"))) {
      audio.removeAttribute("src");
      audio.load();
      audioPool.delete(key);
    }
  }
}

function preload(i) {
  let n = i;
  const count = state.natural ? 1 : 2; // doc lien: cau le chi can them 1 cau du phong
  for (let k = 0; k < count; k++) {
    n = nextSpeakable(n + 1, 1);
    if (n < 0) break;
    getAudio(n);
  }
  trimPool(i);
}

function setLoading(on) { document.getElementById("app").classList.toggle("loading", on); }

function updatePlayUI() {
  const app = document.getElementById("app");
  app.classList.toggle("playing", state.playing);
  if (!state.playing) setLoading(false);
  $("#btnPlay").setAttribute("aria-label", state.playing ? "Tạm dừng" : "Đọc");
  if ("mediaSession" in navigator) navigator.mediaSession.playbackState = state.playing ? "playing" : "paused";
}

function continueAfter(i, token) {
  if (token !== playToken || !state.playing) return;
  const next = nextSpeakable(i + 1, 1);
  if (next < 0) { finish(); return; }
  const doc = state.doc;
  const newBlock = doc.sentences[next].b !== doc.sentences[i].b;
  const heading = doc.blocks[doc.sentences[i].b].type.startsWith("h");
  const gap = heading ? 450 : newBlock ? 260 : 0;
  if (gap) setTimeout(() => { if (token === playToken && state.playing) playFrom(next); }, gap);
  else playFrom(next);
}

// ------------------------------------------------------------ doc lien ca doan (giong tu nhien nhu nguoi)
// Moi "doan doc" gom cac cau lien nhau trong cung mot khoi van. Tao giong ca doan mot lan nen ngu dieu
// len xuong tu nhien; may chu tra ve moc bat dau tung cau de van to sang dung cau dang doc.
const seg = { key: "", list: [], of: [], starts: new Map(), audio: new Map(), loading: null };

function segQuery() {
  return `voice=${encodeURIComponent(state.voice)}&en=${state.en ? 1 : 0}`;
}

function segKeyNow() { return state.doc ? `${state.doc.id}|${state.voice}|${state.en}` : ""; }

function clearSegAudio() {
  for (const audio of seg.audio.values()) {
    audio.pause();
    if (audio.dataset.url) URL.revokeObjectURL(audio.dataset.url);
  }
  seg.audio.clear();
}

function loadSegments() {
  const key = segKeyNow();
  if (!key) return Promise.resolve();
  if (seg.key === key) return Promise.resolve();
  if (seg.loading && seg.loading.key === key) return seg.loading.promise;
  const promise = api(`segments/${state.doc.id}?${segQuery()}`).then((data) => {
    if (segKeyNow() !== key) return;
    clearSegAudio();
    seg.key = key;
    seg.list = data.segments;
    seg.of = [];
    seg.starts.clear();
    data.segments.forEach(([a, b], k) => { for (let i = a; i < b; i++) seg.of[i] = k; });
  }).finally(() => { if (seg.loading && seg.loading.key === key) seg.loading = null; });
  seg.loading = { key, promise };
  return promise;
}

function segStarts(k) {
  if (!seg.starts.has(k)) {
    const promise = api(`seg/${state.doc.id}/${k}/starts?${segQuery()}`).then((d) => d.starts);
    promise.catch(() => seg.starts.delete(k));
    seg.starts.set(k, promise);
  }
  return seg.starts.get(k);
}

async function segAudio(k) {
  if (seg.audio.has(k)) return seg.audio.get(k);
  await segStarts(k); // may chu tao giong xong o buoc nay, lay file mp3 ve se nhanh
  const res = await fetch(`/api/seg/${state.doc.id}/${k}?${segQuery()}`);
  if (!res.ok) throw new Error("Không tải được giọng đọc cả đoạn.");
  const url = URL.createObjectURL(await res.blob()); // blob de tua toi giua doan duoc
  const audio = new Audio(url);
  audio.preload = "auto";
  audio.dataset.url = url;
  audio.dataset.seg = String(k);
  seg.audio.set(k, audio);
  for (const [other, item] of seg.audio) {
    if (item !== current && (other < k - 1 || other > k + 3)) {
      item.pause();
      URL.revokeObjectURL(item.dataset.url);
      seg.audio.delete(other);
    }
  }
  return audio;
}

function preloadSegments(k) {
  for (let n = k + 1; n <= k + 2 && n < seg.list.length; n++) {
    if (segSpeakable(n)) segAudio(n).catch(() => {});
  }
}

function segSpeakable(k) { return speakable(seg.list[k][0]); }

async function playFromNatural(i, token) {
  const k = seg.of[i];
  const [a, b] = seg.list[k];
  setLoading(true);
  let starts;
  let audio;
  const ready = Promise.all([segStarts(k), segAudio(k)]);
  if (!seg.audio.has(k)) {
    // doan chua tao xong: doc tam cau nay kieu tung cau cho khoi phai cho,
    // doan van tiep tuc duoc tao ngam va se doc lien tu cau ke tiep
    const slow = await Promise.race([ready.then(() => false), new Promise((r) => setTimeout(() => r(true), 1200))])
      .catch(() => true);
    if (token !== playToken || !state.playing) return;
    if (slow) {
      ready.catch(() => {});
      playFromSentence(i, token);
      return;
    }
  }
  try {
    [starts, audio] = await ready;
  } catch {
    if (token === playToken && state.playing) playFromSentence(i, token); // loi mang: doc tung cau
    return;
  }
  if (token !== playToken || !state.playing) return;
  current = audio;
  audio.playbackRate = state.speed;
  let lastShown = i;
  audio.ontimeupdate = () => {
    if (token !== playToken) return;
    let j = 0;
    for (let m = 0; m < starts.length; m++) if (starts[m] <= audio.currentTime + 0.08) j = m;
    const idx = a + j;
    if (idx !== lastShown && idx >= i) { lastShown = idx; setCurrent(idx); }
  };
  audio.onended = () => {
    if (token !== playToken || !state.playing) return;
    const next = nextSpeakable(b, 1);
    if (next < 0) { finish(); return; }
    const heading = state.doc.blocks[state.doc.sentences[a].b].type.startsWith("h");
    setTimeout(() => { if (token === playToken && state.playing) playFrom(next); }, heading ? 380 : 220);
  };
  audio.onplaying = () => { if (token === playToken) setLoading(false); };
  audio.onwaiting = () => { if (token === playToken) setLoading(true); };
  audio.onerror = () => { if (token === playToken && state.playing) playFromSentence(i, token); };
  const offset = starts[i - a] || 0;
  const begin = () => {
    try { audio.currentTime = offset; } catch { /* chua san sang */ }
    audio.play().then(() => { setLoading(false); waitTries = 0; preloadSegments(k); }).catch((err) => {
      if (token !== playToken) return;
      if (err.name === "NotAllowedError") {
        state.playing = false;
        updatePlayUI();
        toast("Bấm nút đọc (hoặc phím Space) để bắt đầu nghe.");
      }
    });
  };
  if (audio.readyState >= 1) begin(); else audio.addEventListener("loadedmetadata", begin, { once: true });
}

async function playFrom(i) {
  if (!state.doc) return;
  i = nextSpeakable(i, 1);
  if (i < 0) { finish(); return; }
  if (current) current.pause();
  clearRetryWait();
  if (window.speechSynthesis) speechSynthesis.cancel();
  const token = ++playToken;
  state.playing = true;
  updatePlayUI();
  setCurrent(i);
  if (state.natural) {
    try { await loadSegments(); } catch { /* khong lay duoc danh sach doan: doc tung cau */ }
    if (token !== playToken || !state.playing) return;
    if (seg.key === segKeyNow() && seg.of[i] !== undefined) {
      playFromNatural(i, token);
      return;
    }
  }
  playFromSentence(i, token);
}

async function playFromSentence(i, token) {
  if (current) current.pause();
  setCurrent(i);
  const audio = getAudio(i);
  current = audio;
  audio.playbackRate = state.speed;
  audio.onended = () => continueAfter(i, token);
  audio.onerror = () => { if (token === playToken) handleAudioError(i, token, audio); };
  audio.onplaying = () => { if (token === playToken) setLoading(false); };
  audio.onwaiting = () => { if (token === playToken) setLoading(true); };
  setLoading(audio.readyState < 3);
  try {
    if (audio.currentTime) audio.currentTime = 0;
    await audio.play();
    retried.delete(i);
    waitTries = 0;
  } catch (err) {
    if (token !== playToken) return;
    if (err.name === "NotAllowedError") {
      state.playing = false;
      updatePlayUI();
      toast("Bấm nút đọc (hoặc phím Space) để bắt đầu nghe.");
    } else if (err.name !== "AbortError") {
      handleAudioError(i, token, audio);
    }
    return;
  }
  preload(i);
}

async function handleAudioError(i, token, audio) {
  audioPool.delete(audioKey(i));
  let message = "Không tải được giọng đọc.";
  try {
    const res = await fetch(ttsUrl(i, "&check=" + Date.now()));
    if (res.ok) {
      // lan nay tao duoc (mang vua on dinh lai), doc tiep
      if (token === playToken && state.playing) playFrom(i);
      return;
    }
    const data = await res.json();
    if (data && data.error) message = data.error;
  } catch { /* giu thong bao mac dinh */ }
  if (token !== playToken || !state.playing) return;
  if (!retried.has(i)) {
    retried.add(i);
    setTimeout(() => { if (token === playToken && state.playing) playFrom(i); }, 1500);
    return;
  }
  if (speakWithBrowserVoice(i, token)) {
    toast("Dịch vụ giọng đọc đang lỗi, tạm dùng giọng của trình duyệt.", true);
    return;
  }
  // mat mang giua tai lieu dai: cho mang tro lai roi doc tiep dung cau nay, khong dung han
  if (waitTries < WAIT_MAX_TRIES) {
    if (waitTries === 0) toast(message + " Đang chờ mạng, có mạng lại là đọc tiếp.", true, 8000);
    waitTries++;
    retried.delete(i);
    const resume = () => {
      clearRetryWait();
      if (token === playToken && state.playing) playFrom(i);
    };
    const timer = setTimeout(resume, 5000);
    retryWait = { timer, resume };
    window.addEventListener("online", resume);
    return;
  }
  waitTries = 0;
  state.playing = false;
  updatePlayUI();
  toast(message + " Kiểm tra mạng rồi bấm đọc lại.", true, 6000);
}

function speakWithBrowserVoice(i, token) {
  if (!window.speechSynthesis) return false;
  const voice = speechSynthesis.getVoices().find((v) => v.lang.toLowerCase().startsWith("vi"));
  if (!voice) return false;
  const utterance = new SpeechSynthesisUtterance(state.doc.sentences[i].t);
  utterance.voice = voice;
  utterance.lang = voice.lang;
  utterance.rate = state.speed;
  utterance.onend = () => continueAfter(i, token);
  setLoading(false);
  speechSynthesis.speak(utterance);
  return true;
}

// ------------------------------------------------------------ tro ly noi chuyen (chao, bao nhan, bao xong)
let saying = null;
const greeted = new Set();

function say(text) {
  return new Promise(async (resolve) => {
    try {
      const res = await fetch("/api/tts-text", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, voice: state.voice, en: false }),
      });
      if (!res.ok) { resolve(false); return; }
      const url = URL.createObjectURL(await res.blob());
      const audio = new Audio(url);
      audio.playbackRate = Math.min(state.speed, 1.25);
      const done = (ok) => {
        if (saying && saying.audio === audio) saying = null;
        URL.revokeObjectURL(url);
        resolve(ok);
      };
      saying = { audio, resolve: done };
      audio.onended = () => done(true);
      audio.onerror = () => done(false);
      audio.play().catch(() => done(false)); // trinh duyet chan tu phat: bo qua loi chao, doc luon
    } catch { resolve(false); }
  });
}

function cancelSay() {
  if (!saying) return;
  const { audio, resolve } = saying;
  saying = null;
  audio.pause();
  resolve(false);
}

function introText() {
  const doc = state.doc;
  const length = minutesText((remainingChars[state.idx] || 0) / (CHARS_PER_SECOND * state.speed));
  if (state.justImported === doc.id) {
    // cau ngan, it bien doi nen thuong da co san trong cache, phat gan nhu ngay lap tuc
    return `Dạ, em nhận được tài liệu rồi, nghe khoảng ${length}. Em đọc cho anh nhé.`;
  }
  if (state.idx > 0) return "Dạ, em đọc tiếp từ chỗ lần trước cho anh nhé.";
  return `Dạ, em đọc cho anh nghe nhé, khoảng ${length}.`;
}

async function beginReading() {
  if (!state.doc) return;
  const doc = state.doc;
  if (state.talk && !greeted.has(doc.id)) {
    greeted.add(doc.id);
    state.playing = true;
    updatePlayUI();
    setLoading(true);
    const text = introText();
    state.justImported = null;
    await say(text);
    setLoading(false);
    if (!state.playing || state.doc !== doc) return; // anh bam dung trong luc tro ly dang chao
  }
  resume();
}

function pause() {
  state.playing = false;
  clearRetryWait();
  waitTries = 0;
  cancelSay();
  if (current) current.pause();
  if (window.speechSynthesis) speechSynthesis.cancel();
  updatePlayUI();
}

function resume() {
  if (!state.doc) return;
  const sameSentence = current && Number(current.dataset.i) === state.idx && audioPool.get(audioKey(state.idx)) === current;
  const sameSegment = current && current.dataset.seg !== undefined && seg.key === segKeyNow()
    && seg.audio.get(Number(current.dataset.seg)) === current && seg.of[state.idx] === Number(current.dataset.seg);
  if ((sameSentence || sameSegment) && current.currentTime > 0 && !current.ended) {
    state.playing = true;
    updatePlayUI();
    current.playbackRate = state.speed;
    current.play().catch(() => playFrom(state.idx));
  } else {
    playFrom(state.idx);
  }
}

function togglePlay() {
  if (!state.doc) { toast("Mở một tài liệu trước đã."); return; }
  if (state.playing) pause(); else beginReading();
}

function stopPlayback() {
  playToken++;
  pause();
  current = null;
  for (const audio of audioPool.values()) { audio.removeAttribute("src"); audio.load(); }
  audioPool.clear();
  clearSegAudio();
  seg.key = "";
}

function finish() {
  state.playing = false;
  updatePlayUI();
  toast("Đã đọc hết tài liệu.");
  if (state.talk && state.doc) {
    const open = state.doc.notes.filter((n) => n.kind === "question" && !n.done).length;
    say("Dạ, em đọc xong tài liệu rồi ạ." + (open
      ? ` Anh còn ${open} câu hỏi chưa rõ. Anh bấm Copy để hỏi Claude là có thể hỏi ngay nhé.`
      : " Anh cần nghe lại đoạn nào thì bấm vào đoạn đó nhé."));
  }
}

function jumpTo(i) {
  if (!state.doc) return;
  if (state.playing) playFrom(i);
  else { playToken++; current = null; setCurrent(i, { force: true }); }
}

function step(dir) {
  if (!state.doc) return;
  const target = nextSpeakable(state.idx + dir, dir);
  if (target >= 0) jumpTo(target);
}

function stepBlock(dir) {
  if (!state.doc) return;
  const doc = state.doc;
  const b = doc.sentences[state.idx].b;
  let target;
  if (dir < 0) target = state.idx > doc.blocks[b].start ? doc.blocks[b].start : doc.blocks[Math.max(0, b - 1)].start;
  else target = b + 1 < doc.blocks.length ? doc.blocks[b + 1].start : doc.sentences.length - 1;
  jumpTo(nextSpeakable(target, 1) >= 0 ? nextSpeakable(target, 1) : target);
}

// ------------------------------------------------------------ ghi chu
function renderNotes() {
  const list = $("#noteList");
  list.innerHTML = "";
  const notes = sortedNotes();
  const openQuestions = notes.filter((n) => n.kind === "question" && !n.done).length;
  $("#notesCount").textContent = notes.length ? String(notes.length) : "";
  $("#notesFilter [data-filter=question]").textContent = openQuestions ? `Câu hỏi chưa rõ (${openQuestions})` : "Câu hỏi chưa rõ";
  const shown = state.filter === "question" ? notes.filter((n) => n.kind === "question" && !n.done) : notes;
  if (!state.doc) {
    list.append(el("div", { class: "notes-empty" }, "Mở một tài liệu để xem và thêm ghi chú."));
    return;
  }
  if (!shown.length) {
    const empty = el("div", { class: "notes-empty" });
    empty.innerHTML = state.filter === "question"
      ? "Không còn câu hỏi nào chưa rõ."
      : "Đang nghe mà có ý hay hoặc chỗ chưa hiểu, bấm <kbd>N</kbd> để ghi chú hoặc <kbd>Q</kbd> để đặt câu hỏi. Ghi chú gắn đúng câu đó, bấm vào để nghe lại.";
    list.append(empty);
    return;
  }
  for (const note of shown) list.append(noteCard(note));
}

function noteCard(note) {
  const isQ = note.kind === "question";
  const card = el("div", { class: "note" + (note.done ? " done" : "") + (note.i === state.idx ? " cur" : ""), "data-id": note.id, "data-i": note.i });
  const badge = isQ
    ? el("span", { class: "badge q" }, note.done ? "Đã rõ" : "Câu hỏi")
    : el("span", { class: "badge n" }, "Ghi chú");
  card.append(
    el("div", { class: "note-head" },
      badge,
      el("button", { class: "jump", title: "Tới câu này", onclick: () => jumpTo(note.i) }, `Câu ${note.i + 1}`),
      el("span", { class: "when" }, shortTime(note.created)),
    ),
    el("div", { class: "note-quote", title: "Bấm để nghe lại câu này", onclick: () => playFrom(note.i) }, `"${note.quote}"`),
    el("div", { class: "note-text" + (note.text ? "" : " empty-text") }, note.text || (isQ ? "Đánh dấu chỗ chưa hiểu" : "Đánh dấu")),
  );
  if (note.answer) card.append(el("div", { class: "note-answer" }, el("b", {}, "Trả lời: "), note.answer));
  const actions = el("div", { class: "note-actions" },
    el("button", { onclick: () => playFrom(note.i) }, "Nghe từ đây"),
    note.text || note.answer ? el("button", { onclick: () => speakText([note.text, note.answer ? "Trả lời. " + note.answer : ""].filter(Boolean).join(". ")) }, "Đọc to") : null,
    isQ ? el("button", { onclick: () => patchNote(note, { done: !note.done }) }, note.done ? "Mở lại" : "Đã rõ") : null,
    isQ ? el("button", { onclick: () => editAnswer(card, note) }, note.answer ? "Sửa trả lời" : "Ghi trả lời") : null,
    el("button", { onclick: () => openComposer(note.kind, { i: note.i, quote: note.quote, text: note.text, editId: note.id }) }, "Sửa"),
    el("button", { class: "danger", onclick: () => deleteNote(note) }, "Xoá"),
  );
  card.append(actions);
  return card;
}

function focusNoteCard(id) {
  document.getElementById("app").classList.add("show-notes");
  if (state.filter !== "all") { state.filter = "all"; syncFilter(); renderNotes(); }
  const card = $(`.note[data-id="${id}"]`);
  if (!card) return;
  card.scrollIntoView({ block: "nearest", behavior: "smooth" });
  card.animate([{ boxShadow: "0 0 0 3px var(--hl-line)" }, { boxShadow: "0 0 0 0 transparent" }], { duration: 1200 });
}

function editAnswer(card, note) {
  if (card.querySelector(".note-edit")) return;
  const area = el("textarea", { class: "note-edit", placeholder: "Dán câu trả lời (ví dụ từ Claude) vào đây..." });
  area.value = note.answer || "";
  const save = el("button", { class: "btn primary", onclick: async () => {
    await patchNote(note, { answer: area.value, done: area.value.trim() ? true : note.done });
  } }, "Lưu trả lời");
  const cancel = el("button", { class: "btn ghost", onclick: () => renderNotes() }, "Huỷ");
  card.append(area, el("div", { class: "composer-foot" }, el("span"), el("div", {}, cancel, save)));
  area.focus();
}

async function patchNote(note, changes) {
  try {
    const updated = await api(`doc/${state.doc.id}/notes/${note.id}`, { method: "PATCH", body: changes });
    Object.assign(note, updated);
    afterNotesChanged();
  } catch (err) { toast(err.message, true); }
}

async function deleteNote(note) {
  if (!confirm("Xoá ghi chú này?")) return;
  try {
    await api(`doc/${state.doc.id}/notes/${note.id}`, { method: "DELETE" });
    state.doc.notes = state.doc.notes.filter((n) => n.id !== note.id);
    afterNotesChanged();
  } catch (err) { toast(err.message, true); }
}

function afterNotesChanged() {
  renderNotes();
  decorateNotes();
  sentenceEls[state.idx] && sentenceEls[state.idx].classList.add("cur");
  loadLibrary().catch(() => {});
}

function openComposer(kind, opts = {}) {
  if (!state.doc) { toast("Mở một tài liệu trước đã."); return; }
  state.wasPlaying = state.playing || (state.composer ? state.wasPlaying : false);
  if (state.playing) pause();
  const i = opts.i ?? state.idx;
  state.composer = { i, kind, quote: opts.quote || state.doc.sentences[i].t, editId: opts.editId || null };
  document.getElementById("app").classList.add("show-notes");
  const form = $("#composer");
  form.hidden = false;
  $("#composerWhere").textContent = `${opts.editId ? "Sửa" : "Tại"} câu ${i + 1}`;
  $("#composerQuote").textContent = state.composer.quote;
  $("#composerText").value = opts.text || "";
  setComposerKind(kind);
  $("#noteList").scrollTop = 0;
  $("#composerText").focus();
  if (state.autoDictate && !opts.editId) startDictation();
}

function setComposerKind(kind) {
  if (state.composer) state.composer.kind = kind;
  $$("#composerKind button").forEach((b) => b.classList.toggle("on", b.dataset.kind === kind));
  $("#composer").classList.toggle("is-q", kind === "question");
  $("#composerText").placeholder = kind === "question"
    ? "Chỗ nào chưa hiểu? Nhập hoặc bấm micro để nói câu hỏi..."
    : "Nhập hoặc bấm micro để nói ghi chú...";
}

function closeComposer() {
  stopDictation();
  state.composer = null;
  $("#composer").hidden = true;
}

async function saveComposer() {
  const composer = state.composer;
  if (!composer || !state.doc) return;
  stopDictation();
  const text = $("#composerText").value.trim();
  const button = $("#btnSaveNote");
  button.disabled = true;
  try {
    if (composer.editId) {
      const note = state.doc.notes.find((n) => n.id === composer.editId);
      const updated = await api(`doc/${state.doc.id}/notes/${composer.editId}`, { method: "PATCH", body: { text, kind: composer.kind } });
      Object.assign(note, updated);
    } else {
      const note = await api(`doc/${state.doc.id}/notes`, { body: { i: composer.i, kind: composer.kind, text, quote: composer.quote } });
      state.doc.notes.push(note);
    }
    toast(composer.kind === "question" ? "Đã lưu câu hỏi." : "Đã lưu ghi chú.");
    const shouldResume = state.wasPlaying && state.resume && !composer.editId;
    closeComposer();
    afterNotesChanged();
    if (state.talk && !composer.editId) {
      const line = composer.kind === "question" ? "Dạ, em ghi lại câu hỏi của anh rồi." : "Dạ, em ghi chú lại rồi.";
      await say(shouldResume ? line + " Em đọc tiếp nhé." : line);
    }
    if (shouldResume) resume();
  } catch (err) {
    toast(err.message, true);
  } finally {
    button.disabled = false;
  }
}

// nhap bang giong noi (Web Speech API cua Chrome/Edge)
let recognition = null;
function startDictation() {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) {
    toast("Trình duyệt này chưa hỗ trợ nói để nhập. Dùng Voice Mic: giữ Alt và bấm vào ô ghi chú.");
    return;
  }
  if (recognition) return;
  const area = $("#composerText");
  const base = area.value ? area.value.replace(/\s*$/, " ") : "";
  let finalText = "";
  recognition = new Recognition();
  recognition.lang = "vi-VN";
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.onresult = (event) => {
    let interim = "";
    for (let k = event.resultIndex; k < event.results.length; k++) {
      const result = event.results[k];
      if (result.isFinal) finalText += result[0].transcript.trim() + " ";
      else interim += result[0].transcript;
    }
    area.value = (base + finalText + interim).trimStart();
  };
  recognition.onerror = (event) => {
    if (event.error === "not-allowed" || event.error === "service-not-allowed") toast("Chưa được phép dùng micro. Bấm biểu tượng ổ khoá trên thanh địa chỉ để cho phép.", true);
    else if (!["no-speech", "aborted"].includes(event.error)) toast("Nhận giọng lỗi: " + event.error, true);
  };
  recognition.onend = () => {
    recognition = null;
    $("#btnDictate").classList.remove("rec");
    area.value = area.value.trim();
  };
  recognition.start();
  $("#btnDictate").classList.add("rec");
}

function stopDictation() {
  if (recognition) { try { recognition.stop(); } catch { /* da dung */ } }
}

let sideAudio = null;
async function speakText(text) {
  if (!text.trim()) return;
  if (state.playing) pause();
  try {
    const res = await fetch("/api/tts-text", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice: state.voice, en: state.en }),
    });
    if (!res.ok) throw new Error((await res.json()).error || "Không tạo được giọng đọc.");
    const url = URL.createObjectURL(await res.blob());
    if (sideAudio) sideAudio.pause();
    sideAudio = new Audio(url);
    sideAudio.playbackRate = state.speed;
    sideAudio.onended = () => URL.revokeObjectURL(url);
    await sideAudio.play();
  } catch (err) { toast(err.message, true); }
}

// ------------------------------------------------------------ nhap tai lieu
async function importWith(label, run) {
  const pending = toast(`Đang mở ${label}...`, false, 60000);
  try {
    const doc = await run();
    pending.remove();
    showDoc(doc);
    await loadLibrary();
    if (state.talk) {
      // nhan tai lieu xong: tro ly chao, bao da nhan, roi doc luon
      state.justImported = doc.id;
      greeted.delete(doc.id);
      beginReading();
    } else {
      toast(`Đã mở: ${doc.title}. Bấm Space để nghe.`);
    }
    return true;
  } catch (err) {
    pending.remove();
    toast(err.message, true, 6000);
    return false;
  }
}

async function importFiles(files) {
  for (const file of files) {
    await importWith(file.name, () => api(`upload?name=${encodeURIComponent(file.name)}`, { raw: file }));
  }
}

function detectPasteKind(value) {
  const text = value.trim().replace(/^"(.*)"$/, "$1");
  if (/^(https?:\/\/|www\.)\S+$/i.test(text)) return "url";
  if (/^[a-z]:\\[^\n]+$/i.test(text) || /^\\\\[^\n]+$/.test(text)) return "path";
  return "text";
}

function openPasteModal() {
  $("#pasteModal").hidden = false;
  $("#pasteText").value = "";
  $("#pasteTitleInput").value = "";
  $("#pasteHint").textContent = "";
  $("#pasteText").focus();
}

async function submitPaste() {
  const value = $("#pasteText").value;
  if (!value.trim()) { $("#pasteText").focus(); return; }
  const kind = detectPasteKind(value);
  const label = { url: "link", path: "file/thư mục", text: "văn bản" }[kind];
  const ok = await importWith(label, () => api("import", {
    body: { kind, value: kind === "text" ? value : value.trim().replace(/^"(.*)"$/, "$1"), title: $("#pasteTitleInput").value },
  }));
  if (ok) $("#pasteModal").hidden = true;
}

// ------------------------------------------------------------ chon doan van
function hideSelToolbar() { $("#selToolbar").hidden = true; state.selection = null; }

function onDocMouseUp() {
  setTimeout(() => {
    const sel = window.getSelection();
    const text = sel ? sel.toString().trim() : "";
    if (!state.doc || !text || text.length < 2 || !$("#doc").contains(sel.anchorNode)) { hideSelToolbar(); return; }
    const spanOf = (node) => (node && (node.nodeType === 1 ? node : node.parentElement))?.closest(".s");
    const a = spanOf(sel.anchorNode);
    const b = spanOf(sel.focusNode);
    const indexes = [a, b].filter(Boolean).map((s) => Number(s.dataset.i));
    if (!indexes.length) { hideSelToolbar(); return; }
    state.selection = { i: Math.min(...indexes), quote: text.slice(0, 2000) };
    const rect = sel.getRangeAt(0).getBoundingClientRect();
    const host = $("#reader").getBoundingClientRect();
    const bar = $("#selToolbar");
    bar.hidden = false;
    const half = bar.offsetWidth / 2 + 8;
    const x = Math.min(Math.max(rect.left + rect.width / 2 - host.left, half), host.width - half);
    bar.style.left = `${x}px`;
    bar.style.top = `${Math.max(rect.top - host.top - 8, 40)}px`;
  }, 0);
}

// ------------------------------------------------------------ giao dien chung
function applyPrefs() {
  document.documentElement.style.setProperty("--read-size", `${state.fontSize}px`);
  if (state.theme === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = state.theme;
  $$("#settingsPop [data-theme]").forEach((b) => b.classList.toggle("on", b.dataset.theme === state.theme));
  $("#speed").value = String(state.speed);
  $("#voice").value = state.voice;
  $("#optEnglish").checked = state.en;
  $("#optResume").checked = state.resume;
  $("#optFollow").checked = state.follow;
  $("#optSkipLists").checked = state.skipLists;
  $("#optDictate").checked = state.autoDictate;
  $("#optTalk").checked = state.talk;
  $("#optNatural").checked = state.natural;
}

function syncFilter() {
  $$("#notesFilter button").forEach((b) => b.classList.toggle("on", b.dataset.filter === state.filter));
}

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; }
  catch {
    const area = el("textarea", { style: "position:fixed;opacity:0" });
    area.value = text;
    document.body.append(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    return ok;
  }
}

function isTyping(target) {
  return target && (target.tagName === "TEXTAREA" || target.tagName === "INPUT" || target.tagName === "SELECT" || target.isContentEditable);
}

const emptyTemplate = $("#empty").cloneNode(true);

function bindEvents() {
  $("#btnPlay").addEventListener("click", togglePlay);
  $("#btnPrev").addEventListener("click", () => step(-1));
  $("#btnNext").addEventListener("click", () => step(1));
  $("#btnPrevBlock").addEventListener("click", () => stepBlock(-1));
  $("#btnNextBlock").addEventListener("click", () => stepBlock(1));
  $("#btnNote").addEventListener("click", () => openComposer("note"));
  $("#btnQuestion").addEventListener("click", () => openComposer("question"));

  $("#speed").addEventListener("change", (e) => {
    state.speed = Number(e.target.value);
    prefs.set("speed", state.speed);
    if (current) current.playbackRate = state.speed;
    updateStatus();
  });
  $("#voice").addEventListener("change", (e) => {
    state.voice = e.target.value;
    prefs.set("voice", state.voice);
    if (state.playing) playFrom(state.idx);
    else loadSegments().catch(() => {});
  });
  const bindCheck = (id, key, after) => $(id).addEventListener("change", (e) => {
    state[key] = e.target.checked;
    prefs.set(key, state[key]);
    if (after) after();
  });
  bindCheck("#optEnglish", "en", () => { if (state.playing) playFrom(state.idx); });
  bindCheck("#optResume", "resume");
  bindCheck("#optFollow", "follow");
  bindCheck("#optSkipLists", "skipLists");
  bindCheck("#optDictate", "autoDictate");
  bindCheck("#optTalk", "talk");
  bindCheck("#optNatural", "natural", () => { if (state.playing) playFrom(state.idx); });
  $("#btnVoiceTest").addEventListener("click", async (e) => {
    e.stopPropagation();
    if (state.playing) pause();
    cancelSay();
    const name = $("#voice").selectedOptions[0].textContent.replace(/\s*\(.*\)/, "");
    await say(`Dạ, em chào anh, em là giọng ${name}. Hôm nay em đọc cho anh bài nghiên cứu về trí tuệ nhân tạo AI, `
      + "khoảng mười lăm phút. Anh có câu hỏi thì cứ bấm Q, em ghi lại ngay nhé.");
  });
  $("#btnSettings").addEventListener("click", (e) => { e.stopPropagation(); $("#settingsPop").hidden = !$("#settingsPop").hidden; });
  $("#settingsPop").addEventListener("click", (e) => {
    e.stopPropagation();
    const font = e.target.closest("[data-font]");
    const theme = e.target.closest("[data-theme]");
    if (font) { state.fontSize = Math.max(15, Math.min(30, state.fontSize + Number(font.dataset.font) * 2)); prefs.set("font", state.fontSize); applyPrefs(); }
    if (theme) { state.theme = theme.dataset.theme; prefs.set("theme", state.theme); applyPrefs(); }
  });
  document.addEventListener("click", (e) => {
    if (!$("#settingsPop").hidden && !e.target.closest("#settingsPop")) $("#settingsPop").hidden = true;
  });

  $("#progress").addEventListener("click", (e) => {
    if (!state.doc) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    jumpTo(Math.round(ratio * (state.doc.sentences.length - 1)));
  });

  $("#doc").addEventListener("click", (e) => {
    const sel = window.getSelection();
    if (sel && !sel.isCollapsed && sel.toString().trim()) return;
    const span = e.target.closest(".s");
    if (span) playFrom(Number(span.dataset.i));
  });
  $("#doc").addEventListener("mouseup", onDocMouseUp);
  document.addEventListener("mousedown", (e) => { if (!e.target.closest("#selToolbar")) hideSelToolbar(); });
  $("#selToolbar").addEventListener("click", (e) => {
    const button = e.target.closest("button");
    if (!button || !state.selection) return;
    const { i, quote } = state.selection;
    window.getSelection().removeAllRanges();
    hideSelToolbar();
    if (button.dataset.kind === "play") playFrom(i);
    else openComposer(button.dataset.kind, { i, quote });
  });
  const markScroll = () => { lastUserScroll = Date.now(); hideSelToolbar(); };
  $("#docScroll").addEventListener("wheel", markScroll, { passive: true });
  $("#docScroll").addEventListener("touchmove", markScroll, { passive: true });

  // ghi chu
  $("#composer").addEventListener("submit", (e) => { e.preventDefault(); saveComposer(); });
  $("#btnCancelNote").addEventListener("click", () => {
    const resumeAfter = state.wasPlaying && state.resume;
    closeComposer();
    if (resumeAfter) resume();
  });
  $("#composerKind").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) setComposerKind(b.dataset.kind); });
  $("#btnDictate").addEventListener("click", () => (recognition ? stopDictation() : startDictation()));
  $("#composerText").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); saveComposer(); }
  });
  $("#notesFilter").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    state.filter = b.dataset.filter;
    syncFilter();
    renderNotes();
  });
  $("#btnNotesFile").addEventListener("click", async () => {
    if (!state.doc) return;
    try { await api("open", { body: { target: "notes_file", id: state.doc.id } }); }
    catch (err) { toast(err.message, true); }
  });
  $("#btnCopyForAI").addEventListener("click", async () => {
    if (!state.doc) return;
    const doc = state.doc;
    const openQ = doc.notes.filter((n) => n.kind === "question" && !n.done).length;
    const source = doc.source && doc.source_type !== "text" ? `\nTài liệu gốc: ${doc.source}` : "";
    const text = `Đọc file ghi chú này của tôi: ${doc.notes_file}${source}\n` +
      (openQ ? `Trong đó có ${openQ} câu hỏi tôi chưa rõ. Hãy trả lời từng câu thật dễ hiểu, dựa vào đúng đoạn văn được trích, có ví dụ nếu cần.` :
        "Tóm tắt giúp tôi các ý chính và gợi ý tôi nên tìm hiểu thêm gì.");
    if (await copyText(text)) toast("Đã copy. Dán vào Claude là nó đọc được file ghi chú.");
  });

  // thu vien, nhap
  $("#btnOpenFile").addEventListener("click", () => $("#fileInput").click());
  $("#fileInput").addEventListener("change", (e) => { importFiles(Array.from(e.target.files)); e.target.value = ""; });
  $("#btnClipboard").addEventListener("click", () => importWith("nội dung clipboard", () => api("import", { body: { kind: "clipboard" } })));
  $("#btnPaste").addEventListener("click", openPasteModal);
  $("#btnPasteGo").addEventListener("click", submitPaste);
  $("#pasteText").addEventListener("input", () => {
    const value = $("#pasteText").value;
    $("#pasteHint").textContent = value.trim() ? { url: "Nhận ra: link web", path: "Nhận ra: đường dẫn file hoặc thư mục trên máy", text: `Văn bản, ${value.trim().length.toLocaleString("vi-VN")} ký tự` }[detectPasteKind(value)] : "";
  });
  $("#pasteText").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); submitPaste(); } });
  $$("[data-close]").forEach((b) => b.addEventListener("click", () => { $("#pasteModal").hidden = true; }));
  $("#pasteModal").addEventListener("click", (e) => { if (e.target === e.currentTarget) e.currentTarget.hidden = true; });
  $("#btnNotesDir").addEventListener("click", () => api("open", { body: { target: "notes_dir" } }).catch((err) => toast(err.message, true)));
  $("#btnSource").addEventListener("click", () => api("open", { body: { target: "source", id: state.doc.id } }).catch((err) => toast(err.message, true)));
  $("#btnReload").addEventListener("click", () => importWith("bản mới nhất", () => api(`doc/${state.doc.id}/reload`, { body: {} })));
  $("#btnLibToggle").addEventListener("click", (e) => { e.stopPropagation(); document.getElementById("app").classList.toggle("show-lib"); });
  $("#btnNotesToggle").addEventListener("click", (e) => { e.stopPropagation(); document.getElementById("app").classList.toggle("show-notes"); });
  $("#reader").addEventListener("click", (e) => {
    if (e.target.closest("#btnLibToggle, #btnNotesToggle")) return;
    document.getElementById("app").classList.remove("show-lib", "show-notes");
  });

  // keo tha
  let dragDepth = 0;
  window.addEventListener("dragenter", (e) => { e.preventDefault(); dragDepth++; $("#dropOverlay").hidden = false; });
  window.addEventListener("dragleave", () => { dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) $("#dropOverlay").hidden = true; });
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => {
    e.preventDefault();
    dragDepth = 0;
    $("#dropOverlay").hidden = true;
    const files = Array.from(e.dataTransfer.files || []);
    if (files.length) { importFiles(files); return; }
    const uri = e.dataTransfer.getData("text/uri-list");
    const text = e.dataTransfer.getData("text/plain");
    if (uri && /^https?:/i.test(uri)) importWith("link", () => api("import", { body: { kind: "url", value: uri.split("\n")[0] } }));
    else if (text.trim()) importWith("văn bản", () => api("import", { body: { kind: detectPasteKind(text), value: text } }));
  });

  // phim tat
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (!$("#pasteModal").hidden) { $("#pasteModal").hidden = true; return; }
      if (state.composer) { $("#btnCancelNote").click(); return; }
      $("#settingsPop").hidden = true;
      hideSelToolbar();
      return;
    }
    if (isTyping(e.target) || e.ctrlKey || e.altKey || e.metaKey || !$("#pasteModal").hidden) return;
    const key = e.key.toLowerCase();
    if (e.key === " " || key === "k") { e.preventDefault(); togglePlay(); }
    else if (e.key === "ArrowRight") { e.preventDefault(); e.shiftKey ? stepBlock(1) : step(1); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); e.shiftKey ? stepBlock(-1) : step(-1); }
    else if (key === "n") { e.preventDefault(); openComposer("note", state.selection || {}); }
    else if (key === "q") { e.preventDefault(); openComposer("question", state.selection || {}); }
    else if (key === "r") { e.preventDefault(); if (state.doc) playFrom(state.idx); }
    else if (e.key === "+" || e.key === "=") { const opts = $$("#speed option"); const k = opts.findIndex((o) => Number(o.value) >= state.speed); const next = opts[Math.min(opts.length - 1, k + 1)]; $("#speed").value = next.value; $("#speed").dispatchEvent(new Event("change")); toast(`Tốc độ ${next.textContent}`, false, 1200); }
    else if (e.key === "-") { const opts = $$("#speed option"); const k = opts.findIndex((o) => Number(o.value) >= state.speed); const next = opts[Math.max(0, k - 1)]; $("#speed").value = next.value; $("#speed").dispatchEvent(new Event("change")); toast(`Tốc độ ${next.textContent}`, false, 1200); }
  });

  // nut tren tai nghe / phim media
  if ("mediaSession" in navigator) {
    const ms = navigator.mediaSession;
    ms.setActionHandler("play", () => beginReading());
    ms.setActionHandler("pause", () => pause());
    ms.setActionHandler("previoustrack", () => step(-1));
    ms.setActionHandler("nexttrack", () => step(1));
  }
  if (window.speechSynthesis) speechSynthesis.getVoices();
}

async function init() {
  applyPrefs();
  bindEvents();
  updateStatus();
  renderNotes();
  try { await loadLibrary(); }
  catch (err) { toast(err.message, true); return; }
  const hash = new URLSearchParams(location.hash.slice(1));
  if (hash.get("open")) {
    await importWith("file", () => api("import", { body: { kind: "path", value: hash.get("open") } }));
  } else if (hash.get("doc")) {
    await openDoc(hash.get("doc"));
  } else {
    const last = prefs.get("lastDoc", "");
    if (last && state.library.some((item) => item.id === last)) await openDoc(last);
    else if (state.library.length === 1) await openDoc(state.library[0].id);
  }
}

init();
