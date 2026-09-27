"""Carry-forward rule: 'unchanged' / partial notices use the previous month's rates for what they omit."""

import unittest

from merolagani_notices.history import resolve

NS = "Not specified"


def rec(**kw):
    base = {"symbol": "X", "bank": "X Bank", "sector": "Commercial Banks", "saving_rates": [2.75, 3.25],
            "call": "Up to 1.375%", "ind_lt1": 2.90, "ind_1y": 3.00, "ind_gt1": 4.00,
            "inst_lt1": 2.75, "inst_1y": 2.76, "inst_gt1": 3.50, "notes": []}
    base.update(kw)
    return base


class CarryForwardTests(unittest.TestCase):
    def test_unchanged_notice_uses_previous_month(self):
        months = {"2083-04": rec(),
                  "2083-05": rec(unchanged=True, saving_rates=[], call=NS, ind_lt1=NS, ind_1y=NS, ind_gt1=NS,
                                 inst_lt1=NS, inst_1y=NS, inst_gt1=NS)}
        r = resolve(months, "2083-05")
        self.assertEqual((r["call"], r["ind_1y"], r["inst_gt1"], r["saving_rates"]),
                         ("Up to 1.375%", 3.00, 3.50, [2.75, 3.25]))
        self.assertIn("carried forward from Shrawan 2083", r["notes"][-1])

    def test_partial_notice_keeps_new_rates_and_fills_the_rest(self):
        months = {"2083-04": rec(),
                  "2083-05": rec(partial=True, ind_1y=3.20, call=NS, saving_rates=[], inst_gt1=NS)}
        r = resolve(months, "2083-05")
        self.assertEqual(r["ind_1y"], 3.20)            # new rate from the partial notice
        self.assertEqual(r["call"], "Up to 1.375%")    # carried forward
        self.assertEqual(r["inst_gt1"], 3.50)

    def test_chain_of_notices(self):
        # Ashwin partial -> Bhadra unchanged -> Shrawan full (Himalayan Bank case)
        months = {"2083-04": rec(),
                  "2083-05": rec(unchanged=True, call=NS, ind_1y=NS, saving_rates=[]),
                  "2083-06": rec(partial=True, call=NS, ind_1y=NS, saving_rates=[])}
        r = resolve(months, "2083-06")
        self.assertEqual((r["call"], r["ind_1y"], r["saving_rates"]), ("Up to 1.375%", 3.00, [2.75, 3.25]))

    def test_saving_products_merge_by_name(self):
        months = {"2083-04": rec(partial=True, saving_products={"Remit": 4.00, "Bima": 2.85, "Super": 3.00},
                                 saving_rates=[4.00, 2.85, 3.00]),
                  "2083-05": rec(partial=True, saving_products={"Bima": 2.75}, saving_rates=[2.75])}
        r = resolve(months, "2083-05")
        self.assertEqual(r["saving_products"], {"Remit": 4.00, "Bima": 2.75, "Super": 3.00})
        self.assertEqual(sorted(r["saving_rates"]), [2.75, 3.00, 4.00])

    def test_full_notice_not_filled(self):
        # a normal full notice keeps "Not specified" (e.g. no 3-month institutional FD offered)
        months = {"2083-04": rec(), "2083-05": rec(inst_lt1=NS)}
        self.assertEqual(resolve(months, "2083-05")["inst_lt1"], NS)

    def test_no_notice_this_month_uses_latest(self):
        months = {"2083-04": rec(ind_1y=3.10)}
        self.assertEqual(resolve(months, "2083-06")["ind_1y"], 3.10)


if __name__ == "__main__":
    unittest.main()
