"""A stand-in for net.fetch: canned answers chosen by URL or body, every call and sleep recorded."""
import json
import os
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from resources.lib import net

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(name):
    with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as f:
        return f.read()


def fixture_json(name):
    return json.loads(fixture(name))


def no_log(msg, error=False):
    pass


class FakeNet:
    def __init__(self):
        self.routes = []
        self.calls = []
        self.sleeps = []

    def route(self, match, payload, status=200, headers=None, once=False):
        """Answer requests whose URL contains match (or for which match(method, url, body) is true)."""
        self.routes.append([match, payload, status, headers or {}, once])
        return self

    def __call__(self, method, url, body, headers, timeout):
        text = body.decode("utf-8") if isinstance(body, bytes) else (body or "")
        self.calls.append((method, url, text, headers))
        for route in list(self.routes):
            match, payload, status, hdrs, once = route
            hit = match(method, url, text) if callable(match) else match in url
            if not hit:
                continue
            if once:
                self.routes.remove(route)
            if isinstance(payload, bytes):
                data = payload
            elif isinstance(payload, str):
                data = payload.encode("utf-8")
            else:
                data = json.dumps(payload).encode("utf-8")
            return status, dict(hdrs), data
        raise AssertionError("unexpected request {} {}".format(method, url))

    def install(self, testcase):
        for patch in (mock.patch.object(net, "fetch", self), mock.patch.object(net, "sleep", self.sleeps.append)):
            patch.start()
            testcase.addCleanup(patch.stop)
        net._last_call.clear()
        return self

    def urls(self, fragment=""):
        return [call[1] for call in self.calls if fragment in call[1]]

    def bodies(self, fragment=""):
        return [call[2] for call in self.calls if fragment in call[1]]

    def query(self, fragment=""):
        """The query parameters of the last request whose URL contains fragment."""
        url = self.urls(fragment)[-1]
        return {k: v[0] for k, v in parse_qs(urlsplit(url).query, keep_blank_values=True).items()}

    def headers(self, fragment=""):
        return [call[3] for call in self.calls if fragment in call[1]][-1]
