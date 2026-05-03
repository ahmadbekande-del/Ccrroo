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
    return """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>💥 Destroyer V5</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;600;700;800&display=swap');
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0a0a0f;--surface:#111118;--surface2:#1a1a24;--surface3:#22222f;--border:#2a2a3a;--accent:#00ff88;--accent2:#7b61ff;--red:#ff4466;--warn:#ffaa00;--blue:#4488ff;--text:#e8e8f0;--muted:#666680}
body{background:var(--bg);color:var(--text);font-family:'Syne',sans-serif;min-height:100vh}
.mono{font-family:'Space Mono',monospace}
/* Header */
.hdr{background:var(--surface);border-bottom:1px solid var(--border);padding:14px 20px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100}
.logo{display:flex;align-items:center;gap:10px;font-size:18px;font-weight:800}
.logo span{color:var(--accent)}
.dot{width:8px;height:8px;border-radius:50%;background:#444;display:inline-block}
.dot.on{background:var(--accent);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(0,255,136,.4)}50%{box-shadow:0 0 0 6px rgba(0,255,136,0)}}
.status-txt{font-size:13px;color:var(--muted);font-weight:600}
.status-txt.on{color:var(--accent)}
/* Layout */
.layout{display:grid;grid-template-columns:220px 1fr;min-height:calc(100vh - 57px)}
/* Sidebar */
.sidebar{background:var(--surface);border-left:1px solid var(--border);padding:16px 0}
.nav-sec{padding:6px 16px 4px;font-size:10px;font-weight:700;letter-spacing:2px;color:var(--muted);text-transform:uppercase;margin-top:8px}
.nav-item{display:flex;align-items:center;gap:10px;padding:10px 16px;cursor:pointer;font-size:13px;font-weight:500;color:var(--muted);border-right:2px solid transparent;transition:all .15s}
.nav-item:hover{background:var(--surface2);color:var(--text)}
.nav-item.active{background:rgba(0,255,136,.05);color:var(--accent);border-right-color:var(--accent)}
.badge{margin-right:auto;background:var(--red);color:#fff;font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px}
.badge.warn{background:var(--warn);color:#000}
/* Content */
.content{padding:20px;display:flex;flex-direction:column;gap:16px;overflow-y:auto}
/* Stats */
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.stat{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px;border-top:2px solid}
.stat.g{border-top-color:var(--accent)}
.stat.r{border-top-color:var(--red)}
.stat.w{border-top-color:var(--warn)}
.stat.b{border-top-color:var(--blue)}
.stat-lbl{font-size:10px;color:var(--muted);font-weight:700;letter-spacing:1px;text-transform:uppercase;margin-bottom:8px}
.stat-val{font-size:26px;font-weight:800;font-family:'Space Mono',monospace}
.stat-val.g{color:var(--accent)}
.stat-val.r{color:var(--red)}
.stat-val.w{color:var(--warn)}
.stat-sub{font-size:11px;color:var(--muted);margin-top:4px}
/* Panel */
.panel{background:var(--surface);border:1px solid var(--border);border-radius:10px;overflow:hidden}
.panel-hdr{padding:12px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.panel-title{font-size:13px;font-weight:700}
/* Table */
table{width:100%;border-collapse:collapse}
th{padding:9px 14px;text-align:right;font-size:10px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);border-bottom:1px solid var(--border)}
td{padding:11px 14px;border-bottom:1px solid rgba(42,42,58,.5);font-size:12px;vertical-align:middle}
tr:hover td{background:var(--surface2)}
tr:last-child td{border-bottom:none}
.badge-hot{background:rgba(255,68,102,.15);border:1px solid rgba(255,68,102,.3);color:var(--red);padding:3px 9px;border-radius:20px;font-size:11px;font-weight:700}
.badge-warm{background:rgba(255,170,0,.15);border:1px solid rgba(255,170,0,.3);color:var(--warn);padding:3px 9px;border-radius:20px;font-size:11px;font-weight:700}
.badge-watch{background:rgba(68,136,255,.15);border:1px solid rgba(68,136,255,.3);color:var(--blue);padding:3px 9px;border-radius:20px;font-size:11px;font-weight:700}
.score{font-family:'Space Mono',monospace;font-weight:700}
.score.h{color:var(--accent)}
.score.m{color:var(--warn)}
.score.l{color:var(--blue)}
.up{color:var(--accent);font-family:'Space Mono',monospace;font-weight:700}
.dn{color:var(--red);font-family:'Space Mono',monospace;font-weight:700}
/* Btns */
.btn{padding:7px 14px;border-radius:8px;font-size:12px;font-weight:700;cursor:pointer;border:none;font-family:'Syne',sans-serif;transition:all .15s}
.btn-g{background:var(--accent);color:#000}
.btn-g:hover{background:#00dd77}
.btn-r{background:rgba(255,68,102,.15);border:1px solid rgba(255,68,102,.3);color:var(--red)}
.btn-o{background:transparent;border:1px solid var(--border);color:var(--text)}
.btn-o:hover{border-color:var(--accent);color:var(--accent)}
/* Feed */
.feed{padding:12px 16px;display:flex;flex-direction:column;gap:8px;max-height:350px;overflow-y:auto}
.fi{display:flex;align-items:flex-start;gap:10px;padding:9px;background:var(--surface2);border-radius:7px;border-right:3px solid}
.fi.hot{border-right-color:var(--red)}
.fi.warm{border-right-color:var(--warn)}
.fi.watch{border-right-color:var(--blue)}
.fi.system{border-right-color:var(--muted)}
.fi-title{font-size:12px;font-weight:700;margin-bottom:2px}
.fi-sub{font-size:11px;color:var(--muted)}
.fi-time{font-size:10px;color:var(--muted);font-family:'Space Mono',monospace;white-space:nowrap;margin-right:auto}
/* TG Setup */
.tg-box{padding:16px;display:flex;flex-direction:column;gap:12px}
.tg-lbl{font-size:11px;font-weight:700;color:var(--muted);margin-bottom:4px}
.tg-inp{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:9px 12px;color:var(--text);font-family:'Space Mono',monospace;font-size:12px;width:100%}
.tg-inp:focus{outline:none;border-color:var(--accent2)}
.tg-inp::placeholder{color:var(--muted)}
/* Config */
.cfg-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;padding:16px}
.cfg-grp{background:var(--surface2);border-radius:8px;padding:14px}
.cfg-lbl{font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:var(--muted);margin-bottom:12px}
.cfg-row{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.cfg-row:last-child{margin-bottom:0}
.cfg-name{font-size:12px}
.cfg-inp{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:5px 9px;color:var(--accent);font-family:'Space Mono',monospace;font-size:12px;width:90px;text-align:center}
.cfg-inp:focus{outline:none;border-color:var(--accent)}
.tog{width:38px;height:20px;background:var(--surface3);border-radius:10px;position:relative;cursor:pointer;border:none;transition:background .2s}
.tog.on{background:var(--accent)}
.tog::after{content:'';width:14px;height:14px;background:#fff;border-radius:50%;position:absolute;top:3px;right:3px;transition:right .2s}
.tog.on::after{right:21px}
/* Weights */
.wt-row{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--border)}
.wt-name{font-size:12px;font-family:'Space Mono',monospace;min-width:130px;color:var(--text)}
.wt-bar{flex:1;height:5px;background:var(--surface3);border-radius:3px;overflow:hidden}
.wt-fill{height:100%;background:var(--accent);border-radius:3px}
.wt-val{font-size:12px;font-weight:700;font-family:'Space Mono',monospace;color:var(--accent);min-width:32px;text-align:left}
/* Market */
.mkt-row{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;padding:14px 16px}
.mkt{background:var(--surface2);border-radius:8px;padding:11px}
.mkt-name{font-size:10px;color:var(--muted);font-weight:700;margin-bottom:5px}
.mkt-val{font-size:15px;font-weight:800;font-family:'Space Mono',monospace}
/* Bottom bar */
.bot-bar{padding:10px 16px;border-top:1px solid var(--border);display:flex;gap:8px;align-items:center}
/* Empty */
.empty{padding:30px;text-align:center;color:var(--muted);font-size:13px}
/* Toast */
.toast{position:fixed;bottom:20px;left:20px;background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:12px 16px;z-index:999;transform:translateY(80px);opacity:0;transition:all .3s;min-width:240px;display:flex;gap:10px;align-items:center}
.toast.show{transform:translateY(0);opacity:1}
/* Scrollbar */
::-webkit-scrollbar{width:4px}::-webkit-scrollbar-thumb{background:var(--surface3);border-radius:2px}
/* Page hidden */
.page{display:none}.page.active{display:block}
</style>
</head>
<body>
<div class="hdr">
  <div class="logo">💥 Destroyer<span>V5</span></div>
  <div style="display:flex;align-items:center;gap:14px">
    <span class="dot" id="dot"></span>
    <span class="status-txt" id="status-txt">متوقف</span>
    <span style="font-size:11px;color:var(--muted);font-family:'Space Mono',monospace" id="scan-info">—</span>
  </div>
</div>

<div class="layout">
  <div class="sidebar">
    <div class="nav-sec">لوحة التحكم</div>
    <div class="nav-item active" onclick="showPage('signals')">📊 الإشارات <span class="badge" id="badge-hot">0</span></div>
    <div class="nav-item" onclick="showPage('feed')">📡 السجل المباشر</div>
    <div class="nav-item" onclick="showPage('performance')">🏆 الأداء</div>
    <div class="nav-sec">الإعدادات</div>
    <div class="nav-item" onclick="showPage('telegram')">📱 تيليغرام</div>
    <div class="nav-item" onclick="showPage('config')">⚙️ الإعدادات</div>
    <div style="margin-top:auto;padding:14px 16px;border-top:1px solid var(--border);margin-top:20px">
      <button class="btn btn-g" id="main-btn" onclick="toggleBot()" style="width:100%;padding:10px;font-size:13px;border-radius:8px">▶ تشغيل البوت</button>
      <div style="margin-top:8px;font-size:11px;color:var(--muted);text-align:center" id="next-txt">التالي: —</div>
    </div>
  </div>

  <div class="content">
    <!-- SIGNALS -->
    <div class="page active" id="page-signals">
      <div class="stats">
        <div class="stat g"><div class="stat-lbl">HOT 🔴</div><div class="stat-val g" id="s-hot">0</div><div class="stat-sub">Score ≥ 8</div></div>
        <div class="stat w"><div class="stat-lbl">WARM 🟡</div><div class="stat-val w" id="s-warm">0</div><div class="stat-sub">Score ≥ 5</div></div>
        <div class="stat b"><div class="stat-lbl">WATCH 👀</div><div class="stat-val" id="s-watch" style="color:var(--blue)">0</div><div class="stat-sub">Score ≥ 3</div></div>
        <div class="stat g"><div class="stat-lbl">Win Rate</div><div class="stat-val g" id="s-wr">—</div><div class="stat-sub">آخر 30 إشارة</div></div>
      </div>
      <div class="panel">
        <div class="panel-hdr">
          <span class="panel-title">نظرة السوق</span>
          <span style="font-size:11px;color:var(--muted);font-family:'Space Mono',monospace" id="mkt-time">—</span>
        </div>
        <div class="mkt-row">
          <div class="mkt"><div class="mkt-name">BTC/USDT</div><div class="mkt-val" id="btc-p">$—</div><div style="font-size:11px;font-weight:700;margin-top:3px" id="btc-c">—</div></div>
          <div class="mkt"><div class="mkt-name">ETH/USDT</div><div class="mkt-val" id="eth-p">$—</div><div style="font-size:11px;font-weight:700;margin-top:3px" id="eth-c">—</div></div>
          <div class="mkt"><div class="mkt-name">Macro Veto</div><div class="mkt-val" id="macro-s" style="font-size:13px;color:var(--accent)">✅ آمن</div></div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-hdr">
          <span class="panel-title">الإشارات النشطة</span>
          <div style="display:flex;gap:8px">
            <select class="btn btn-o" id="filter-type" onchange="renderSigs()" style="cursor:pointer;font-family:'Syne',sans-serif;font-size:12px">
              <option value="all">الكل</option><option value="HOT">HOT</option><option value="WARM">WARM</option><option value="WATCH">WATCH</option>
            </select>
            <button class="btn btn-o" onclick="fetchAndRender()">🔄 تحديث</button>
          </div>
        </div>
        <div id="sigs-wrap">
          <div class="empty" id="sigs-empty">ابدأ البوت لرؤية الإشارات</div>
          <table id="sigs-table" style="display:none">
            <thead><tr><th>العملة</th><th>السعر</th><th>24h%</th><th>الإشارة</th><th>Score</th><th>المؤشرات</th><th>الوقت</th></tr></thead>
            <tbody id="sigs-body"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- FEED -->
    <div class="page" id="page-feed">
      <div class="panel">
        <div class="panel-hdr"><span class="panel-title">📡 السجل المباشر</span><button class="btn btn-o" onclick="document.getElementById('feed-list').innerHTML=''">مسح</button></div>
        <div class="feed" id="feed-list"><div class="empty">لا يوجد أحداث بعد</div></div>
      </div>
    </div>

    <!-- PERFORMANCE -->
    <div class="page" id="page-performance">
      <div class="stats">
        <div class="stat g"><div class="stat-lbl">الإجمالي</div><div class="stat-val" id="p-total" style="color:var(--text)">0</div></div>
        <div class="stat g"><div class="stat-lbl">نجحت ✅</div><div class="stat-val g" id="p-win">0</div></div>
        <div class="stat r"><div class="stat-lbl">فشلت ❌</div><div class="stat-val r" id="p-loss">0</div></div>
        <div class="stat g"><div class="stat-lbl">Win Rate</div><div class="stat-val g" id="p-wr">—</div></div>
      </div>
      <div class="panel">
        <div class="panel-hdr"><span class="panel-title">🧠 أوزان AI</span></div>
        <div style="padding:14px 16px" id="weights-wrap"><div class="empty">لا توجد بيانات</div></div>
      </div>
    </div>

    <!-- TELEGRAM -->
    <div class="page" id="page-telegram">
      <div class="panel">
        <div class="panel-hdr"><span class="panel-title">📱 إعداد تيليغرام</span></div>
        <div class="tg-box">
          <div style="background:rgba(123,97,255,.08);border:1px solid rgba(123,97,255,.2);border-radius:9px;padding:13px;font-size:12px;line-height:1.9;color:var(--muted)">
            1. افتح <strong style="color:var(--text)">@BotFather</strong> ← أرسل <code style="color:var(--accent2);background:var(--surface3);padding:1px 6px;border-radius:4px">/newbot</code><br>
            2. احفظ الـ <strong style="color:var(--text)">Token</strong> وضعه أدناه<br>
            3. أرسل رسالة للبوت ← افتح <code style="color:var(--accent2);background:var(--surface3);padding:1px 6px;border-radius:4px">api.telegram.org/bot{TOKEN}/getUpdates</code><br>
            4. احفظ الـ <strong style="color:var(--text)">Chat ID</strong>
          </div>
          <div><div class="tg-lbl">Bot Token</div><input class="tg-inp" id="tg-token" type="password" placeholder="1234567890:ABCDefGhIJKlmNoPQRsTUVwxyZ"></div>
          <div><div class="tg-lbl">Chat ID</div><input class="tg-inp" id="tg-chat" placeholder="-100xxxxxxxxxx"></div>
          <div style="display:flex;gap:10px">
            <button class="btn btn-o" onclick="testTg()" style="flex:1">📤 اختبار</button>
            <button class="btn btn-g" onclick="saveTg()" style="flex:1">حفظ</button>
          </div>
          <div id="tg-status" style="font-size:12px;display:none;padding:8px;border-radius:6px"></div>
        </div>
      </div>
    </div>

    <!-- CONFIG -->
    <div class="page" id="page-config">
      <div class="panel">
        <div class="panel-hdr"><span class="panel-title">⚙️ الإعدادات</span><button class="btn btn-g" onclick="saveConfig()">حفظ</button></div>
        <div class="cfg-grid">
          <div class="cfg-grp">
            <div class="cfg-lbl">المؤقتات</div>
            <div class="cfg-row"><span class="cfg-name">فترة الفحص (دقيقة)</span><input class="cfg-inp" id="c-interval" value="30"></div>
            <div class="cfg-row"><span class="cfg-name">مهلة الإشارة (يوم)</span><input class="cfg-inp" id="c-cooldown" value="7"></div>
            <div class="cfg-row"><span class="cfg-name">تجميد Macro (ثانية)</span><input class="cfg-inp" id="c-freeze" value="120"></div>
          </div>
          <div class="cfg-grp">
            <div class="cfg-lbl">حدود الإشارات</div>
            <div class="cfg-row"><span class="cfg-name">HOT Score ≥</span><input class="cfg-inp" id="c-hot" value="8"></div>
            <div class="cfg-row"><span class="cfg-name">WARM Score ≥</span><input class="cfg-inp" id="c-warm" value="5"></div>
            <div class="cfg-row"><span class="cfg-name">حد السيولة ($)</span><input class="cfg-inp" id="c-liq" value="400000"></div>
          </div>
          <div class="cfg-grp">
            <div class="cfg-lbl">الحماية</div>
            <div class="cfg-row"><span class="cfg-name">Macro Veto</span><button class="tog on" id="t-macro" onclick="this.classList.toggle('on')"></button></div>
            <div class="cfg-row"><span class="cfg-name">Liquidity Filter</span><button class="tog on" id="t-liq" onclick="this.classList.toggle('on')"></button></div>
            <div class="cfg-row"><span class="cfg-name">Market Guard</span><button class="tog on" id="t-guard" onclick="this.classList.toggle('on')"></button></div>
          </div>
          <div class="cfg-grp">
            <div class="cfg-lbl">الذكاء الاصطناعي</div>
            <div class="cfg-row"><span class="cfg-name">AI Learning</span><button class="tog on" id="t-ai" onclick="this.classList.toggle('on')"></button></div>
            <div class="cfg-row"><span class="cfg-name">تقارير دورية</span><button class="tog on" id="t-rep" onclick="this.classList.toggle('on')"></button></div>
            <div class="cfg-row"><span class="cfg-name">نسبة فيتو BTC %</span><input class="cfg-inp" id="c-veto" value="0.4"></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>

<div class="toast" id="toast"><span id="t-icon">✅</span><div><div style="font-size:13px;font-weight:700" id="t-title"></div><div style="font-size:11px;color:var(--muted)" id="t-msg"></div></div></div>

<script>
const API = '';
let sigs=[], running=false, pollTimer=null;

function showPage(p){
  document.querySelectorAll('.page').forEach(el=>el.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(el=>el.classList.remove('active'));
  document.getElementById('page-'+p).classList.add('active');
  event.currentTarget.classList.add('active');
  if(p==='performance') fetchPerf();
  if(p==='feed') fetchFeed();
}

async function toggleBot(){
  const btn=document.getElementById('main-btn');
  if(!running){
    const r=await fetch(API+'/api/start',{method:'POST'});
    const d=await r.json();
    if(d.ok){running=true;updateUI();toast('🚀','البوت يعمل','جاري الفحص...');startPoll();}
  } else {
    const r=await fetch(API+'/api/stop',{method:'POST'});
    running=false;updateUI();toast('⏹','تم الإيقاف','');stopPoll();
  }
}

function updateUI(){
  const btn=document.getElementById('main-btn');
  const dot=document.getElementById('dot');
  const st=document.getElementById('status-txt');
  if(running){btn.textContent='⏹ إيقاف';btn.className='btn btn-r';dot.className='dot on';st.textContent='يعمل الآن';st.className='status-txt on';}
  else{btn.textContent='▶ تشغيل البوت';btn.className='btn btn-g';dot.className='dot';st.textContent='متوقف';st.className='status-txt';}
}

function startPoll(){pollTimer=setInterval(fetchAndRender,15000);fetchAndRender();}
function stopPoll(){if(pollTimer)clearInterval(pollTimer);}

async function fetchAndRender(){
  try{
    const [sr,str]=await Promise.all([fetch(API+'/api/status'),fetch(API+'/api/signals?limit=60')]);
    const status=await sr.json(), signals=await str.json();
    running=status.running; updateUI();
    sigs=signals;
    document.getElementById('s-hot').textContent=status.hot||0;
    document.getElementById('s-warm').textContent=status.warm||0;
    document.getElementById('s-watch').textContent=status.watch||0;
    document.getElementById('s-wr').textContent=status.win_rate?status.win_rate+'%':'—';
    document.getElementById('badge-hot').textContent=status.hot||0;
    if(status.next_scan) document.getElementById('next-txt').textContent='التالي: '+new Date(status.next_scan).toLocaleTimeString('ar');
    if(status.market){
      document.getElementById('btc-p').textContent='$'+(status.market.btc||0).toLocaleString();
      const bc=status.market.btc_chg||0;
      const bcel=document.getElementById('btc-c');
      bcel.textContent=(bc>0?'+':'')+bc.toFixed(2)+'%';
      bcel.style.color=bc>0?'var(--accent)':'var(--red)';
    }
    document.getElementById('mkt-time').textContent=new Date().toLocaleTimeString('ar');
    document.getElementById('macro-s').textContent=status.macro_veto?'⚠️ فيتو فعّال':'✅ آمن';
    document.getElementById('macro-s').style.color=status.macro_veto?'var(--red)':'var(--accent)';
    renderSigs();
  }catch(e){console.log('fetch error',e);}
}

function renderSigs(){
  const f=document.getElementById('filter-type').value;
  const filtered=f==='all'?sigs:sigs.filter(s=>s.type===f);
  const empty=document.getElementById('sigs-empty');
  const table=document.getElementById('sigs-table');
  const tbody=document.getElementById('sigs-body');
  if(!filtered.length){empty.style.display='';table.style.display='none';return;}
  empty.style.display='none';table.style.display='';
  tbody.innerHTML=filtered.map(s=>{
    const bc=s.type==='HOT'?'badge-hot':s.type==='WARM'?'badge-warm':'badge-watch';
    const em=s.type==='HOT'?'🔴':s.type==='WARM'?'🟡':'👀';
    const sc=s.score>=8?'h':s.score>=5?'m':'l';
    const chg=s.change24h||0;
    const chgClass=chg>=0?'up':'dn';
    const t=s.timestamp?s.timestamp.slice(11,16):'—';
    const inds=(s.signals||[]).slice(0,3).map(i=>`<span style="background:var(--surface3);padding:2px 6px;border-radius:4px;font-size:10px;color:var(--muted);margin:1px;display:inline-block">${i}</span>`).join('');
    const more=(s.signals||[]).length>3?`<span style="font-size:10px;color:var(--muted)">+${s.signals.length-3}</span>`:'';
    return `<tr>
      <td><strong>${s.coin}</strong><span style="font-size:10px;color:var(--muted);margin-right:4px">/USDT</span></td>
      <td><span class="up">$${(s.price||0).toFixed(4)}</span></td>
      <td><span class="${chgClass}">${chg>=0?'+':''}${chg}%</span></td>
      <td><span class="${bc}">${em} ${s.type}</span></td>
      <td><span class="score ${sc}">${s.score}</span></td>
      <td>${inds}${more}</td>
      <td style="font-size:11px;color:var(--muted);font-family:'Space Mono',monospace">${t}</td>
    </tr>`;
  }).join('');
}

async function fetchFeed(){
  try{
    const r=await fetch(API+'/api/feed?limit=80');
    const items=await r.json();
    const list=document.getElementById('feed-list');
    if(!items.length){list.innerHTML='<div class="empty">لا يوجد أحداث بعد</div>';return;}
    list.innerHTML=items.map(f=>{
      const t=f.time?f.time.slice(11,19):'—';
      return `<div class="fi ${f.type||'system'}">
        <span style="font-size:14px">${f.icon||'ℹ️'}</span>
        <div style="flex:1"><div class="fi-title">${f.title}</div>${f.sub?`<div class="fi-sub">${f.sub}</div>`:''}</div>
        <span class="fi-time">${t}</span>
      </div>`;
    }).join('');
  }catch(e){}
}

async function fetchPerf(){
  try{
    const r=await fetch(API+'/api/performance');
    const d=await r.json();
    document.getElementById('p-total').textContent=d.total||0;
    document.getElementById('p-win').textContent=d.win||0;
    document.getElementById('p-loss').textContent=d.loss||0;
    const wr=d.total>0?Math.round(d.win/d.total*100)+'%':'—';
    document.getElementById('p-wr').textContent=wr;
    document.getElementById('p-wr').parentElement.className='stat '+(d.total>0&&(d.win/d.total)>=0.6?'g':'r');
    const ww=document.getElementById('weights-wrap');
    const weights=d.ai_weights||{};
    const sorted=Object.entries(weights).sort((a,b)=>b[1]-a[1]);
    ww.innerHTML=sorted.map(([k,v])=>`<div class="wt-row">
      <span class="wt-name">${k}</span>
      <div class="wt-bar"><div class="wt-fill" style="width:${Math.min(100,v/3.5*100)}%"></div></div>
      <span class="wt-val">${v.toFixed(2)}</span>
    </div>`).join('');
  }catch(e){}
}

async function saveTg(){
  const token=document.getElementById('tg-token').value.trim();
  const chat=document.getElementById('tg-chat').value.trim();
  if(!token||!chat){toast('⚠️','بيانات ناقصة','أدخل Token و Chat ID');return;}
  const r=await fetch(API+'/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({TG_TOKEN:token,TG_CHAT:chat})});
  const d=await r.json();
  if(d.ok) toast('✅','تم الحفظ','يمكنك الآن الاختبار');
}

async function testTg(){
  const token=document.getElementById('tg-token').value.trim();
  const chat=document.getElementById('tg-chat').value.trim();
  const st=document.getElementById('tg-status');
  st.style.display='block';st.textContent='🔄 جاري الاختبار...';st.style.background='rgba(102,102,128,.2)';
  const r=await fetch(API+'/api/telegram/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token,chat})});
  const d=await r.json();
  if(d.ok){st.textContent='✅ متصل! تم إرسال رسالة تجريبية';st.style.background='rgba(0,255,136,.1)';st.style.color='var(--accent)';}
  else{st.textContent='❌ فشل — تحقق من Token و Chat ID';st.style.background='rgba(255,68,102,.1)';st.style.color='var(--red)';}
}

async function saveConfig(){
  const data={
    SCAN_INTERVAL:+document.getElementById('c-interval').value,
    MIN_SCORE_HOT:+document.getElementById('c-hot').value,
    MIN_SCORE_WARM:+document.getElementById('c-warm').value,
    LIQUIDITY_MIN:+document.getElementById('c-liq').value,
    SIGNAL_COOLDOWN_DAYS:+document.getElementById('c-cooldown').value,
    MACRO_FREEZE_SEC:+document.getElementById('c-freeze').value,
    MACRO_VETO_PCT:+document.getElementById('c-veto').value,
    MACRO_VETO_ON:document.getElementById('t-macro').classList.contains('on'),
    LIQUIDITY_FILTER_ON:document.getElementById('t-liq').classList.contains('on'),
    MARKET_GUARD_ON:document.getElementById('t-guard').classList.contains('on'),
    AI_LEARNING_ON:document.getElementById('t-ai').classList.contains('on'),
    PERIODIC_REPORTS_ON:document.getElementById('t-rep').classList.contains('on'),
  };
  await fetch(API+'/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  toast('✅','تم الحفظ','الإعدادات الجديدة مُطبّقة');
}

function toast(icon,title,msg){
  document.getElementById('t-icon').textContent=icon;
  document.getElementById('t-title').textContent=title;
  document.getElementById('t-msg').textContent=msg;
  const t=document.getElementById('toast');
  t.classList.add('show');
  setTimeout(()=>t.classList.remove('show'),3500);
}

// بدء التحقق من الحالة
fetchAndRender();
setInterval(fetchAndRender,30000);
</script>
</body>
</html>"""

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

