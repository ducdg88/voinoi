"""Tro ly doc tai lieu (chay local). Mo: .venv\\Scripts\\pythonw.exe doc_reader.py"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.request
import webbrowser
from pathlib import Path

from reader import store
from reader.server import log, make_server

BROWSER_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def already_running(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=1.5) as response:
            return json.loads(response.read().decode("utf-8")).get("app") == "doc-reader"
    except Exception:
        return False


# giao viec "doc tai lieu nay" tu dong lenh: khong ai bam nut nen phai cho phep tu phat tieng
AUTOPLAY = "--autoplay-policy=no-user-gesture-required"


def open_ui(url: str, mode: str) -> None:
    if mode == "app":
        for candidate in BROWSER_CANDIDATES:
            if Path(candidate).exists():
                subprocess.Popen([candidate, f"--app={url}", "--window-size=1320,880", AUTOPLAY])
                return
        found = shutil.which("chrome") or shutil.which("msedge")
        if found:
            subprocess.Popen([found, f"--app={url}", AUTOPLAY])
            return
    webbrowser.open(url)


def main() -> int:
    settings = store.load_settings()
    parser = argparse.ArgumentParser(description="Tro ly doc tai lieu bang giong tieng Viet")
    parser.add_argument("--port", type=int, default=int(settings.get("port", 8767)))
    parser.add_argument("--no-browser", action="store_true", help="chi chay may chu, khong mo cua so")
    parser.add_argument("--tab", action="store_true", help="mo trong tab trinh duyet thay vi cua so rieng")
    parser.add_argument("file", nargs="?", help="file can mo ngay (tuy chon)")
    args = parser.parse_args()

    url = f"http://127.0.0.1:{args.port}/"
    if args.file:
        from urllib.parse import quote
        url += "#open=" + quote(str(Path(args.file).resolve()))
    mode = "tab" if args.tab else str(settings.get("open_mode", "app"))

    if already_running(args.port):
        if not args.no_browser:
            open_ui(url, mode)
        return 0

    try:
        server = make_server(args.port)
    except OSError as exc:
        log(f"khong mo duoc cong {args.port}: {exc}")
        print(f"Cong {args.port} dang bi chuong trinh khac dung. Doi 'port' trong reader-data/settings.json.")
        return 1
    log(f"doc reader started on {url}")
    if not args.no_browser:
        open_ui(url, mode)
    print(f"Tro ly doc dang chay: {url}  (Ctrl+C de tat)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
