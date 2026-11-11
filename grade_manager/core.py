"""Grading rules, input validation and statistics.

This module has no UI and no file access, so every rule can be tested alone.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Sequence

MAX_MARK = 100

# Each major has a fixed course list. Marks are entered in this order.
STREAMS = {
    "Natural Science": ("English Grammar", "Mathematics", "Chemistry", "Biology", "Physics"),
    "Social Science": ("English Grammar", "Mathematics (SS)", "Geography", "History", "Economics"),
}
STREAM_NAMES = tuple(STREAMS)
UNASSIGNED = "Unassigned"  # only for records saved before majors existed

# (minimum average, letter). Checked from the top down.
GRADE_BANDS = ((90, "A"), (80, "B"), (70, "C"), (60, "D"), (0, "F"))
GRADES = tuple(letter for _, letter in GRADE_BANDS)
GRADE_LABELS = {
    "A": "Excellent",
    "B": "Very good",
    "C": "Good",
    "D": "Satisfactory",
    "F": "Fail",
}

_MARK_RE = re.compile(r"^\d{1,3}(\.\d{1,2})?$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-]{0,14}$")
_TWO_PLACES = Decimal("0.01")


class ValidationErrors(Exception):
    """Raised with every problem found, keyed by field.

    Keys: "name", "id", "stream" and "mark:<course index>" (0-based).
    """

    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__("; ".join(errors.values()))


@dataclass(frozen=True)
class Subject:
    name: str
    mark: float
    grade: str


@dataclass(frozen=True)
class StudentRecord:
    student_id: str
    name: str
    stream: str
    subjects: tuple[Subject, ...]
    average: float
    grade: str
    created: str

    @property
    def passed(self) -> bool:
        return self.grade != "F"

    def to_dict(self) -> dict:
        return {
            "student_id": self.student_id,
            "name": self.name,
            "stream": self.stream,
            "subjects": [
                {"name": s.name, "mark": s.mark, "grade": s.grade} for s in self.subjects
            ],
            "average": self.average,
            "grade": self.grade,
            "created": self.created,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StudentRecord":
        return cls(
            student_id=str(data["student_id"]),
            name=str(data["name"]),
            stream=str(data.get("stream", UNASSIGNED)),
            subjects=tuple(
                Subject(str(s["name"]), float(s["mark"]), str(s["grade"]))
                for s in data["subjects"]
            ),
            average=float(data["average"]),
            grade=str(data["grade"]),
            created=str(data["created"]),
        )


def parse_mark(raw: object) -> Decimal:
    """Convert text to a mark between 0 and 100 (up to two decimals)."""
    text = str(raw).strip()
    if not text:
        raise ValueError("enter a mark.")
    if text.startswith("-"):
        raise ValueError("marks cannot be negative.")
    if not _MARK_RE.match(text):
        raise ValueError("use a number such as 78 or 78.5.")
    value = Decimal(text)
    if value > MAX_MARK:
        raise ValueError(f"marks cannot be higher than {MAX_MARK}.")
    return value


def letter_grade(average: Decimal | float | int) -> str:
    """Return A, B, C, D or F for an average between 0 and 100."""
    if not 0 <= average <= MAX_MARK:
        raise ValueError("average must be between 0 and 100.")
    for minimum, letter in GRADE_BANDS:
        if average >= minimum:
            return letter
    raise ValueError("average must be between 0 and 100.")  # unreachable guard


def next_student_id(existing_ids: Iterable[str]) -> str:
    """Return the next free ID in the form S001, S002, ..."""
    highest = 0
    for sid in existing_ids:
        match = re.fullmatch(r"S(\d+)", sid.upper())
        if match:
            highest = max(highest, int(match.group(1)))
    return f"S{highest + 1:03d}"


def _valid_name(name: str) -> bool:
    return (
        2 <= len(name) <= 60
        and name[0].isalpha()
        and all(ch.isalpha() or ch in " .'-" for ch in name)
    )


def build_record(
    name: str,
    student_id: str,
    stream: str,
    marks: Sequence[str],
    existing_ids: Iterable[str] = (),
) -> StudentRecord:
    """Validate the form values and return a graded record.

    marks holds one text value per course of the chosen major, in the order of
    STREAMS[stream]. Every course needs a mark. Raises ValidationErrors.
    """
    errors: dict[str, str] = {}
    existing = {sid.upper() for sid in existing_ids}

    name = " ".join(name.split())
    if not name:
        errors["name"] = "Student name: enter a name."
    elif not _valid_name(name):
        errors["name"] = (
            "Student name: use 2 to 60 letters, spaces, periods, apostrophes or hyphens."
        )

    student_id = student_id.strip()
    if student_id:
        if not _ID_RE.match(student_id):
            errors["id"] = "Student ID: use up to 15 letters, digits or hyphens."
        elif student_id.upper() in existing:
            errors["id"] = f"Student ID: {student_id} is already used."
    else:
        student_id = next_student_id(existing)

    courses = STREAMS.get(stream)
    if courses is None:
        errors["stream"] = "Major: choose Natural Science or Social Science."
        courses = ()
    elif len(marks) != len(courses):
        raise ValueError("marks must have one value per course")

    parsed: list[Decimal] = []
    for index, course in enumerate(courses):
        try:
            parsed.append(parse_mark(marks[index]))
        except ValueError as exc:
            errors[f"mark:{index}"] = f"{course}: {exc}"

    if errors:
        raise ValidationErrors(errors)

    average = (sum(parsed) / len(parsed)).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
    subjects = tuple(
        Subject(course, float(mark), letter_grade(mark)) for course, mark in zip(courses, parsed)
    )
    return StudentRecord(
        student_id=student_id,
        name=name,
        stream=stream,
        subjects=subjects,
        average=float(average),
        grade=letter_grade(average),
        created=datetime.now().isoformat(timespec="seconds"),
    )


def class_stats(records: Sequence[StudentRecord], stream: str | None = None) -> dict:
    """Summary figures for the Records screen. Pass a major to limit the group."""
    if stream:
        records = [r for r in records if r.stream == stream]
    distribution = {letter: 0 for letter in GRADES}
    for record in records:
        distribution[record.grade] += 1
    if not records:
        return {
            "count": 0, "mean": None, "highest": None, "lowest": None,
            "pass_rate": None, "distribution": distribution,
        }
    averages = [r.average for r in records]
    mean = (sum(Decimal(str(a)) for a in averages) / len(averages)).quantize(
        _TWO_PLACES, rounding=ROUND_HALF_UP
    )
    passed = sum(1 for r in records if r.passed)
    return {
        "count": len(records),
        "mean": float(mean),
        "highest": max(averages),
        "lowest": min(averages),
        "pass_rate": round(100 * passed / len(records), 1),
        "distribution": distribution,
    }


def group_by_stream(records: Sequence[StudentRecord]) -> dict[str, list[StudentRecord]]:
    """Records grouped by major, each group sorted by name. Empty groups are kept."""
    groups: dict[str, list[StudentRecord]] = {name: [] for name in STREAM_NAMES}
    for record in records:
        groups.setdefault(record.stream, []).append(record)
    for members in groups.values():
        members.sort(key=lambda r: r.name.casefold())
    return {k: v for k, v in groups.items() if v or k in STREAM_NAMES}
