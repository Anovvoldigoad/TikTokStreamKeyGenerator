import unittest
from Libs.cookie_payload import normalize_cookie_entries


class CookieImportContractTests(unittest.TestCase):
    def test_flat_export(self):
        exported = [{"name": "sessionid", "value": "token"}, {"name": "msToken", "value": "valid"}]
        self.assertEqual(normalize_cookie_entries(exported), exported)

    def test_wrapped_exports_match_flat_stream_session(self):
        cookies = [{"name": "sid_tt", "value": "secret", "expirationDate": 1750000000}]
        for wrapper in ("cookies", "Cookie"):
            with self.subTest(wrapper=wrapper):
                entries = normalize_cookie_entries({wrapper: cookies})
                self.assertEqual(entries[0]["name"], "sid_tt")
                self.assertEqual(entries[0]["value"], "secret")
                self.assertEqual(entries[0]["expires"], 1750000000)

    def test_single_cookie_export(self):
        self.assertEqual(normalize_cookie_entries({"name": "sessionid", "value": "x"})[0]["value"], "x")

    def test_no_cookie_values_rejected(self):
        for invalid in ({}, [], [{"name": "cookie"}], {"cookies": "not a list"}):
            with self.subTest(invalid=invalid), self.assertRaises(RuntimeError):
                normalize_cookie_entries(invalid)

    def test_not_permit_malformed_entries(self):
        with self.assertRaisesRegex(RuntimeError, "not an object"):
            normalize_cookie_entries([{"name": "sessionid", "value": "ok"}, "garbage"])


if __name__ == "__main__":
    unittest.main()
