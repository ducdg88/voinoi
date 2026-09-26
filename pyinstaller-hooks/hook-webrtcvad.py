# Ban cai la webrtcvad-wheels (khong co metadata ten "webrtcvad"), hook mac dinh cua PyInstaller se loi.
# Hook rong nay thay the no; module _webrtcvad van duoc dong goi binh thuong.
hiddenimports = ["_webrtcvad"]
