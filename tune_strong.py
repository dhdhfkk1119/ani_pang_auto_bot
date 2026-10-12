"""Compare 'strong hand' rules on all logged hands (cached equities).
Splits: early (before 10-13) vs today (10-13, the out-of-sample day for this rule)."""
import functools, glob, re
import hands, replay, strategy
exec(open('tune_margin.py').read().split("hs = replay.group")[0])     # cached simulate + run()
logs=sorted(glob.glob("logs/bot_*.log"))
def load(paths): return replay.group(replay.parse(paths))
early=load([p for p in logs if '20261013' not in p]); today=load([p for p in logs if '20261013' in p])
print(len(early),'early hands,',len(today),'hands today')
CONF={'A current (strong eq>=.65 or need*1.15, no caps)':dict(STRONG_EQ=.65,STRONG_NEED_CLAUSE=True,HARD_CALL_FRAC=None,HARD_EXPOSURE_FRAC=None),
 'B caps only (1/3 call, 40% hand)':dict(STRONG_EQ=.65,STRONG_NEED_CLAUSE=True,HARD_CALL_FRAC=1/3,HARD_EXPOSURE_FRAC=.4),
 'C strong tightened (eq>=.8, no need clause)':dict(STRONG_EQ=.8,STRONG_NEED_CLAUSE=False,HARD_CALL_FRAC=None,HARD_EXPOSURE_FRAC=None),
 'D tightened + caps':dict(STRONG_EQ=.8,STRONG_NEED_CLAUSE=False,HARD_CALL_FRAC=1/3,HARD_EXPOSURE_FRAC=.4),
 'E tightened + stricter caps (1/4, 30%)':dict(STRONG_EQ=.8,STRONG_NEED_CLAUSE=False,HARD_CALL_FRAC=1/4,HARD_EXPOSURE_FRAC=.3)}
print(f"{'rule':48s} | {'early real->new':>17s} | {'today real->new':>17s}")
for name,c in CONF.items():
    for k,v in c.items(): setattr(strategy,k,v)
    er,en,ec=run(early); tr,tn,tc=run(today)
    print(f"{name:48s} | {er:7.1f} -> {en:7.1f} | {tr:7.1f} -> {tn:7.1f}  (changed {ec}/{tc})",flush=True)
