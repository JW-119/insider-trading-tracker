#!/usr/bin/env python3
"""Insider Trading Tracker

SEC EDGAR에서 Form 4 (내부자 거래 보고서) 데이터를 수집하여 엑셀 파일로 저장합니다.

Usage:
    python main.py                              # watchlist 모드, 오늘 날짜
    python main.py --tickers AAPL MSFT          # 특정 종목만
    python main.py --mode latest                # 최신 Form 4 전체
    python main.py --date 2026-02-24            # 특정 날짜 지정
"""

import argparse
import os
import sys
from datetime import datetime

import config
from scraper import collect_insider_trades
from excel_writer import save_to_excel


def main():
    parser = argparse.ArgumentParser(description="Insider Trading Tracker")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="파일명에 사용할 날짜 (YYYY-MM-DD). 기본값: 오늘",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["watchlist", "latest"],
        default=None,
        help="수집 모드. 기본값: config.COLLECT_MODE",
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        type=str,
        default=None,
        help="수집할 종목 티커 (예: AAPL MSFT GOOGL)",
    )
    parser.add_argument(
        "--max-filings",
        type=int,
        default=10,
        help="티커당 최대 filing 수. 기본값: 10",
    )
    args = parser.parse_args()

    # 날짜 처리
    if args.date:
        try:
            datetime.strptime(args.date, "%Y-%m-%d")
            date_str = args.date
        except ValueError:
            print(f"[Error] 잘못된 날짜 형식: {args.date} (YYYY-MM-DD 형식 필요)")
            sys.exit(1)
    else:
        date_str = datetime.now().strftime("%Y-%m-%d")

    # 모드 및 티커 설정
    mode = args.mode or config.COLLECT_MODE
    tickers = [t.upper() for t in args.tickers] if args.tickers else None

    # 배너
    print(f"\n{'='*55}")
    print(f"  Insider Trading Tracker")
    print(f"  날짜: {date_str}")
    print(f"  모드: {mode}")
    if tickers:
        print(f"  종목: {', '.join(tickers)}")
    else:
        print(f"  종목: {', '.join(config.WATCHLIST_TICKERS)}")
    print(f"{'='*55}\n")

    # 데이터 수집
    print("[Main] 데이터 수집을 시작합니다...")
    try:
        trades = collect_insider_trades(
            tickers=tickers,
            mode=mode,
            max_filings_per_ticker=args.max_filings,
        )
    except Exception as e:
        print(f"[Error] 데이터 수집 실패: {e}")
        sys.exit(1)

    if not trades:
        print("[Main] 수집된 거래 데이터가 없습니다.")
        sys.exit(0)

    print(f"[Main] 총 {len(trades)}건의 거래 데이터 수집 완료")

    # 엑셀 저장
    file_name = f"insider-trades-{date_str}.xlsx"
    file_path = os.path.join(config.DATA_DIR, file_name)

    try:
        save_to_excel(trades, file_path, "SEC Form 4 Insider Trades", date_str)
    except Exception as e:
        print(f"[Error] 엑셀 저장 실패: {e}")
        sys.exit(1)

    print(f"\n{'='*55}")
    print(f"  완료! 파일: {file_path}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
