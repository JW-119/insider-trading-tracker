"""Form 4 XML 파싱 모듈."""

from bs4 import BeautifulSoup

import config


def parse_form4_xml(xml_content: str, filing_url: str) -> list[dict]:
    """Form 4 XML을 파싱하여 거래 목록을 반환.

    Args:
        xml_content: Form 4 XML 원문
        filing_url: filing URL (참조용)

    Returns:
        [{"company": ..., "insider_name": ..., "transaction_code": ..., ...}, ...]
    """
    try:
        soup = BeautifulSoup(xml_content, "xml")
    except Exception:
        soup = BeautifulSoup(xml_content, "html.parser")

    trades = []

    # Issuer 정보
    issuer = soup.find("issuer") or soup.find("Issuer")
    company = ""
    issuer_cik = ""
    if issuer:
        name_tag = issuer.find("issuerName") or issuer.find("IssuerName")
        cik_tag = issuer.find("issuerCik") or issuer.find("IssuerCik")
        company = name_tag.text.strip() if name_tag else ""
        issuer_cik = cik_tag.text.strip() if cik_tag else ""

    ticker_tag = None
    if issuer:
        ticker_tag = issuer.find("issuerTradingSymbol") or issuer.find("IssuerTradingSymbol")
    ticker = ticker_tag.text.strip().upper() if ticker_tag else ""

    # Owner 정보
    owner_tag = soup.find("reportingOwner") or soup.find("ReportingOwner")
    insider_name = ""
    insider_title = ""

    if owner_tag:
        # Owner ID
        owner_id = owner_tag.find("reportingOwnerId") or owner_tag.find("ReportingOwnerId")
        if owner_id:
            name_tag = owner_id.find("rptOwnerName") or owner_id.find("RptOwnerName")
            insider_name = name_tag.text.strip() if name_tag else ""

        # Owner Relationship
        rel = owner_tag.find("reportingOwnerRelationship") or owner_tag.find("ReportingOwnerRelationship")
        if rel:
            titles = []
            if _get_bool(rel, "isDirector"):
                titles.append("Director")
            if _get_bool(rel, "isOfficer"):
                officer_title = _get_text(rel, "officerTitle")
                titles.append(officer_title if officer_title else "Officer")
            if _get_bool(rel, "isTenPercentOwner"):
                titles.append("10% Owner")
            if _get_bool(rel, "isOther"):
                other_text = _get_text(rel, "otherText")
                titles.append(other_text if other_text else "Other")
            insider_title = ", ".join(titles)

    # Non-Derivative Transactions
    nd_table = soup.find("nonDerivativeTable") or soup.find("NonDerivativeTable")
    if nd_table:
        transactions = nd_table.find_all("nonDerivativeTransaction") or nd_table.find_all("NonDerivativeTransaction")
        for txn in transactions:
            trade = _parse_transaction(txn, "Non-Derivative")
            trade.update({
                "company": company,
                "ticker": ticker,
                "insider_name": insider_name,
                "insider_title": insider_title,
                "filing_url": filing_url,
            })
            trades.append(trade)

    # Derivative Transactions
    d_table = soup.find("derivativeTable") or soup.find("DerivativeTable")
    if d_table:
        transactions = d_table.find_all("derivativeTransaction") or d_table.find_all("DerivativeTransaction")
        for txn in transactions:
            trade = _parse_transaction(txn, "Derivative")
            trade.update({
                "company": company,
                "ticker": ticker,
                "insider_name": insider_name,
                "insider_title": insider_title,
                "filing_url": filing_url,
            })
            trades.append(trade)

    return trades


def _parse_transaction(txn, security_type: str) -> dict:
    """개별 거래 항목을 파싱."""
    # Transaction code
    coding = txn.find("transactionCoding") or txn.find("TransactionCoding")
    code = ""
    if coding:
        code_tag = coding.find("transactionCode") or coding.find("TransactionCode")
        code = code_tag.text.strip() if code_tag else ""

    # Transaction type (readable)
    txn_type = config.TRANSACTION_CODES.get(code, code)

    # Shares
    amounts = txn.find("transactionAmounts") or txn.find("TransactionAmounts")
    shares = 0.0
    price = 0.0
    acquired_disposed = ""

    if amounts:
        shares_tag = amounts.find("transactionShares") or amounts.find("TransactionShares")
        if shares_tag:
            val = shares_tag.find("value") or shares_tag.find("Value")
            shares = _to_float(val.text if val else "0")

        price_tag = amounts.find("transactionPricePerShare") or amounts.find("TransactionPricePerShare")
        if price_tag:
            val = price_tag.find("value") or price_tag.find("Value")
            price = _to_float(val.text if val else "0")

        ad_tag = amounts.find("transactionAcquiredDisposedCode") or amounts.find("TransactionAcquiredDisposedCode")
        if ad_tag:
            val = ad_tag.find("value") or ad_tag.find("Value")
            acquired_disposed = val.text.strip() if val else ""

    # Shares owned after
    post = txn.find("postTransactionAmounts") or txn.find("PostTransactionAmounts")
    shares_after = 0.0
    if post:
        held = post.find("sharesOwnedFollowingTransaction") or post.find("SharesOwnedFollowingTransaction")
        if held:
            val = held.find("value") or held.find("Value")
            shares_after = _to_float(val.text if val else "0")

    # Ownership type (Direct/Indirect)
    ownership_tag = txn.find("ownershipNature") or txn.find("OwnershipNature")
    ownership = "D"
    if ownership_tag:
        do_tag = ownership_tag.find("directOrIndirectOwnership") or ownership_tag.find("DirectOrIndirectOwnership")
        if do_tag:
            val = do_tag.find("value") or do_tag.find("Value")
            ownership = val.text.strip() if val else "D"

    ownership_display = "Direct" if ownership == "D" else "Indirect"

    # Disposed → 음수 shares
    if acquired_disposed == "D":
        shares = -abs(shares)

    total_value = abs(shares) * price

    return {
        "transaction_code": code,
        "transaction_type": txn_type,
        "shares": shares,
        "price_per_share": price,
        "total_value": total_value,
        "shares_owned_after": shares_after,
        "ownership_type": ownership_display,
    }


def _get_text(parent, tag_name: str) -> str:
    """태그에서 텍스트 추출 (대소문자 폴백)."""
    tag = parent.find(tag_name)
    if not tag:
        # camelCase → PascalCase 시도
        pascal = tag_name[0].upper() + tag_name[1:]
        tag = parent.find(pascal)
    return tag.text.strip() if tag else ""


def _get_bool(parent, tag_name: str) -> bool:
    """불리언 태그 값 확인."""
    text = _get_text(parent, tag_name)
    return text in ("1", "true", "True")


def _to_float(text: str) -> float:
    """문자열을 float로 변환."""
    try:
        return float(text.replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0.0
