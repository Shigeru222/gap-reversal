"""引け→翌朝ギャップ反転の分析ロジック（画面から独立）"""
import math
import re
from io import StringIO

import pandas as pd

NIKKEI_URL = "https://indexes.nikkei.co.jp/nkave/index/component?idx=nk225"
EXTRA = [("1321", "日経225連動型ETF"), ("1570", "日経レバETF")]
CODE_RE = re.compile(r"\d{3}[0-9A-Z]")


# ---------- 銘柄リスト ----------
def parse_ticker_text(text):
    """「7203,トヨタ」形式（区切りはカンマ・タブ・空白）の行を読む"""
    rows = []
    for line in text.splitlines():
        parts = [p for p in re.split(r"[,\t\s]+", line.strip()) if p]
        if parts and CODE_RE.fullmatch(parts[0]):
            rows.append((parts[0], parts[1] if len(parts) > 1 else parts[0]))
    return dedupe(rows)


def dedupe(rows):
    seen, out = set(), []
    for c, n in rows:
        if c not in seen:
            seen.add(c)
            out.append((c, n))
    return out


def fetch_nikkei225():
    import requests
    html = requests.get(NIKKEI_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30).text
    rows = []
    try:
        for t in pd.read_html(StringIO(html)):
            cols = [str(c) for c in t.columns]
            ci = next((i for i, c in enumerate(cols) if "コード" in c), None)
            ni = next((i for i, c in enumerate(cols) if "銘柄" in c), None)
            if ci is None or ni is None:
                continue
            for code, name in zip(t.iloc[:, ci], t.iloc[:, ni]):
                code = str(code).strip()
                if CODE_RE.fullmatch(code):
                    rows.append((code, str(name).strip()))
    except ValueError:
        pass
    return dedupe(rows)


# ---------- 株価取得 ----------
def fetch_prices(codes, years):
    """yfinanceで一括取得。{コード: DataFrame(Open, Close, Volume)} を返す"""
    import yfinance as yf
    tickers = [f"{c}.T" for c in codes]
    raw = yf.download(tickers, period=f"{years}y", interval="1d", auto_adjust=True,
                      group_by="ticker", threads=True, progress=False)
    out = {}
    for c, t in zip(codes, tickers):
        try:
            df = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
        except KeyError:
            continue
        out_df = clean(df)
        if out_df is not None:
            out[c] = out_df
    return out


def clean(df):
    if df is None or df.empty or not {"Open", "Close", "Volume"} <= set(df.columns):
        return None
    df = df[["Open", "Close", "Volume"]].dropna()
    df = df[(df["Open"] > 0) & (df["Close"] > 0)]
    if len(df) < 60:
        return None
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df = df[~df.index.duplicated()].sort_index()
    return df


# ---------- 分析 ----------
def points(df):
    """(日付, 当日騰落r, 翌朝ギャップg) の一覧。出来高ゼロの日は除外"""
    c, o, v = df["Close"].to_numpy(), df["Open"].to_numpy(), df["Volume"].to_numpy()
    idx = df.index
    out = []
    for t in range(1, len(df) - 1):
        if v[t] <= 0 or v[t + 1] <= 0:
            continue
        r, g = c[t] / c[t - 1] - 1, o[t + 1] / c[t] - 1
        if abs(r) < 0.5 and abs(g) < 0.5:
            out.append((idx[t], r, g))
    return out


def part(pts):
    U = Ud = D = Du = g_dn = g_up = 0
    both = long_s = 0.0
    for _, r, g in pts:
        g_dn += g < 0
        g_up += g > 0
        if r > 0:
            U += 1; Ud += g < 0; both += -g
        elif r < 0:
            D += 1; Du += g > 0; both += g; long_s += g
    N, n = U + D, max(len(pts), 1)
    pD, pU = g_dn / n, g_up / n
    nan = float("nan")
    return dict(U=U, Ud=Ud, D=D, Du=Du, N=N,
                R=(Ud + Du) / N if N else nan,
                R0=(U * pD + D * pU) / N if N else nan,
                both=both / N if N else nan,
                long=long_s / D if D else nan)


def analyze(df):
    pts = points(df)
    if len(pts) < 30:
        return None
    a, h = part(pts), len(pts) // 2
    p1, p2 = part(pts[:h]), part(pts[h:])
    z = (a["R"] - a["R0"]) / math.sqrt(a["R0"] * (1 - a["R0"]) / a["N"])
    rs = pd.Series([p[1] for p in pts]); gs = pd.Series([p[2] for p in pts])
    return dict(
        日数=a["N"], 反転率=a["R"], 偶然の水準=a["R0"], z値=z,
        p値=math.erfc(abs(z) / math.sqrt(2)),
        前半反転率=p1["R"], 後半反転率=p2["R"], 前半偶然=p1["R0"], 後半偶然=p2["R0"],
        相関=rs.corr(gs),
        上昇日=a["U"], 上昇後安寄り=a["Ud"], 下落日=a["D"], 下落後高寄り=a["Du"],
        両方向損益_コスト前=a["both"], 買いのみ損益_コスト前=a["long"],
        売買代金中央値_億円=float((df["Close"] * df["Volume"]).median() / 1e8),
        開始=df.index[0].date(), 終了=df.index[-1].date(),
    )


def judge(res, cost, alpha, min_n):
    """cost は小数（0.001 = 0.1%）。補正後の有意水準を返す"""
    a_adj = alpha / max(len(res), 1)
    for x in res:
        x["両方向損益_コスト後"] = x["両方向損益_コスト前"] - cost
        x["買いのみ損益_コスト後"] = x["買いのみ損益_コスト前"] - cost
        sig = x["p値"] < a_adj and x["z値"] > 0
        stable = x["前半反転率"] > x["前半偶然"] and x["後半反転率"] > x["後半偶然"]
        prof = x["両方向損益_コスト後"] > 0 or x["買いのみ損益_コスト後"] > 0
        if x["日数"] < min_n:
            x["判定"] = "日数不足"
        elif sig and stable and prof:
            x["判定"] = "傾向あり"
        elif (x["p値"] < alpha and x["z値"] > 0) or (stable and x["z値"] > 1):
            x["判定"] = "要検証"
        else:
            x["判定"] = "なし"
    return a_adj


ORDER = {"傾向あり": 0, "要検証": 1, "なし": 2, "日数不足": 3}


def run(prices, names, cost, alpha, min_n):
    res = []
    for code, df in prices.items():
        x = analyze(df)
        if x:
            res.append(dict(コード=code, 銘柄=names.get(code, code), **x))
    if not res:
        return pd.DataFrame(), alpha
    a_adj = judge(res, cost, alpha, min_n)
    out = pd.DataFrame(res)
    out["_o"] = out["判定"].map(ORDER)
    out = out.sort_values(["_o", "z値"], ascending=[True, False]).drop(columns="_o")
    return out.reset_index(drop=True), a_adj
