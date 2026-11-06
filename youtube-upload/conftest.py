import googleapiclient.http as h
_orig = h.HttpMockSequence.request
calls = []
def rec(self, uri, method="GET", body=None, headers=None, *a, **k):
    calls.append((method, uri, body))
    return _orig(self, uri, method, body, headers, *a, **k)
h.HttpMockSequence.request = rec
