"""Insider Trading Tracker — Streamlit 대시보드.

Usage:
    streamlit run dashboard.py
"""

import os
import glob
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

import config


def _format_metric(value: float) -> str:
    """지표 표시용 포맷."""
    if abs(value) >= 1e9:
        return f"${value / 1e9:.2f}B"
    if abs(value) >= 1e6:
        return f"${value / 1e6:.2f}M"
    if abs(value) >= 1e3:
        return f"${value / 1e3:.1f}K"
    return f"${value:,.0f}"


# --- 페이지 설정 ---
st.set_page_config(
    page_title="Insider Trading Tracker",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Insider Trading Tracker")
st.caption("SEC Form 4 내부자 거래 데이터 대시보드")


# --- 실시간 데이터 수집 ---
@st.cache_data(ttl=3600, show_spinner=False)
def load_data_by_date(start_date: str, end_date: str, max_filings: int) -> pd.DataFrame:
    """SEC EDGAR에서 날짜 범위의 모든 Form 4 데이터를 수집."""
    from scraper import collect_all_form4_by_date

    raw_trades = collect_all_form4_by_date(
        start_date=start_date,
        end_date=end_date,
        max_filings=max_filings,
    )

    if not raw_trades:
        return pd.DataFrame()

    df = pd.DataFrame(raw_trades)

    # 컬럼명을 COLUMN_NAMES의 key 형식으로 통일
    for col in config.COLUMN_NAMES:
        if col not in df.columns:
            df[col] = ""

    return df


# --- 로컬 데이터 로드 (엑셀 파일이 있는 경우) ---
@st.cache_data
def load_data_local() -> pd.DataFrame:
    """data/ 폴더의 모든 엑셀 파일을 로드하여 병합."""
    pattern = os.path.join(config.DATA_DIR, "insider-trades-*.xlsx")
    files = sorted(glob.glob(pattern), reverse=True)

    if not files:
        return pd.DataFrame()

    frames = []
    for f in files:
        try:
            xl = pd.ExcelFile(f)
            for sheet in xl.sheet_names:
                df = pd.read_excel(f, sheet_name=sheet, header=1)
                frames.append(df)
        except Exception as e:
            st.warning(f"파일 로드 실패: {os.path.basename(f)} — {e}")

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


# --- 사이드바: 데이터 수집 설정 ---
st.sidebar.header("⚙️ 데이터 수집")

# 로컬 엑셀 파일 존재 여부 확인
has_local_data = len(glob.glob(os.path.join(config.DATA_DIR, "insider-trades-*.xlsx"))) > 0

if has_local_data:
    data_source = st.sidebar.radio(
        "데이터 소스",
        ["SEC EDGAR 실시간 수집", "로컬 Excel 파일"],
        index=0,
    )
else:
    data_source = "SEC EDGAR 실시간 수집"

if data_source == "SEC EDGAR 실시간 수집":
    # 날짜 범위 선택
    today = date.today()
    # 주말이면 가장 최근 영업일로 기본값 설정
    default_end = today
    if today.weekday() == 5:  # 토요일
        default_end = today - timedelta(days=1)
    elif today.weekday() == 6:  # 일요일
        default_end = today - timedelta(days=2)

    default_start = default_end - timedelta(days=4)  # 최근 5일

    col_start, col_end = st.sidebar.columns(2)
    with col_start:
        start_dt = st.date_input("시작일", value=default_start)
    with col_end:
        end_dt = st.date_input("종료일", value=default_end)

    max_filings = st.sidebar.slider(
        "최대 Filing 수",
        min_value=50,
        max_value=500,
        value=200,
        step=50,
        help="하루 평균 500~1300건의 Form 4가 있습니다",
    )

    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = end_dt.strftime("%Y-%m-%d")

    with st.spinner(f"SEC EDGAR에서 {start_str} ~ {end_str} 데이터를 수집 중..."):
        df = load_data_by_date(start_str, end_str, max_filings)

    if df.empty:
        st.warning("해당 기간에 Form 4 데이터가 없습니다. 날짜를 확인하세요 (주말/공휴일 제외).")
        st.stop()
else:
    df = load_data_local()
    if df.empty:
        st.warning("데이터가 없습니다. `python main.py`를 실행하여 데이터를 먼저 수집하세요.")
        st.stop()

# --- 데이터 전처리 ---
# 컬럼명 정규화 (엑셀에서 읽어온 표시명 → 원래 키)
reverse_col = {v: k for k, v in config.COLUMN_NAMES.items()}
df = df.rename(columns=reverse_col)

# 숫자 변환
for col in ["shares", "price_per_share", "shares_owned_after"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

# total_value 재계산
if "total_value" in df.columns:
    df["total_value"] = df["shares"].abs() * df["price_per_share"]

# filing_date를 datetime으로 변환
if "filing_date" in df.columns:
    df["filing_date"] = pd.to_datetime(df["filing_date"], errors="coerce")

# 날짜 내림차순 → 거래금액 내림차순 정렬
sort_cols = []
sort_asc = []
if "filing_date" in df.columns:
    sort_cols.append("filing_date")
    sort_asc.append(False)
if "total_value" in df.columns:
    sort_cols.append("total_value")
    sort_asc.append(False)
if sort_cols:
    df = df.sort_values(sort_cols, ascending=sort_asc, na_position="last").reset_index(drop=True)

# --- 사이드바 필터 ---
st.sidebar.header("🔍 필터")

# 티커 필터
if "ticker" in df.columns:
    tickers = sorted(df["ticker"].dropna().unique())
    selected_tickers = st.sidebar.multiselect("종목 (Ticker)", tickers, default=[])
    if selected_tickers:
        df = df[df["ticker"].isin(selected_tickers)]

# 거래 유형 필터
if "transaction_code" in df.columns:
    codes = sorted(df["transaction_code"].dropna().unique())
    selected_codes = st.sidebar.multiselect(
        "거래 유형", codes, default=[],
        format_func=lambda c: f"{c} — {config.TRANSACTION_CODES.get(c, c)}",
    )
    if selected_codes:
        df = df[df["transaction_code"].isin(selected_codes)]

# 최소 금액 필터
if "total_value" in df.columns:
    min_value = st.sidebar.number_input(
        "최소 거래 금액 ($)",
        min_value=0,
        value=0,
        step=10000,
    )
    if min_value > 0:
        df = df[df["total_value"] >= min_value]

# --- 요약 지표 ---
st.markdown("---")
col1, col2, col3, col4 = st.columns(4)

total_trades = len(df)
col1.metric("총 거래 건수", f"{total_trades:,}")

if "transaction_code" in df.columns and "total_value" in df.columns:
    purchases = df[df["transaction_code"] == "P"]
    sales = df[df["transaction_code"] == "S"]

    purchase_value = purchases["total_value"].sum()
    sale_value = sales["total_value"].sum()

    col2.metric("매수 금액", _format_metric(purchase_value))
    col3.metric("매도 금액", _format_metric(sale_value))
    col4.metric("순매수 금액", _format_metric(purchase_value - sale_value))

st.markdown("---")

# --- 거래 테이블 ---
st.subheader("📋 거래 내역")

# 표시용 컬럼명으로 변환
display_df = df.copy()
display_df = display_df.rename(columns=config.COLUMN_NAMES)

# Total Value 포맷팅
if "Total Value" in display_df.columns:
    display_df["Total Value"] = display_df["Total Value"].apply(
        lambda v: f"${v:,.0f}" if pd.notna(v) and isinstance(v, (int, float)) else ""
    )

# Price/Share 포맷팅
if "Price/Share" in display_df.columns:
    display_df["Price/Share"] = display_df["Price/Share"].apply(
        lambda v: f"${v:,.2f}" if pd.notna(v) and isinstance(v, (int, float)) else ""
    )

# Shares 포맷팅
if "Shares" in display_df.columns:
    display_df["Shares"] = display_df["Shares"].apply(
        lambda v: f"{v:,.0f}" if pd.notna(v) and isinstance(v, (int, float)) else ""
    )

# Filing URL 제거 (테이블에서 너무 길어서)
display_cols = [c for c in display_df.columns if c != "Filing URL"]
st.dataframe(display_df[display_cols], use_container_width=True, height=400)

# --- 차트 ---
st.markdown("---")

chart_col1, chart_col2 = st.columns(2)

# 일별 거래금액 추이
with chart_col1:
    st.subheader("📈 일별 거래금액 추이")
    if "filing_date" in df.columns and "total_value" in df.columns:
        daily = df.groupby([df["filing_date"].dt.date, "transaction_code"])["total_value"].sum().reset_index()
        daily.columns = ["date", "code", "value"]
        daily["type"] = daily["code"].map(config.TRANSACTION_CODES)

        fig = px.bar(
            daily,
            x="date",
            y="value",
            color="type",
            barmode="group",
            labels={"date": "날짜", "value": "거래금액 ($)", "type": "거래유형"},
        )
        fig.update_layout(height=400, margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig, use_container_width=True)

# 종목별 Top 10
with chart_col2:
    st.subheader("🏆 종목별 거래금액 Top 10")
    if "ticker" in df.columns and "total_value" in df.columns:
        top10 = df.groupby("ticker")["total_value"].sum().nlargest(10).reset_index()
        top10.columns = ["ticker", "value"]

        fig = px.bar(
            top10,
            x="value",
            y="ticker",
            orientation="h",
            labels={"value": "거래금액 ($)", "ticker": "종목"},
        )
        fig.update_layout(height=400, margin=dict(l=20, r=20, t=20, b=20), yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)

# 거래유형 파이차트
st.subheader("🍩 거래유형 분포")
if "transaction_code" in df.columns:
    pie_data = df["transaction_code"].value_counts().reset_index()
    pie_data.columns = ["code", "count"]
    pie_data["type"] = pie_data["code"].map(config.TRANSACTION_CODES)

    fig = px.pie(
        pie_data,
        values="count",
        names="type",
        hole=0.4,
    )
    fig.update_layout(height=400, margin=dict(l=20, r=20, t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)
