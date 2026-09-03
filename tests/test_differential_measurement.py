"""ed3c/noodles#406 - the two non-obvious axes of the provider differential, and their controls.

Four of the canary's six axes are direct readings (tokens, wall-clock, filter pass rate, correlated
miss). Two are computed, and both compute a number that is easy to report and easy to get backwards:

* `confirmed_rate` - monitor findings as confirmed/total. Raw finding COUNT rewards a noisy reviewer:
  a monitor that files ten findings of which one survives verification outranks a monitor that files
  three that all survive. The denominator is what removes that incentive, so the denominator is the
  measurement, not a footnote on it.
* `rework_distance` - changed lines between a lane's FIRST result and its ADMITTED result, over the
  changed lines of the admitted result against the base. First-pass wall-clock hides this cost
  entirely: a lane that produces something in half the time and then rewrites two thirds of it is
  not faster.

A measurement applied to live lanes before it has been shown to discriminate is a number with no
demonstrated failure mode. These controls plant fixtures whose values are known by construction and
assert BOTH directions of each axis - the case that must score high and the case that must score
low - so a computation that is inverted, or that has collapsed onto a constant, reds here rather
than being read as a provider result.

Ceiling, stated: `rework_distance` counts CHANGED LINES, not semantic edits, so a rewrite that
lands on the same line count as its predecessor still scores the lines it moved, and a one-character
correction and a one-line rewrite score the same. That is the cheap denominator this repository
already has (`git diff --numstat`); a semantic distance would need an oracle this atom does not own.
"""
from __future__ import annotations

import unittest


def confirmed_rate(findings: list[dict]) -> tuple[int, int, float]:
    """(confirmed, total, rate) for one monitor pass. Rate is 0.0 on an empty pass, never undefined.

    A finding is confirmed when a reader other than its author reproduced the defect it names; the
    caller owns that judgement, this owns only the arithmetic and the denominator."""
    total = len(findings)
    confirmed = sum(1 for item in findings if item.get("confirmed"))
    return confirmed, total, (confirmed / total if total else 0.0)


def rework_distance(first_to_admitted: int, base_to_admitted: int) -> tuple[int, int, float]:
    """(reworked, final, ratio) - changed lines redone after the first result, over the final atom.

    Both arguments are `git diff --numstat` added+deleted sums: `first..admitted` and
    `base..admitted`. Ratio is 0.0 when the admitted result is empty, so a lane that produced nothing
    scores no rework rather than dividing by zero."""
    return first_to_admitted, base_to_admitted, (first_to_admitted / base_to_admitted if base_to_admitted else 0.0)


class ConfirmedRateTests(unittest.TestCase):
    def test_denominator_inverts_the_ranking_raw_count_would_give(self) -> None:
        noisy = [{"confirmed": i == 0} for i in range(10)]
        precise = [{"confirmed": True} for _ in range(3)]
        noisy_confirmed, noisy_total, noisy_rate = confirmed_rate(noisy)
        precise_confirmed, precise_total, precise_rate = confirmed_rate(precise)
        # constraint: the planted values - raw count ranks noisy ABOVE precise, the rate must not.
        self.assertGreater(noisy_total, precise_total)
        self.assertLess(noisy_confirmed, precise_confirmed)
        self.assertLess(noisy_rate, precise_rate)

    def test_both_extremes_are_reached_so_the_metric_is_not_a_constant(self) -> None:
        self.assertEqual(confirmed_rate([{"confirmed": True}, {"confirmed": True}]), (2, 2, 1.0))
        self.assertEqual(confirmed_rate([{"confirmed": False}, {"confirmed": False}]), (0, 2, 0.0))

    def test_empty_pass_is_zero_rather_than_undefined(self) -> None:
        self.assertEqual(confirmed_rate([]), (0, 0, 0.0))

    def test_a_missing_confirmed_key_counts_against_the_monitor(self) -> None:
        # constraint: unverified is not confirmed; the absent field must not read as a pass.
        self.assertEqual(confirmed_rate([{"summary": "no verdict recorded"}]), (0, 1, 0.0))


class ReworkDistanceTests(unittest.TestCase):
    def test_a_first_result_that_was_admitted_unchanged_scores_zero(self) -> None:
        self.assertEqual(rework_distance(0, 40), (0, 40, 0.0))

    def test_a_first_result_two_thirds_rewritten_scores_two_thirds(self) -> None:
        reworked, final, ratio = rework_distance(30, 45)
        self.assertEqual((reworked, final), (30, 45))
        self.assertAlmostEqual(ratio, 2 / 3)

    def test_the_two_planted_directions_are_distinguished(self) -> None:
        # constraint: the discrimination claim itself - a clean lane and a rewritten lane of the same
        # constraint: final size must not produce the same number.
        self.assertNotEqual(rework_distance(0, 45)[2], rework_distance(30, 45)[2])

    def test_an_empty_admitted_result_is_zero_rather_than_a_division_error(self) -> None:
        self.assertEqual(rework_distance(0, 0), (0, 0, 0.0))


if __name__ == "__main__":
    unittest.main()
