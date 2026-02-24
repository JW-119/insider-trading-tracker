"""SEC EDGAR Form 4 데이터 수집 모듈."""

import json
import os
import time

import requests

import config


def _get_session() -> requests.Session:
    """SEC EDGAR 요청용 세션 반환."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": config.SEC_USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
    })
    return session


def fetch_ticker_to_cik_map() -> dict[str, str]:
    """SEC company_tickers.json에서 ticker→CIK 매핑을 로드 (캐싱).

    Returns:
        {"AAPL": "0000320193", ...}
    """
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(config.CACHE_DIR, "company_tickers.json")

    # 캐시가 1일 이내이면 재사용
    if os.path.exists(cache_path):
        age = time.time() - os.path.getmtime(cache_path)
        if age < 86400:
            print("[Scraper] CIK 매핑 캐시 사용")
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)

    print("[Scraper] CIK 매핑 다운로드 중...")
    session = _get_session()
    resp = session.get(config.SEC_TICKERS_URL, timeout=config.REQUEST_TIMEOUT)
    resp.raise_for_status()

    raw = resp.json()
    mapping = {}
    for entry in raw.values():
        ticker = entry["ticker"].upper()
        cik = str(entry["cik_str"]).zfill(10)
        mapping[ticker] = cik

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(mapping, f)

    print(f"[Scraper] CIK 매핑 완료: {len(mapping)}개 종목")
    return mapping


def fetch_form4_filings_for_cik(session: requests.Session, cik: str, ticker: str) -> list[dict]:
    """특정 CIK의 최근 Form 4 filing 목록을 수집.

    Returns:
        [{"accessionNumber": "...", "filingDate": "...", "primaryDocument": "..."}, ...]
    """
    url = config.SEC_SUBMISSIONS_URL.format(cik=cik)
    resp = session.get(url, timeout=config.REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    filings = data.get("filings", {}).get("recent", {})
    forms = filings.get("form", [])
    accessions = filings.get("accessionNumber", [])
    dates = filings.get("filingDate", [])
    documents = filings.get("primaryDocument", [])

    results = []
    for i, form in enumerate(forms):
        if form == "4":
            acc_no = accessions[i].replace("-", "")
            doc = documents[i]
            filing_url = f"{config.SEC_FILING_BASE}/{cik}/{acc_no}/{doc}"
            results.append({
                "accessionNumber": accessions[i],
                "filingDate": dates[i],
                "primaryDocument": doc,
                "url": filing_url,
                "ticker": ticker,
            })

    return results


def fetch_form4_xml(session: requests.Session, url: str) -> str | None:
    """Form 4 XML 원문을 다운로드.

    Returns:
        XML 문자열 또는 None (실패 시)
    """
    try:
        resp = session.get(url, timeout=config.REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        print(f"[Scraper] XML 다운로드 실패: {url} — {e}")
        return None


def collect_insider_trades(
    tickers: list[str] | None = None,
    mode: str | None = None,
    max_filings_per_ticker: int = 10,
) -> list[dict]:
    """내부자 거래 데이터를 수집.

    Args:
        tickers: 수집할 티커 목록 (None이면 config에서 로드)
        mode: "watchlist" 또는 "latest"
        max_filings_per_ticker: 티커당 최대 filing 수

    Returns:
        [{"url": ..., "xml": ..., "ticker": ..., "filingDate": ...}, ...]
    """
    from parser import parse_form4_xml

    if mode is None:
        mode = config.COLLECT_MODE

    if tickers is None:
        tickers = config.WATCHLIST_TICKERS

    session = _get_session()

    # CIK 매핑 로드
    cik_map = fetch_ticker_to_cik_map()

    all_trades = []

    if mode == "watchlist":
        print(f"[Scraper] Watchlist 모드: {len(tickers)}개 종목 수집")

        for ticker in tickers:
            ticker = ticker.upper()
            cik = cik_map.get(ticker)
            if not cik:
                print(f"[Scraper] {ticker} — CIK를 찾을 수 없습니다. 건너뜀.")
                continue

            print(f"[Scraper] {ticker} (CIK: {cik}) — Form 4 수집 중...")
            time.sleep(config.REQUEST_DELAY)

            try:
                filings = fetch_form4_filings_for_cik(session, cik, ticker)
            except requests.RequestException as e:
                print(f"[Scraper] {ticker} — filing 목록 수집 실패: {e}")
                continue

            filings = filings[:max_filings_per_ticker]
            print(f"[Scraper] {ticker} — {len(filings)}개 Form 4 발견")

            for filing in filings:
                time.sleep(config.REQUEST_DELAY)
                xml = fetch_form4_xml(session, filing["url"])
                if xml is None:
                    continue

                trades = parse_form4_xml(xml, filing["url"])
                for trade in trades:
                    trade["ticker"] = ticker
                    trade["filing_date"] = filing["filingDate"]
                all_trades.extend(trades)

    elif mode == "latest":
        print("[Scraper] Latest 모드: 최신 Form 4 전체 수집")
        # EFTS full-text search API로 최신 Form 4 수집
        from datetime import datetime, timedelta

        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        search_url = (
            f"https://efts.sec.gov/LATEST/search-index?"
            f"q=%224%22&forms=4&dateRange=custom"
            f"&startdt={start_date}&enddt={end_date}"
        )

        try:
            resp = session.get(search_url, timeout=config.REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            hits = data.get("hits", {}).get("hits", [])
            print(f"[Scraper] Latest 모드: {len(hits)}개 Form 4 발견")

            for hit in hits[:50]:  # 최대 50개
                source = hit.get("_source", {})
                file_num = source.get("file_num", "")
                # latest 모드에서는 개별 XML URL 구성이 복잡하므로 건너뜀
        except requests.RequestException as e:
            print(f"[Scraper] Latest 모드 검색 실패: {e}")
            print("[Scraper] Watchlist 모드로 전환합니다.")
            return collect_insider_trades(tickers=tickers, mode="watchlist")

    print(f"[Scraper] 총 {len(all_trades)}건의 거래 데이터 수집 완료")
    return all_trades
