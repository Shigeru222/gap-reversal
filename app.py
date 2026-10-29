"""翌朝ギャップ反転スキャナー（Streamlit版）"""
import altair as alt
import pandas as pd
import streamlit as st

import core

st.set_page_config(page_title="翌朝ギャップ反転スキャナー", page_icon="📈", layout="wide")
st.title("翌朝ギャップ反転スキャナー")
st.caption("前日比で上がった日は翌朝安く寄り、下がった日は翌朝高く寄る。この反転が偶然以上に起きている国内株を探します。")
with st.expander("計算式", expanded=False):
    st.markdown(
        "- 当日騰落 **r** ＝ 終値(t) ÷ 終値(t−1) − 1\n"
        "- 翌朝ギャップ **g** ＝ 始値(t+1) ÷ 終値(t) − 1\n"
        "- **反転**＝ r と g の符号が逆\n"
        "- **偶然の水準**＝ その銘柄の安寄り・高寄りの比率から計算した、r と g が無関係な場合の反転率\n"
        "- 株価は配当・分割調整済み。出来高ゼロの日は除外"
    )

# ---------- 条件 ----------
with st.sidebar:
    st.header("条件")
    src = st.radio("対象銘柄", ["日経225（自動取得）", "自分で指定"], key="src")
    custom = ""
    if src == "自分で指定":
        custom = st.text_area("1行に「コード,銘柄名」", "7203,トヨタ\n8306,三菱UFJ\n6758,ソニーG", height=160, key="custom")
    add_etf = st.checkbox("比較用に1321・1570を追加", value=True, key="add_etf")
    years = st.slider("期間（年）", 1, 10, 3, key="years")
    st.divider()
    cost_pct = st.number_input("往復コスト（%）", 0.0, 2.0, 0.10, 0.01, key="cost",
                               help="手数料＋スプレッド＋（売りの場合）貸株料の概算")
    alpha = st.number_input("有意水準", 0.001, 0.20, 0.05, 0.01, format="%.3f", key="alpha",
                            help="銘柄数で割って補正します（ボンフェローニ）")
    min_n = st.number_input("最小サンプル（日）", 20, 3000, 200, 10, key="min_n")
    go = st.button("株価を取得して分析", type="primary", use_container_width=True)
    st.caption("株価の取得は条件を変えたときだけ。コスト・有意水準の変更は即時に再計算されます。")


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def get_universe():
    return core.fetch_nikkei225()


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def get_prices(codes, yrs):
    return core.fetch_prices(list(codes), yrs)


# ---------- 取得 ----------
if go:
    if src == "日経225（自動取得）":
        with st.spinner("日経225の採用銘柄を取得中…"):
            try:
                universe = get_universe()
            except Exception as e:
                universe = []
                st.error(f"採用銘柄の取得に失敗しました（{e}）。「自分で指定」に切り替えてください。")
        if 0 < len(universe) < 200:
            st.warning(f"日経のページから {len(universe)} 銘柄しか取れませんでした。全銘柄を調べる場合は「自分で指定」に貼り付けてください。")
    else:
        universe = core.parse_ticker_text(custom)
    if add_etf:
        universe = core.dedupe(universe + core.EXTRA)
    if universe:
        with st.spinner(f"{len(universe)}銘柄・過去{years}年の株価を取得中…（1〜2分）"):
            try:
                prices = get_prices(tuple(c for c, _ in universe), years)
            except Exception as e:
                prices = {}
                st.error(f"株価の取得に失敗しました（{e}）。取得先の混雑の可能性があります。数分おいて再実行してください。")
        if prices:
            st.session_state["prices"] = prices
            st.session_state["names"] = dict(universe)
            missing = len(universe) - len(prices)
            if missing:
                st.info(f"{missing}銘柄はデータが取れなかったため除外しました。")
    else:
        st.error("対象銘柄がありません。")

if "prices" not in st.session_state:
    st.info("左の条件を確認して「株価を取得して分析」を押してください。スマホでは左上の「>」で条件が開きます。")
    st.stop()

# ---------- 分析 ----------
res, a_adj = core.run(st.session_state["prices"], st.session_state["names"], cost_pct / 100, alpha, int(min_n))
if res.empty:
    st.error("分析できる銘柄がありませんでした。")
    st.stop()

cnt = res["判定"].value_counts()
c1, c2, c3, c4 = st.columns(4)
c1.metric("分析した銘柄", len(res))
c2.metric("傾向あり", int(cnt.get("傾向あり", 0)))
c3.metric("要検証", int(cnt.get("要検証", 0)))
c4.metric("補正後の有意水準", f"{a_adj:.5f}")

st.subheader("反転傾向ランキング")
show = st.multiselect("表示する判定", list(core.ORDER), default=["傾向あり", "要検証", "なし"], key="show")
view = res[res["判定"].isin(show)].copy()
pct_cols = ["反転率", "偶然の水準", "前半反転率", "後半反転率", "両方向損益_コスト後", "買いのみ損益_コスト後"]
for c in pct_cols:
    view[c] = view[c] * 100
cols = ["判定", "コード", "銘柄", "日数", "反転率", "偶然の水準", "z値", "前半反転率", "後半反転率",
        "相関", "両方向損益_コスト後", "買いのみ損益_コスト後", "売買代金中央値_億円"]
st.dataframe(
    view[cols], hide_index=True, use_container_width=True,
    column_config={
        "反転率": st.column_config.NumberColumn(format="%.1f%%"),
        "偶然の水準": st.column_config.NumberColumn(format="%.1f%%"),
        "前半反転率": st.column_config.NumberColumn("前半", format="%.1f%%"),
        "後半反転率": st.column_config.NumberColumn("後半", format="%.1f%%"),
        "z値": st.column_config.NumberColumn(format="%.2f"),
        "相関": st.column_config.NumberColumn("相関 r→g", format="%.2f"),
        "両方向損益_コスト後": st.column_config.NumberColumn("両方向 損益/回", format="%.3f%%"),
        "買いのみ損益_コスト後": st.column_config.NumberColumn("買いのみ 損益/回", format="%.3f%%"),
        "売買代金中央値_億円": st.column_config.NumberColumn("売買代金(億円)", format="%.1f"),
    },
)
st.caption("傾向あり＝補正後も有意・前後半とも偶然の水準超え・コスト後プラス。要検証＝一部のみ満たす。損益/回はコスト後、税引前。")
st.download_button("結果をCSVで保存", res.to_csv(index=False).encode("utf-8-sig"),
                   file_name="gap_reversal_results.csv", mime="text/csv")

# ---------- 詳細 ----------
st.subheader("銘柄の詳細")
labels = {f"{r.コード} {r.銘柄}（{r.判定}）": r.コード for r in res.itertuples()}
pick = labels[st.selectbox("銘柄を選ぶ", list(labels), key="pick")]
x = res[res["コード"] == pick].iloc[0]
df = st.session_state["prices"][pick]

left, right = st.columns([2, 3])
with left:
    ct = pd.DataFrame(
        {"翌朝 安く寄る": [f"{x['上昇後安寄り']}（{x['上昇後安寄り']/max(x['上昇日'],1):.1%}）", x["下落日"] - x["下落後高寄り"]],
         "翌朝 高く寄る": [x["上昇日"] - x["上昇後安寄り"], f"{x['下落後高寄り']}（{x['下落後高寄り']/max(x['下落日'],1):.1%}）"]},
        index=[f"当日 上昇（{x['上昇日']}日）", f"当日 下落（{x['下落日']}日）"]).astype(str)
    st.table(ct)
    st.markdown(
        f"- 期間：{x['開始']} 〜 {x['終了']}\n"
        f"- 反転率 {x['反転率']:.1%} ／ 偶然の水準 {x['偶然の水準']:.1%}\n"
        f"- z値 {x['z値']:.2f}（p値 {x['p値']:.4f}、補正後の基準 {a_adj:.5f}）\n"
        f"- 前半 {x['前半反転率']:.1%} ／ 後半 {x['後半反転率']:.1%}\n"
        f"- 平均損益/回（コスト前）：両方向 {x['両方向損益_コスト前']:+.3%}、買いのみ {x['買いのみ損益_コスト前']:+.3%}\n"
        f"- 売買代金の中央値：{x['売買代金中央値_億円']:.1f}億円/日"
    )
with right:
    pts = pd.DataFrame(core.points(df), columns=["日付", "r", "g"])
    pts["反転"] = ((pts["r"] > 0) & (pts["g"] < 0)) | ((pts["r"] < 0) & (pts["g"] > 0))
    pts["区分"] = pts["反転"].map({True: "反転", False: "非反転"})
    xr = float(pts["r"].abs().quantile(0.99)) * 1.1 or 0.01
    yr = float(pts["g"].abs().quantile(0.99)) * 1.1 or 0.01
    base = alt.Chart(pts)
    dots = base.mark_circle(size=18, opacity=0.55).encode(
        x=alt.X("r:Q", title="当日騰落 r", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[-xr, xr], clamp=True)),
        y=alt.Y("g:Q", title="翌朝ギャップ g", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[-yr, yr], clamp=True)),
        color=alt.Color("区分:N", scale=alt.Scale(domain=["反転", "非反転"], range=["#3b5bdb", "#adb5bd"])),
        tooltip=[alt.Tooltip("日付:T", format="%Y-%m-%d"), alt.Tooltip("r:Q", format=".2%"), alt.Tooltip("g:Q", format=".2%")],
    )
    line = base.transform_regression("r", "g").mark_line(color="#e03131", size=2).encode(x="r:Q", y="g:Q")
    st.altair_chart((dots + line).properties(height=380), use_container_width=True)
    st.caption("左上と右下が「反転」の領域。赤い回帰線が右下がりなら反転傾向。")

with st.expander("結果を読むときの注意", expanded=True):
    st.markdown(
        "1. 銘柄を大量に調べると、偶然だけで「傾向あり」に見える銘柄が必ず出ます。補正後の判定と、前半・後半の両方で同じ傾向かを確認してください。\n"
        "2. 終値は引けの板寄せで決まるため、売り気配と買い気配の差だけで見かけの反転が出ます。売買代金の小さい銘柄ほど強く出ます。\n"
        "3. 「両方向」は上げた日に引けで信用売り・翌朝買い戻しを含みます。売りが使えない場合は「買いのみ」を見てください。\n"
        "4. 株価は非公式ライブラリ（yfinance）経由のYahoo Financeデータです。欠損や誤差がありえます。\n"
        "5. 過去の統計は将来の利益を保証しません。最終的な売買判断はご自身で行ってください。"
    )
