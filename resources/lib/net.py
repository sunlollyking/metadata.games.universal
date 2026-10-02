"""HTTP for the online providers: timeouts, pacing, throttling retries and credential-free logging.

fetch() is the only function that touches the network; tests replace it with
canned answers. request() paces calls per host, retries once when the host
says it is throttled and raises Error for any other failure. Log lines drop
a query string that carries a credential.
"""
import http.client
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

USER_AGENT = "Kodi game scraper"
TIMEOUT = 30
THROTTLED = (429,)
RETRY_AFTER = 2.0
SECRET_KEYS = frozenset(("y", "apikey", "devid", "devpassword", "ssid", "sspassword",
                         "client_id", "client_secret", "access_token"))
Log = Callable[[str, bool], None]
sleep = time.sleep
_last_call: Dict[str, float] = {}


class Error(Exception):
    """No usable answer: a transport failure or an HTTP error status."""

    def __init__(self, url: str, status: int = 0, body: str = "", reason: str = ""):
        super().__init__(url)
        self.url = safe_url(url)
        self.status = status
        self.body = body
        self.reason = reason

    def __str__(self) -> str:
        what = "HTTP {}".format(self.status) if self.status else (self.reason or "no answer")
        detail = " ".join(self.body.split())[:200]
        return "{} from {}{}".format(what, self.url, ": " + detail if detail else "")


class Response:
    def __init__(self, status: int, headers: Dict[str, str], body: bytes):
        self.status = status
        self.headers = headers
        self.body = body

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", "replace")

    def json(self) -> Any:
        return json.loads(self.text)


def safe_url(url: str) -> str:
    """The URL without its query string when any parameter is a credential."""
    parts = urllib.parse.urlsplit(url)
    keys = {k.lower() for k, _ in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)}
    if keys & SECRET_KEYS:
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    return url


def fetch(method: str, url: str, body: Optional[bytes], headers: Dict[str, str],
          timeout: float) -> Tuple[int, Dict[str, str], bytes]:
    """One HTTP exchange. Error statuses are returned like any other; transport failures raise Error."""
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
    except urllib.error.HTTPError as err:
        try:
            payload = err.read()
        except Exception:
            payload = b""
        return err.code, {k.lower(): v for k, v in (err.headers or {}).items()}, payload
    except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as err:
        raise Error(url, reason=str(getattr(err, "reason", None) or err))


def request(method: str, url: str, params: Optional[Dict[str, Any]] = None, data: Any = None,
            headers: Optional[Dict[str, str]] = None, log: Optional[Log] = None, min_interval: float = 0.0,
            throttled: Sequence[int] = THROTTLED, retry_after: float = RETRY_AFTER) -> Response:
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    body = data.encode("utf-8") if isinstance(data, str) else data
    head = {"User-Agent": USER_AGENT}
    head.update(headers or {})
    host = urllib.parse.urlsplit(url).netloc
    for attempt in (1, 2):
        _pace(host, min_interval)
        status, resp_headers, payload = fetch(method, url, body, head, TIMEOUT)
        if status not in throttled or attempt == 2:
            break
        wait = _retry_after(resp_headers, retry_after)
        if log:
            log("{} throttled {} ({}); retrying in {:.0f}s".format(host, safe_url(url), status, wait), False)
        sleep(wait)
    if log:
        log("{} {} -> {}".format(method, safe_url(url), status), False)
    if status >= 400:
        raise Error(url, status, payload.decode("utf-8", "replace"))
    return Response(status, resp_headers, payload)


def get(url: str, params: Optional[Dict[str, Any]] = None, **kw: Any) -> Response:
    return request("GET", url, params, None, **kw)


def post(url: str, data: Any = None, params: Optional[Dict[str, Any]] = None, **kw: Any) -> Response:
    return request("POST", url, params, data if data is not None else b"", **kw)


def get_json(url: str, params: Optional[Dict[str, Any]] = None, **kw: Any) -> Any:
    return get(url, params, **kw).json()


def get_text(url: str, params: Optional[Dict[str, Any]] = None, **kw: Any) -> str:
    return get(url, params, **kw).text


def post_json(url: str, data: Any = None, params: Optional[Dict[str, Any]] = None, **kw: Any) -> Any:
    return post(url, data, params, **kw).json()


def _pace(host: str, min_interval: float) -> None:
    if min_interval > 0:
        wait = _last_call.get(host, 0.0) + min_interval - time.time()
        if wait > 0:
            sleep(wait)
    _last_call[host] = time.time()


def _retry_after(headers: Dict[str, str], default: float) -> float:
    try:
        return max(float(headers.get("retry-after", "")), 0.0)
    except ValueError:
        return default
