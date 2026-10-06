# Anipang 7-poker bot

Runs from the PC with the phone on USB (adb at `D:\auto_bot\scrcpy-win64-v4.1\adb.exe`). No Claude session needed.

Start: double-click `start_bot.bat` (or `python run_bot.py`). Stop: close the window / Ctrl+C.

## What it does
- Lobby -> 1500만 room. Alone in a room: waits 25 s for someone (taps the 게임 시작 button if it shows), then 방이동.
- Start hand: discards one of 4 cards, then opens one (hides pairs / flush mates).
- Betting is call/check or die only, from the OCR of the CALL amount, the pot and my gold:
  - call when the (calibrated) win probability beats the pot odds `call / (pot + call)`; through the 5th card the start-hand conditions also keep me in (trips / pair / 3 suited / 3 consecutive / 4-5-7 style)
  - die if the call is all-in, >= 1/4 of my gold, >= 10억 without two pair, or the hand's total exposure reaches 1/4 of the gold at the start of the hand
- Out of gold: 돈받기 popup -> 기본리필 (5/day) -> ONE mission reward -> back to the room.

## Win-probability model (calibrated on real hands)
- `strategy.simulate` = Monte-Carlo equity vs the opponents' open cards; the call/die rule compares it with the pot odds `call / (pot + call)`.
- `backtest.py` replays `logs/decisions.csv` (not committed) against the real outcomes. Finding: up to the 6th card the model is accurate (actual/predicted 0.88-1.07), but at the 7th-card bet it is overconfident (pair 0.46, two pair 0.58, trips/straight 0.65, flush+ 0.79), because only strong hands are left. `strategy.calibrate` applies shrunk ratios (0.64 / 0.68 / 0.86 / 0.89) at 7 cards.
- Per-hand exposure: the sum of calls in one hand must stay under 1/4 of the gold at the start of the hand (a two-pair hand once lost ~25억 by calling 1억 -> 7.5억 -> 15억).

## Safety
- Never pays: shop / gold "+" / gem "+" taps are refused in `adb.py`, and a Google Play / billing window stops the bot (exit 4).
- Never taps the profile inside a room.

## Files
- `bot.py` main loop, `strategy.py` decisions, `hands.py` Korean hand ranking, `cards.py` card reading,
  `ocr.py` amounts, `recovery.py` refill/mission, `run_bot.py` supervisor
- `logs/decisions.csv` every decision (cards, opponents, call, gold, reason), `logs/bot_*.log`
- `templates/` card/UI templates. Unreadable cards are dumped to `templates/unknown/` (the bot dies on those hands).

## Known gaps
- 돈받기 popup "확인" template (`templates/ui/confirm_refill*.png`) and the mission reward "lit" check are not verified on a real out-of-gold screen yet.
