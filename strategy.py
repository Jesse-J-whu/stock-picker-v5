"""
鸭口选股策略 V5
========================
在 V4 基础上，策略逻辑重构为：

【前置条件】
  周线和日线当前均处于 BOLL 鸭口扩张状态

【入选条件】（满足其一即可）
  1. MA 金叉：当天 5日线上穿10日线、20日线，且10日线上穿20日线
  2. 连续阳线：连续6个交易日的日K线为阳线，或连续4周的周K线为阳线
"""

import numpy as np
import pandas as pd
import json
import os
import sys
import re
import requests
from datetime import datetime
from jinja2 import Template
import time

# ============================================================
# HTTP 基础设施
# ============================================================

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# ============================================================
# 数据获取层
# ============================================================

def get_all_a_stocks():
    """通过腾讯实时行情批量探测有效A股"""
    print("[1/4] 获取A股股票列表...")

    code_ranges = []
    code_ranges += [f"sz{str(i).zfill(6)}" for i in range(1, 1000)]
    code_ranges += [f"sz{str(i).zfill(6)}" for i in range(2001, 3000)]
    code_ranges += [f"sz{str(i).zfill(6)}" for i in range(300001, 302000)]
    code_ranges += [f"sh{str(i).zfill(6)}" for i in range(600000, 602000)]
    code_ranges += [f"sh{str(i).zfill(6)}" for i in range(603000, 604000)]
    code_ranges += [f"sh{str(i).zfill(6)}" for i in range(605000, 606000)]
    code_ranges += [f"sh{str(i).zfill(6)}" for i in range(688001, 690000)]

    all_stocks = []
    batch_size = 80

    for i in range(0, len(code_ranges), batch_size):
        batch = code_ranges[i:i + batch_size]
        query = ','.join(batch)
        url = f"https://qt.gtimg.cn/q={query}"
        try:
            resp = SESSION.get(url, timeout=20)
            if resp.status_code != 200:
                continue
            text = resp.text
            for entry in text.split(';'):
                entry = entry.strip()
                if not entry:
                    continue
                match = re.search(r'v_(\w+)="(\d+)~(.+?)~(\d+)~([^~]*)~', entry)
                if not match:
                    continue
                name = match.group(3).strip()
                code = match.group(4)
                price_str = match.group(5)
                if not name or not code or len(code) != 6:
                    continue
                if 'ST' in name or '退' in name or 'PT' in name:
                    continue
                try:
                    price = float(price_str)
                    if price <= 0:
                        continue
                except (ValueError, TypeError):
                    continue
                all_stocks.append({'代码': code, '名称': name})
        except Exception:
            continue

        if (i // batch_size) % 20 == 0 and i > 0:
            print(f"    已探测 {i}/{len(code_ranges)}，有效 {len(all_stocks)} 只...")
        time.sleep(0.05)

    df = pd.DataFrame(all_stocks)
    if df.empty:
        print("  股票列表获取失败!")
        return df
    df = df.drop_duplicates(subset='代码').reset_index(drop=True)
    print(f"  共 {len(df)} 只股票待筛选")
    return df


def _fetch_kline(symbol, period, count):
    """
    通用K线获取（腾讯财经前复权接口）
    period: 'week' / 'month' / 'day'
    返回 DataFrame(date, open, close, high, low, vol) 或空 DataFrame
    """
    period_map = {'week': 'qfqweek', 'month': 'qfqmonth', 'day': 'qfqday'}
    qfq_key = period_map.get(period, f'qfq{period}')

    url = (
        f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
        f"_var=kline_{period}qfq&param={symbol},{period},,,{count},qfq"
    )
    try:
        resp = SESSION.get(url, timeout=20)
        if resp.status_code != 200:
            return pd.DataFrame()
        text = resp.text.strip()
        if '=' in text:
            text = text.split('=', 1)[1]
        data = json.loads(text)
        if data.get('code') != 0:
            return pd.DataFrame()
        stock_data = data.get('data', {})
        if not stock_data:
            return pd.DataFrame()
        first_key = list(stock_data.keys())[0]
        klines = stock_data[first_key].get(qfq_key, [])
        if not klines:
            return pd.DataFrame()
        rows = []
        for k in klines:
            if len(k) >= 6:
                try:
                    rows.append({
                        'date':  k[0],
                        'open':  float(k[1]),
                        'close': float(k[2]),
                        'high':  float(k[3]),
                        'low':   float(k[4]),
                        'vol':   float(k[5]),
                    })
                except (ValueError, IndexError):
                    continue
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df = df.sort_values('date').reset_index(drop=True)
        return df
    except Exception:
        return pd.DataFrame()


def get_kline(stock_code, period, count):
    """统一接口：按股票代码 + 周期获取K线"""
    if stock_code.startswith(('60', '68')):
        symbol = f"sh{stock_code}"
    else:
        symbol = f"sz{stock_code}"
    return _fetch_kline(symbol, period, count)


def get_daily_display(stock_code):
    """获取最新实时行情（用于展示）"""
    if stock_code.startswith(('60', '68')):
        symbol = f"sh{stock_code}"
    else:
        symbol = f"sz{stock_code}"
    url = f"https://qt.gtimg.cn/q={symbol}"
    try:
        resp = SESSION.get(url, timeout=15)
        text = resp.text.strip()
        match = re.search(r'"(.+)"', text)
        if not match:
            return {}
        parts = match.group(1).split('~')
        if len(parts) < 40:
            return {}
        price = float(parts[3])
        prev_close = float(parts[4])
        change_pct = (price - prev_close) / prev_close * 100 if prev_close > 0 else 0
        return {
            'price':      price,
            'change_pct': round(change_pct, 2),
            'volume':     float(parts[36]) if parts[36] else 0,
            'high':       float(parts[33]) if parts[33] else price,
            'low':        float(parts[34]) if parts[34] else price,
            'open':       float(parts[5])  if parts[5]  else price,
        }
    except Exception:
        return {}


# ============================================================
# 技术指标计算工具
# ============================================================

def ema(series, n):
    return series.ewm(span=n, adjust=False).mean()

def ma(series, n):
    return series.rolling(window=n, min_periods=n).mean()

def std_dev(series, n):
    return series.rolling(window=n, min_periods=n).std(ddof=0)

def ref(series, n):
    return series.shift(n)

def cross_up(s1, s2):
    """s1 上穿 s2（金叉）"""
    return (s1 > s2) & (ref(s1, 1) <= ref(s2, 1))


# ============================================================
# V5 策略指标计算函数
# ============================================================

def calc_boll(df, period=20):
    """
    计算 BOLL 鸭口条件
    条件：UB上升 & MID上升 & LB下降（鸭口扩张）
    """
    close = df['close']
    mid   = ma(close, period)
    upper = mid + 2 * std_dev(close, period)
    lower = mid - 2 * std_dev(close, period)
    cond  = (upper > ref(upper, 1)) & (mid > ref(mid, 1)) & (lower < ref(lower, 1))
    return cond


def calc_boll_current(df, period=20):
    """
    判断当前（最新一根K线）是否处于鸭口形态
    返回 bool：当前 UB↑ & MID↑ & LB↓
    """
    cond = calc_boll(df, period)
    if cond.empty:
        return False
    return bool(cond.iloc[-1])


def calc_ma_cross(df):
    """
    MA 金叉条件：
    当天 5日线上穿10日线、20日线，且10日线上穿20日线
    返回 bool
    """
    close = df['close']
    ma5 = ma(close, 5)
    ma10 = ma(close, 10)
    ma20 = ma(close, 20)
    
    # 当天5日线上穿10日线
    cross_5_10 = cross_up(ma5, ma10)
    # 当天5日线上穿20日线
    cross_5_20 = cross_up(ma5, ma20)
    # 当天10日线上穿20日线
    cross_10_20 = cross_up(ma10, ma20)
    
    # 三个金叉同时发生
    ma_cross = cross_5_10 & cross_5_20 & cross_10_20
    
    if ma_cross.empty:
        return False
    return bool(ma_cross.iloc[-1])


def calc_consecutive_yang_daily(df, n=6):
    """
    连续 n 个交易日的日K线为阳线
    阳线定义：close > open
    返回 bool
    """
    if len(df) < n:
        return False
    
    # 阳线：收盘价 > 开盘价
    yang = df['close'] > df['open']
    
    # 取最近 n 根K线
    recent_yang = yang.iloc[-n:]
    
    # 是否全部为阳
    return bool(recent_yang.all())


def calc_consecutive_yang_weekly(df_week, n=4):
    """
    连续 n 个周的周K线为阳线
    阳线定义：close > open
    返回 bool
    """
    if len(df_week) < n:
        return False
    
    # 阳线：收盘价 > 开盘价
    yang = df_week['close'] > df_week['open']
    
    # 取最近 n 根K线
    recent_yang = yang.iloc[-n:]
    
    # 是否全部为阳
    return bool(recent_yang.all())


# ============================================================
# V5 主策略
# ============================================================

def apply_strategy(df_week, df_day):
    """
    V5 策略：
    【前置条件】周线和日线当前均处于 BOLL 鸭口扩张状态
    【入选条件】满足其一即可：
      1. MA 金叉：当天 5日线上穿10日线、20日线，且10日线上穿20日线
      2. 连续阳线：连续6个交易日的日K线为阳线，或连续4周的周K线为阳线
    
    传入周线、日线 DataFrame（均含 date/open/close/high/low/vol）
    返回 (bool, dict) —— 是否满足条件及详情
    """
    
    # ── 【前置条件】周线和日线当前均处于 BOLL 鸭口 ─────────────
    boll_cur_w = calc_boll_current(df_week)
    boll_cur_d = calc_boll_current(df_day)
    boll_current_ok = boll_cur_w and boll_cur_d
    
    # 快速剪枝：前置条件不满足直接返回 False
    if not boll_current_ok:
        return False, {
            'BOLL_WEEK': '✓' if boll_cur_w else '✗',
            'BOLL_DAY': '✓' if boll_cur_d else '✗',
            'MA_CROSS': '-',
            'YANG_6D': '-',
            'YANG_4W': '-',
            'SELECTED': False
        }
    
    # ── 【条件1】MA 金叉 ────────────────────────────────────────
    ma_cross = calc_ma_cross(df_day)
    
    # ── 【条件2】连续阳线 ──────────────────────────────────────
    yang_6d = calc_consecutive_yang_daily(df_day, n=6)
    yang_4w = calc_consecutive_yang_weekly(df_week, n=4)
    consecutive_yang = yang_6d or yang_4w
    
    # 满足任一条件即可入选
    selected = ma_cross or consecutive_yang
    
    detail = {
        'BOLL_WEEK': '✓' if boll_cur_w else '✗',
        'BOLL_DAY': '✓' if boll_cur_d else '✗',
        'MA_CROSS': '✓' if ma_cross else '✗',
        'YANG_6D': '✓' if yang_6d else '✗',
        'YANG_4W': '✓' if yang_4w else '✗',
        'SELECTED': selected
    }
    
    return selected, detail


# ============================================================
# 主流程
# ============================================================

MIN_WEEK  = 60
MIN_DAY   = 60

FETCH_WEEK  = 130
FETCH_DAY   = 100


def run_strategy():
    print("=" * 60)
    print(f"  鸭口选股 V5 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    print("\n策略逻辑：")
    print("  【前置】周线鸭口 & 日线鸭口")
    print("  【条件1】MA金叉：5日线上穿10/20日线，10日线上穿20日线")
    print("  【条件2】连续阳线：6日阳线 或 4周阳线")
    print("=" * 60)

    stocks = get_all_a_stocks()
    if stocks.empty:
        print("无法获取股票列表，退出")
        return []

    selected = []
    total    = len(stocks)
    failed   = 0

    print(f"\n[2/4] 逐只计算策略信号（共 {total} 只）...")
    for idx, row in stocks.iterrows():
        code = row['代码']
        name = row['名称']

        if idx % 200 == 0:
            print(f"  进度: {idx}/{total} ({idx/total*100:.1f}%)")

        df_week  = get_kline(code, 'week',  FETCH_WEEK)
        df_day   = get_kline(code, 'day',   FETCH_DAY)

        if (df_week.empty  or len(df_week)  < MIN_WEEK  or
                df_day.empty   or len(df_day)   < MIN_DAY):
            failed += 1
            time.sleep(0.05)
            continue

        try:
            hit, detail = apply_strategy(df_week, df_day)
            if hit:
                selected.append({
                    'code':   code,
                    'name':   name,
                    'detail': detail,
                })
                print(f"  ★ 选中: {code} {name} (MA:{detail['MA_CROSS']} 6日阳:{detail['YANG_6D']} 4周阳:{detail['YANG_4W']})")
        except Exception as e:
            failed += 1
            time.sleep(0.05)
            continue

        time.sleep(0.15)

    print(f"\n  策略计算完成: 成功 {total - failed}, 失败 {failed}")

    print(f"\n[3/4] 获取选中股票的最新行情...")
    for item in selected:
        daily = get_daily_display(item['code'])
        item.update(daily)
        time.sleep(0.1)

    print(f"\n  共选出 {len(selected)} 只股票")
    return selected


# ============================================================
# HTML 生成
# ============================================================

def generate_html(selected_stocks, output_path):
    print(f"\n[4/4] 生成展示页面...")

    template_str = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>鸭口选股 V5</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC',
                 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
    background: #080c1a;
    color: #dde3ff;
    min-height: 100vh;
    padding-bottom: env(safe-area-inset-bottom);
}
.header {
    background: linear-gradient(135deg, #131836 0%, #0a0f28 100%);
    padding: 18px 16px 14px;
    border-bottom: 1px solid rgba(90, 120, 255, 0.18);
    position: sticky;
    top: 0;
    z-index: 100;
    backdrop-filter: blur(20px);
}
.header h1 {
    font-size: 21px;
    font-weight: 800;
    background: linear-gradient(90deg, #7ba4ff, #c084fc, #f472b6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    letter-spacing: 1.5px;
}
.header .meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 7px;
    font-size: 12px;
    color: #6870a0;
}
.header .count {
    background: rgba(90,120,255,0.15);
    color: #8fa4ff;
    padding: 2px 10px;
    border-radius: 12px;
    font-weight: 700;
}
.tags {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    margin-top: 9px;
}
.tag {
    font-size: 10px;
    padding: 3px 8px;
    border-radius: 5px;
    font-weight: 600;
    letter-spacing: 0.3px;
}
.tag-v5    { background: rgba(255,100,100,0.18); color: #ff7070; border: 1px solid rgba(255,100,100,0.35); }
.tag-boll  { background: rgba(100,150,255,0.12); color: #7ba4ff; }
.tag-ma    { background: rgba(52,211,153,0.10);  color: #34d399; }
.tag-yang  { background: rgba(251,191,36,0.10);  color: #fbbf24; }
.strategy-desc {
    background: rgba(90,120,255,0.05);
    border: 1px solid rgba(90,120,255,0.12);
    border-radius: 10px;
    padding: 11px 13px;
    margin: 10px 12px 4px;
    font-size: 11px;
    color: #6870a0;
    line-height: 1.85;
}
.strategy-desc strong { color: #a0b0ff; }
.strategy-desc .v5-highlight { color: #ff8080; font-weight: 700; }
.disclaimer {
    background: rgba(234,179,8,0.06);
    border: 1px solid rgba(234,179,8,0.14);
    border-radius: 10px;
    padding: 10px 13px;
    margin: 4px 12px 4px;
    font-size: 11px;
    color: #a89040;
    line-height: 1.5;
}
.stock-list { padding: 10px 12px; }
.stock-card {
    background: linear-gradient(135deg, rgba(20,26,60,0.85) 0%, rgba(10,14,36,0.92) 100%);
    border: 1px solid rgba(90,120,255,0.10);
    border-radius: 14px;
    padding: 14px;
    margin-bottom: 10px;
    position: relative;
    overflow: hidden;
    transition: transform 0.15s;
}
.stock-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, rgba(255,120,120,0.5), transparent);
}
.stock-card:active { transform: scale(0.985); }
.card-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
}
.stock-name { font-size: 17px; font-weight: 700; color: #e6eaff; }
.stock-code {
    font-size: 12px;
    color: #525880;
    margin-top: 2px;
    font-family: 'SF Mono','Fira Code',monospace;
}
.stock-price { text-align: right; }
.price-value {
    font-size: 22px;
    font-weight: 700;
    font-family: 'SF Mono','DIN Alternate',monospace;
}
.price-change { font-size: 13px; font-weight: 600; margin-top: 1px; }
.up   { color: #f43f5e; }
.down { color: #10b981; }
.flat { color: #6870a0; }
.card-bottom {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    margin-top: 12px;
    padding-top: 11px;
    border-top: 1px solid rgba(90,120,255,0.07);
}
.metric { text-align: center; }
.metric-label { font-size: 10px; color: #525880; letter-spacing: 0.4px; }
.metric-value {
    font-size: 13px;
    color: #a0aacc;
    margin-top: 2px;
    font-family: 'SF Mono',monospace;
}
.signal-row {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 10px;
    padding-top: 9px;
    border-top: 1px solid rgba(90,120,255,0.07);
}
.sig {
    font-size: 10px;
    padding: 2px 7px;
    border-radius: 4px;
    font-family: 'SF Mono',monospace;
    white-space: nowrap;
}
.sig-boll { background: rgba(100,150,255,0.1); color: #7ba4ff; }
.sig-ma   { background: rgba(52,211,153,0.1);  color: #34d399; }
.sig-yang { background: rgba(251,191,36,0.1);  color: #fbbf24; }
.empty-state {
    text-align: center;
    padding: 60px 20px;
    color: #525880;
}
.empty-state .icon { font-size: 48px; margin-bottom: 16px; }
.empty-state p { font-size: 14px; line-height: 1.7; }
.footer {
    text-align: center;
    padding: 18px;
    font-size: 11px;
    color: #363b5a;
    border-top: 1px solid rgba(90,120,255,0.06);
    margin-top: 8px;
}
</style>
</head>
<body>
<div class="header">
    <h1>鸭口选股 V5</h1>
    <div class="meta">
        <span>{{ update_time }}</span>
        <span class="count">{{ stock_count }} 只</span>
    </div>
    <div class="tags">
        <span class="tag tag-v5">★ V5 新策略</span>
        <span class="tag tag-boll">BOLL 周鸭口+日鸭口</span>
        <span class="tag tag-ma">MA 5/10/20 金叉</span>
        <span class="tag tag-yang">连续阳线 6日/4周</span>
    </div>
</div>

<div class="strategy-desc">
    <strong>策略逻辑（V5）：</strong>
    <span class="v5-highlight">【前置】周线鸭口 & 日线鸭口</span>
    + 【条件1】MA金叉：5日线上穿10/20日线，10日线上穿20日线
    + 【条件2】连续阳线：6日阳线 或 4周阳线
    （满足任一条件即可入选）
</div>

<div class="disclaimer">
    本页面仅为量化策略筛选结果展示，不构成任何投资建议。股市有风险，投资需谨慎。
</div>

<div class="stock-list">
{% if stocks %}
{% for s in stocks %}
<div class="stock-card">
    <div class="card-top">
        <div>
            <div class="stock-name">{{ s.name }}</div>
            <div class="stock-code">{{ s.code }}</div>
        </div>
        <div class="stock-price">
            {% if s.price %}
            <div class="price-value {% if s.change_pct > 0 %}up{% elif s.change_pct < 0 %}down{% else %}flat{% endif %}">
                {{ "%.2f"|format(s.price) }}
            </div>
            <div class="price-change {% if s.change_pct > 0 %}up{% elif s.change_pct < 0 %}down{% else %}flat{% endif %}">
                {% if s.change_pct > 0 %}+{% endif %}{{ "%.2f"|format(s.change_pct) }}%
            </div>
            {% else %}
            <div class="price-value flat">--</div>
            {% endif %}
        </div>
    </div>
    {% if s.price %}
    <div class="card-bottom">
        <div class="metric">
            <div class="metric-label">开盘</div>
            <div class="metric-value">{{ "%.2f"|format(s.open) }}</div>
        </div>
        <div class="metric">
            <div class="metric-label">最高</div>
            <div class="metric-value">{{ "%.2f"|format(s.high) }}</div>
        </div>
        <div class="metric">
            <div class="metric-label">最低</div>
            <div class="metric-value">{{ "%.2f"|format(s.low) }}</div>
        </div>
    </div>
    {% endif %}
    {% if s.detail %}
    <div class="signal-row">
        <span class="sig sig-boll">周鸭口{{ s.detail.BOLL_WEEK }} 日鸭口{{ s.detail.BOLL_DAY }}</span>
        <span class="sig sig-ma">MA金叉 {{ s.detail.MA_CROSS }}</span>
        <span class="sig sig-yang">6日阳{{ s.detail.YANG_6D }} 4周阳{{ s.detail.YANG_4W }}</span>
    </div>
    {% endif %}
</div>
{% endfor %}
{% else %}
<div class="empty-state">
    <div class="icon">📊</div>
    <p>今日暂无符合策略的股票<br>策略每个交易日收盘后自动更新</p>
</div>
{% endif %}
</div>

<div class="footer">
    <p>鸭口选股 V5 · 周鸭口+日鸭口 + MA金叉/连续阳线 · 数据来源：腾讯财经</p>
    <p style="margin-top:4px;">每个交易日 16:30 自动更新</p>
</div>
</body>
</html>"""

    template = Template(template_str)
    html = template.render(
        stocks=selected_stocks,
        stock_count=len(selected_stocks),
        update_time=datetime.now().strftime('%Y年%m月%d日 %H:%M 更新'),
    )
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  页面已生成: {output_path}")


def save_data_json(selected_stocks, output_path):
    """保存选股结果为 JSON"""
    data = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'strategy': '鸭口选股 V5',
        'conditions': {
            'PREREQUISITE': '周线鸭口 & 日线鸭口',
            'CONDITION_1': 'MA金叉：5日线上穿10/20日线，10日线上穿20日线',
            'CONDITION_2': '连续阳线：6日阳线 或 4周阳线',
        },
        'count': len(selected_stocks),
        'stocks': selected_stocks,
    }
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  数据已保存: {output_path}")


if __name__ == '__main__':
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'docs')
    os.makedirs(output_dir, exist_ok=True)

    results = run_strategy()

    html_path = os.path.join(output_dir, 'index.html')
    generate_html(results, html_path)

    json_path = os.path.join(output_dir, 'data.json')
    save_data_json(results, json_path)

    print(f"\n{'=' * 60}")
    print(f"  完成! 共选出 {len(results)} 只股票")
    print(f"  HTML: {html_path}")
    print(f"  JSON: {json_path}")
    print(f"{'=' * 60}")
