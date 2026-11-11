"""Saving and loading records as a JSON file, plus CSV export."""
from __future__ import annotations

import csv
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from .core import StudentRecord

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "records.json"


class DuplicateIdError(ValueError):
    pass


class RecordStore:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or os.environ.get("SGM_DATA") or DEFAULT_PATH)
        self.recovered_from: Path | None = None
        self._records: list[StudentRecord] = self._load()

    def _load(self) -> list[StudentRecord]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return [StudentRecord.from_dict(item) for item in payload["records"]]
        except (OSError, ValueError, KeyError, TypeError):
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = self.path.with_name(f"{self.path.stem}.corrupt-{stamp}.json")
            try:
                self.path.replace(backup)
                self.recovered_from = backup
            except OSError:
                pass
            return []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 2, "records": [r.to_dict() for r in self._records]}
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def all(self) -> list[StudentRecord]:
        return list(self._records)

    def ids(self) -> list[str]:
        return [r.student_id for r in self._records]

    def get(self, student_id: str) -> StudentRecord | None:
        return next((r for r in self._records if r.student_id == student_id), None)

    def add(self, record: StudentRecord) -> None:
        if record.student_id.upper() in {i.upper() for i in self.ids()}:
            raise DuplicateIdError(f"{record.student_id} is already saved.")
        self._records.append(record)
        self._save()

    def delete(self, student_id: str) -> bool:
        before = len(self._records)
        self._records = [r for r in self._records if r.student_id != student_id]
        if len(self._records) != before:
            self._save()
            return True
        return False

    def export_csv(self, destination: Path | str) -> int:
        """Write all records to a CSV file and return the row count."""
        with open(destination, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                ["Student ID", "Name", "Major", "Marks", "Average", "Grade", "Status", "Saved"]
            )
            for r in self._records:
                marks = "; ".join(f"{s.name}: {s.mark:g}" for s in r.subjects)
                writer.writerow(
                    [r.student_id, r.name, r.stream, marks, f"{r.average:.2f}", r.grade,
                     "Pass" if r.passed else "Fail", r.created]
                )
        return len(self._records)
