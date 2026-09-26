<p align="center"><img src="assets/voinoi.png" width="160" alt="VoiNoi"></p>

# VoiNoi (Voi Nói)

Ứng dụng Windows chạy nền: nói tiếng Việt thành chữ, dán đúng vào ô anh đang chọn. Kèm Trợ lý đọc (đọc to tài liệu)
và chế độ trò chuyện bằng giọng nói với trợ lý AI.

Tên cũ: Vietnamese Voice Mic. Từ bản 2.0.0 đổi tên thành VoiNoi.

## Có gì mới ở 2.0.0 (nhanh hơn, hết treo)

Đo trên máy thật, từ log của app:

| Việc | Trước | Bây giờ |
| --- | --- | --- |
| Chọn "Gõ chữ" trên vòng tròn tới lúc mic nghe | 1 giây, có lúc 11 đến 16 giây (treo cả giao diện) | 0,26 giây |
| Mở micro mỗi lần nói | khoảng 1 giây | 0,03 giây |
| Nhận diện xong tới lúc chữ được dán | chờ thêm khoảng 3 giây | dán ngay |
| Chọn "Nói" tới lúc trợ lý nghe | 11 giây trở lên | khoảng 2,7 giây |
| Đoạn dài 36 giây có một đoạn cuối chỉ là tiếng ồn | 24,8 giây | 2,7 giây (11 giây nếu phải nhờ Whisper nghe lại chỗ Google làm rơi chữ) |
| Tiếng động (click chuột, gõ phím) bị tưởng là lời nói | chờ Whisper 9 giây rồi báo lỗi | báo ngay sau 0,6 giây |

Nguyên nhân đã sửa:

- Dò ô nhập bằng UI Automation chạy trên luồng giao diện. Với Chrome và terminal, mỗi lần dò mất 2 đến 5 giây nên vòng tròn,
  HUD và phím tắt đứng hình. Khi chọn "Gõ chữ" trên vòng tròn, app còn dò trúng chính vòng tròn nên có lúc bỏ qua luôn.
  Giờ chọn "Gõ chữ" là nghe ngay, còn việc dò (khi tắt vòng tròn) chạy ở luồng phụ.
- Mỗi lần nói app khởi tạo lại PortAudio 3 đến 4 lần. Giờ giữ sẵn một bản dùng chung, cắm rút mic vẫn tự nhận lại.
- Hàm học từ vựng đọc lại file cấu hình gần 3.000 lần cho mỗi câu, chạy trước khi dán. Giờ có cache và chạy sau khi dán.
- Google không nghe ra một đoạn thì app thử lại tuần tự tới 14 lần. Giờ gửi lại và chia đôi song song, Whisper cứu đoạn
  hỏng ngay trong lúc các đoạn khác đang chạy.
- Đoạn chỉ có tiếng ồn bị tính là lỗi 0%, kéo độ tin cậy xuống dưới 82% và bắt Whisper nghe lại cả bài. Giờ đoạn ồn không
  tính là mất chữ.
- Whisper hay bịa câu kiểu "Hãy subscribe cho kênh..." khi gặp tiếng ồn. Giờ lọc bỏ trên kết quả của Whisper.
- Đoạn nào Google trả về quá ít chữ so với độ dài (thường rơi mất câu đầu), app cho Whisper nghe riêng đoạn đó và lấy bản
  đầy đủ hơn. Chỉnh ngưỡng bằng `low_coverage_wpm` (mặc định 92, đặt 0 để tắt).
- Chế độ "Nói": bộ não AI được dò sẵn ở nền và nhớ 10 phút, câu chào ngắn lại và được tạo giọng sẵn.

## Cách dùng nhanh

1. Chạy `Start VoiNoi.cmd` (bản nguồn) hoặc `VoiNoi.exe` (bản đóng gói).
2. Giữ `Alt` và click chuột trái vào ô chat hoặc ô nhập muốn gõ. Vòng tròn hiện ra:
   trên = Gõ chữ, trái = Đọc, phải = Nói, dưới = Hủy.
3. Chọn "Gõ chữ", nói nội dung. Ngừng nói thì app tự nhận diện và dán vào đúng chỗ vừa `Alt + click`.
4. Đang nghe mà muốn dừng sớm: bấm `Esc`, phần đã nói vẫn được nhận diện.
5. Dán lỗi hoặc đổi cửa sổ: bấm `Ctrl+V` để dán lại, chữ mới nhất luôn nằm trên clipboard.

Tạo shortcut có icon VoiNoi trên Desktop và Start Menu:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-shortcut.ps1
```

## Vòng tròn chọn chế độ

- Gõ chữ: nói thành chữ vào ô đã chọn.
- Đọc: bôi đen hoặc `Ctrl+C` đoạn cần nghe trước, trợ lý đọc to đoạn đó. Chưa copy gì thì mở cửa sổ Trợ lý đọc.
- Nói: trò chuyện với trợ lý AI bằng giọng nói.
- Hủy: `Esc`, click ra ngoài, hoặc để yên 10 giây.
- Tắt vòng tròn (`Alt + click` là gõ chữ ngay): `"enable_radial_menu": false` trong `voice-mic-settings.local.json`.

## Trò chuyện bằng giọng nói

- Mở: `Alt + click` rồi chọn "Nói", hoặc phím tắt `Ctrl+Alt+V` ở bất kỳ đâu (đổi bằng `voice_chat_hotkey`).
- Hoặc chọn "Gõ chữ" rồi nói "trò chuyện", "nói chuyện" hay "voice".
- Tạm dừng: nói "tạm dừng", "chờ chút", hoặc bấm `Ctrl+Alt+V`. Nói tiếp: `Alt + click` hoặc `Ctrl+Alt+V`.
- Tắt hẳn: nói "thôi", "dừng lại", "cảm ơn em", hoặc bấm `Esc`. Im lặng khoảng 12 giây cũng tự nghỉ.
- Bộ não AI tự chọn theo thứ tự: Claude API (có `ANTHROPIC_API_KEY` và đã cài `anthropic`), Claude Code dòng lệnh
  (đã đăng nhập), Ollama trên máy (`qwen2.5:7b`). Ép bằng `voice_chat_backend`: `auto`, `claude-api`, `claude-cli`, `ollama`.
- Mỗi cuộc trò chuyện lưu trong `reader-data/conversations/`.

## Trợ lý đọc tài liệu

Đọc to tài liệu, ghi chú, bài nghiên cứu bằng giọng tiếng Việt tự nhiên (Hoài My, Nam Minh).

- Mở: chạy `Start Doc Reader.cmd`, hoặc kéo thả một file lên file này.
- Đầu vào: txt, md, pdf có lớp chữ, docx, html, epub, link web, Google Docs công khai, nội dung vừa `Ctrl+C`.
- Phím tắt: `Space` đọc hoặc dừng, mũi tên trái phải để qua câu, `N` ghi chú, `Q` đặt câu hỏi, `R` đọc lại câu.
- Ghi chú lưu thành Markdown trong `reader-data/notes/`. Chạy local tại `http://127.0.0.1:8767`.
- Cần Internet để tạo giọng đọc (`edge-tts`), âm thanh được cache trong `reader-data/tts-cache/`.

## Cấu hình mic

Sửa `voice-mic-settings.local.json` (riêng từng máy, không đưa lên GitHub):

```json
{
  "preferred_microphone": "BKD-11 Pro Audio",
  "microphone_name_hints": ["USB Audio Device", "Microphone", "Headset"],
  "enable_whisper_fallback": true,
  "whisper_model": "small"
}
```

`preferred_microphone` để trống thì app tự chọn theo danh sách gợi ý.

## Cứu lại nội dung vừa nói

- `Ctrl+V` dán lại chữ mới nhất.
- `voice-last.txt`: chữ mới nhất. `voice-transcripts.jsonl`: lịch sử. `voice-last.wav`: âm thanh gần nhất.
- Các file này chỉ nằm trên máy, đã có trong `.gitignore`.

## Chạy từ mã nguồn

Yêu cầu: Windows 10 hoặc 11, Python 3.10 trở lên, micro, Internet (Google Speech Recognition).

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Muốn có Whisper làm dự phòng khi Google không nghe ra (nặng vài trăm MB):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-whisper.txt
```

Chạy: `Start VoiNoi.cmd` (tự tắt bản cũ đang chạy, chỉ giữ một bản).

## Tự chạy cùng Windows

```powershell
powershell -ExecutionPolicy Bypass -File .\install-startup.ps1
```

Gỡ: `uninstall-startup.ps1`.

## Build bản phát hành

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

Kết quả:

```text
dist\VoiNoi\VoiNoi.exe
releases\VoiNoi-windows.zip
releases\version.json
```

Bản `.exe` không đóng gói Whisper để gọn nhẹ. Repo `ducdg88/voinoi` đang để riêng tư nên tự cập nhật tắt sẵn
(`auto_update_enabled: false`): app không tải được file từ Release riêng tư. Nếu sau này mở công khai repo, bật lại
`auto_update_enabled` và mỗi bản mới tải cả `VoiNoi-windows.zip` lẫn `version.json` lên GitHub Release.

## Xử lý lỗi thường gặp

- Không nhận giọng: kiểm tra mic trong Windows và `preferred_microphone`.
- Nhận sai nhiều: nói gần mic hơn, giảm tiếng nền, thêm từ khóa vào `speech_context_terms`.
- Không dán đúng chỗ: `Alt + click` đúng vào ô nhập trước khi chọn "Gõ chữ".
- Xem chi tiết từng bước (có mốc mili giây): `voice-mic.log`.

## File quan trọng

- `voice_mic_icon.py`: code app chính.
- `reader/`: Trợ lý đọc và trò chuyện bằng giọng nói. `doc_reader.py`: mở Trợ lý đọc.
- `voice-mic-settings.json`: cấu hình mặc định. `voice-mic-settings.local.json`: cấu hình riêng từng máy.
- `voice-context.json`: từ vựng mặc định. `voice-context.local.json`: từ vựng app tự học trên máy.
- `Start VoiNoi.cmd`, `Start-VoiNoi.ps1`: chạy bản nguồn.
- `build.ps1`, `updater.ps1`: đóng gói và tự cập nhật.
- `install-shortcut.ps1`, `install-startup.ps1`, `uninstall-startup.ps1`: shortcut và tự chạy cùng Windows.
- `assets/`: icon VoiNoi và script vẽ icon (`make_icon.py`).
