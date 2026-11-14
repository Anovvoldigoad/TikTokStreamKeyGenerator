"""Hosted signing HTTP transport.

Use curl_cffi on desktop exactly as before. Android Python distributions
without a curl_cffi wheel use standard requests for the *hosted signer* only.
This does not replace TikTok's separate device/header signing requirements.
"""
try:
    from curl_cffi import requests
except ImportError:
    import requests as _requests

    class _RequestsAdapter:
        exceptions = _requests.exceptions

        @staticmethod
        def post(*args, impersonate=None, **kwargs):
            # 'impersonate' is a curl_cffi-only argument.
            return _requests.post(*args, **kwargs)

    requests = _RequestsAdapter()
