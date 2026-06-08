#!/usr/bin/env bash
set -e

python3 -m pip install --upgrade pip
pip3 install -r requirements.txt

pyinstaller \
  --onefile \
  --windowed \
  --name MTS-CoinSort \
  MTS_Coin_Sort.py

mkdir -p AppDir/usr/bin
cp dist/MTS-CoinSort AppDir/usr/bin/MTS-CoinSort

cat > AppDir/MTS-CoinSort.desktop <<EOF
[Desktop Entry]
Type=Application
Name=MTS CoinSort
Exec=MTS-CoinSort
Icon=mts-coinsort
Categories=Utility;
EOF

mkdir -p AppDir/usr/share/icons/hicolor/256x256/apps
# Optional later:
# cp icon.png AppDir/usr/share/icons/hicolor/256x256/apps/mts-coinsort.png

wget -O appimagetool https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x appimagetool

ARCH=x86_64 ./appimagetool AppDir MTS-CoinSort-x86_64.AppImage