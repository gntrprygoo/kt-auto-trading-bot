import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("kt_bot_profit_test", ROOT / "v3_swing_bot_fixed.py")
BOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BOT)


class ProfitProtectionTests(unittest.TestCase):
    def setUp(self):
        self.originals = {
            "binance_get": BOT.binance_get,
            "binance_post": BOT.binance_post,
            "binance_delete": BOT.binance_delete,
            "save_json_atomic": BOT.save_json_atomic,
            "send_telegram": BOT.send_telegram,
            "log_line": BOT.log_line,
            "journal": BOT.journal,
            "filters": BOT.SYMBOL_FILTERS_CACHE,
        }
        self.posts = []
        self.deletes = []
        self.notifications = []
        self.position = {"symbol": "TESTUSDT", "positionAmt": "10", "markPrice": "100"}

        BOT.binance_get = lambda *_args, **_kwargs: [dict(self.position)]

        def fake_post(path, payload, *_args, **_kwargs):
            self.posts.append((path, dict(payload)))
            return {"algoId": 9000 + len(self.posts)}

        BOT.binance_post = fake_post
        BOT.binance_delete = lambda path, payload, *_args, **_kwargs: self.deletes.append((path, dict(payload))) or {}
        BOT.save_json_atomic = lambda *_args, **_kwargs: None
        BOT.send_telegram = lambda text: self.notifications.append(text)
        BOT.log_line = lambda *_args, **_kwargs: None
        BOT.SYMBOL_FILTERS_CACHE = {"TESTUSDT": ("0.001", "0.1", 3, 1)}

    def tearDown(self):
        BOT.binance_get = self.originals["binance_get"]
        BOT.binance_post = self.originals["binance_post"]
        BOT.binance_delete = self.originals["binance_delete"]
        BOT.save_json_atomic = self.originals["save_json_atomic"]
        BOT.send_telegram = self.originals["send_telegram"]
        BOT.log_line = self.originals["log_line"]
        BOT.journal = self.originals["journal"]
        BOT.SYMBOL_FILTERS_CACHE = self.originals["filters"]

    @staticmethod
    def trade():
        return {
            "pair": "TESTUSDT",
            "side": "LONG",
            "entry": 100.0,
            "qty": 10.0,
            "status": "OPEN",
            "sl": 98.0,
            "sl_order_id": 101,
            "tp2_order_id": 202,
            "tp2_price_str": "104.0",
            "tp1_hit": False,
            "be_sl_set": False,
            "sl_plus_set": False,
        }

    def test_price_format_is_side_aware(self):
        self.assertEqual(BOT._sl_plus_price_str(100.0, "LONG", "0.1"), "101.0")
        self.assertEqual(BOT._sl_plus_price_str(100.0, "SHORT", "0.1"), "99.0")

    def test_running_profit_below_1_5_percent_does_nothing(self):
        trade = self.trade()
        BOT.journal = [trade]
        self.position["markPrice"] = "101.49"
        BOT._check_profit_sl_plus(trade, "key", "secret")
        self.assertEqual(self.posts, [])
        self.assertEqual(self.deletes, [])
        self.assertFalse(trade["sl_plus_set"])

    def test_running_profit_1_5_percent_locks_1_percent(self):
        trade = self.trade()
        BOT.journal = [trade]
        self.position["markPrice"] = "101.50"
        BOT._check_profit_sl_plus(trade, "key", "secret")
        self.assertEqual(len(self.posts), 1)
        payload = self.posts[0][1]
        self.assertEqual(payload["type"], "STOP_MARKET")
        self.assertEqual(payload["triggerPrice"], "101.0")
        self.assertEqual(payload["closePosition"], "true")
        self.assertTrue(trade["sl_plus_set"])
        self.assertEqual(trade["sl_plus_lock_pct"], 0.01)
        self.assertEqual(trade["be_trigger"], "profit_1_5pct_sl_plus")

    def test_tp1_waits_until_plus_1_percent_is_valid(self):
        trade = self.trade()
        BOT.journal = [trade]
        self.position.update({"positionAmt": "5", "markPrice": "100.80"})
        BOT._check_tp1_hit(trade, "key", "secret")
        self.assertEqual(self.posts, [])
        self.assertEqual(self.deletes, [])
        self.assertFalse(trade["tp1_hit"])
        self.assertFalse(trade["sl_plus_set"])

    def test_tp1_waits_when_mark_equals_sl_plus_level(self):
        trade = self.trade()
        BOT.journal = [trade]
        self.position.update({"positionAmt": "5", "markPrice": "101.00"})
        BOT._check_tp1_hit(trade, "key", "secret")
        self.assertEqual(self.posts, [])
        self.assertEqual(self.deletes, [])
        self.assertFalse(trade["sl_plus_set"])

    def test_tp1_moves_sl_to_plus_1_percent_and_keeps_tp2(self):
        trade = self.trade()
        BOT.journal = [trade]
        self.position.update({"positionAmt": "5", "markPrice": "101.20"})
        BOT._check_tp1_hit(trade, "key", "secret")
        self.assertEqual(len(self.posts), 2)
        stop_payload = self.posts[0][1]
        tp2_payload = self.posts[1][1]
        self.assertEqual(stop_payload["triggerPrice"], "101.0")
        self.assertEqual(stop_payload["quantity"], "5.0")
        self.assertEqual(tp2_payload["type"], "TAKE_PROFIT_MARKET")
        self.assertEqual(tp2_payload["triggerPrice"], "104.0")
        self.assertTrue(trade["tp1_hit"])
        self.assertTrue(trade["sl_plus_set"])
        self.assertEqual(trade["be_trigger"], "tp1_sl_plus")
        self.assertEqual(trade["sl_plus_price"], 101.0)


if __name__ == "__main__":
    unittest.main()
