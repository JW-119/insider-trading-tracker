"""Insider Trading Tracker 설정."""

import os
from dotenv import load_dotenv

load_dotenv()

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CACHE_DIR = os.path.join(BASE_DIR, "cache")

# --- SEC EDGAR Settings ---
# .env → st.secrets → 기본값 순서로 폴백
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "")
if not SEC_USER_AGENT:
    try:
        import streamlit as st
        SEC_USER_AGENT = st.secrets.get("SEC_USER_AGENT", "")
    except Exception:
        pass
if not SEC_USER_AGENT:
    SEC_USER_AGENT = "MyApp admin@example.com"

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_EFTS_URL = "https://efts.sec.gov/LATEST/search-index?q=%22form-type%22%3A%224%22&dateRange=custom&startdt={start}&enddt={end}&forms=4"
SEC_FULL_TEXT_URL = "https://efts.sec.gov/LATEST/search-index?q=%224%22&forms=4&dateRange=custom&startdt={start}&enddt={end}"
SEC_ARCHIVES_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
SEC_FILING_BASE = "https://www.sec.gov/Archives/edgar/data"

# --- 관심 종목 ---
WATCHLIST_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "META", "TSLA", "JPM", "V", "JNJ",
]

# --- 수집 모드 ---
COLLECT_MODE = "watchlist"  # "watchlist" 또는 "latest"

# --- 엑셀 컬럼 매핑 ---
COLUMN_NAMES = {
    "filing_date": "Filing Date",
    "ticker": "Ticker",
    "company": "Company",
    "insider_name": "Insider Name",
    "insider_title": "Insider Title",
    "transaction_type": "Type",
    "transaction_code": "Code",
    "shares": "Shares",
    "price_per_share": "Price/Share",
    "total_value": "Total Value",
    "shares_owned_after": "Shares After",
    "ownership_type": "Ownership",
    "filing_url": "Filing URL",
}

# --- 거래 코드 ---
TRANSACTION_CODES = {
    "P": "Purchase",
    "S": "Sale",
    "A": "Grant/Award",
    "D": "Disposition (Gift)",
    "F": "Tax Withholding",
    "M": "Option Exercise",
    "C": "Conversion",
    "G": "Gift",
    "J": "Other",
    "K": "Equity Swap",
    "U": "Tender of Shares",
    "W": "Will/Inheritance",
    "X": "Option Exercise (OTM)",
    "Z": "Trust",
}

# --- Request Settings ---
REQUEST_DELAY = 0.15  # SEC rate limit (10 req/sec)
REQUEST_TIMEOUT = 30
