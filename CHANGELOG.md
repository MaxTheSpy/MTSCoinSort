# Changelog
A list of ongoing changes per version release. 

## V0.1.3
- *NEW* - Added numista API support for searching numista number which will then populate `Coin_Types.csv`
- *NEW* - API Max quota usage. `Settings>Numista API Settings>Set monthly API Call Max`
- *NEW* - Users can now see API stats such as `API calls used`, `remaining api calls`, `success/failed calls` and `lifetime API calls` (Note: Calls made outside of this software will not count. )
- *MODIFIED* - Users can now change country/denomination through a single session, if type you found in unowned, it prompts you to enter a numista number which will use the API to gather the `Country`, `Denomination`, and `year range` for that coin.
- *MODIFIED* - Mint list selection now defaults to `No Mint`. 
- *MODIFIED* - Coin type selection is now a list depending on total types: 1 type + other shows one line. 5 types + other shows all 5 options, 6 types + other gives you a rollling 7 line window. around the selected type.
- *MODIFIED* - Typing a number on the numpad jumps you back to year input just like pressing + or - jumps you to mint.
- *FIXED* - On the coin sort screen, when tabbing down in bulk sorting mode, you could selet an invisible "Next Roll" option used for CRH. You can no longer select this invisible option in standard bulk mode.
- *FIXED* - Numista numbers were not always clickable in type selection. These should now all be clickable to open in your default browser when clicked.

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