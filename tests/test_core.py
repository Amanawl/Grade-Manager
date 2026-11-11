import unittest
from decimal import Decimal

from grade_manager.core import (
    STREAMS, ValidationErrors, build_record, class_stats, group_by_stream, letter_grade,
    next_student_id, parse_mark,
)

NS, SS = "Natural Science", "Social Science"


def marks(*values):
    return [str(v) for v in values]


def ns(name="Sara T", sid="", *values, existing=()):
    return build_record(name, sid, NS, marks(*(values or (70, 70, 70, 70, 70))), existing)


class TestMajors(unittest.TestCase):
    def test_course_lists(self):
        self.assertEqual(STREAMS[NS], ("English Grammar", "Mathematics", "Chemistry", "Biology", "Physics"))
        self.assertEqual(STREAMS[SS], ("English Grammar", "Mathematics (SS)", "Geography", "History", "Economics"))

    def test_natural_science_record_uses_its_courses(self):
        rec = ns("Abebe K", "", 80, 90, 85, 75, 95)
        self.assertEqual(rec.stream, NS)
        self.assertEqual([s.name for s in rec.subjects], list(STREAMS[NS]))
        self.assertEqual(rec.average, 85.0)

    def test_social_science_record_uses_its_courses(self):
        rec = build_record("Hana G", "", SS, marks(60, 70, 80, 90, 100))
        self.assertEqual(rec.stream, SS)
        self.assertEqual([s.name for s in rec.subjects], list(STREAMS[SS]))
        self.assertEqual(rec.average, 80.0)
        self.assertEqual(rec.grade, "B")

    def test_unknown_major_rejected(self):
        for bad in ("", "Arts", "natural science"):
            with self.subTest(stream=bad), self.assertRaises(ValidationErrors) as ctx:
                build_record("Sara T", "", bad, marks(70, 70, 70, 70, 70))
            self.assertIn("stream", ctx.exception.errors)

    def test_every_course_needs_a_mark(self):
        with self.assertRaises(ValidationErrors) as ctx:
            build_record("Sara T", "", SS, marks(70, 70, "", 70, 70))
        self.assertEqual(set(ctx.exception.errors), {"mark:2"})
        self.assertTrue(ctx.exception.errors["mark:2"].startswith("Geography"))

    def test_wrong_mark_count_is_a_programming_error(self):
        with self.assertRaises(ValueError):
            build_record("Sara T", "", NS, marks(70, 70))

    def test_group_by_stream(self):
        a = ns("Zed A", "S001")
        b = build_record("Bea B", "S002", SS, marks(50, 50, 50, 50, 50))
        c = ns("Amy C", "S003")
        groups = group_by_stream([a, b, c])
        self.assertEqual(list(groups), [NS, SS])
        self.assertEqual([r.name for r in groups[NS]], ["Amy C", "Zed A"])
        self.assertEqual([r.name for r in groups[SS]], ["Bea B"])

    def test_stats_for_one_major(self):
        recs = [ns("Aa", "S001", 90, 90, 90, 90, 90),
                build_record("Bb", "S002", SS, marks(40, 40, 40, 40, 40)),
                build_record("Cc", "S003", SS, marks(80, 80, 80, 80, 80))]
        self.assertEqual(class_stats(recs, NS)["count"], 1)
        social = class_stats(recs, SS)
        self.assertEqual((social["count"], social["mean"], social["pass_rate"]), (2, 60.0, 50.0))
        self.assertEqual(class_stats(recs)["count"], 3)
        self.assertEqual(class_stats(recs, "Unassigned")["count"], 0)


class TestParseMark(unittest.TestCase):
    def test_valid(self):
        for text, expected in (("0", 0), ("100", 100), ("78.5", Decimal("78.5")), (" 65 ", 65), ("99.99", Decimal("99.99"))):
            self.assertEqual(parse_mark(text), expected)

    def test_invalid(self):
        for text in ("", "   ", "abc", "-1", "101", "100.01", "1e2", "nan", "inf", "7 8", "78.555", "5,5", "+5", "0x10", "1000"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_mark(text)


class TestLetterGrade(unittest.TestCase):
    def test_boundaries(self):
        cases = {100: "A", 90: "A", 89.99: "B", 80: "B", 79.99: "C", 70: "C",
                 69.99: "D", 60: "D", 59.99: "F", 0: "F"}
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(letter_grade(value), expected)

    def test_out_of_range(self):
        for value in (-0.01, 100.01):
            with self.assertRaises(ValueError):
                letter_grade(value)


class TestBuildRecord(unittest.TestCase):
    def test_average_and_grade(self):
        rec = ns("Abebe Kebede", "", 80, 90, 85, 85, 85)
        self.assertEqual((rec.average, rec.grade, rec.student_id), (85.0, "B", "S001"))
        self.assertTrue(rec.passed)

    def test_rounding_half_up_decides_grade(self):
        rec = ns("Sara T", "", 89.99, 90, 90, 90, 90)  # mean 89.998 rounds to 90.00
        self.assertEqual((rec.average, rec.grade), (90.0, "A"))

    def test_fail(self):
        rec = ns("Sara T", "", 40, 55, 30, 50, 45)
        self.assertEqual(rec.grade, "F")
        self.assertFalse(rec.passed)

    def test_per_subject_grades(self):
        rec = ns("Sara T", "", 95, 50, 85, 72, 61)
        self.assertEqual([s.grade for s in rec.subjects], ["A", "F", "B", "C", "D"])

    def test_name_rules(self):
        for bad in ("", "   ", "A", "Abe123", "=cmd", "x" * 61, "<b>hi</b>"):
            with self.subTest(name=bad), self.assertRaises(ValidationErrors) as ctx:
                ns(bad)
            self.assertIn("name", ctx.exception.errors)
        for good in ("O'Brien-Smith Jr.", "አበበ ከበደ", "  Abebe   Kebede  "):
            with self.subTest(name=good):
                ns(good)

    def test_id_rules(self):
        with self.assertRaises(ValidationErrors) as ctx:
            ns("Sara T", "-bad")
        self.assertIn("id", ctx.exception.errors)
        with self.assertRaises(ValidationErrors) as ctx:
            ns("Sara T", "s001", existing=["S001"])
        self.assertIn("already used", ctx.exception.errors["id"])
        self.assertEqual(ns("Sara T", "BDU-22").student_id, "BDU-22")

    def test_collects_all_errors_with_course_keys(self):
        with self.assertRaises(ValidationErrors) as ctx:
            build_record("", "", NS, marks("abc", 105, 70, 70, 70))
        errors = ctx.exception.errors
        self.assertEqual(set(errors), {"name", "mark:0", "mark:1"})
        self.assertTrue(errors["mark:0"].startswith("English Grammar"))
        self.assertTrue(errors["mark:1"].startswith("Mathematics"))


class TestHelpers(unittest.TestCase):
    def test_next_student_id(self):
        self.assertEqual(next_student_id([]), "S001")
        self.assertEqual(next_student_id(["S001", "S009", "X5"]), "S010")

    def test_class_stats(self):
        empty = class_stats([])
        self.assertEqual(empty["count"], 0)
        self.assertIsNone(empty["mean"])
        recs = [ns(n, "", *([m] * 5)) for n, m in (("Aa", 95), ("Bb", 75), ("Cc", 40))]
        stats = class_stats(recs)
        self.assertEqual(stats["count"], 3)
        self.assertEqual(stats["mean"], 70.0)
        self.assertEqual((stats["highest"], stats["lowest"]), (95.0, 40.0))
        self.assertEqual(stats["pass_rate"], 66.7)
        self.assertEqual(stats["distribution"], {"A": 1, "B": 0, "C": 1, "D": 0, "F": 1})


if __name__ == "__main__":
    unittest.main()
