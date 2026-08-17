"""Test de _request_with_retry (dashboard_refresh_modal.py) -- bug real 2026-08-17:
un 503 puntual de GitHub tumbo el refresh diario sin ningun reintento. Sin
dependencias externas (solo stdlib unittest + mock). Correr con:
    python -m unittest test_request_with_retry.py -v
"""
import unittest
from unittest.mock import MagicMock, patch

import requests

import dashboard_refresh_modal as mod


def _http_error(status):
    resp = MagicMock()
    resp.status_code = status
    return requests.exceptions.HTTPError(response=resp)


class RequestWithRetryTests(unittest.TestCase):

    def test_succeeds_first_try_without_sleeping(self):
        fn = MagicMock(return_value="ok")
        with patch("time.sleep") as mock_sleep:
            result = mod._request_with_retry(fn)
        self.assertEqual(result, "ok")
        fn.assert_called_once()
        mock_sleep.assert_not_called()

    def test_retries_on_503_then_succeeds(self):
        fn = MagicMock(side_effect=[_http_error(503), "ok"])
        with patch("time.sleep") as mock_sleep:
            result = mod._request_with_retry(fn)
        self.assertEqual(result, "ok")
        self.assertEqual(fn.call_count, 2)
        mock_sleep.assert_called_once_with(2)

    def test_retries_on_timeout_and_connection_error(self):
        fn = MagicMock(side_effect=[
            requests.exceptions.Timeout(),
            requests.exceptions.ConnectionError(),
            "ok",
        ])
        with patch("time.sleep"):
            result = mod._request_with_retry(fn)
        self.assertEqual(result, "ok")
        self.assertEqual(fn.call_count, 3)

    def test_does_not_retry_on_4xx(self):
        # Un 404/401/403 es un error real -- reintentarlo es un fallo mas lento, no
        # una recuperacion. Debe propagar en el primer intento.
        fn = MagicMock(side_effect=_http_error(404))
        with patch("time.sleep") as mock_sleep:
            with self.assertRaises(requests.exceptions.HTTPError):
                mod._request_with_retry(fn)
        fn.assert_called_once()
        mock_sleep.assert_not_called()

    def test_raises_after_exhausting_all_attempts(self):
        fn = MagicMock(side_effect=_http_error(503))
        with patch("time.sleep") as mock_sleep:
            with self.assertRaises(requests.exceptions.HTTPError):
                mod._request_with_retry(fn, attempts=3, base_delay=2)
        self.assertEqual(fn.call_count, 3)
        mock_sleep.assert_any_call(2)
        mock_sleep.assert_any_call(4)


if __name__ == "__main__":
    unittest.main()
