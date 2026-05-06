# analyze_capsule.py — Reads Round 3 capsule, outputs a parameter recommendation table.

import csv, math, os

BID_COLS  = [('bid_price_1','bid_volume_1'), ('bid_price_2','bid_volume_2'), ('bid_price_3','bid_volume_3')]
ASK_COLS  = [('ask_price_1','ask_volume_1'), ('ask_price_2','ask_volume_2'), ('ask_price_3','ask_volume_3')]
PRODUCTS  = ['HYDROGEL_PACK','VELVETFRUIT_EXTRACT'] + [f'VEV_{k}' for k in [4000,4500,5000,5100,5200,5300,5400,5500,6000,6500]]
DAYS = [0,1,2]

def load_rows(day):
    rows = []
    fname = f'prices_round_3_day_{day}.csv'
    if not os.path.exists(fname):
        print(f'WARNING: {fname} missing')
        return rows
    with open(fname) as f:
        reader = csv.DictReader(f, delimiter=';')
        for r in reader:
            rows.append(r)
    return rows

def get_float(row, col):
    v = row.get(col, '').strip()
    if v == '':
        return None
    return float(v)

def mid_from_row(row):
    bp1 = get_float(row, 'bid_price_1')
    ap1 = get_float(row, 'ask_price_1')
    if bp1 and ap1:
        return (bp1+ap1)/2.0
    # fallback: try other levels
    for (bc, _),(ac,_) in zip(BID_COLS, ASK_COLS):
        bp = get_float(row, bc)
        ap = get_float(row, ac)
        if bp and ap:
            return (bp+ap)/2.0
    return None

# ---------- collect all rows ----------
all_rows = []
for d in DAYS:
    all_rows.extend(load_rows(d))

# ---------- VELVETFRUIT_EXTRACT drift ----------
vev_rows = [r for r in all_rows if r.get('product','') == 'VELVETFRUIT_EXTRACT']
vev_drift_ticks = []
for d in DAYS:
    day_rows = [r for r in vev_rows if int(r.get('day',0)) == d]
    if len(day_rows) < 2:
        continue
    first_ts = min(int(r['timestamp']) for r in day_rows)
    last_ts  = max(int(r['timestamp']) for r in day_rows)
    first_mid = mid_from_row(day_rows[0])
    last_mid  = mid_from_row(day_rows[-1])
    if first_mid and last_mid and last_ts > first_ts:
        drift_per_tick = (last_mid - first_mid) / (last_ts - first_ts)
        vev_drift_ticks.append(drift_per_tick)
        print(f'VEV Day {d}: open mid {first_mid:.2f} close {last_mid:.2f} slope {drift_per_tick:.6f} per tick')

if vev_drift_ticks:
    median_slope = sorted(vev_drift_ticks)[len(vev_drift_ticks)//2]
    print(f'Recommended VEV_FAIR_SLOPE = {median_slope:.6f}')
else:
    median_slope = 0.005

# ---------- VEV opening buy tolerance ----------
day0_vev = [r for r in vev_rows if int(r.get('day',0)) == 0]
if day0_vev:
    first_ask = get_float(day0_vev[0], 'ask_price_1')
    first_mid = mid_from_row(day0_vev[0])
    if first_ask and first_mid:
        spread = first_ask - first_mid
        recommended_tol = max(3, int(spread)+1)
        print(f'VEV opening ask {first_ask:.2f} mid {first_mid:.2f} spread {spread:.2f}')
        print(f'Recommended VEV_BUY_TOL = {recommended_tol}')

# ---------- HYDROGEL_PACK bot offset ----------
hp_rows = [r for r in all_rows if r.get('product','') == 'HYDROGEL_PACK']
offsets = []
for row in hp_rows:
    mid = mid_from_row(row)
    bid1 = get_float(row, 'bid_price_1')
    ask1 = get_float(row, 'ask_price_1')
    if mid and bid1 and ask1:
        offsets.append(mid - bid1)   # how many ticks bot is below mid
        offsets.append(ask1 - mid)   # above mid
if offsets:
    avg_offset = sum(offsets)/len(offsets)
    print(f'Hydrogel bot avg offset from mid: {avg_offset:.2f} ticks')
    recommended_halfspread = max(1, int(avg_offset)-1)
    print(f'Recommended HP_HALFSPREAD = {recommended_halfspread}')

# ---------- HP mid movement per tick (for refresh) ----------
hp_movements = []
for d in DAYS:
    day_rows = [r for r in hp_rows if int(r.get('day',0)) == d]
    prev_mid = None
    for row in day_rows:
        mid = mid_from_row(row)
        if prev_mid and mid:
            hp_movements.append(abs(mid - prev_mid))
        prev_mid = mid
if hp_movements:
    avg_move = sum(hp_movements)/len(hp_movements)
    recommended_refresh = max(1, int(avg_move*2))   # refresh when mid moves twice the average tick
    print(f'Hydrogel avg mid movement per tick: {avg_move:.3f}')
    print(f'Recommended HP_REFRESH_TICK = {recommended_refresh}')

# ---------- Options: BS fair vs market mid for ATM/OTM strikes ----------
def bs_call(S,K,T,sigma=0.235):
    if T<=0: return max(0,S-K)
    d1 = (math.log(S/K) + 0.5*sigma**2*T) / (sigma*math.sqrt(T))
    d2 = d1 - sigma*math.sqrt(T)
    # manual norm_cdf approximation (same as trader)
    a = [0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429]
    p = 0.3275911
    def ncdf(x):
        sign = 1 if x>=0 else -1
        x = abs(x)/math.sqrt(2)
        t = 1/(1+p*x)
        y = 1 - (((((a[4]*t+a[3])*t)+a[2])*t+a[1])*t+a[0])*t*math.exp(-x*x)
        return 0.5*(1+sign*y)
    return S*ncdf(d1) - K*ncdf(d2)

strikes_to_check = [4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500]
for d in DAYS:
    day_rows = [r for r in all_rows if int(r.get('day',0)) == d]
    vev_day = [r for r in day_rows if r.get('product','') == 'VELVETFRUIT_EXTRACT']
    # get a representative S for each timestamp from VEV rows
    S_map = {}
    for r in vev_day:
        ts = int(r['timestamp'])
        mid = mid_from_row(r)
        if mid:
            S_map[ts] = mid
    for strike in strikes_to_check:
        voucher = f'VEV_{strike}'
        voucher_rows = [r for r in day_rows if r.get('product','') == voucher]
        premiums = []
        for r in voucher_rows:
            ts = int(r['timestamp'])
            if ts not in S_map:
                continue
            S = S_map[ts]
            T = (5.0 - ts/10000.0)/365.0
            if T<=0:
                continue
            theo = bs_call(S, strike, T)
            market_mid = mid_from_row(r)
            if market_mid:
                premium = market_mid - theo
                premiums.append((ts, premium))
        if premiums:
            avg_premium = sum(p[1] for p in premiums)/len(premiums)
            max_premium = max(p[1] for p in premiums)
            print(f'Day {d} {voucher}: avg mispricing {avg_premium:.2f} ticks, max {max_premium:.2f}')
            if avg_premium > 4 and strike >= 5200:
                print(f'  ** CONSIDER SELLING **')

# ---------- Final recommendation table ----------
print('\n====== PARAMETER RECOMMENDATIONS (for next upload) ======')
print(f'vev_fair_slope = {median_slope:.6f}')
print(f'vev_buy_tol = {recommended_tol if "recommended_tol" in dir() else 3}')
print(f'hp_halfspread = {recommended_halfspread if "recommended_halfspread" in dir() else 6}')
print(f'hp_refresh_tick = {recommended_refresh if "recommended_refresh" in dir() else 4}')
print(f'opt_limit (boost to 500 for OTM selling if avg premium > 4)')
print(f'bs_sigma = 0.235  (keep; market uses fixed IV)')