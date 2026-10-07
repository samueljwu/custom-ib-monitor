"""Retrieve IBKR Activity Flex reports for automatic trade sync."""

from datetime import date
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.error import HTTPError, URLError
import time
import xml.etree.ElementTree as ET


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        # Flex authenticates with a token in the URL. Never forward it to a
        # redirect target, even when the target looks like another IBKR host.
        return None


_opener = build_opener(_RejectRedirects)


def fetch_flex(query_id, token, timeout=20, from_day=None, to_day=None):
    """Fetch a saved Flex query; the token is supplied at call time only."""
    if not query_id or not token:
        raise ValueError("Flex query ID and token are required")
    base = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/"
    headers = {"User-Agent": "Python/PortfolioMonitor"}
    params = {"t": token, "q": query_id, "v": 3}
    if (from_day is None) != (to_day is None):
        raise ValueError("Both Flex date bounds are required")
    if from_day is not None:
        first, last = date.fromisoformat(str(from_day)), date.fromisoformat(str(to_day))
        if first > last:
            raise ValueError("Flex start date is after end date")
        params.update({"fd": first.strftime("%Y%m%d"), "td": last.strftime("%Y%m%d")})
    url = base + "SendRequest?" + urlencode(params)
    try:
        with _opener.open(Request(url, headers=headers), timeout=timeout) as response:
            status = ET.fromstring(response.read())
    except (HTTPError, URLError, TimeoutError):
        raise ValueError("Flex service request failed; check the query, token and connection") from None
    if status.findtext("Status") != "Success":
        code = status.findtext("ErrorCode")
        message = status.findtext("ErrorMessage") or "Flex request failed"
        raise ValueError(f"Flex error {code}: {message}" if code else message)
    reference = status.findtext("ReferenceCode")
    if not reference:
        raise ValueError("Flex did not return a reference code")
    url = base + "GetStatement?" + urlencode({"t": token, "q": reference, "v": 3})
    for _ in range(8):
        try:
            with _opener.open(Request(url, headers=headers), timeout=timeout) as response:
                data = response.read(30_000_001)
        except (HTTPError, URLError, TimeoutError):
            raise ValueError("Flex statement download failed; check the query, token and connection") from None
        if len(data) > 30_000_000:
            raise ValueError("Flex report is too large")
        if b"<FlexQueryResponse" in data or b"<FlexStatements" in data:
            return data
        message = ET.fromstring(data).findtext("ErrorMessage") or "Flex statement unavailable"
        if "progress" not in message.lower() and "not ready" not in message.lower():
            raise ValueError(message)
        time.sleep(1)
    raise TimeoutError("Flex statement is still being generated")
