python -m pip install --upgrade pip
pip install -r requirements.txt

pyinstaller `
  --onefile `
  --console `
  --name "MTS-CoinSort" `
  MTS_Coin_Sort.py

Write-Host "EXE created in: dist\MTS-CoinSort.exe"