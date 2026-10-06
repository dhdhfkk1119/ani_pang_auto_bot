"""Wait for the discard screen, tap one card, record what happens (0.4s steps)."""
import time, cv2, os
import adb, bot, cards, hands
out = "shots/diag"; os.makedirs(out, exist_ok=True)
for f in os.listdir(out): os.remove(os.path.join(out, f))
t0 = time.time()
while time.time() - t0 < 240:
    img = adb.screencap()
    if bot.state(img) == "choose":
        break
    time.sleep(0.5)
else:
    raise SystemExit("no choose screen")
cs = cards.read_choose(img)
print("hand", [hands.fmt(c) if c else None for c in cs])
i = bot.best_discard(cs); x = cards.CH_LEFTS[i] + 96
print("tap card idx", i, hands.fmt(cs[i]), "at", (x, cards.CH_TAP_Y), flush=True)
cv2.imwrite(f"{out}/00_before.png", img)
adb.tap(x, cards.CH_TAP_Y)
for k in range(1, 15):
    time.sleep(0.4)
    cv2.imwrite(f"{out}/{k:02d}.png", adb.screencap())
print("done")
