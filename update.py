"""Fail-closed updater: external API schema must be explicitly verified before enabling.
Never silently insert unknown results into the verified draw dataset.
"""
import sys
print('尚未啟用自動匯入：需要先確認資料 API 欄位及與官方獎號一致性；既有資料保持不變。')
sys.exit(0)
