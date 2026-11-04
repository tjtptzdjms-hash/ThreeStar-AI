"""Streamlit views; research never writes draws or prediction logs."""
from pathlib import Path
import pandas as pd
import streamlit as st
from analysis_v2 import backtest, history_patterns

NAMES = {'hot': '熱號', 'cold': '冷號', 'weighted': '熱40／遺漏60',
         'pattern': '同位置轉移牌路', 'random': '固定種子隨機'}


@st.cache_data(show_spinner=False)
def run_backtest(records, window, top_n, max_tests, holdout):
    return backtest(records, window, top_n, max_tests, holdout)


def render(df):
    records = df.assign(date=df.date.dt.strftime('%Y-%m-%d')).to_dict('records')
    st.metric('已收錄期數', len(df))
    st.caption(f"最新資料：{records[0]['date']}／{records[0]['issue']}／{records[0]['number']}")
    patterns, testing, logs = st.tabs(['歷史牌路', '逐期回測與保留驗證', '原始預測紀錄'])
    with patterns:
        window = st.selectbox('牌路分析期數', [30, 50, 100, 200, 500], index=2)
        detail, summary = history_patterns(records, window)
        st.caption('大小定義：0–4 為小，5–9 為大。連莊只比較相鄰期的相同位置；第一期無前期可比較。')
        st.dataframe(pd.DataFrame(summary), hide_index=True, use_container_width=True)
        st.dataframe(pd.DataFrame(detail).iloc[::-1], hide_index=True, use_container_width=True)
        st.download_button('下載牌路明細', pd.DataFrame(detail).to_csv(index=False).encode('utf-8-sig'), 'patterns.csv')
    with testing:
        st.write('各策略使用相同組數。每一期只取該日期之前的資料；最新一段保留作驗證，策略只用探索區間挑選。')
        with st.form('v2_backtest'):
            window = st.selectbox('訓練視窗', [10, 30, 50, 100, 200], index=1)
            top_n = st.selectbox('每期不同號碼組數', [8, 10, 20, 50], index=2)
            max_tests = st.number_input('最多測試期數（含保留驗證）', 2, 1000, 200)
            holdout = st.number_input('最新保留驗證期數', 1, 500, 50)
            submitted = st.form_submit_button('執行 V2 回測')
        st.caption('反覆查看驗證結果後再調參，該區間就不能再視為未見資料。95% 區間使用 Wilson 方法，未校正多重比較或序列相依；不構成獲利證據。')
        if submitted:
            try:
                with st.spinner('逐期計算中…'):
                    detail, summary, chosen = run_backtest(records, window, top_n, max_tests, holdout)
                result = pd.DataFrame(summary)
                result['策略'] = result['策略'].map(NAMES)
                st.dataframe(result, hide_index=True, use_container_width=True)
                check = next(r for r in summary if r['策略'] == chosen and r['區間'] == '保留驗證')
                st.info(f"探索區間選定：{NAMES[chosen]}；保留驗證命中 {check['命中期數']}/{check['回測期數']} 期（{check['命中率']:.2%}）。每期 {top_n} 組的理論隨機基準為 {top_n/1000:.2%}。")
                st.caption('牌路策略為各位置數字的一階轉移統計，採加一平滑；展示的奇偶、大小、和值與跨度為描述統計，不會自動加入策略。所有評分均非中獎機率。')
                st.download_button('下載 V2 逐期回測', pd.DataFrame(detail).to_csv(index=False).encode('utf-8-sig'), 'v2_backtest.csv')
                st.dataframe(pd.DataFrame(detail), hide_index=True, use_container_width=True)
            except ValueError as exc:
                st.warning(str(exc))
    with logs:
        path = Path('predictions.csv')
        if path.exists():
            raw = pd.read_csv(path, dtype=str).fillna('')
            st.caption('完整原始紀錄，保留手動測試與未結算項目；不將它們混入 V2 回測。每日預測及自動結算仍沿用原策略。')
            st.dataframe(raw, hide_index=True, use_container_width=True)
        else:
            st.info('尚無 predictions.csv。')
