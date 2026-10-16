# 三星彩統計實驗室 V1

## 啟動
`pip install -r requirements.txt`
`streamlit run app.py`

## 匯入資料
CSV 必須包含 `date,issue,number` 三欄，例如 `2026-10-15,115000250,496`。
請以台灣彩券官方公告核對資料。程式會依期別去重、保留 007 等前導零。

## 自動更新
附帶 `.github/workflows/update.yml`，每天台灣時間約 22:15 執行 `update.py`。
預設使用公開第三方唯讀 API；由於資料結構可能變動，更新器採嚴格驗證：解析失敗或資料不一致時不會覆寫原始資料。
首次部署前請先上傳至少一份已驗證的 CSV，並確認 GitHub Actions 具有 contents:write 權限。
第三方 API 並非台灣彩券官方服務；結果以官方公告為準。

## 回測注意
熱門/冷門候選每次為 8 組，與隨機 8 組比較。各組理論中獎率皆為 0.8%；回測短期差異不能證明預測優勢。
