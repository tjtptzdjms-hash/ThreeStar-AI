import io, os, re
from pathlib import Path
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title='三星彩統計實驗室',layout='wide')
DATA=Path('draws.csv')
COLS=['date','issue','number']

def clean(df):
    df=df.rename(columns={c:c.strip().lower() for c in df.columns})
    if not set(COLS).issubset(df.columns): raise ValueError('CSV 必須包含 date, issue, number 欄位')
    df=df[COLS].copy()
    df['date']=pd.to_datetime(df.date,errors='coerce')
    df['number']=df.number.astype(str).str.replace(r'\.0$','',regex=True).str.zfill(3)
    df=df[df.date.notna() & df.number.str.fullmatch(r'\d{3}')]
    df=df.drop_duplicates('issue',keep='last').sort_values(['date','issue'],ascending=False).reset_index(drop=True)
    return df

def load():
    return clean(pd.read_csv(DATA,dtype=str)) if DATA.exists() else pd.DataFrame(columns=COLS)

def metrics(df, n):
    d=df.head(n)
    out=[]
    for pos,name in enumerate(['百位','十位','個位']):
        seq=d.number.str[pos].tolist()
        for digit in '0123456789':
            freq=seq.count(digit)
            miss=next((i for i,x in enumerate(seq) if x==digit),len(seq))
            out.append({'位置':name,'數字':digit,'出現次數':freq,'出現率':freq/len(seq) if seq else 0,'遺漏期數':miss,'樣本數':len(seq)})
    return pd.DataFrame(out)

st.title('🎯 三星彩統計實驗室 V1.1')
st.caption('歷史統計與回測研究用途；不代表能預測獨立隨機開獎。資料未更新時請以官方公告為準。')
with st.sidebar:
    st.header('資料管理')
    st.write('CSV 欄位：date, issue, number；號碼如 007 必須保留前導零。')
    upload=st.file_uploader('匯入官方核對後的 CSV',type='csv')
    if upload:
        try:
            incoming=clean(pd.read_csv(upload,dtype=str))
            existing=load()
            merged=clean(pd.concat([incoming,existing],ignore_index=True))
            merged.assign(date=merged.date.dt.strftime('%Y-%m-%d')).to_csv(DATA,index=False)
            st.success(f'已合併 {len(merged)} 期資料')
        except Exception as e: st.error(f'匯入失敗：{e}')
    st.markdown('[官方開獎查詢](https://lotto.ctbcbank.com/result_all.htm)')

df=load()
if df.empty:
    st.warning('目前沒有已驗證的歷史資料。請先匯入 CSV；系統不會把示範號碼當成真實獎號。')
    st.download_button('下載 CSV 範本','date,issue,number\n2026-01-01,example-001,007\n','template.csv','text/csv')
    st.stop()

st.metric('已收錄期數',len(df))
st.write('最新資料：',df.iloc[0]['date'].strftime('%Y-%m-%d'),'／',df.iloc[0]['issue'],'／',df.iloc[0]['number'])
window=st.select_slider('分析最近多少期',options=[10,30,50,100,200,500],value=100)
if len(df)<window: st.info(f'目前只有 {len(df)} 期，統計依現有資料計算。')
stat=metrics(df,window)
st.subheader('📊 V1.1 快速摘要')

summary_cols = st.columns(3)

for col, p in zip(summary_cols, ['百位', '十位', '個位']):
    v = stat[stat['位置'] == p].copy()

    hot = (
        v.sort_values(
            ['出現次數', '遺漏期數', '數字'],
            ascending=[False, True, True]
        )
        .head(3)
    )

    overdue = (
        v.sort_values(
            ['遺漏期數', '出現次數', '數字'],
            ascending=[False, True, True]
        )
        .head(3)
    )

    with col:
        st.markdown(f'### {p}')

        st.write(
            '🔥 熱號 Top 3：',
            '、'.join(
                f"{r['數字']}（{int(r['出現次數'])}次）"
                for _, r in hot.iterrows()
            )
        )

        st.write(
            '⏳ 遺漏 Top 3：',
            '、'.join(
                f"{r['數字']}（{int(r['遺漏期數'])}期）"
                for _, r in overdue.iterrows()
            )
        )
st.subheader("🔁 近期重複與連莊")

recent = df.head(window).copy()

def split_number(n):
    s = str(n).zfill(3)
    return int(s[0]), int(s[1]), int(s[2])

recent[["百位", "十位", "個位"]] = recent["number"].apply(
    lambda x: pd.Series(split_number(x))
)

repeat_info = []

for pos in ["百位", "十位", "個位"]:
    vals = recent[pos].tolist()

    repeat_count = sum(
        vals[i] == vals[i - 1]
        for i in range(1, len(vals))
    )

    current_streak = 1

    for i in range(1, len(vals)):
        if vals[i] == vals[i - 1]:
            current_streak += 1
        else:
            break

    repeat_info.append(
        {
            "位置": pos,
            "最近連莊值": vals[0] if vals else None,
            "目前連莊期數": current_streak,
            "近期期數內相鄰重複次數": repeat_count,
        }
    )

repeat_df = pd.DataFrame(repeat_info)

st.dataframe(
    repeat_df,
    use_container_width=True,
    hide_index=True
)
st.subheader("⭐ 組合評分")

score_map = {}

for pos in ["百位", "十位", "個位"]:
    v = stat[stat["位置"] == pos].copy()

    max_count = max(v["出現次數"].max(), 1)
    max_miss = max(v["遺漏期數"].max(), 1)

    score_map[pos] = {}

    for _, r in v.iterrows():
        hot_score = r["出現次數"] / max_count
        miss_score = r["遺漏期數"] / max_miss

        score = (
            hot_score * 0.6
            + miss_score * 0.4
        )

        score_map[pos][int(r["數字"])] = score

candidates = []

for h in range(10):
    for t in range(10):
        for o in range(10):
            score = (
                score_map["百位"][h]
                + score_map["十位"][t]
                + score_map["個位"][o]
            ) / 3

            candidates.append(
                {
                    "號碼": f"{h}{t}{o}",
                    "評分": round(score * 100, 1)
                }
            )

combo_df = pd.DataFrame(candidates)

combo_df = combo_df.sort_values(
    "評分",
    ascending=False
).head(10)

st.dataframe(
    combo_df,
    use_container_width=True,
    hide_index=True
)

st.caption(
    "評分僅依歷史熱度與遺漏值計算，不代表中獎機率提高。"
)
t1,t2,t3,t4=st.tabs(['冷熱與遺漏','開獎走勢','參考組合','歷史回測'])
with t1:
    for p in ['百位','十位','個位']:
        st.subheader(p)
        v=stat[stat['位置']==p].sort_values('出現次數',ascending=False)
        st.bar_chart(v.set_index('數字')['出現次數'])
        st.dataframe(v,hide_index=True,use_container_width=True)
with t2:
    k=st.slider('走勢期數',10,min(100,max(10,len(df))),min(30,max(10,len(df))))
    for p,idx in [('百位',0),('十位',1),('個位',2)]:
        st.subheader(p)
        seq=df.head(k).iloc[::-1].copy()
        seq['數字']=seq.number.str[idx].astype(int)
        st.line_chart(seq.set_index('issue')['數字'],y_label='數字 0–9')
    st.dataframe(df.head(k).assign(date=lambda x:x.date.dt.strftime('%Y-%m-%d')),hide_index=True)
with t3:
    st.write('依歷史出現次數選出每個位置的候選數字，僅供示範；不代表中獎機率較高。')
    strategy=st.radio('候選策略',['熱門','冷門'],horizontal=True)
    count=st.slider('每個位置取幾個數字',1,3,2)
    picks=[]
    for p in ['百位','十位','個位']:
        v=stat[stat['位置']==p].sort_values(['出現次數','數字'],ascending=[strategy=='冷門',True])
        picks.append(v['數字'].head(count).tolist())
    import itertools
    combos=[''.join(x) for x in itertools.product(*picks)]
    st.write('候選組合：', '、'.join(combos))
    st.caption(f'共 {len(combos)} 組不同號碼；完全命中其中一組的理論機率為 {len(combos)/1000:.2%}。')
with t4:
    st.write('逐期僅使用該期以前的資料，避免使用未來資訊。比較熱門、冷門與固定隨機基準。')
    ntrain=st.number_input('每次使用前多少期作為訓練',min_value=10,max_value=200,value=30)
    ntest=st.number_input('最多回測多少期',min_value=1,max_value=1000,value=100)
    if len(df)<ntrain+1: st.warning('資料不足，至少需要訓練期數再加1期。')
    else:
        import random,itertools
        chronological=df.iloc[::-1].reset_index(drop=True)
        results=[]
        start=max(ntrain,len(chronological)-ntest)
        for i in range(start,len(chronological)):
            prior=chronological.iloc[:i].iloc[::-1]
            s=metrics(prior,ntrain)
            target=chronological.iloc[i].number
            record={'期別':chronological.iloc[i].issue,'實際號碼':target}
            for strat in ['熱門','冷門']:
                sets=[]
                for p in ['百位','十位','個位']:
                    v=s[s['位置']==p].sort_values(['出現次數','數字'],ascending=[strat=='冷門',True])
                    sets.append(v['數字'].head(2).tolist())
                picks=[''.join(x) for x in itertools.product(*sets)]
                record[strat]=int(target in picks)
            rng=random.Random(i)
            record['隨機8組']=int(target in {f'{x:03d}' for x in rng.sample(range(1000),8)})
            results.append(record)
        r=pd.DataFrame(results)
        st.dataframe(pd.DataFrame({'方法':['熱門8組','冷門8組','隨機8組'],'命中期數':[int(r['熱門'].sum()),int(r['冷門'].sum()),int(r['隨機8組'].sum())],'回測期數':[len(r)]*3,'理論命中率':[.008]*3}),hide_index=True)
        st.download_button('下載逐期回測',r.to_csv(index=False).encode('utf-8-sig'),'backtest.csv')
