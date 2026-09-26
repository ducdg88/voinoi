# Vietnamese Voice Mic

Ung dung Windows chay nen de nhap tieng Viet bang giong noi vao o chat/input.

## Tinh nang chinh

- Kich hoat bang `Alt + click chuot trai` vao dung o muon nhap.
- Khoa cua so va vi tri ban dau, sau khi nhan dien se dan lai dung vi tri do.
- Nhan dien tieng Viet bang Google Speech Recognition, co confidence trong log/HUD khi Google tra ve.
- VAD bang WebRTC/RMS de biet khi nao dang noi va khi nao da ngung.
- Toi uu cho doan noi dai: cat chunk tai vung am luong thap, gui chunk song song, ghep bo trung lap.
- HUD/vong tron hien trang thai: dang nghe, dang nhan dien, da co text.
- Bao ve dan nham: neu cua so target da dong thi bo qua dan.
- Recovery: transcript moi nhat duoc giu tren clipboard, luu vao `voice-last.txt`,
  lich su luu vao `voice-transcripts.jsonl`, audio gan nhat luu vao `voice-last.wav`.
- Co the build ban Windows `.exe`, tao zip release va manifest update.
- Auto-update doc manifest tu GitHub Release latest.
- Du lieu ca nhan/context hoc rieng luu local va khong dua len GitHub.

## Cach dung nhanh

1. Chay `Start Vietnamese Voice Mic.cmd`.
2. Giu `Alt` va click chuot trai vao o chat/input muon nhap.
3. Khi vong tron hien `DANG NGHE`, noi noi dung can nhap.
4. Khi ban ngung noi, app doi sang `DANG NHAN DIEN`.
5. Khi co ket qua, app hien preview va tu dan vao dung vi tri da `Alt + click`.
6. Sau khi app nhan dien, ban co the bam `Ctrl+V` de dan lai transcript moi nhat neu can.
7. Khi dang nghe, bam `Esc` de dung va xu ly phan audio da thu.

## Cuu lai noi dung vua noi

Neu app cat cau, dan loi, hoac ban doi cua so lam target khong con dung:

- Bam `Ctrl+V` de dan lai transcript moi nhat vi app giu no tren clipboard.
- Mo `voice-last.txt` de xem transcript moi nhat.
- Mo `voice-transcripts.jsonl` de xem lich su cac lan nhan dien.
- File `voice-last.wav` giu audio gan nhat, huu ich khi can kiem tra lai am thanh da thu.

Nhung file recovery nay nam tren may cua ban va da duoc dua vao `.gitignore`, khong day len GitHub.

## Cau hinh mic

File cau hinh:

```text
voice-mic-settings.json
```

Vi du:

```json
{
  "preferred_microphone": "BKD-11 Pro Audio",
  "microphone_name_hints": [
    "BKD-11 Pro Audio",
    "USB Audio Device",
    "Microphone",
    "Headset"
  ],
  "enable_particle_effect": true,
  "enable_context_memory": true
}
```

Neu muon app tu chon mic theo danh sach goi y, dat:

```json
"preferred_microphone": ""
```

## Tro ly doc tai lieu (Doc Reader)

Tro ly doc to tai lieu, ghi chu, bai nghien cuu bang giong tieng Viet tu nhien (Hoai My / Nam Minh),
de chi can nghe. Dang nghe ma thac mac thi dat cau hoi hoac ghi chu ngay tai cau do.

- Mo: chay `Start Doc Reader.cmd` (hoac keo tha mot file len file nay de mo ngay file do).
- Dau vao: txt, md (Obsidian), pdf co lop chu, docx, html, epub, link web, Google Docs cong khai,
  noi dung vua `Ctrl+C` (chu, link hoac duong dan file).
- Doc tung cau, to sang cau dang doc, tu cuon theo, doc truoc cac cau ke tiep de khong bi ngat.
- Cau tieng Anh tu doi sang giong tieng Anh. Toc do 0.8x den 2x. Nho vi tri dang nghe cua tung tai lieu.
- Phim tat: `Space` doc/dung, `<-` `->` cau truoc/sau, `Shift` + mui ten nhay doan, `N` ghi chu,
  `Q` dat cau hoi, `R` doc lai cau hien tai. Nut tai nghe va phim media cung dieu khien duoc.
- Ghi chu nhap bang tay, bang micro trong o ghi chu, hoac bang Voice Mic (`Alt + click`).
- Moi tai lieu co mot file ghi chu Markdown trong `reader-data/notes/` (kem cau trich, ngu canh doan van,
  danh sach cau hoi chua ro). `reader-data/notes/_INDEX.md` liet ke tat ca. Nut `Copy de hoi Claude`
  tao san loi nhan kem duong dan file de dan cho Claude doc va tra loi.
- Chay local tai `http://127.0.0.1:8767`, chi nhan ket noi tu chinh may nay. Can Internet de tao giong doc
  (dich vu giong doc cua Microsoft Edge qua `edge-tts`), am thanh duoc cache trong `reader-data/tts-cache/`.
- Du lieu cua tro ly doc nam trong `reader-data/` va khong dua len GitHub.
- Doi cong, thu muc ghi chu (vi du mot thu muc Obsidian hoac Google Drive): sua `reader-data/settings.json`
  (`port`, `notes_dir`).

## Vong tron chon che do (Alt + click)

- `Alt + click` vao khung chat: hien ngay vong tron nho, chua vao che do nao. O dang tro sang mau cam.
  Tro chuot vao o roi click (hoac giu chuot keo toi o roi tha): tren = Go chu, trai = Doc, phai = Noi, duoi = Huy.
  - Go chu: voice to text nhu cu.
  - Doc: boi den hoac Ctrl+C doan can nghe truoc; tro ly giong nam doc to doan do va luu vao Tro ly doc.
    Chua copy gi thi mo cua so Tro ly doc de anh dan hoac keo file vao.
  - Noi: tro chuyen voi tro ly.
  - Huy: `Esc`, click ra ngoai, hoac de yen 10 giay.
- Dang nghe: nut tron nho co song am, nhan trang thai co dau. Noi xong hien the ket qua kem so ky tu, so tu,
  toc do noi, do tin cay.
- Dang doc: `Ctrl+Alt+V` hoac `Alt + click` de tam dung / doc tiep, `Esc` de dung han.
- Tat vong tron (Alt + click go chu ngay nhu truoc): `"enable_radial_menu": false` trong `voice-mic-settings.local.json`.

## Tro chuyen bang giong noi (lenh "voice")

- Mo chac chan, khong can noi lenh: `Alt + click` roi chon nut "Noi", hoac phim tat `Ctrl+Alt+V` o bat ky dau.
  Doi phim tat: `"voice_chat_hotkey": "ctrl+alt+space"` (de trong thi tat).
- Mo bang giong noi: chon "Go chu" roi noi "tro chuyen" (nhan dien chac nhat), "noi chuyen", hoac "voice".
  Chu "voice" noi mot minh Google hay nghe nham, nen may xet ca cac cach nghe du phong va nghe them mot luot tieng Anh.
- Tro ly giong nam (Nam Minh) chao anh, anh noi cau hoi, tro ly tra loi bang giong noi roi tu nghe tiep.
- Khi Google khong nghe ra chu nao ma Whisper chi doan duoc vai chu cho ca doan dai (thuong la tieng on),
  Voice Mic bao "thu lai" thay vi dan cau vo nghia vao khung chat.
- Noi "de nguyen" / "giu nguyen" / "nhap chu": mic nghe lai de anh doc chu vao khung chat nhu cu.
- Noi binh thuong (khong phai lenh): van go chu vao khung chat nhu truoc.
- Tam dung (giu cuoc tro chuyen): noi "tam dung", "cho chut", "doi da", hoac bam `Ctrl+Alt+V`.
  Noi tiep: `Alt + click` hoac `Ctrl+Alt+V`.
- Tat han: noi "thoi", "dung lai", "cam on em", "tam biet", hoac bam `Esc`. Im lang khoang 12 giay cung tu nghi.
  `Alt + click` luc tro ly dang noi de ngat loi.
- Giong doc tu nhien hon: Tro ly doc doc lien ca doan (ngu dieu nhu nguoi doc), doc day du chu viet tat
  (TP. HCM, 50k, 5tr, 9h30...), co 4 giong da ngu moi (Andrew, Brian, Ava, Emma) doc tot tu tieng Anh xen ke.
  Nut "Nghe thu" de so sanh. Bang doc tu sua trong `reader-data/pronunciations.json` (vi du `"AI": "ây ai"`).
- Bo nao AI tu chon: Claude API (neu co `ANTHROPIC_API_KEY` va da cai `anthropic`) -> Claude Code dong lenh
  (neu da `claude` roi `/login`) -> Ollama tren may (`qwen2.5:7b`). Ep bang `voice_chat_backend` trong
  `voice-mic-settings.local.json` (`auto`, `claude-api`, `claude-cli`, `ollama`). Doi giong: `voice_chat_voice`,
  toc do: `voice_chat_rate` (vi du `+8%`). Tat lenh giong noi: `"enable_voice_commands": false`.
- Moi cuoc tro chuyen luu lai trong `reader-data/conversations/`.

## Chay tu source

Yeu cau:

- Windows 10/11
- Python 3.10 tro len
- Microphone hoat dong
- Internet de dung Google Speech Recognition

Cai thu vien:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Chay app:

```powershell
python .\voice_mic_icon.py
```

Hoac:

```text
Start Vietnamese Voice Mic.cmd
```

## Cai tu chay cung Windows

Chay PowerShell tai thu muc project:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-startup.ps1
```

Go auto-start:

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall-startup.ps1
```

## Build ban phat hanh

Chay:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

Ket qua:

```text
dist\VietnameseVoiceMic\VietnameseVoiceMic.exe
releases\VietnameseVoiceMic-windows.zip
releases\version.json
```

Gui thu muc nay cho nguoi khac:

```text
dist\VietnameseVoiceMic
```

Hoac upload zip trong `releases` len GitHub Release.

## Day len GitHub

Kiem tra thay doi:

```powershell
git status
git diff --stat
```

Commit:

```powershell
git add .
git commit -m "Improve Vietnamese Voice Mic dictation"
```

Push len GitHub:

```powershell
git push origin main
```

## Cap nhat ban moi

Build script tao `releases\version.json` gom:

- `version`
- `zip_url`
- `sha256`
- `notes`
- `release_url`

Auto-update mac dinh doc manifest tai:

```text
https://github.com/Ducpt88/VietnameseVoiceMic/releases/latest/download/version.json
```

Khi tao ban moi, chay `build.ps1`, sau do upload 2 file nay len GitHub Release:

```text
releases\VietnameseVoiceMic-windows.zip
releases\version.json
```

## Xu ly loi thuong gap

- Khong nhan giong: kiem tra mic trong Windows va `preferred_microphone`.
- Bi cat cau som: tang `WEBRTC_VOICE_END_SECONDS` va `RMS_VOICE_END_SECONDS` trong `voice_mic_icon.py`.
- Nhan sai nhieu: noi gan mic hon, giam tieng nen, hoac them tu khoa vao `speech_context_terms`.
- Khong dan dung cho: hay `Alt + click` dung vao o input truoc khi noi.
- App khong bat: phai giu `Alt` trong luc click chuot trai vao o input.

## File quan trong

- `voice_mic_icon.py`: code app chinh.
- `voice-mic-settings.json`: cau hinh mic, context, update.
- `voice-mic-settings.local.json`: cau hinh rieng cua tung may, khong dua len GitHub.
- `voice-context.json`: bo nho public mac dinh, khong chua transcript ca nhan.
- `voice-context.local.json`: bo nho hoc rieng cua tung may, khong dua len GitHub.
- `voice-last.txt`: transcript moi nhat de cuu lai khi can.
- `voice-transcripts.jsonl`: lich su transcript tren may local.
- `voice-last.wav`: audio gan nhat da thu tren may local.
- `Start Vietnamese Voice Mic.cmd`: chay app tu source.
- `Start-VietnameseVoiceMic.ps1`: restart app va dam bao chi con mot instance.
- `build.ps1`: build exe, zip release va manifest.
- `updater.ps1`: helper cap nhat ban moi.
- `install-startup.ps1`: cai auto-start cung Windows.
- `uninstall-startup.ps1`: go auto-start.
