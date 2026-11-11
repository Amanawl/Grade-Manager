import csv
import json
import tempfile
import unittest
from pathlib import Path

from grade_manager.core import build_record
from grade_manager.storage import DuplicateIdError, RecordStore


def make(name, mark, sid="", stream="Natural Science"):
    return build_record(name, sid, stream, [str(mark)] * 5)


class TestStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "data" / "records.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trip(self):
        store = RecordStore(self.path)
        store.add(make("Abebe K", 88, "S001"))
        again = RecordStore(self.path)
        self.assertEqual(again.all(), store.all())

    def test_duplicate_id_rejected(self):
        store = RecordStore(self.path)
        store.add(make("Abebe K", 88, "S001"))
        with self.assertRaises(DuplicateIdError):
            store.add(make("Sara T", 70, "s001"))

    def test_delete(self):
        store = RecordStore(self.path)
        store.add(make("Abebe K", 88, "S001"))
        self.assertTrue(store.delete("S001"))
        self.assertFalse(store.delete("S001"))
        self.assertEqual(RecordStore(self.path).all(), [])

    def test_corrupt_file_is_backed_up(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json", encoding="utf-8")
        store = RecordStore(self.path)
        self.assertEqual(store.all(), [])
        self.assertIsNotNone(store.recovered_from)
        self.assertTrue(store.recovered_from.exists())

    def test_wrong_shape_is_treated_as_corrupt(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"records": [{"name": "x"}]}), encoding="utf-8")
        self.assertEqual(RecordStore(self.path).all(), [])

    def test_export_csv(self):
        store = RecordStore(self.path)
        store.add(make("Abebe K", 88, "S001"))
        out = Path(self.tmp.name) / "out.csv"
        self.assertEqual(store.export_csv(out), 1)
        with open(out, newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[0][:2], ["Student ID", "Name"])
        self.assertEqual(rows[0][2], "Major")
        self.assertEqual(rows[1][:2], ["S001", "Abebe K"])
        self.assertEqual(rows[1][2], "Natural Science")
        self.assertTrue(rows[1][3].startswith("English Grammar: 88; Mathematics: 88"))
        self.assertEqual(rows[1][4:7], ["88.00", "B", "Pass"])

    def test_major_survives_round_trip(self):
        store = RecordStore(self.path)
        store.add(make("Hana G", 70, "S002", "Social Science"))
        self.assertEqual(RecordStore(self.path).all()[0].stream, "Social Science")

    def test_record_saved_before_majors_loads_as_unassigned(self):
        self.path.parent.mkdir(parents=True)
        legacy = {"version": 1, "records": [{
            "student_id": "S001", "name": "Old Record",
            "subjects": [{"name": "Math", "mark": 80.0, "grade": "B"}],
            "average": 80.0, "grade": "B", "created": "2026-10-01T10:00:00"}]}
        self.path.write_text(json.dumps(legacy), encoding="utf-8")
        store = RecordStore(self.path)
        self.assertEqual(store.all()[0].stream, "Unassigned")
        self.assertIsNone(store.recovered_from)


if __name__ == "__main__":
    unittest.main()
