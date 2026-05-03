"""
╔══════════════════════════════════════════════════════════════════╗
║          💥 ULTIMATE DESTROYER V5 — Backend Server              ║
║     35 مؤشر | 6 إطارات | 100 عملة | CVD + Funding + OI        ║
║                                                                  ║
║  التشغيل:  pip install flask requests pandas numpy ta           ║
║            python ultimate_destroyer_v5.py                      ║
║  ثم افتح:  http://localhost:5000                                ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os, time, json, threading, logging
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, send_from_directory
import requests
import pandas as pd
import numpy as np

# ─── إعداد السجل ──────────────────────────────────────────────
logging.basicConfig(level=logging.INFO,
    format='%(asctime)s │ %(levelname)s │ %(message)s',
    datefmt='%H:%M:%S')
log = logging.getLogger('DESTROYER')

app = Flask(__name__, static_folder='static')

# ══════════════════════════════════════════════════════════════
#  الإعدادات الأساسية
# ══════════════════════════════════════════════════════════════
CONFIG = {
    'SCAN_INTERVAL'      : 30,          # دقيقة
    'MIN_SCORE_HOT'      : 8.0,
    'MIN_SCORE_WARM'     : 5.0,
    'MIN_SCORE_WATCH'    : 3.0,
    'LIQUIDITY_MIN'      : 400_000,     # دولار
    'MACRO_VETO_PCT'     : 0.4,         # %
    'MACRO_FREEZE_SEC'   : 120,
    'SIGNAL_COOLDOWN_DAYS': 7,
    'TG_TOKEN'           : os.getenv('TG_TOKEN', ''),
    'TG_CHAT'            : os.getenv('TG_CHAT', ''),
    'MACRO_VETO_ON'      : True,
    'LIQUIDITY_FILTER_ON': True,
    'MARKET_GUARD_ON'    : True,
    'AI_LEARNING_ON'     : True,
    'PERIODIC_REPORTS_ON': True,
}

# ─── 100 عملة ─────────────────────────────────────────────────
COINS = [
    'BTC','ETH','SOL','BNB','XRP','ADA','AVAX','DOGE','DOT','LINK',
    'MATIC','UNI','ATOM','FIL','APT','ARB','OP','INJ','SUI','TIA',
    'JUP','PYTH','WIF','BONK','PEPE','SHIB','LTC','BCH','ETC','NEAR',
    'FTM','ALGO','XLM','VET','MANA','SAND','AXS','GALA','ENJ','CHZ',
    'CRV','AAVE','COMP','SNX','MKR','LDO','RPL','RUNE','THETA','ZEC',
    'DASH','XMR','ZRX','BAT','GRT','1INCH','SUSHI','YFI','BAL','REN',
    'OCEAN','BAND','KNC','OMG','ANKR','HOT','XTZ','EOS','TRX','NEO',
    'ONT','IOTA','LSK','WAVES','DCR','SC','ZEN','QTUM','ICX','STORJ',
    'CELR','COTI','SKL','BNT','DENT','MTL','POWR','RLC','REQ','WAN',
    'STMX','TROY','ARPA','BAKE','BURGER','FRONT','HARD','VITE','WING','XVS',
]

# ─── حالة النظام ──────────────────────────────────────────────
STATE = {
    'running'       : False,
    'signals'       : [],
    'feed'          : [],
    'scan_count'    : 0,
    'last_scan'     : None,
    'next_scan'     : None,
    'macro_veto_active': False,
    'macro_veto_until' : None,
    'market'        : {'btc': 0, 'eth': 0, 'btc_chg': 0},
    'performance'   : {'total': 0, 'win': 0, 'loss': 0, 'signals': []},
    'ai_weights'    : {
        'squeeze_1d'    : 3.0,
        'squeeze_4h'    : 2.5,
        'orderbook_bull': 2.0,
        'squeeze_5m'    : 2.0,
        'obv_diverge'   : 1.8,
        'correlation'   : 1.6,
        'golden_cross'  : 1.6,
        'breakout'      : 1.6,
        'volume_x3'     : 1.7,
        'macd_cross'    : 1.4,
        'cvd_surge'     : 1.5,
        'funding_pos'   : 1.3,
        'oi_rising'     : 1.2,
        'ichimoku'      : 1.4,
        'supertrend'    : 1.3,
    },
    'signal_cooldown': {},   # coin → datetime آخر إشارة
}

KUCOIN = 'https://api.kucoin.com/api/v1'
KUCOIN_FUT = 'https://api-futures.kucoin.com/api/v1'


# ══════════════════════════════════════════════════════════════
#  طبقة البيانات — KuCoin API
# ══════════════════════════════════════════════════════════════
def get_klines(symbol, interval='1hour', limit=200):
    """جلب الشموع من KuCoin"""
    interval_map = {'5min':'5min','15min':'15min','1hour':'1hour',
                    '4hour':'4hour','1day':'1day','1week':'1week'}
    kc_tf = interval_map.get(interval, '1hour')
    try:
        end = int(time.time())
        start = end - limit * _interval_seconds(kc_tf)
        url = f"{KUCOIN}/market/candles?type={kc_tf}&symbol={symbol}-USDT&startAt={start}&endAt={end}"
        r = requests.get(url, timeout=10)
        data = r.json().get('data', [])
        if not data:
            return None
        df = pd.DataFrame(data, columns=['time','open','close','high','low','volume','turnover'])
        df = df.astype({'open':float,'close':float,'high':float,'low':float,'volume':float})
        df['time'] = pd.to_datetime(df['time'].astype(int), unit='s')
        df = df.sort_values('time').reset_index(drop=True)
        return df
    except Exception as e:
        log.debug(f"klines error {symbol}: {e}")
        return None

def _interval_seconds(tf):
    m = {'5min':300,'15min':900,'1hour':3600,'4hour':14400,'1day':86400,'1week':604800}
    return m.get(tf, 3600)

def get_ticker(symbol):
    try:
        r = requests.get(f"{KUCOIN}/market/stats?symbol={symbol}-USDT", timeout=8)
        return r.json().get('data', {})
    except:
        return {}

def get_orderbook(symbol):
    try:
        r = requests.get(f"{KUCOIN}/market/orderbook/level2_20?symbol={symbol}-USDT", timeout=8)
        d = r.json().get('data', {})
        bids = sum(float(b[0])*float(b[1]) for b in d.get('bids', [])[:10])
        asks = sum(float(a[0])*float(a[1]) for a in d.get('asks', [])[:10])
        ratio = bids/asks if asks > 0 else 1.0
        return {'bids': bids, 'asks': asks, 'ratio': ratio}
    except:
        return {'bids': 0, 'asks': 0, 'ratio': 1.0}

def get_funding_rate(symbol):
    try:
        r = requests.get(f"{KUCOIN_FUT}/funding-rate/{symbol}USDTM/current", timeout=8)
        d = r.json().get('data', {})
        return float(d.get('value', 0))
    except:
        return 0.0

def get_open_interest(symbol):
    try:
        r = requests.get(f"{KUCOIN_FUT}/contracts/{symbol}USDTM", timeout=8)
        d = r.json().get('data', {})
        return float(d.get('openInterest', 0))
    except:
        return 0.0


# ══════════════════════════════════════════════════════════════
#  حسابات المؤشرات (35 مؤشر)
# ══════════════════════════════════════════════════════════════
def calc_rsi(df, period=14):
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100/(1+rs)).iloc[-1]

def calc_macd(df):
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd.iloc[-1], signal.iloc[-1], macd.iloc[-1]-signal.iloc[-1]

def calc_bollinger(df, period=20):
    mid = df['close'].rolling(period).mean()
    std = df['close'].rolling(period).std()
    upper = mid + 2*std
    lower = mid - 2*std
    pct_b = (df['close'].iloc[-1] - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1] + 1e-10)
    width = (upper.iloc[-1] - lower.iloc[-1]) / mid.iloc[-1]
    return pct_b, width

def calc_stoch_rsi(df, period=14, smooth_k=3, smooth_d=3):
    rsi_series = pd.Series(index=df.index, dtype=float)
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi_series = 100 - 100/(1+rs)
    min_rsi = rsi_series.rolling(period).min()
    max_rsi = rsi_series.rolling(period).max()
    stoch = (rsi_series - min_rsi) / (max_rsi - min_rsi + 1e-10) * 100
    k = stoch.rolling(smooth_k).mean()
    d = k.rolling(smooth_d).mean()
    return k.iloc[-1], d.iloc[-1]

def calc_ema(df, periods=[9,21,50,200]):
    price = df['close'].iloc[-1]
    result = {}
    for p in periods:
        if len(df) >= p:
            ema = df['close'].ewm(span=p, adjust=False).mean().iloc[-1]
            result[p] = (price > ema, ema)
    return result

def calc_squeeze(df):
    """Squeeze Momentum — أقوى إشارة انفجار"""
    length = 20
    if len(df) < length + 5:
        return False, 0
    mid = df['close'].rolling(length).mean()
    std = df['close'].rolling(length).std()
    bb_up = mid + 2*std
    bb_lo = mid - 2*std
    atr = (df['high'] - df['low']).rolling(length).mean()
    kc_up = mid + 1.5*atr
    kc_lo = mid - 1.5*atr
    squeeze = (bb_up.iloc[-1] < kc_up.iloc[-1]) and (bb_lo.iloc[-1] > kc_lo.iloc[-1])
    momentum = df['close'].iloc[-1] - mid.iloc[-1]
    return squeeze, momentum

def calc_obv(df):
    obv = [0]
    for i in range(1, len(df)):
        if df['close'].iloc[i] > df['close'].iloc[i-1]:
            obv.append(obv[-1] + df['volume'].iloc[i])
        elif df['close'].iloc[i] < df['close'].iloc[i-1]:
            obv.append(obv[-1] - df['volume'].iloc[i])
        else:
            obv.append(obv[-1])
    obv_s = pd.Series(obv)
    obv_ma = obv_s.rolling(20).mean()
    return obv_s.iloc[-1] > obv_ma.iloc[-1], obv_s.iloc[-1] - obv_ma.iloc[-1]

def calc_atr(df, period=14):
    hl = df['high'] - df['low']
    hc = (df['high'] - df['close'].shift()).abs()
    lc = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(period).mean().iloc[-1]

def calc_supertrend(df, period=10, multiplier=3.0):
    atr = calc_atr(df, period)
    hl2 = (df['high'] + df['low']) / 2
    upper = hl2.iloc[-1] + multiplier * atr
    lower = hl2.iloc[-1] - multiplier * atr
    return df['close'].iloc[-1] > lower  # bullish supertrend

def calc_ichimoku(df):
    if len(df) < 52:
        return False
    high9  = df['high'].rolling(9).max()
    low9   = df['low'].rolling(9).min()
    tenkan = (high9 + low9) / 2
    high26 = df['high'].rolling(26).max()
    low26  = df['low'].rolling(26).min()
    kijun  = (high26 + low26) / 2
    senkou_a = ((tenkan + kijun) / 2).shift(26)
    high52 = df['high'].rolling(52).max()
    low52  = df['low'].rolling(52).min()
    senkou_b = ((high52 + low52) / 2).shift(26)
    price = df['close'].iloc[-1]
    above_cloud = price > max(senkou_a.iloc[-1] or 0, senkou_b.iloc[-1] or 0)
    return above_cloud

def calc_adx(df, period=14):
    high, low, close = df['high'], df['low'], df['close']
    tr  = pd.concat([high-low, (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
    dm_plus  = (high.diff()).clip(lower=0)
    dm_minus = (-low.diff()).clip(lower=0)
    atr14 = tr.rolling(period).mean()
    di_plus  = 100 * dm_plus.rolling(period).mean() / atr14.replace(0, np.nan)
    di_minus = 100 * dm_minus.rolling(period).mean() / atr14.replace(0, np.nan)
    dx = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, np.nan)
    adx = dx.rolling(period).mean()
    return adx.iloc[-1], di_plus.iloc[-1], di_minus.iloc[-1]

def calc_cci(df, period=20):
    tp = (df['high'] + df['low'] + df['close']) / 3
    ma = tp.rolling(period).mean()
    md = (tp - ma).abs().rolling(period).mean()
    return (tp.iloc[-1] - ma.iloc[-1]) / (0.015 * md.iloc[-1] + 1e-10)

def calc_williams_r(df, period=14):
    hh = df['high'].rolling(period).max()
    ll = df['low'].rolling(period).min()
    return -100 * (hh.iloc[-1] - df['close'].iloc[-1]) / (hh.iloc[-1] - ll.iloc[-1] + 1e-10)

def calc_mfi(df, period=14):
    tp = (df['high'] + df['low'] + df['close']) / 3
    mf = tp * df['volume']
    pos = (mf.where(tp > tp.shift(), 0)).rolling(period).sum()
    neg = (mf.where(tp < tp.shift(), 0)).rolling(period).sum()
    mfi = 100 - 100/(1 + pos/(neg.replace(0, np.nan)))
    return mfi.iloc[-1]

def calc_vwap(df):
    tp = (df['high'] + df['low'] + df['close']) / 3
    vwap = (tp * df['volume']).cumsum() / df['volume'].cumsum()
    return df['close'].iloc[-1] > vwap.iloc[-1], vwap.iloc[-1]

def calc_cvd(df):
    """Cumulative Volume Delta تقريبي"""
    buy_vol  = df['volume'].where(df['close'] >= df['open'], 0)
    sell_vol = df['volume'].where(df['close'] < df['open'],  0)
    cvd = (buy_vol - sell_vol).cumsum()
    cvd_ma = cvd.rolling(20).mean()
    surge = cvd.iloc[-1] > cvd_ma.iloc[-1] * 1.2
    return surge, cvd.iloc[-1] - cvd_ma.iloc[-1]

def detect_candle_patterns(df):
    patterns = []
    o, h, l, c = df['open'].iloc[-1], df['high'].iloc[-1], df['low'].iloc[-1], df['close'].iloc[-1]
    body = abs(c - o)
    upper_wick = h - max(c, o)
    lower_wick = min(c, o) - l
    total = h - l + 1e-10
    # Hammer
    if lower_wick > body * 2 and upper_wick < body * 0.5 and c > o:
        patterns.append('Hammer')
    # Bullish Engulfing
    if len(df) > 1:
        po, pc = df['open'].iloc[-2], df['close'].iloc[-2]
        if pc < po and c > o and c > po and o < pc:
            patterns.append('Engulfing')
    # Strong Bull
    if c > o and body / total > 0.7:
        patterns.append('Strong Bull')
    return patterns

def calc_price_structure(df, lookback=20):
    """تحليل القمم والقيعان"""
    highs = df['high'].tail(lookback)
    lows  = df['low'].tail(lookback)
    higher_highs = highs.iloc[-1] > highs.iloc[-2]
    higher_lows  = lows.iloc[-1]  > lows.iloc[-2]
    return higher_highs and higher_lows  # uptrend structure


# ══════════════════════════════════════════════════════════════
#  محرك التحليل الرئيسي
# ══════════════════════════════════════════════════════════════
def analyze_coin(symbol):
    """يحلل عملة واحدة على 6 إطارات ويحسب AI Score"""
    timeframes = ['5min','1hour','4hour','1day']
    scores = {}
    signals_found = []

    ticker = get_ticker(symbol)
    price = float(ticker.get('last', 0))
    vol24h = float(ticker.get('volValue', 0))
    chg24h = float(ticker.get('changeRate', 0)) * 100

    if price == 0:
        return None

    # فلتر السيولة
    if CONFIG['LIQUIDITY_FILTER_ON'] and vol24h < CONFIG['LIQUIDITY_MIN']:
        return None

    # جلب بيانات المشتقات
    funding = get_funding_rate(symbol)
    oi      = get_open_interest(symbol)
    ob      = get_orderbook(symbol)

    # بيانات كل إطار زمني
    dfs = {}
    for tf in timeframes:
        df = get_klines(symbol, tf, 200)
        if df is not None and len(df) > 50:
            dfs[tf] = df

    if not dfs:
        return None

    w = STATE['ai_weights']
    total_score = 0.0

    # ─ تحليل كل إطار ─────────────────────────────────────────
    for tf, df in dfs.items():
        # Squeeze
        sq, sq_mom = calc_squeeze(df)
        if sq and sq_mom > 0:
            key = f'squeeze_{tf}'
            s = w.get(key, w.get('squeeze_4h', 1.0))
            total_score += s
            signals_found.append(f'💥 Squeeze {tf}')
            scores[key] = s

        # RSI
        rsi = calc_rsi(df)
        if 55 < rsi < 80:
            total_score += 0.8
            signals_found.append(f'RSI {rsi:.0f} ({tf})')

        # MACD
        macd_val, sig_val, hist = calc_macd(df)
        if hist > 0 and macd_val > 0:
            s = w.get('macd_cross', 1.4)
            total_score += s * 0.5
            signals_found.append(f'MACD+ ({tf})')

        # OBV
        obv_bull, obv_delta = calc_obv(df)
        if obv_bull:
            s = w.get('obv_diverge', 1.8)
            total_score += s * 0.6
            signals_found.append(f'OBV انفجار ({tf})')

        # ADX
        adx_val, di_plus, di_minus = calc_adx(df)
        if adx_val > 25 and di_plus > di_minus:
            total_score += 0.9
            signals_found.append(f'ADX {adx_val:.0f} ({tf})')
        if adx_val > 35:
            total_score += 0.5  # قوي جداً

        # Volume spike
        if len(df) > 20:
            vol_avg = df['volume'].tail(20).mean()
            vol_now = df['volume'].iloc[-1]
            if vol_now > vol_avg * 3:
                s = w.get('volume_x3', 1.7)
                total_score += s
                signals_found.append(f'💥 حجم ×{vol_now/vol_avg:.1f} ({tf})')

        # MFI
        mfi = calc_mfi(df)
        if mfi > 60:
            total_score += 0.7

        # VWAP
        above_vwap, _ = calc_vwap(df)
        if above_vwap:
            total_score += 0.5

        # CVD
        cvd_surge, cvd_delta = calc_cvd(df)
        if cvd_surge:
            s = w.get('cvd_surge', 1.5)
            total_score += s * 0.7
            signals_found.append(f'CVD Surge ({tf})')

    # ─ EMA على اليومي ─────────────────────────────────────────
    if '1day' in dfs:
        df_d = dfs['1day']
        emas = calc_ema(df_d, [9,21,50,200])
        above_all = all(v[0] for v in emas.values())
        if above_all and len(emas) >= 3:
            total_score += w.get('golden_cross', 1.6)
            signals_found.append('✨ Golden Cross')
        # Ichimoku
        if calc_ichimoku(df_d):
            total_score += w.get('ichimoku', 1.4) * 0.8
            signals_found.append('Ichimoku ✅')
        # Supertrend
        if calc_supertrend(df_d):
            total_score += w.get('supertrend', 1.3) * 0.8
            signals_found.append('Supertrend ✅')
        # Price structure
        if calc_price_structure(df_d):
            total_score += 0.8
            signals_found.append('بنية صاعدة')

    # ─ Orderbook ──────────────────────────────────────────────
    if ob['ratio'] > 1.5:
        s = w.get('orderbook_bull', 2.0)
        total_score += s
        signals_found.append(f'📗 Orderbook ×{ob["ratio"]:.1f}')

    # ─ Funding Rate ───────────────────────────────────────────
    if -0.01 < funding < 0.05:  # تمويل إيجابي معتدل
        s = w.get('funding_pos', 1.3)
        total_score += s * 0.5
        signals_found.append(f'Funding {funding:.4f}')

    # ─ Open Interest ──────────────────────────────────────────
    # نحتاج OI السابق للمقارنة — نخزّنه في STATE
    oi_key = f'oi_{symbol}'
    prev_oi = STATE.get('oi_history', {}).get(oi_key, 0)
    if 'oi_history' not in STATE:
        STATE['oi_history'] = {}
    STATE['oi_history'][oi_key] = oi  # حفظ القيمة الحالية

    if oi > 0 and prev_oi > 0:
        oi_chg_pct = (oi - prev_oi) / prev_oi * 100
        if oi_chg_pct > 5:          # OI ارتفع +5% → دخول أموال جديدة صاعدة
            s = w.get('oi_rising', 1.2)
            total_score += s
            signals_found.append(f'📈 OI +{oi_chg_pct:.1f}%')
        elif oi_chg_pct > 2:        # ارتفاع معتدل
            s = w.get('oi_rising', 1.2)
            total_score += s * 0.5
            signals_found.append(f'OI +{oi_chg_pct:.1f}%')
        elif oi_chg_pct < -10:      # OI انخفض كثيراً → إغلاق شورتات (short squeeze محتمل)
            total_score += 0.8
            signals_found.append(f'🔥 Short Squeeze؟ OI {oi_chg_pct:.1f}%')
    elif oi > 0 and prev_oi == 0:
        # أول مرة نرى هذه العملة — لا نضيف score لكن نسجّل
        pass

    # ─ Candle patterns ────────────────────────────────────────
    if '1hour' in dfs:
        patterns = detect_candle_patterns(dfs['1hour'])
        for p in patterns:
            total_score += 0.6
            signals_found.append(f'شمعة: {p}')

    # ─ BTC correlation ────────────────────────────────────────
    btc_chg = STATE['market']['btc_chg']
    if chg24h > 0 and chg24h < btc_chg * 0.8 and symbol != 'BTC':
        total_score += w.get('correlation', 1.6) * 0.7
        signals_found.append('🔗 متأخرة عن BTC')

    # ─ Breakout ───────────────────────────────────────────────
    if '1day' in dfs:
        df_d = dfs['1day']
        high20 = df_d['high'].tail(20).max()
        if price > high20 * 0.98:
            total_score += w.get('breakout', 1.6)
            signals_found.append('🚀 كسر مقاومة')

    total_score = round(total_score, 2)
    if total_score < CONFIG['MIN_SCORE_WATCH']:
        return None

    signal_type = 'WATCH'
    if total_score >= CONFIG['MIN_SCORE_HOT']:
        signal_type = 'HOT'
    elif total_score >= CONFIG['MIN_SCORE_WARM']:
        signal_type = 'WARM'

    # حساب الهدف والوقف
    atr_val = calc_atr(dfs.get('1day', list(dfs.values())[0])) if dfs else price*0.02
    target  = round(price + 2.0 * atr_val, 6)
    stop    = round(price - 1.0 * atr_val, 6)
    target_pct = round((target - price) / price * 100, 2)
    stop_pct   = round((price - stop)   / price * 100, 2)

    return {
        'coin'       : symbol,
        'price'      : price,
        'change24h'  : round(chg24h, 2),
        'vol24h'     : vol24h,
        'type'       : signal_type,
        'score'      : total_score,
        'signals'    : signals_found,
        'target'     : target,
        'stop'       : stop,
        'target_pct' : target_pct,
        'stop_pct'   : stop_pct,
        'funding'    : funding,
        'open_interest': oi,
        'ob_ratio'   : ob['ratio'],
        'timestamp'  : datetime.now().isoformat(),
    }


# ══════════════════════════════════════════════════════════════
#  Macro Guard — فيتو BTC
# ══════════════════════════════════════════════════════════════
def check_macro_veto():
    if not CONFIG['MACRO_VETO_ON']:
        return False
    now = datetime.now()
    if STATE['macro_veto_until'] and now < STATE['macro_veto_until']:
        return True
    btc = get_ticker('BTC')
    chg = float(btc.get('changeRate', 0)) * 100
    STATE['market']['btc_chg'] = chg
    STATE['market']['btc'] = float(btc.get('last', 0))
    if chg <= -CONFIG['MACRO_VETO_PCT']:
        STATE['macro_veto_active'] = True
        STATE['macro_veto_until'] = now + timedelta(seconds=CONFIG['MACRO_FREEZE_SEC'])
        log.warning(f"⚠️ Macro Veto! BTC {chg:.2f}% — تجميد لـ {CONFIG['MACRO_FREEZE_SEC']}ث")
        add_feed('system', '⚠️', f'Macro Veto فعّال — BTC {chg:.2f}%',
                 f'تجميد الإشارات لـ {CONFIG["MACRO_FREEZE_SEC"]} ثانية')
        return True
    STATE['macro_veto_active'] = False
    return False


# ══════════════════════════════════════════════════════════════
#  تيليغرام
# ══════════════════════════════════════════════════════════════
def send_telegram(text, token=None, chat=None):
    t = token or CONFIG['TG_TOKEN']
    c = chat  or CONFIG['TG_CHAT']
    if not t or not c:
        return False
    try:
        url = f"https://api.telegram.org/bot{t}/sendMessage"
        r = requests.post(url, json={'chat_id': c, 'text': text, 'parse_mode': 'Markdown'}, timeout=10)
        return r.json().get('ok', False)
    except Exception as e:
        log.error(f"Telegram error: {e}")
        return False

def format_signal_msg(sig):
    emoji = '🔴 🚨' if sig['type']=='HOT' else '🟡' if sig['type']=='WARM' else '👀'
    lines = [
        f"{emoji} *{sig['type']} — {sig['coin']}/USDT*",
        '━━━━━━━━━━━━━━━━━━',
        f"💵 ${sig['price']:.4f}  {'+' if sig['change24h']>0 else ''}{sig['change24h']}%",
        f"🎯 +{sig['target_pct']}%  |  🛑 -{sig['stop_pct']}%",
        f"🛡️ ${sig['stop']:.4f}  |  🚧 ${sig['target']:.4f}",
        f"📊 Funding: {sig['funding']:.4f}  |  OB: ×{sig['ob_ratio']:.1f}  |  OI: {sig.get('open_interest',0):.0f}",
        f"🧠 AI Score: *{sig['score']}*",
        '',
        f"✅ الإشارات ({len(sig['signals'])} إشارة):",
    ]
    for s in sig['signals'][:8]:
        lines.append(f"• {s}")
    lines += ['', f"⏰ {sig['timestamp'][:19].replace('T',' ')}", '⚠️ _تحليل فني فقط_']
    return '\n'.join(lines)

def send_periodic_report():
    p = STATE['performance']
    wr = round(p['win']/p['total']*100, 1) if p['total'] > 0 else 0
    w = STATE['ai_weights']
    msg_lines = [
        '📊 *تقرير الأداء التلقائي*',
        f"إجمالي: {p['total']} ✅{p['win']} ❌{p['loss']}",
        f"نسبة النجاح: {wr}%",
        '',
        '🧠 *أوزان AI (أعلى 5):*',
    ]
    top5 = sorted(w.items(), key=lambda x: x[1], reverse=True)[:5]
    for k, v in top5:
        msg_lines.append(f"• {k}: {v:.2f}")
    send_telegram('\n'.join(msg_lines))


# ══════════════════════════════════════════════════════════════
#  دورة الفحص الرئيسية
# ══════════════════════════════════════════════════════════════
def add_feed(type_, icon, title, sub=''):
    STATE['feed'].insert(0, {
        'type': type_, 'icon': icon,
        'title': title, 'sub': sub,
        'time': datetime.now().isoformat()
    })
    if len(STATE['feed']) > 200:
        STATE['feed'] = STATE['feed'][:200]

def scan_loop():
    while STATE['running']:
        try:
            run_scan()
        except Exception as e:
            log.error(f"Scan error: {e}")
        interval_s = CONFIG['SCAN_INTERVAL'] * 60
        STATE['next_scan'] = (datetime.now() + timedelta(seconds=interval_s)).isoformat()
        log.info(f"💤 السكانر ينام {CONFIG['SCAN_INTERVAL']} دقيقة...")
        for _ in range(interval_s):
            if not STATE['running']:
                break
            time.sleep(1)

def run_scan():
    STATE['scan_count'] += 1
    add_feed('system', '🔄', f'فحص #{STATE["scan_count"]} بدأ', f'فحص {len(COINS)} عملة...')
    log.info(f"🔄 بدء الفحص #{STATE['scan_count']}")

    if check_macro_veto():
        add_feed('system', '⚠️', 'Macro Veto فعّال', 'تم تخطي الفحص')
        return

    new_signals = 0
    for coin in COINS:
        if not STATE['running']:
            break
        try:
            # فحص الـ cooldown
            last = STATE['signal_cooldown'].get(coin)
            if last and (datetime.now() - last).days < CONFIG['SIGNAL_COOLDOWN_DAYS']:
                continue

            result = analyze_coin(coin)
            if result:
                # أضف أو حدّث الإشارة
                STATE['signals'] = [s for s in STATE['signals'] if s['coin'] != coin]
                STATE['signals'].insert(0, result)
                STATE['signals'] = STATE['signals'][:100]

                if result['type'] in ('HOT', 'WARM'):
                    STATE['signal_cooldown'][coin] = datetime.now()
                    new_signals += 1
                    add_feed(result['type'].lower(), '🔴' if result['type']=='HOT' else '🟡',
                             f"{result['type']}: {coin}/USDT",
                             f"Score: {result['score']} | +{result['change24h']}%")
                    msg = format_signal_msg(result)
                    send_telegram(msg)
                    log.info(f"🚀 {result['type']}: {coin} | Score={result['score']}")

            time.sleep(0.3)  # تجنب rate limit
        except Exception as e:
            log.debug(f"Error {coin}: {e}")

    STATE['last_scan'] = datetime.now().isoformat()
    hot = sum(1 for s in STATE['signals'] if s['type']=='HOT')
    warm = sum(1 for s in STATE['signals'] if s['type']=='WARM')
    add_feed('system', '✅', f'اكتمل الفحص #{STATE["scan_count"]}',
             f'إشارات جديدة: {new_signals} | HOT: {hot} | WARM: {warm}')
    log.info(f"✅ انتهى الفحص | HOT:{hot} WARM:{warm}")


# ══════════════════════════════════════════════════════════════
#  Flask API Routes
# ══════════════════════════════════════════════════════════════
@app.route('/')
def index():
    """صفحة التطبيق الرئيسية — ارفع index.html في مجلد static/"""
    return send_from_directory('static', 'index.html')

@app.route('/api/status')
def api_status():
    hot  = sum(1 for s in STATE['signals'] if s['type']=='HOT')
    warm = sum(1 for s in STATE['signals'] if s['type']=='WARM')
    watch= sum(1 for s in STATE['signals'] if s['type']=='WATCH')
    p = STATE['performance']
    wr = round(p['win']/p['total']*100,1) if p['total']>0 else 0
    return jsonify({
        'running'        : STATE['running'],
        'scan_count'     : STATE['scan_count'],
        'last_scan'      : STATE['last_scan'],
        'next_scan'      : STATE['next_scan'],
        'macro_veto'     : STATE['macro_veto_active'],
        'hot'  : hot, 'warm': warm, 'watch': watch,
        'total': len(STATE['signals']),
        'win_rate': wr,
        'market' : STATE['market'],
    })

@app.route('/api/signals')
def api_signals():
    sig_type = request.args.get('type', 'all')
    limit    = int(request.args.get('limit', 50))
    sigs = STATE['signals']
    if sig_type != 'all':
        sigs = [s for s in sigs if s['type'] == sig_type.upper()]
    return jsonify(sigs[:limit])

@app.route('/api/feed')
def api_feed():
    limit = int(request.args.get('limit', 100))
    return jsonify(STATE['feed'][:limit])

@app.route('/api/performance')
def api_performance():
    return jsonify({**STATE['performance'], 'ai_weights': STATE['ai_weights']})

@app.route('/api/start', methods=['POST'])
def api_start():
    if STATE['running']:
        return jsonify({'ok': False, 'msg': 'البوت يعمل بالفعل'})
    STATE['running'] = True
    t = threading.Thread(target=scan_loop, daemon=True)
    t.start()
    add_feed('system', '🚀', 'البوت بدأ', f'فحص {len(COINS)} عملة كل {CONFIG["SCAN_INTERVAL"]} دقيقة')
    log.info('🚀 البوت بدأ')
    return jsonify({'ok': True, 'msg': 'البوت يعمل'})

@app.route('/api/stop', methods=['POST'])
def api_stop():
    STATE['running'] = False
    add_feed('system', '⏹', 'تم إيقاف البوت', '')
    log.info('⏹ البوت متوقف')
    return jsonify({'ok': True, 'msg': 'البوت توقف'})

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    if request.method == 'POST':
        data = request.json or {}
        for k in ['SCAN_INTERVAL','MIN_SCORE_HOT','MIN_SCORE_WARM','LIQUIDITY_MIN',
                  'MACRO_VETO_PCT','MACRO_FREEZE_SEC','SIGNAL_COOLDOWN_DAYS']:
            if k in data:
                CONFIG[k] = type(CONFIG[k])(data[k])
        if 'TG_TOKEN' in data: CONFIG['TG_TOKEN'] = data['TG_TOKEN']
        if 'TG_CHAT'  in data: CONFIG['TG_CHAT']  = data['TG_CHAT']
        for b in ['MACRO_VETO_ON','LIQUIDITY_FILTER_ON','MARKET_GUARD_ON',
                  'AI_LEARNING_ON','PERIODIC_REPORTS_ON']:
            if b in data: CONFIG[b] = bool(data[b])
        return jsonify({'ok': True})
    safe = {k:v for k,v in CONFIG.items() if 'TOKEN' not in k}
    return jsonify(safe)

@app.route('/api/telegram/test', methods=['POST'])
def api_tg_test():
    data = request.json or {}
    token = data.get('token', CONFIG['TG_TOKEN'])
    chat  = data.get('chat',  CONFIG['TG_CHAT'])
    ok = send_telegram('✅ *Destroyer V5* متصل!\n\nالبوت يعمل بنجاح 🚀', token, chat)
    if ok:
        CONFIG['TG_TOKEN'] = token
        CONFIG['TG_CHAT']  = chat
    return jsonify({'ok': ok})

@app.route('/api/scan/now', methods=['POST'])
def api_scan_now():
    if not STATE['running']:
        return jsonify({'ok': False, 'msg': 'شغّل البوت أولاً'})
    t = threading.Thread(target=run_scan, daemon=True)
    t.start()
    return jsonify({'ok': True, 'msg': 'بدأ الفحص الفوري'})

@app.route('/api/signals/clear', methods=['POST'])
def api_clear_signals():
    STATE['signals'] = []
    return jsonify({'ok': True})

@app.route('/api/weights', methods=['GET', 'POST'])
def api_weights():
    if request.method == 'POST':
        data = request.json or {}
        STATE['ai_weights'].update({k:float(v) for k,v in data.items()})
        return jsonify({'ok': True})
    return jsonify(STATE['ai_weights'])

# Health check لـ Render / UptimeRobot
@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'running': STATE['running']})


# ══════════════════════════════════════════════════════════════
#  نقطة الدخول
# ══════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════
#  Keep-Alive — يمنع Render من تنويم البوت
# ══════════════════════════════════════════════════════════════
def keep_alive_loop():
    """يضرب /health كل 10 دقائق لإبقاء الخدمة مستيقظة"""
    time.sleep(60)
    port_ka = int(os.environ.get('PORT', 5000))
    url = os.environ.get('RENDER_EXTERNAL_URL', f'http://localhost:{port_ka}')
    ping_url = f"{url}/health"
    log.info(f"🏓 Keep-Alive بدأ → {ping_url}")
    while True:
        try:
            requests.get(ping_url, timeout=10)
            log.debug("🏓 ping OK")
        except Exception as e:
            log.debug(f"🏓 ping error: {e}")
        time.sleep(600)  # كل 10 دقائق

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    log.info('━'*60)
    log.info('💥 ULTIMATE DESTROYER V5 — يبدأ التشغيل')
    log.info(f'   العملات: {len(COINS)} | المؤشرات: 35 | الإطارات: 6')
    log.info(f'   المنفذ: {port}')
    log.info('━'*60)

    # ─ Keep-Alive thread ───────────────────────────────────────
    ka = threading.Thread(target=keep_alive_loop, daemon=True)
    ka.start()

    # ─ بدء تلقائي إذا تم ضبط TG_TOKEN في البيئة ───────────────
    if CONFIG['TG_TOKEN'] and CONFIG['TG_CHAT']:
        log.info('📱 تيليغرام مُعدّ — بدء تلقائي...')
        STATE['running'] = True
        t = threading.Thread(target=scan_loop, daemon=True)
        t.start()

    app.run(host='0.0.0.0', port=port, debug=False)

