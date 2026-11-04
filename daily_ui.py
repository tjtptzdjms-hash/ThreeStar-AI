"""Today's independent research snapshots and separate forward performance."""
from datetime import datetime
from pathlib import Path
import pandas as pd
import streamlit as st
from prediction_records import TZ, STRATEGIES, complete_snapshot, settled_summary


def render_daily():
    st.subheader('今日 Top 20 與事前追蹤')
    st.caption('V2 已接入同位置數字轉移牌路；奇偶、大小、和值、跨度仍為描述統計。新策略尚未證明優於隨機。')
    st.caption('兩套各20組，分開追蹤；不是合併的40組推薦，分數與排名不代表中獎機率。')
    path = Path('predictions.csv')
    if not path.exists():
        st.info('尚無預測紀錄。')
        return
    raw = pd.read_csv(path, dtype=str).fillna('')
    required = {'target_date', 'strategy', 'window', 'created_at', 'rank', 'number', 'status', 'actual_number'}
    if not required.issubset(raw.columns):
        st.error('預測檔欄位不完整，無法顯示。')
        return
    records = raw.to_dict('records')
    strategy = st.selectbox('顯示策略', list(STRATEGIES), format_func=STRATEGIES.get)
    today = datetime.now(TZ).date().isoformat()
    st.write('目標日期：', today)
    daily = [r for r in records if r['strategy'] == strategy and r['target_date'] == today]
    if not daily:
        st.info('此策略今日尚未保存事前預測。週一至週六中午排程執行後才會顯示，實際時間可能延遲；不會把歷史回測補成正式預測。')
    elif not complete_snapshot(daily):
        st.warning('今日紀錄不完整、重複或建立時間無效，暫不顯示候選號碼。')
    else:
        st.write('預測建立時間：', daily[0]['created_at'])
        table = pd.DataFrame(sorted(daily, key=lambda r: int(r['rank'])))
        st.dataframe(table[['rank', 'number', 'status']].rename(columns={'rank': '排名', 'number': '號碼', 'status': '狀態'}), hide_index=True, use_container_width=True)
    stats = []
    for key, label in STRATEGIES.items():
        days = settled_summary(records, key)
        hits = sum(r['命中'] for r in days)
        stats.append({'策略': label, '已結算期數': len(days), '命中期數': hits,
                      '命中率': f'{hits/len(days):.2%}' if days else '尚無資料', '理論隨機基準': '2%'})
    st.subheader('各策略事前績效（分開統計）')
    st.dataframe(pd.DataFrame(stats), hide_index=True, use_container_width=True)
    st.caption('只納入完整20組、當日19點前建立且已結算的快照；排除10/19及10/22手動測試。兩套開始日期不同，累積績效不宜直接比較。')
    days = settled_summary(records, strategy)
    if days:
        st.dataframe(pd.DataFrame(days).tail(30).iloc[::-1], hide_index=True, use_container_width=True)
