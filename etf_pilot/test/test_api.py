import akshare as ak
# 日线
df = ak.fund_etf_hist_em(symbol="513100", period="daily", start_date="20240101", end_date="20250224", adjust="qfq")
print("日线:", df is None or df.empty, df.shape if df is not None else None)
# 实时
spot = ak.fund_etf_spot_em()
print("实时:", spot is None or spot.empty, spot.columns.tolist() if spot is not None else None)