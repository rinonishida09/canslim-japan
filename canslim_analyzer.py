"""
CANSLIM 日本株自動売買分析システム
========================================
オニールの成長株発掘法（CANSLIM）に基づき、
毎営業日の市場終了後（15:30以降）に東証銘柄をスクリーニングし、
SBI証券へのRPA自動発注用JSONを出力する。

【運用条件】
- 初期資金: 200,000円
- 1銘柄最大: 総資産の20%以内
- 最大保有銘柄数: 5銘柄
- スイングトレード（デイトレ禁止、信用取引なし）
"""

from __future__ import annotations

import json
import csv
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict

try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
except ImportError:
    print("必要なライブラリをインストールしてください:")
    print("pip3 install yfinance pandas numpy")
    sys.exit(1)

# ============================================================
# 設定
# ============================================================
TOTAL_ASSETS = 500_000          # 総資産（円）
MAX_POSITION_RATIO = 0.20       # 1銘柄最大比率
MAX_HOLDINGS = 5                # 最大保有銘柄数
STOP_LOSS_PCT = 0.075           # 損切り（7.5%）
TAKE_PROFIT_PCT = 0.225         # 利益確定（22.5%）
BREAKOUT_CHASE_LIMIT = 0.05     # ピボットから5%超はスキップ
MIN_VOLUME_SURGE = 1.40         # 出来高40%増以上
RSI_MIN = 50
RSI_MAX = 75

WATCHLIST = [
    # ── 大型・主力成長株 ──
    "6758.T",   # ソニーグループ
    "6861.T",   # キーエンス
    "9983.T",   # ファーストリテイリング
    "4063.T",   # 信越化学工業
    "6367.T",   # ダイキン工業
    "7203.T",   # トヨタ自動車
    "9984.T",   # ソフトバンクグループ
    "6098.T",   # リクルートHD
    "4519.T",   # 中外製薬
    "6954.T",   # ファナック
    "7741.T",   # HOYA
    "4543.T",   # テルモ
    "6723.T",   # ルネサスエレクトロニクス
    "3659.T",   # ネクソン
    "4307.T",   # 野村総合研究所
    "6273.T",   # SMC
    "7267.T",   # ホンダ
    "8035.T",   # 東京エレクトロン
    "6762.T",   # TDK
    "4901.T",   # 富士フイルム
    "6971.T",   # 京セラ
    "6501.T",   # 日立製作所
    "6326.T",   # クボタ
    "7832.T",   # バンダイナムコHD
    "4661.T",   # オリエンタルランド
    "9433.T",   # KDDI
    "9432.T",   # 日本電信電話（NTT）
    "8306.T",   # 三菱UFJフィナンシャルG
    "4502.T",   # 武田薬品工業
    "4568.T",   # 第一三共

    # ── 中型・高成長株 ──
    "4385.T",   # メルカリ
    "3697.T",   # SHIFT
    "4431.T",   # スマレジ
    "4053.T",   # SBIホールディングス
    "3994.T",   # マネーフォワード
    "4478.T",   # フリー
    "3923.T",   # ラクス
    "4552.T",   # JCRファーマ
    "6532.T",   # ベイカレント・コンサルティング
    "9843.T",   # ニトリHD
    "7453.T",   # 良品計画
    "2914.T",   # JT（日本たばこ産業）
    "6857.T",   # アドバンテスト
    "6146.T",   # ディスコ
    "4755.T",   # 楽天グループ
    "3092.T",   # ZOZO
    "4565.T",   # そーせいグループ
    "2413.T",   # エムスリー
    "6088.T",   # シグマクシス
    "4194.T",   # ビジョナル

    # ── 小型・高成長株（CANSLIM向き）──
    "4166.T",   # カオナビ
    "4436.T",   # ミンカブ・ジ・インフォノイド
    "4448.T",   # キュービック
    "3542.T",   # 夢展望
    "7342.T",   # ウェルスナビ
    "4051.T",   # GMOフィナンシャルゲート
    "4397.T",   # チームスピリット
    "6555.T",   # MS＆ADインシュアランスG
    "4369.T",   # トリケミカル研究所
    "4443.T",   # Sansan
    "4776.T",   # サイボウズ
    "3769.T",   # GMOペイメントゲートウェイ
    "4371.T",   # コアコンセプト・テクノロジー
    "4484.T",   # ランサーズ
    "4485.T",   # JTOWER
    "4493.T",   # サイバーセキュリティクラウド
    "6095.T",   # メドピア
    "4350.T",   # メディカルシステムネットワーク
    "3696.T",   # セレス
    "4446.T",   # Link-U

    # ── 半導体・電子部品・製造 ──
    "6920.T",   # レーザーテック
    "6316.T",   # 丸山製作所
    "6594.T",   # 日本電産（ニデック）
    "6645.T",   # オムロン
    "6902.T",   # デンソー
    "6963.T",   # ローム
    "8001.T",   # 伊藤忠商事
    "5803.T",   # フジクラ
    "6770.T",   # アルプスアルパイン
    "6472.T",   # NTN

    # ── 不動産・インフラ関連 ──
    "8031.T",   # 三井物産
    "1925.T",   # 大和ハウス工業
    "3291.T",   # 飯田グループHD
    "8801.T",   # 三井不動産
    "3288.T",   # オープンハウスグループ
    "1928.T",   # 積水ハウス
    "3244.T",   # サムティ

    # ── ヘルスケア・バイオ ──
    "4523.T",   # エーザイ
    "4506.T",   # 住友ファーマ
    "4911.T",   # 資生堂
    "7733.T",   # オリンパス
    "6869.T",   # シスメックス
    "4021.T",   # 日産化学

    # ── 消費・サービス ──
    "9766.T",   # コナミグループ
    "9697.T",   # カプコン
    "4680.T",   # ラウンドワン
    "9861.T",   # 吉野家HD
    "7974.T",   # 任天堂
    "2267.T",   # ヤクルト本社
]

OUTPUT_DIR = Path(__file__).parent
TRADE_HISTORY_FILE = OUTPUT_DIR / "trade_history.csv"
HOLDINGS_FILE = OUTPUT_DIR / "current_holdings.json"

# ============================================================
# テクニカル指標
# ============================================================

def calc_rsi(prices: pd.Series, period: int = 14) -> float:
    delta = prices.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 2)


def calc_macd(prices: pd.Series):
    exp12 = prices.ewm(span=12, adjust=False).mean()
    exp26 = prices.ewm(span=26, adjust=False).mean()
    macd_line = exp12 - exp26
    signal = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal
    return (
        round(float(macd_line.iloc[-1]), 4),
        round(float(signal.iloc[-1]), 4),
        round(float(histogram.iloc[-1]), 4),
    )


def calc_bollinger(prices: pd.Series, period: int = 20):
    ma = prices.rolling(period).mean()
    std = prices.rolling(period).std()
    upper = ma + 2 * std
    lower = ma - 2 * std
    return (
        round(float(upper.iloc[-1]), 2),
        round(float(ma.iloc[-1]), 2),
        round(float(lower.iloc[-1]), 2),
    )


def is_new_high(prices: pd.Series, lookback: int = 52) -> bool:
    if len(prices) < lookback:
        return False
    return float(prices.iloc[-1]) >= float(prices.iloc[-lookback:].max()) * 0.98


def volume_surge_ratio(volumes: pd.Series, period: int = 25) -> float:
    avg_vol = float(volumes.iloc[-period-1:-1].mean())
    if avg_vol == 0:
        return 0.0
    return round(float(volumes.iloc[-1]) / avg_vol, 2)

# ============================================================
# 市場トレンド判断
# ============================================================

def check_market_trend() -> dict:
    try:
        nikkei = yf.download("^N225", period="3mo", interval="1d", progress=False)
        if nikkei.empty:
            return {"trend": "不明", "caution": True}

        close = nikkei["Close"].squeeze()
        ma25 = float(close.rolling(25).mean().iloc[-1])
        ma75 = float(close.rolling(75).mean().iloc[-1])
        current = float(close.iloc[-1])

        distribution_days = 0
        vol = nikkei["Volume"].squeeze()
        for i in range(-20, -1):
            if abs(i) >= len(close):
                continue
            price_down = float(close.iloc[i]) < float(close.iloc[i - 1])
            vol_up = float(vol.iloc[i]) > float(vol.iloc[i - 1])
            if price_down and vol_up:
                distribution_days += 1

        if current > ma25 > ma75:
            trend = "上昇"
        elif current < ma25 < ma75:
            trend = "下落"
        else:
            trend = "中立"

        caution = distribution_days >= 4 or trend == "下落"

        return {
            "trend": trend,
            "nikkei_current": round(current, 2),
            "ma25": round(ma25, 2),
            "ma75": round(ma75, 2),
            "distribution_days": distribution_days,
            "caution": caution,
        }
    except Exception as e:
        print(f"  市場データ取得エラー: {e}")
        return {"trend": "不明", "caution": False}

# ============================================================
# 個別銘柄分析
# ============================================================

def analyze_stock(ticker: str) -> Optional[dict]:
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y", interval="1d")
        if hist is None or len(hist) < 75:
            return None

        close = hist["Close"].squeeze()
        volume = hist["Volume"].squeeze()
        current_price = float(close.iloc[-1])

        ma25 = float(close.rolling(25).mean().iloc[-1])
        ma75 = float(close.rolling(75).mean().iloc[-1])

        rsi = calc_rsi(close)
        macd_val, signal_val, histogram_val = calc_macd(close)
        bb_upper, bb_mid, bb_lower = calc_bollinger(close)
        vol_ratio = volume_surge_ratio(volume)
        new_high = is_new_high(close)

        above_ma25 = current_price > ma25
        above_ma75 = current_price > ma75
        rsi_ok = RSI_MIN <= rsi <= RSI_MAX
        macd_bullish = histogram_val > 0
        vol_surge = vol_ratio >= MIN_VOLUME_SURGE

        pivot = float(close.iloc[-20:].max())
        above_pivot = current_price > pivot
        chase_ok = current_price <= pivot * (1 + BREAKOUT_CHASE_LIMIT)

        score = 0
        score += 20 if above_ma25 else 0
        score += 20 if above_ma75 else 0
        score += 15 if rsi_ok else 0
        score += 15 if macd_bullish else 0
        score += 20 if vol_surge else 0
        score += 10 if new_high else 0

        buy_price = round(current_price, 0)
        stop_loss = round(buy_price * (1 - STOP_LOSS_PCT), 0)
        take_profit = round(buy_price * (1 + TAKE_PROFIT_PCT), 0)

        budget = TOTAL_ASSETS * MAX_POSITION_RATIO
        # S株（1株単位）対応
        shares = int(budget // buy_price)
        if shares == 0:
            shares = 0

        try:
            info = stock.info
            name = info.get("longName") or info.get("shortName") or ticker
        except Exception:
            name = ticker

        return {
            "ticker": ticker,
            "name": name,
            "current_price": current_price,
            "ma25": round(ma25, 2),
            "ma75": round(ma75, 2),
            "rsi": rsi,
            "macd_histogram": histogram_val,
            "bb_upper": bb_upper,
            "bb_lower": bb_lower,
            "volume_ratio": vol_ratio,
            "new_high": new_high,
            "score": score,
            "buy_price": buy_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "shares": shares,
            "chase_ok": chase_ok,
            "buy_signal": score >= 70 and shares > 0 and chase_ok and above_ma25 and above_ma75,
        }
    except Exception as e:
        print(f"  [{ticker}] エラー: {e}")
        return None

# ============================================================
# 保有銘柄の売却判断
# ============================================================

def load_holdings() -> list:
    if not HOLDINGS_FILE.exists():
        return []
    with open(HOLDINGS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def check_sell_signals(holdings: list) -> list:
    sell_candidates = []
    for h in holdings:
        ticker = h["ticker"]
        buy_price = h["buy_price"]
        shares = h["shares"]
        buy_date = h.get("buy_date", "")

        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="3mo", interval="1d")
            if hist is None or hist.empty:
                continue
            current_price = float(hist["Close"].squeeze().iloc[-1])
        except Exception:
            continue

        change_pct = (current_price - buy_price) / buy_price
        reason = None

        if change_pct <= -STOP_LOSS_PCT:
            reason = f"損切り（{round(change_pct*100,1)}%下落）"
        elif change_pct >= TAKE_PROFIT_PCT:
            reason = f"利益確定（{round(change_pct*100,1)}%上昇）"
            if buy_date:
                try:
                    bd = datetime.strptime(buy_date, "%Y-%m-%d")
                    weeks_held = (datetime.now() - bd).days / 7
                    if weeks_held < 3 and change_pct >= 0.20:
                        reason += "【8週間ホールドルール検討】"
                except Exception:
                    pass

        if reason:
            sell_candidates.append({
                "ticker": ticker,
                "name": h.get("name", ticker),
                "shares": shares,
                "buy_price": buy_price,
                "current_price": round(current_price, 2),
                "change_pct": round(change_pct * 100, 2),
                "reason": reason,
            })

    return sell_candidates

# ============================================================
# 月次パフォーマンスレポート
# ============================================================

def generate_monthly_report() -> dict:
    if not TRADE_HISTORY_FILE.exists():
        return {"message": "取引履歴がありません。"}

    trades = []
    with open(TRADE_HISTORY_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            trades.append(row)

    if not trades:
        return {"message": "取引履歴がありません。"}

    profits = []
    losses = []
    for t in trades:
        pnl = float(t.get("pnl", 0))
        if pnl > 0:
            profits.append(pnl)
        elif pnl < 0:
            losses.append(pnl)

    total = len(trades)
    win_rate = round(len(profits) / total * 100, 1) if total > 0 else 0
    avg_profit = round(float(np.mean(profits)), 0) if profits else 0
    avg_loss = round(float(np.mean(losses)), 0) if losses else 0

    cumulative = [0.0]
    for t in trades:
        cumulative.append(cumulative[-1] + float(t.get("pnl", 0)))
    peak = cumulative[0]
    max_dd = 0.0
    for v in cumulative:
        if v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd

    suggestions = []
    if win_rate < 40:
        suggestions.append("勝率が低め。ブレイクアウト時の出来高確認を強化してください。")
    if profits and losses and avg_profit < abs(avg_loss) * 2:
        suggestions.append("損益比率が目標（3:1）を下回っています。損切りを早める検討を。")
    if max_dd > TOTAL_ASSETS * 0.15:
        suggestions.append("最大ドローダウンが15%超。市場警戒時の新規買い停止を徹底してください。")
    if not suggestions:
        suggestions.append("ルール通りの運用が継続できています。このまま維持してください。")

    return {
        "総取引数": total,
        "勝率": f"{win_rate}%",
        "平均利益": f"{avg_profit:,.0f}円",
        "平均損失": f"{avg_loss:,.0f}円",
        "最大ドローダウン": f"{max_dd:,.0f}円",
        "改善提案": suggestions,
    }

# ============================================================
# メイン
# ============================================================

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"  CANSLIM 日本株分析システム — {today}")
    print(f"{'='*60}\n")

    print("【1】市場トレンド確認中...")
    market = check_market_trend()
    print(f"  日経平均: {market.get('nikkei_current', 'N/A')} | トレンド: {market['trend']}")
    print(f"  売り抜け日数（直近20日）: {market.get('distribution_days', 'N/A')}日")

    if market["caution"]:
        print("\n⚠️  市場が下落または要注意局面。新規買いは見送り推奨。\n")

    print("【2】保有銘柄の売却チェック中...")
    holdings = load_holdings()
    sell_signals = check_sell_signals(holdings)

    print(f"【3】{len(WATCHLIST)}銘柄をスクリーニング中...")
    results = []
    for ticker in WATCHLIST:
        print(f"  分析中: {ticker}    ", end="\r")
        result = analyze_stock(ticker)
        if result:
            results.append(result)
    print()

    results.sort(key=lambda x: x["score"], reverse=True)
    buy_candidates = [r for r in results if r["buy_signal"]]

    available_slots = MAX_HOLDINGS - len(holdings)
    buy_candidates = buy_candidates[:available_slots]

    if market["caution"]:
        buy_candidates = []

    # --- 出力 ---
    print(f"\n{'='*60}")
    print("  ■ 購入候補")
    print(f"{'='*60}")
    if buy_candidates:
        for i, b in enumerate(buy_candidates, 1):
            code = b["ticker"].replace(".T", "")
            print(f"\n  {i}. [{code}] {b['name']}")
            print(f"     購入価格   : {b['buy_price']:,.0f}円")
            print(f"     購入株数   : {b['shares']}株")
            print(f"     損切価格   : {b['stop_loss']:,.0f}円（-7.5%）")
            print(f"     利確価格   : {b['take_profit']:,.0f}円（+22.5%）")
            print(f"     RSI        : {b['rsi']} / 出来高比: {b['volume_ratio']}x / 新高値: {b['new_high']}")
            print(f"     スコア     : {b['score']}/100")
    else:
        print("\n  ⚠️  本日の購入候補なし（見送り）")

    print(f"\n{'='*60}")
    print("  ■ 売却候補")
    print(f"{'='*60}")
    if sell_signals:
        for s in sell_signals:
            code = s["ticker"].replace(".T", "")
            print(f"\n  [{code}] {s['name']}")
            print(f"     売却株数 : {s['shares']}株")
            print(f"     売却理由 : {s['reason']}")
            print(f"     現在値   : {s['current_price']:,.0f}円（{s['change_pct']:+.1f}%）")
    else:
        print("\n  売却候補なし")

    # --- JSON出力 ---
    rpa_output = {
        "date": today,
        "market_trend": market["trend"],
        "market_caution": market["caution"],
        "buy": [
            {
                "code": b["ticker"].replace(".T", ""),
                "name": b["name"],
                "shares": str(b["shares"]),
                "order_type": "指値",
                "price": str(int(b["buy_price"])),
                "stop_loss": str(int(b["stop_loss"])),
                "take_profit": str(int(b["take_profit"])),
            }
            for b in buy_candidates
        ],
        "sell": [
            {
                "code": s["ticker"].replace(".T", ""),
                "name": s["name"],
                "shares": str(s["shares"]),
                "order_type": "成行",
                "reason": s["reason"],
            }
            for s in sell_signals
        ],
    }

    json_file = OUTPUT_DIR / f"trade_order_{today}.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(rpa_output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print("  ■ RPA用JSON出力")
    print(f"{'='*60}")
    print(json.dumps(rpa_output, ensure_ascii=False, indent=2))
    print(f"\n✅ 保存: {json_file}")

    print(f"\n{'='*60}")
    print("  ■ スクリーニング結果（スコア上位10銘柄）")
    print(f"{'='*60}")
    print(f"  {'コード':<10} {'銘柄名':<20} {'スコア':>5} {'RSI':>6} {'出来高比':>8} {'新高値':>6}")
    print(f"  {'-'*58}")
    for r in results[:10]:
        code = r["ticker"].replace(".T", "")
        name = r["name"][:18]
        print(f"  {code:<10} {name:<20} {r['score']:>5} {r['rsi']:>6} {r['volume_ratio']:>8.2f}x {str(r['new_high']):>6}")

    print(f"\n{'='*60}")
    print("  ■ 月次パフォーマンスレポート")
    print(f"{'='*60}")
    report = generate_monthly_report()
    for k, v in report.items():
        if k == "改善提案":
            print("\n  【改善提案】")
            for s in v:
                print(f"  • {s}")
        else:
            print(f"  {k}: {v}")

    print(f"\n{'='*60}\n")

    # --- HTML レポート出力 ---
    html_file = OUTPUT_DIR / f"trade_report_{today}.html"
    generate_html_report(rpa_output, results[:10], market, report, html_file)
    print(f"📊 HTMLレポート: {html_file}")

    # iCloud Drive にコピー（iPhone確認用）
    icloud = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/CANSLIM"
    try:
        icloud.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(html_file, icloud / html_file.name)
        print(f"☁️  iCloud同期: {icloud / html_file.name}")
    except Exception as e:
        print(f"  iCloudコピースキップ: {e}")

    return rpa_output


def generate_html_report(rpa_output: dict, top_stocks: list, market: dict, perf: dict, html_file: Path):
    today = rpa_output.get("date", "")
    trend = market.get("trend", "不明")
    caution = market.get("caution", False)
    nikkei = market.get("nikkei_current", "-")
    dist_days = market.get("distribution_days", "-")
    buy_list = rpa_output.get("buy", [])
    sell_list = rpa_output.get("sell", [])

    trend_color = {"上昇": "#22c55e", "下落": "#ef4444", "中立": "#f59e0b"}.get(trend, "#94a3b8")
    caution_banner = (
        '<div class="banner">⚠️ 市場が要注意局面です。新規買いは見送りを推奨します。</div>'
        if caution else ""
    )

    def buy_rows():
        if not buy_list:
            return '<tr><td colspan="6" style="text-align:center;color:#94a3b8;">本日の買い候補なし</td></tr>'
        rows = ""
        for b in buy_list:
            rows += f"""
            <tr>
                <td><strong>{b['code']}</strong></td>
                <td>{b.get('name','')}</td>
                <td class="num">{int(b['price']):,}円</td>
                <td class="num">{b['shares']}株</td>
                <td class="num loss">{int(b['stop_loss']):,}円</td>
                <td class="num profit">{int(b['take_profit']):,}円</td>
            </tr>"""
        return rows

    def sell_rows():
        if not sell_list:
            return '<tr><td colspan="4" style="text-align:center;color:#94a3b8;">本日の売り候補なし</td></tr>'
        rows = ""
        for s in sell_list:
            rows += f"""
            <tr>
                <td><strong>{s['code']}</strong></td>
                <td>{s.get('name','')}</td>
                <td class="num">{s['shares']}株</td>
                <td>{s.get('reason','')}</td>
            </tr>"""
        return rows

    def screening_rows():
        rows = ""
        for r in top_stocks:
            code = r["ticker"].replace(".T", "")
            score_color = "#22c55e" if r["score"] >= 80 else "#f59e0b" if r["score"] >= 70 else "#94a3b8"
            signal = "✅ 買いシグナル" if r.get("buy_signal") else ""
            rows += f"""
            <tr>
                <td><strong>{code}</strong></td>
                <td>{r['name'][:20]}</td>
                <td style="color:{score_color};font-weight:bold">{r['score']}</td>
                <td class="num">{r['rsi']}</td>
                <td class="num">{r['volume_ratio']}x</td>
                <td>{'✅' if r['new_high'] else ''}</td>
                <td style="color:#22c55e">{signal}</td>
            </tr>"""
        return rows

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CANSLIM レポート {today}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', sans-serif;
         background: #0f172a; color: #e2e8f0; padding: 24px; }}
  h1 {{ font-size: 22px; font-weight: 700; color: #f8fafc; margin-bottom: 4px; }}
  .subtitle {{ color: #94a3b8; font-size: 14px; margin-bottom: 24px; }}
  .banner {{ background: #7c2d12; border: 1px solid #f97316; border-radius: 8px;
             padding: 12px 16px; margin-bottom: 20px; color: #fed7aa; font-size: 14px; }}
  .cards {{ display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; margin-bottom: 24px; }}
  .card {{ background: #1e293b; border-radius: 10px; padding: 16px; }}
  .card-label {{ font-size: 12px; color: #94a3b8; margin-bottom: 4px; }}
  .card-value {{ font-size: 22px; font-weight: 700; }}
  section {{ background: #1e293b; border-radius: 10px; padding: 20px; margin-bottom: 20px; }}
  h2 {{ font-size: 15px; font-weight: 600; color: #94a3b8; text-transform: uppercase;
        letter-spacing: 0.05em; margin-bottom: 14px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  th {{ text-align: left; padding: 8px 10px; color: #64748b; font-weight: 500;
        border-bottom: 1px solid #334155; font-size: 12px; }}
  td {{ padding: 10px 10px; border-bottom: 1px solid #1e293b; }}
  tr:hover td {{ background: #263348; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .profit {{ color: #22c55e; }}
  .loss {{ color: #ef4444; }}
  .btn {{ display: inline-block; margin-top: 16px; padding: 12px 28px;
          background: #2563eb; color: #fff; border-radius: 8px; font-size: 15px;
          font-weight: 600; cursor: pointer; border: none; width: 100%; }}
  .btn:hover {{ background: #1d4ed8; }}
  .btn-copy {{ background: #334155; margin-top: 8px; }}
  .copied {{ background: #15803d !important; }}
  .cmd-box {{ background: #0f172a; border: 1px solid #334155; border-radius: 6px;
              padding: 10px 14px; font-family: monospace; font-size: 13px;
              color: #7dd3fc; margin-top: 8px; word-break: break-all; }}
  footer {{ color: #475569; font-size: 12px; text-align: center; margin-top: 24px; }}
</style>
</head>
<body>

<h1>📊 CANSLIM 日本株レポート</h1>
<div class="subtitle">{today} 生成 | 自動スクリーニング結果</div>

{caution_banner}

<div class="cards">
  <div class="card">
    <div class="card-label">日経平均</div>
    <div class="card-value">{nikkei:,}</div>
  </div>
  <div class="card">
    <div class="card-label">市場トレンド</div>
    <div class="card-value" style="color:{trend_color}">{trend}</div>
  </div>
  <div class="card">
    <div class="card-label">売り抜け日数</div>
    <div class="card-value" style="color:{'#ef4444' if isinstance(dist_days,int) and dist_days>=4 else '#e2e8f0'}">{dist_days}日</div>
  </div>
  <div class="card">
    <div class="card-label">買い候補 / 売り候補</div>
    <div class="card-value">{len(buy_list)} / {len(sell_list)}</div>
  </div>
</div>

<section>
  <h2>🟢 買い候補</h2>
  <table>
    <thead><tr>
      <th>コード</th><th>銘柄名</th><th>指値</th><th>株数</th>
      <th>損切（-7.5%）</th><th>利確（+22.5%）</th>
    </tr></thead>
    <tbody>{buy_rows()}</tbody>
  </table>
</section>

<section>
  <h2>🔴 売り候補</h2>
  <table>
    <thead><tr>
      <th>コード</th><th>銘柄名</th><th>株数</th><th>理由</th>
    </tr></thead>
    <tbody>{sell_rows()}</tbody>
  </table>
</section>

<section>
  <h2>📈 スクリーニング上位10銘柄</h2>
  <table>
    <thead><tr>
      <th>コード</th><th>銘柄名</th><th>スコア</th><th>RSI</th><th>出来高比</th><th>新高値</th><th></th>
    </tr></thead>
    <tbody>{screening_rows()}</tbody>
  </table>
</section>

<section>
  <h2>⚡ SBI証券に発注する</h2>
  <p style="color:#94a3b8;font-size:13px;margin-bottom:12px;">
    ターミナルで以下のコマンドを実行すると、SBI証券の発注画面が起動します。
  </p>
  <div class="cmd-box" id="cmd">python3 ~/Desktop/sbi_rpa.py</div>
  <button class="btn btn-copy" onclick="copyCmd()">📋 コマンドをコピー</button>
  <p style="color:#475569;font-size:12px;margin-top:8px;">
    ※ コピー後、ターミナルを開いてペーストしてEnterを押してください
  </p>
</section>

<footer>CANSLIM 自動分析システム | 最終判断は必ず人間が行ってください</footer>

<script>
function copyCmd() {{
  const cmd = document.getElementById('cmd').textContent;
  navigator.clipboard.writeText(cmd).then(() => {{
    const btn = document.querySelector('.btn-copy');
    btn.textContent = '✅ コピーしました';
    btn.classList.add('copied');
    setTimeout(() => {{
      btn.textContent = '📋 コマンドをコピー';
      btn.classList.remove('copied');
    }}, 2000);
  }});
}}
</script>
</body>
</html>"""

    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    main()
