python -m pip install --upgrade pip
if (Test-Path requirements.txt) { pip install -r requirements.txt }
pip install pyinstaller
pyinstaller --onefile --console --name "MTS-CoinSort" MTS_Coin_Sort.py
