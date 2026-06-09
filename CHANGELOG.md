# Changelog
A list of ongoing changes per version release. 

## V0.1.2
- Removed `Collection Sorting` and `Collection Audit` session types.
- `Coin Roll Hunt` session type now confirms whether or not you want to start CRH.
- Settings page now allows you to select your own denomination and coins per roll. 
- Coin Type selection can now be changed with numpad period while entering coins.
- Fixed bug where enter on mint selection does not save coin.
- While Coin Roll Hunting Manual Mode is selected, User is now prompted to confirm coin counts above the set count per roll. User can bypass and add the extra coin if there is truely an extra coin, go back and manually select next roll, or prompt to add the extra coin to the next roll.

## V0.1.0
- Numista Export CSV is now integrated and will automatically detect: Countries, Denomination, Coin Type.
- CoinSort no longer generates supporting folders and files needed for the app to save data to the root of where the application was run. `Windows: C:\Users\<username>\AppData\Roaming\MTS CoinSort\`, `Linux: ~/.config/mts-coinsort/ AND ~/.local/share/mts-coinsort/`

## V0.0.19
- Added numpad support for Windows OS while keeping compatability with Linux
- Github Created to track project
- Added persistant sessions and session loading via Session .CSVs.

## V0.0.3
- Added support for Numista Export .CSV Integration
- CoinSort will now automatically flag coins that are not in your collection as you type them in.

## V0.0.1
- Created main bulk of software specifically for sorting US 1 Cent (Pennies) Coins.
- Added fields to select year and mint and save them to a CSV.