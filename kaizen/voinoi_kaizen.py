"""Loop-VoiNoi: vong lap Kaizen tu cai tien Voice Mic (VoiNoi).

5 nhip moi lan chay:
  1. DO       doc so that: voice-mic.log, voice-transcripts.jsonl, tin nhan that gui trong To Ong.
  2. CHAN     xep hang mat xich yeu theo impact (so phien bi anh huong).
  3. SUA      tu sua cai an toan (hoc tu nghe sai, giu Whisper lau hon); loi can sua code thi bom
              1 phieu Worker: codex vao DG-Core Inbox, co thang leo va cau dao.
  4. XAC MINH so du doan nhip truoc voi so that nhip nay.
  5. LAP      ghi report md/json/html + state.json, lich Windows chay lai.

Chay:  .venv\\Scripts\\python.exe kaizen\\voinoi_kaizen.py [--days 7] [--dry-run] [--open]
"""
from __future__ import annotations

import argparse
import bisect
import ctypes
import datetime as dt
import difflib
import hashlib
import html
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
import unicodedata
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = ROOT / "voice-mic.log"
TRANSCRIPTS_FILE = ROOT / "voice-transcripts.jsonl"
LOCAL_SETTINGS = ROOT / "voice-mic-settings.local.json"
BASE_SETTINGS = ROOT / "voice-mic-settings.json"
START_SCRIPT = ROOT / "Start-VoiNoi.ps1"
TOONG_ACCOUNTS = Path.home() / ".toong" / "accounts"

DG_CORE = Path(r"E:\DG Media Holding AI Mascot Building Map\DG-Core")
REPORT_DIR = DG_CORE / "05-Reports" / "kaizen" / "voinoi"
INBOX_DIR = DG_CORE / "04-Task-Boards" / "Inbox"
FOUNDER_QUEUE_DIR = DG_CORE / "04-Task-Boards" / "Founder-Decision-Queue"
STATE_FILE = REPORT_DIR / "state.json"

STUCK_AFTER = 3          # so nhip bom phieu ma metric khong cai thien thi leo nac
MAX_FIX_LEVEL = 3        # het nac moi bao Founder
MODEL_BY_LEVEL = {0: "sonnet", 1: "opus", 2: "opus", 3: "opus"}

# Muc tieu (goal). Khong ha chuan de "co cai tien".
TARGET_LATENCY_P50_MS = 5000
TARGET_COLD_LOAD_RATE = 0.10
TARGET_LOW_CONF_RATE = 0.15
TARGET_PASTE_FAIL_RATE = 0.0
TARGET_DELIVERY_RATE = 0.90
LOW_CONF = 70

WHISPER_IDLE_STEPS = [15, 45, 120, 240]   # phut giu Whisper trong RAM
MIN_FREE_RAM_GB_TO_KEEP_WHISPER = 6.0
LEARN_MIN_COUNT = 2                       # mot cap sua tu phai lap >= 2 lan moi hoc
LEARNED_SOURCE = "kaizen-loop"

LOG_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) (.*)$")


# ---------------------------------------------------------------- tien ich

def now() -> dt.datetime:
    return dt.datetime.now()


def parse_ts(stamp: str) -> dt.datetime:
    return dt.datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S.%f")


def field(text: str, name: str) -> str | None:
    m = re.search(rf"(?:^|\| ){re.escape(name)}=([^|]*)", text)
    return m.group(1).strip() if m else None


def pct(v: float) -> str:
    return f"{v * 100:.0f}%"


def quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = min(len(values) - 1, max(0, round(q * (len(values) - 1))))
    return values[idx]


def norm(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text)).strip()


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def free_ram_gb() -> float:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    st = MEMORYSTATUSEX()
    st.dwLength = ctypes.sizeof(st)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
    return st.ullAvailPhys / 1024 ** 3


def hwnd_exe(hwnd: int) -> str:
    user32 = ctypes.windll.user32
    if not hwnd or not user32.IsWindow(hwnd):
        return ""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid.value)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(520)
        size = wintypes.DWORD(520)
        if ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return Path(buf.value).name
    finally:
        ctypes.windll.kernel32.CloseHandle(h)
    return ""


# ---------------------------------------------------------------- nhip 1: DO

def parse_sessions(since: dt.datetime) -> list[dict]:
    sessions: list[dict] = []
    current: dict | None = None
    whisper_loading = False
    since_key = since.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line[:19] < since_key:
                continue
            m = LOG_RE.match(line.rstrip("\n"))
            if not m:
                continue
            ts, msg = parse_ts(m.group(1)), m.group(2)
            if msg.startswith("loading faster-whisper"):
                whisper_loading = True
                if current and "paste" not in current:
                    current["cold_load"] = True
                continue
            if msg.startswith("faster-whisper") and "model loaded" in msg:
                whisper_loading = False
                continue
            if msg.startswith("session start |"):
                current = {"start": ts, "id": field(msg, "id"), "hwnd": int(field(msg, "locked_hwnd") or 0),
                           "cold_load": whisper_loading, "unrecognized": 0, "chunk_failed": 0,
                           "paste_fail": 0, "focus_miss": 0}
                sessions.append(current)
                continue
            if current is None:
                continue
            if msg.startswith(("auto stop after trailing silence", "capture complete")):
                current.setdefault("stop", ts)
            elif msg.startswith("transcribe start"):
                current.setdefault("stop", ts)
                current["transcribe_start"] = ts
            elif msg.startswith("session transcript |"):
                current["transcript_at"] = ts
                current["text"] = field(msg, "text") or ""
                api = field(msg, "api") or ""
                current["api_ms"] = int(api[:-2]) if api.endswith("ms") and api[:-2].isdigit() else None
                conf = (field(msg, "confidence_avg") or "").rstrip("%")
                current["confidence"] = int(conf) if conf.isdigit() else None
            elif "unrecognized" in msg and msg.startswith("google chunk"):
                current["unrecognized"] += 1
            elif "failed | UnknownValueError" in msg:
                current["chunk_failed"] += 1
            elif msg.startswith("paste focus |"):
                target, focused = field(msg, "target"), field(msg, "focused")
                if target and focused and target != "0" and target != focused:
                    current["focus_miss"] += 1
            elif msg.startswith("chunk pasted") or msg.startswith("paste sent"):
                current.setdefault("paste", ts)
            elif msg.startswith(("chunk paste skipped", "chunk paste error", "paste skipped")):
                current["paste_fail"] += 1
            elif msg.startswith("session done |"):
                current["done_reason"] = field(msg, "reason")
    for s in sessions:
        if s.get("stop") and s.get("paste"):
            s["latency_ms"] = (s["paste"] - s["stop"]).total_seconds() * 1000
        if s.get("stop") and s.get("transcribe_start"):
            s["capture_wait_ms"] = (s["transcribe_start"] - s["stop"]).total_seconds() * 1000
    return [s for s in sessions if s.get("text")]


def load_transcripts(since: dt.datetime) -> list[dict]:
    out = []
    try:
        with TRANSCRIPTS_FILE.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                    t = dt.datetime.strptime(d["created_at"], "%Y-%m-%d %H:%M:%S")
                except Exception:
                    continue
                if t >= since and d.get("text"):
                    d["at"] = t
                    out.append(d)
    except FileNotFoundError:
        pass
    return out


def message_text(content) -> str:
    """Chu nguoi dung go trong mot tin nhan. Tin co anh hoac noi dung dan luu dang danh sach;
    lay cac phan "text", bo phan the he thong (bat dau bang "<")."""
    if isinstance(content, str):
        return "" if content.startswith("<") else content
    if not isinstance(content, list):
        return ""
    parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
    return "\n".join(p for p in parts if p and not p.lstrip().startswith("<"))


def load_toong_messages(since: dt.datetime) -> list[tuple[dt.datetime, str]]:
    """Tin nhan nguoi dung that su gui trong To Ong (moi account, moi du an)."""
    msgs = []
    cutoff = since.timestamp()
    utc_offset = dt.datetime.now().astimezone().utcoffset() or dt.timedelta(0)
    # Thu muc projects cua moi account thuong la junction tro ve cung ~/.claude/projects:
    # doc moi file that mot lan, neu khong tin nhan bi dem lap theo so account.
    seen: set[str] = set()
    for f in TOONG_ACCOUNTS.glob("*/projects/*/*.jsonl"):
        try:
            if f.stat().st_mtime < cutoff:
                continue
            real = os.path.normcase(os.path.realpath(f))
            if real in seen:
                continue
            seen.add(real)
            with f.open(encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"type":"user"' not in line.replace(" ", ""):
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    content = message_text(d.get("message", {}).get("content"))
                    if not content:
                        continue
                    t = dt.datetime.fromisoformat(d["timestamp"].replace("Z", "")) + utc_offset
                    if t >= since:
                        msgs.append((t, content))
        except OSError:
            continue
    msgs.sort()
    return msgs


def match_deliveries(transcripts: list[dict], messages: list[tuple[dt.datetime, str]]) -> list[dict]:
    """Chu da noi co toi tin nhan that khong, va Founder da sua tay bao nhieu."""
    results = []
    times = [t for t, _ in messages]  # messages da sap theo thoi gian
    for tr in transcripts:
        spoken = norm(tr["text"])
        if len(spoken) < 12:
            continue
        best, best_msg = 0.0, ""
        spoken_words = spoken.split()
        lo = bisect.bisect_left(times, tr["at"])
        hi = bisect.bisect_right(times, tr["at"] + dt.timedelta(minutes=30))
        for t, content in messages[lo:hi]:
            # so theo tu, khong theo ky tu: tin nhan dan dai (hang chuc nghin ky tu) so theo ky tu rat cham
            sm = difflib.SequenceMatcher(None, spoken_words, norm(content).split(), autojunk=False)
            # do phu: phan chu da noi con lai trong tin nhan gui di
            cover = sum(b.size for b in sm.get_matching_blocks()) / max(1, len(spoken_words))
            if cover > best:
                best, best_msg = cover, content
        results.append({"at": tr["at"], "hwnd": tr.get("hwnd"), "spoken": tr["text"],
                        "sent": best_msg if best >= 0.6 else "", "cover": round(best, 3)})
    return results


def measure(days: int) -> dict:
    since = now() - dt.timedelta(days=days)
    sessions = parse_sessions(since)
    transcripts = load_transcripts(since)
    messages = load_toong_messages(since)

    # Cua so da dong (To Ong khoi dong lai) thi Windows khong con biet no la cua ai; chi loai
    # lan noi vao cua so con song cua chuong trinh khac, con lai de phan so noi dung quyet dinh.
    other_hwnds = {h for h in {t.get("hwnd") for t in transcripts} if hwnd_exe(h).lower() not in ("", "toong.exe")}
    deliveries = match_deliveries([t for t in transcripts if t.get("hwnd") not in other_hwnds], messages)

    n = len(sessions)
    lat = [s["latency_ms"] for s in sessions if "latency_ms" in s]
    api = [s["api_ms"] for s in sessions if s.get("api_ms")]
    wait = [s["capture_wait_ms"] for s in sessions if "capture_wait_ms" in s]
    conf = [s["confidence"] for s in sessions if s.get("confidence") is not None]
    delivered = [d for d in deliveries if d["sent"]]

    return {
        "window_days": days,
        "since": since.isoformat(timespec="seconds"),
        "sessions": n,
        "latency_p50_ms": round(quantile(lat, 0.5)),
        "latency_p90_ms": round(quantile(lat, 0.9)),
        "api_p50_ms": round(quantile(api, 0.5)),
        "capture_wait_p50_ms": round(quantile(wait, 0.5)),
        "cold_load_sessions": sum(1 for s in sessions if s.get("cold_load")),
        "cold_load_rate": round(sum(1 for s in sessions if s.get("cold_load")) / n, 3) if n else 0,
        "low_conf_sessions": sum(1 for c in conf if c < LOW_CONF),
        "low_conf_rate": round(sum(1 for c in conf if c < LOW_CONF) / len(conf), 3) if conf else 0,
        "confidence_avg": round(statistics.mean(conf)) if conf else None,
        "unrecognized_chunks": sum(s["unrecognized"] + s["chunk_failed"] for s in sessions),
        "paste_fail_sessions": sum(1 for s in sessions if s["paste_fail"] or s["focus_miss"]),
        "paste_fail_rate": round(sum(1 for s in sessions if s["paste_fail"] or s["focus_miss"]) / n, 3) if n else 0,
        "toong_transcripts": len(deliveries),
        "toong_delivered": len(delivered),
        "delivery_rate": round(len(delivered) / len(deliveries), 3) if deliveries else None,
        "edit_rate": round(1 - statistics.mean(d["cover"] for d in delivered), 3) if delivered else None,
        "_deliveries": deliveries,
        "_sessions": sessions,
    }


# ---------------------------------------------------------------- nhip 2: CHAN

def diagnose(m: dict) -> list[dict]:
    n = max(1, m["sessions"])
    f: list[dict] = []

    if m["cold_load_rate"] > TARGET_COLD_LOAD_RATE:
        f.append({"id": "WHISPER_COLD_LOAD", "actor": "loop", "metric": "cold_load_rate", "goal": "down",
                  "value": m["cold_load_rate"], "target": TARGET_COLD_LOAD_RATE,
                  "impact": m["cold_load_sessions"],
                  "root_cause": "Whisper bi do khoi RAM sau thoi gian nghi, phien dau tien phai nap lai model (~28 giay) lam cham ca may",
                  "evidence": f"{m['cold_load_sessions']}/{m['sessions']} phien trung luc nap Whisper"})

    if m["latency_p50_ms"] > TARGET_LATENCY_P50_MS:
        api_share = m["api_p50_ms"] / max(1, m["latency_p50_ms"])
        cause = ("Thoi gian nhan dang (Google + Whisper tren CPU) chiem phan lon do tre"
                 if api_share >= 0.5 else
                 "Thoi gian tu luc dung noi den luc bat dau nhan dang qua lau (capture_wait)")
        f.append({"id": "LATENCY_HIGH", "actor": "codex", "metric": "latency_p50_ms", "goal": "down",
                  "value": m["latency_p50_ms"], "target": TARGET_LATENCY_P50_MS,
                  "impact": round(n * min(1.0, m["latency_p50_ms"] / TARGET_LATENCY_P50_MS - 1)),
                  "root_cause": cause,
                  "evidence": f"p50={m['latency_p50_ms']} ms, p90={m['latency_p90_ms']} ms, nhan dang p50={m['api_p50_ms']} ms, capture_wait p50={m['capture_wait_p50_ms']} ms"})

    if m["paste_fail_rate"] > TARGET_PASTE_FAIL_RATE:
        f.append({"id": "PASTE_FAIL", "actor": "codex", "metric": "paste_fail_rate", "goal": "down",
                  "value": m["paste_fail_rate"], "target": TARGET_PASTE_FAIL_RATE,
                  "impact": m["paste_fail_sessions"],
                  "root_cause": "Dan hong: sai cua so focus hoac clipboard ban khi dan",
                  "evidence": f"{m['paste_fail_sessions']}/{m['sessions']} phien co paste error hoac focus lech"})

    if m["delivery_rate"] is not None and m["delivery_rate"] < TARGET_DELIVERY_RATE:
        lost = m["toong_transcripts"] - m["toong_delivered"]
        f.append({"id": "TOONG_NOT_DELIVERED", "actor": "codex", "metric": "delivery_rate", "goal": "up",
                  "value": m["delivery_rate"], "target": TARGET_DELIVERY_RATE, "impact": lost,
                  "root_cause": "Chu da noi khong xuat hien trong tin nhan gui di o To Ong (dan rong, Founder xoa di hoac noi nham o)",
                  "evidence": f"{m['toong_delivered']}/{m['toong_transcripts']} ban ghi toi duoc tin nhan To Ong trong 30 phut"})

    if m["low_conf_rate"] > TARGET_LOW_CONF_RATE:
        f.append({"id": "LOW_CONFIDENCE", "actor": "codex", "metric": "low_conf_rate", "goal": "down",
                  "value": m["low_conf_rate"], "target": TARGET_LOW_CONF_RATE,
                  "impact": m["low_conf_sessions"],
                  "root_cause": "Nhieu phien nhan dang do tin cay thap, nhieu chunk Google khong nghe ra",
                  "evidence": f"{m['low_conf_sessions']} phien < {LOW_CONF}%, {m['unrecognized_chunks']} chunk khong nhan ra"})

    f.sort(key=lambda x: x["impact"], reverse=True)
    return f


# ---------------------------------------------------------------- nhip 3: SUA

def load_local_settings() -> dict:
    return read_json(LOCAL_SETTINGS, {})


def save_local_settings(data: dict, dry: bool) -> None:
    if dry:
        return
    backup = LOCAL_SETTINGS.with_name(f"{LOCAL_SETTINGS.name}.bak-kaizen-{now():%Y%m%d-%H%M%S}")
    if LOCAL_SETTINGS.exists():
        shutil.copy2(LOCAL_SETTINGS, backup)
    write_json(LOCAL_SETTINGS, data)


def learn_corrections(deliveries: list[dict], dry: bool) -> list[dict]:
    """Hoc tu nghe sai: cum tu Founder sua tay truoc khi gui, lap lai >= 2 lan, va chua tung duoc giu nguyen."""
    pairs: dict[tuple[str, str], int] = {}
    kept: set[str] = set()
    for d in deliveries:
        if not d["sent"]:
            continue
        a, b = d["spoken"].split(), d["sent"].split()
        sm = difflib.SequenceMatcher(None, [norm(w) for w in a], [norm(w) for w in b], autojunk=False)
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == "equal":
                for k in range(i1, i2):
                    kept.add(norm(a[k]))
                    if k + 1 < i2:
                        kept.add(norm(a[k] + " " + a[k + 1]))
            elif op == "replace" and 1 <= i2 - i1 <= 3 and 1 <= j2 - j1 <= 3:
                src = " ".join(a[i1:i2]).strip(".,!?;:")
                dst = " ".join(b[j1:j2]).strip(".,!?;:")
                if src and dst and norm(src) != norm(dst) and len(norm(src)) >= 3:
                    pairs[(src, dst)] = pairs.get((src, dst), 0) + 1

    settings = load_local_settings()
    reps = settings.setdefault("speech_cleanup_replacements", [])
    existing = {str(r.get("pattern", "")) for r in reps}
    learned = []
    for (src, dst), count in sorted(pairs.items(), key=lambda kv: -kv[1]):
        if count < LEARN_MIN_COUNT or norm(src) in kept:
            continue
        pattern = r"(?<!\w)" + r"\s+".join(re.escape(w) for w in src.split()) + r"(?!\w)"
        if pattern in existing:
            continue
        reps.append({"pattern": pattern, "replacement": dst, "regex": True, "nguon": LEARNED_SOURCE,
                     "learned_at": now().strftime("%Y-%m-%d"), "seen": count})
        existing.add(pattern)
        learned.append({"from": src, "to": dst, "seen": count})
    if learned:
        save_local_settings(settings, dry)
    return learned


def voinoi_idle() -> bool:
    """Khong dang co phien noi nao: dong log cuoi cu hon 3 phut."""
    try:
        return time.time() - LOG_FILE.stat().st_mtime > 180
    except OSError:
        return False


def restart_voinoi(dry: bool) -> str:
    if dry:
        return "dry-run"
    if not voinoi_idle():
        return "hoan: VoiNoi dang duoc dung, lan chay sau se khoi dong lai"
    subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                      "-File", str(START_SCRIPT)], cwd=str(ROOT), creationflags=0x08000000)
    return "da khoi dong lai"


def fix_whisper_idle(finding: dict, dry: bool) -> dict:
    settings = load_local_settings()
    base = read_json(BASE_SETTINGS, {})
    cur = float(settings.get("whisper_idle_unload_minutes", base.get("whisper_idle_unload_minutes", 15)) or 0)
    nxt = next((s for s in WHISPER_IDLE_STEPS if s > cur), None)
    ram = free_ram_gb()
    if cur == 0:
        return {"action": "skip", "why": "Whisper da giu san vinh vien"}
    if nxt is None:
        return {"action": "maxed", "why": f"da o nac cao nhat {cur:.0f} phut"}
    if ram < MIN_FREE_RAM_GB_TO_KEEP_WHISPER:
        return {"action": "skip", "why": f"RAM trong chi con {ram:.1f} GB, giu Whisper lau hon se lam may nang"}
    settings["whisper_idle_unload_minutes"] = nxt
    save_local_settings(settings, dry)
    restart = restart_voinoi(dry)
    return {"action": "applied", "change": f"whisper_idle_unload_minutes {cur:.0f} -> {nxt}",
            "ram_free_gb": round(ram, 1), "restart": restart,
            "predicted": {"metric": "cold_load_rate", "value": round(finding["value"] * cur / nxt, 3)}}


def fingerprint(finding: dict, level: int = 0) -> str:
    raw = f"{finding['id']}|L{level}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


OPEN_BOARDS = ("Inbox", "Backlog", "This-Week", "Today", "Waiting-Review", "Doing", "In-Progress")


def open_ticket(finding: dict, level: int) -> Path | None:
    """Phieu cung loi, cung nac con mo o bat ky cot nao (khong phu thuoc cau chu nguyen nhan)."""
    for board in OPEN_BOARDS:
        for p in (INBOX_DIR.parent / board).glob(f"*-kaizen-voinoi-{finding['id'].lower()}-*.md"):
            try:
                m = re.search(r"Kaizen-Level: (\d+)", p.read_text(encoding="utf-8"))
            except OSError:
                continue
            if (int(m.group(1)) if m else 0) == level:
                return p
    return None


def write_ticket(finding: dict, level: int, report_path: Path, dry: bool) -> str:
    fp = fingerprint(finding, level)
    existing = open_ticket(finding, level)
    if existing:
        return f"skip-dup: {finding['id']} nac {level} -> {existing.parent.name}/{existing.name}"
    prio = "P0" if level > 0 else "P1"
    model = MODEL_BY_LEVEL.get(level, "opus")
    extra = ("\nLEO NAC " + str(level) + ": cach sua truoc KHONG lam metric tot len. Doi cach lam, dao root cause MOI, "
             "duoc refactor rong hon.\n") if level else ""
    body = f"""Task: [Kaizen VoiNoi] Sua mat xich yeu: {finding['root_cause']}
Owner/Agent: codex-worker
Phong ban: Cong cu noi bo (VoiNoi, E:\\VietnameseVoiceMic)
Uu tien: {prio}
Deadline: {(now() + dt.timedelta(days=2)):%Y-%m-%d}
Dau vao: report kaizen {report_path} + so do that
Output can tra: sua goc mat xich trong voice_mic_icon.py, chay lai, verify bang so that (khong ha chuan)
Can Founder duyet: Khong
Workflow dung: dg-code-worker
Worker: codex
Model: {model}
Muc-tieu-dich: {finding['metric']} {'<=' if finding['goal'] == 'down' else '>='} {finding['target']}
Tai-chinh-cap: XANH
Do-luong: {finding['metric']} (hien {finding['value']}) do bang kaizen/voinoi_kaizen.py
Kaizen-Fingerprint: {fp}
Kaizen-Level: {level}
{extra}
Bang chung: {finding['evidence']}
"""
    name = f"{now():%Y%m%d}-kaizen-voinoi-{finding['id'].lower()}-{fp}.md"
    if not dry:
        INBOX_DIR.mkdir(parents=True, exist_ok=True)
        (INBOX_DIR / name).write_text(body, encoding="utf-8")
    return f"ticket: {finding['id']} -> {name} (nac {level}, {model})"


def write_founder_item(finding: dict, tries: int, dry: bool) -> str:
    name = f"{now():%Y%m%d}-kaizen-voinoi-{finding['id'].lower()}.md"
    body = f"""# Quyet dinh cho Founder: VoiNoi {finding['id']}

Loop-VoiNoi da thu {tries} nac sua ma chi so {finding['metric']} khong tot len.
Hien: {finding['value']} (muc tieu {finding['target']}).
Nguyen nhan dang nghi: {finding['root_cause']}
Bang chung: {finding['evidence']}

Can Founder chon: chap nhan muc hien tai, doi cong cu nhan dang, hoac cap them tai nguyen.
Loop da NGUNG bom phieu cho loi nay.
"""
    if not dry:
        FOUNDER_QUEUE_DIR.mkdir(parents=True, exist_ok=True)
        (FOUNDER_QUEUE_DIR / name).write_text(body, encoding="utf-8")
    return f"founder-queue: {finding['id']} -> {name}"


def improved(history: list[dict], goal: str) -> bool:
    if len(history) < 2:
        return True
    a, b = history[-2]["metric"], history[-1]["metric"]
    return b < a if goal == "down" else b > a


SHARED_DICT_SCRIPT = Path.home() / ".claude" / "skills" / "hieu-giong-noi" / "scripts" / "nhan_tu_voinoi.py"


def share_learned() -> str:
    """Dua luat vua hoc ve tu dien giong noi dung chung (skill hieu-giong-noi) neu may co skill do,
    de Claude va cac app khac cung sua duoc cung tu, khong chi VoiNoi."""
    if not SHARED_DICT_SCRIPT.exists():
        return "tu-dien-chung: bo qua (may khong co skill hieu-giong-noi)"
    out = subprocess.run([sys.executable, str(SHARED_DICT_SCRIPT), "--ap-dung"], capture_output=True,
                         text=True, encoding="utf-8", errors="replace", timeout=120)
    first = (out.stdout.strip().splitlines() or ["(khong co dau ra)"])[0]
    return f"tu-dien-chung: {first}" if out.returncode == 0 else f"tu-dien-chung LOI: {out.stderr.strip()[:200]}"


def act(findings: list[dict], m: dict, state: dict, report_path: Path, dry: bool) -> list[str]:
    actions: list[str] = []
    today = now().strftime("%Y-%m-%d")

    # Tu sua an toan 1: hoc tu nghe sai (co hieu luc ngay, VoiNoi doc lai file khi doi)
    learned = learn_corrections(m["_deliveries"], dry)
    for item in learned:
        actions.append(f"hoc-tu: '{item['from']}' -> '{item['to']}' (gap {item['seen']} lan)")
    state.setdefault("learned", []).extend({**x, "date": today} for x in learned)
    if learned and not dry:
        actions.append(share_learned())

    ticket_sent = False
    for f in findings:
        rec = state.setdefault("findings", {}).setdefault(f["id"], {"history": [], "level": 0, "tickets": 0})
        hist = rec["history"]
        if not hist or hist[-1]["date"] != today:
            hist.append({"date": today, "metric": f["value"]})
        else:
            hist[-1]["metric"] = f["value"]
        del hist[:-30]

        if f["actor"] == "loop" and f["id"] == "WHISPER_COLD_LOAD":
            res = fix_whisper_idle(f, dry)
            actions.append(f"tu-sua WHISPER_COLD_LOAD: {res.get('change') or res['why']}"
                           + (f" | {res['restart']}" if res.get("restart") else ""))
            if res.get("predicted"):
                state.setdefault("predictions", []).append({"date": today, **res["predicted"]})
            continue

        if f["actor"] != "codex" or ticket_sent:
            continue  # moi nhip chi 1 phieu sua
        if rec.get("parked"):
            actions.append(f"parked: {f['id']} da leo Founder, khong bom them")
            continue
        if rec["tickets"] >= STUCK_AFTER and not improved(hist, f["goal"]):
            rec["level"] += 1
            rec["tickets"] = 0
            if rec["level"] > MAX_FIX_LEVEL:
                rec["parked"] = True
                actions.append(write_founder_item(f, MAX_FIX_LEVEL, dry))
                continue
        elif improved(hist, f["goal"]) and len(hist) >= 2:
            rec["level"] = 0
        msg = write_ticket(f, rec["level"], report_path, dry)
        # Dem so NGAY phieu o nac nay ton tai ma metric chua dat (ca phieu moi lan phieu con mo)
        if rec.get("last_ticket_day") != today:
            rec["tickets"] += 1
            rec["last_ticket_day"] = today
        if msg.startswith("ticket"):
            ticket_sent = True
        actions.append(msg)

    # finding da het (metric dat) -> reset
    alive = {f["id"] for f in findings}
    for fid, rec in state.get("findings", {}).items():
        if fid not in alive and (rec.get("level") or rec.get("parked")):
            rec.update(level=0, tickets=0, parked=False)
            actions.append(f"dat-muc-tieu: {fid} reset thang leo")
    return actions


# ---------------------------------------------------------------- nhip 4: XAC MINH

def verify(m: dict, state: dict) -> list[dict]:
    out = []
    remaining = []
    today = now().strftime("%Y-%m-%d")
    for p in state.get("predictions", []):
        if p["date"] == today or p.get("due", "") > today:
            remaining.append(p)
            continue
        actual = m.get(p["metric"])
        out.append({"metric": p["metric"], "predicted": p["value"], "actual": actual,
                    "from": p["date"], "error": None if actual is None else round(actual - p["value"], 3),
                    "note": p.get("note", "")})
    state["predictions"] = remaining
    state.setdefault("verified", []).extend(out)
    del state["verified"][:-50]
    return out


# ---------------------------------------------------------------- nhip 5: LAP (report)

def metric_rows(m: dict) -> list[tuple[str, str, str, bool]]:
    def ok(v, t, goal):
        return v is not None and (v <= t if goal == "down" else v >= t)
    return [
        ("Độ trễ nói xong tới lúc có chữ (p50)", f"{m['latency_p50_ms'] / 1000:.1f} giây", f"≤ {TARGET_LATENCY_P50_MS / 1000:.0f} giây",
         ok(m["latency_p50_ms"], TARGET_LATENCY_P50_MS, "down")),
        ("Độ trễ p90", f"{m['latency_p90_ms'] / 1000:.1f} giây", "theo dõi", True),
        ("Thời gian nhận dạng, Google + Whisper (p50)", f"{m['api_p50_ms'] / 1000:.1f} giây", "theo dõi", True),
        ("Phiên trúng lúc nạp Whisper", f"{m['cold_load_sessions']} ({pct(m['cold_load_rate'])})", f"≤ {pct(TARGET_COLD_LOAD_RATE)}",
         ok(m["cold_load_rate"], TARGET_COLD_LOAD_RATE, "down")),
        ("Phiên độ tin cậy thấp", f"{m['low_conf_sessions']} ({pct(m['low_conf_rate'])})", f"≤ {pct(TARGET_LOW_CONF_RATE)}",
         ok(m["low_conf_rate"], TARGET_LOW_CONF_RATE, "down")),
        ("Phiên dán lỗi (log)", f"{m['paste_fail_sessions']} ({pct(m['paste_fail_rate'])})", "0",
         ok(m["paste_fail_rate"], TARGET_PASTE_FAIL_RATE, "down")),
        ("Chữ nói tới được tin nhắn Tổ Ong",
         "chưa có dữ liệu" if m["delivery_rate"] is None else f"{m['toong_delivered']}/{m['toong_transcripts']} ({pct(m['delivery_rate'])})",
         f"≥ {pct(TARGET_DELIVERY_RATE)}", m["delivery_rate"] is None or ok(m["delivery_rate"], TARGET_DELIVERY_RATE, "up")),
        ("Phần chữ Founder sửa tay", "chưa có dữ liệu" if m["edit_rate"] is None else pct(m["edit_rate"]), "theo dõi", True),
    ]


def render_md(m, findings, actions, checks, state) -> str:
    lines = [f"# Kaizen VoiNoi {now():%Y-%m-%d %H:%M}", "",
             f"Cửa sổ đo: {m['window_days']} ngày, {m['sessions']} phiên nói.", "", "## Đo", ""]
    for name, val, target, good in metric_rows(m):
        lines.append(f"- {'✅' if good else '❌'} {name}: {val} (mục tiêu {target})")
    lines += ["", "## Chẩn (xếp theo impact)", ""]
    lines += [f"- [{f['actor']}] {f['id']} impact={f['impact']}: {f['root_cause']}. Bằng chứng: {f['evidence']}"
              for f in findings] or ["- Không còn mắt xích yếu vượt ngưỡng."]
    lines += ["", "## Sửa", ""] + ([f"- {a}" for a in actions] or ["- Không có hành động."])
    lines += ["", "## Xác minh (dự đoán so với thực tế)", ""]
    lines += [f"- {c['metric']}: dự đoán {c['predicted']}, thực tế {c['actual']} (từ {c['from']})" for c in checks] \
        or ["- Chưa có dự đoán nào tới hạn đối chiếu."]
    lines += ["", "## Thông tin còn thiếu", "",
              "- info_gap: chưa đo trực tiếp được lần Founder phải bấm Ctrl+V lại; đang đo gián tiếp qua tỉ lệ chữ tới tin nhắn Tổ Ong.",
              "", "## Liên kết hệ sinh thái", "",
              "- supports: Founder ra lệnh bằng giọng nói cho mọi ô Tổ Ong",
              "- depends_on: voice-mic.log, voice-transcripts.jsonl, hội thoại Tổ Ong (~/.toong/accounts)",
              "- handoff_to: codex-worker qua DG-Core/04-Task-Boards/Inbox; Founder-Decision-Queue khi hết nấc",
              "- kpi: độ trễ p50, tỉ lệ chữ tới đích, tỉ lệ nạp nguội Whisper",
              "- owner: Loop-VoiNoi", "- gate: không hạ mục tiêu, mỗi nhịp tối đa 1 phiếu",
              "- missing_links: tín hiệu Ctrl+V dán lại (info_gap)"]
    return "\n".join(lines).replace("—", ",").replace("–", ",") + "\n"


def render_html(m, findings, actions, checks, state) -> str:
    e = html.escape
    rows = "".join(
        f"<tr><td>{e(n)}</td><td class='{'ok' if g else 'no'}'>{e(v)}</td><td>{e(t)}</td></tr>"
        for n, v, t, g in metric_rows(m))
    finds = "".join(
        f"<li><b>{e(f['id'])}</b> <span class='tag'>{e(f['actor'])}</span> <span class='tag'>impact {f['impact']}</span>"
        f"<br>{e(f['root_cause'])}<br><small>{e(f['evidence'])}</small></li>" for f in findings
    ) or "<li>Không còn mắt xích yếu vượt ngưỡng.</li>"
    acts = "".join(f"<li>{e(a)}</li>" for a in actions) or "<li>Không có hành động.</li>"
    chk = "".join(f"<li>{e(c['metric'])}: dự đoán {c['predicted']}, thực tế {c['actual']} (từ {e(c['from'])})</li>"
                  for c in checks) or "<li>Chưa có dự đoán nào tới hạn đối chiếu.</li>"
    ladder = "".join(
        f"<tr><td>{e(fid)}</td><td>{rec.get('level', 0)}</td><td>{rec.get('tickets', 0)}</td>"
        f"<td>{'Đã báo Founder' if rec.get('parked') else 'Đang tự sửa'}</td>"
        f"<td>{e(' → '.join(str(h['metric']) for h in rec.get('history', [])[-7:]))}</td></tr>"
        for fid, rec in state.get("findings", {}).items()) or "<tr><td colspan=5>Chưa có</td></tr>"
    learned = "".join(f"<li>“{e(x['from'])}” thành “{e(x['to'])}” ({e(x['date'])})</li>"
                      for x in state.get("learned", [])[-15:]) or "<li>Chưa học từ nào.</li>"
    runs = state.get("runs", [])[-14:]
    spark = ""
    if len(runs) >= 2:
        vals = [r["latency_p50_ms"] for r in runs]
        hi = max(vals) or 1
        pts = " ".join(f"{20 + i * (560 / (len(vals) - 1)):.0f},{110 - v / hi * 90:.0f}" for i, v in enumerate(vals))
        spark = (f"<svg viewBox='0 0 600 130' role='img' aria-label='Độ trễ p50 qua các lần chạy'>"
                 f"<polyline points='{pts}' fill='none' stroke='var(--accent)' stroke-width='3'/>"
                 f"<text x='20' y='125' class='muted'>{e(runs[0]['at'][:16])}</text>"
                 f"<text x='580' y='125' text-anchor='end' class='muted'>{e(runs[-1]['at'][:16])}</text></svg>")
    else:
        spark = "<p class='muted'>Cần ít nhất 2 lần chạy để vẽ xu hướng.</p>"
    page = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Loop VoiNoi</title>
<style>
:root{{--bg:#f6f5f1;--card:#fff;--ink:#1d1d1b;--muted:#6b6a64;--line:#dcdad2;--accent:#2f6fd6;--ok:#1f9d6b;--no:#d4483b}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#16171a;--card:#1f2024;--ink:#ecebe6;--muted:#9d9c95;--line:#34353a;--accent:#6b9cf0;--ok:#45c28f;--no:#f07466}}}}
:root[data-theme="dark"]{{--bg:#16171a;--card:#1f2024;--ink:#ecebe6;--muted:#9d9c95;--line:#34353a;--accent:#6b9cf0;--ok:#45c28f;--no:#f07466}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 "Segoe UI",system-ui,sans-serif}}
main{{max-width:980px;margin:0 auto;padding:28px 16px 60px}}h1{{margin:0;font-size:26px}}h2{{font-size:19px;margin:28px 0 10px}}
.muted{{color:var(--muted);fill:var(--muted);font-size:13px}}.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;margin:12px 0;overflow-x:auto}}
table{{width:100%;border-collapse:collapse}}td,th{{text-align:left;padding:8px;border-bottom:1px solid var(--line);vertical-align:top}}th{{color:var(--muted)}}
.ok{{color:var(--ok);font-weight:600}}.no{{color:var(--no);font-weight:600}}.tag{{font-size:12px;border:1px solid var(--line);border-radius:99px;padding:1px 8px;color:var(--muted)}}
ol.loop{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;list-style:none;padding:0;counter-reset:s}}
ol.loop li{{counter-increment:s;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}}
ol.loop li::before{{content:counter(s) ". ";font-weight:700;color:var(--accent)}}svg{{width:100%;height:auto}}
</style></head><body><main>
<h1>Loop VoiNoi tự cải thiện</h1>
<p class="muted">Lần chạy {now():%Y-%m-%d %H:%M}. Cửa sổ đo {m['window_days']} ngày, {m['sessions']} phiên nói. Lịch: tự chạy mỗi 3 giờ.</p>
<ol class="loop"><li>Đo từ log thật</li><li>Chẩn mắt xích yếu</li><li>Sửa: tự sửa hoặc bơm phiếu</li><li>Xác minh dự đoán</li><li>Lặp theo lịch</li></ol>
<h2>1. Đo</h2><div class="card"><table><tr><th>Chỉ số</th><th>Hiện tại</th><th>Mục tiêu</th></tr>{rows}</table></div>
<h2>Xu hướng độ trễ p50</h2><div class="card">{spark}</div>
<h2>2. Chẩn</h2><div class="card"><ul>{finds}</ul></div>
<h2>3. Sửa (lần chạy này)</h2><div class="card"><ul>{acts}</ul></div>
<h2>Thang leo tự sửa</h2><div class="card"><table><tr><th>Lỗi</th><th>Nấc</th><th>Phiếu ở nấc</th><th>Trạng thái</th><th>Chỉ số 7 lần gần nhất</th></tr>{ladder}</table></div>
<h2>Từ loop đã tự học</h2><div class="card"><ul>{learned}</ul></div>
<h2>4. Xác minh</h2><div class="card"><ul>{chk}</ul></div>
<p class="muted">info_gap: chưa đo trực tiếp được lần Founder phải bấm Ctrl+V lại; đang đo gián tiếp qua tỉ lệ chữ tới tin nhắn Tổ Ong.</p>
</main></body></html>"""
    return page.replace("—", ",").replace("–", ",")


def main() -> int:
    ap = argparse.ArgumentParser()
    # 3 ngay (~30 phien): du so de tin, du nhanh de thang leo 3 ngay thay duoc tac dung cua ban sua
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    state = read_json(STATE_FILE, {})
    stamp = now().strftime("%Y-%m-%d")
    md_path = REPORT_DIR / f"kaizen-{stamp}.md"

    m = measure(args.days)                                   # 1. DO
    findings = diagnose(m)                                   # 2. CHAN
    checks = verify(m, state)                                # 4. XAC MINH (truoc khi dat du doan moi)
    actions = act(findings, m, state, md_path, args.dry_run)  # 3. SUA

    public = {k: v for k, v in m.items() if not k.startswith("_")}
    state.setdefault("runs", []).append({"at": now().isoformat(timespec="seconds"), **public})
    del state["runs"][:-200]

    md = render_md(m, findings, actions, checks, state)      # 5. LAP
    page = render_html(m, findings, actions, checks, state)
    if not args.dry_run:
        md_path.write_text(md, encoding="utf-8")
        write_json(REPORT_DIR / f"kaizen-{stamp}.json",
                   {"metrics": public, "findings": findings, "actions": actions, "verified": checks})
        (REPORT_DIR / "dashboard.html").write_text(page, encoding="utf-8")
        write_json(STATE_FILE, state)
        with (REPORT_DIR / "cron.log").open("a", encoding="utf-8") as fh:
            fh.write(f"{now():%Y-%m-%d %H:%M:%S} sessions={m['sessions']} p50={m['latency_p50_ms']} "
                     f"findings={[f['id'] for f in findings]} actions={len(actions)}\n")
    # Task Scheduler chay bang pythonw.exe: khong co console, sys.stdout la None.
    # Truoc day dong nay lam moi lan chay bao that bai (ma 1) du viec da xong.
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8")
        print(md)
    if args.open and not args.dry_run:
        subprocess.Popen(["cmd", "/c", "start", "", str(REPORT_DIR / "dashboard.html")], creationflags=0x08000000)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
