"""Desktop interface for the Student Grade Manager (customtkinter)."""
from __future__ import annotations

import sys
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from . import __version__
from .core import (
    GRADE_BANDS, GRADE_LABELS, GRADES, STREAMS, STREAM_NAMES, StudentRecord,
    ValidationErrors, build_record, class_stats, group_by_stream,
)
from .storage import DuplicateIdError, RecordStore

# Palette
BG = "#0E111A"
SIDEBAR = "#121622"
SURFACE = "#171C2B"
SURFACE_2 = "#1F2638"
BORDER = "#2A3350"
TEXT = "#E8ECF6"
MUTED = "#8A94B0"
ACCENT = "#7C8CFF"
ACCENT_HOVER = "#6474F0"
ACCENT_DIM = "#2B3568"
ERROR = "#F2677D"
GRADE_COLORS = {
    "A": "#3DD9B0", "B": "#6FA8FF", "C": "#F2C14E", "D": "#F59A5B", "F": "#F2677D",
}
STREAM_COLORS = {"Natural Science": "#5FD0E8", "Social Science": "#C79BFF", "Unassigned": MUTED}
FONT = {"win32": "Segoe UI", "darwin": "SF Pro Text"}.get(sys.platform, "DejaVu Sans")


def font(size: int, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT, size=size, weight=weight)


class CourseRow:
    """One fixed course with a mark field."""

    def __init__(self, parent: ctk.CTkFrame, course: str, on_change):
        self.course = course
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self.frame, text=course, font=font(13), text_color=TEXT,
                     anchor="w").grid(row=0, column=0, sticky="w", padx=(4, 8))
        self.mark = ctk.CTkEntry(
            self.frame, width=110, height=36, placeholder_text="0 to 100",
            fg_color=SURFACE_2, border_color=BORDER, border_width=1,
            corner_radius=8, font=font(13), justify="right",
        )
        self.mark.grid(row=0, column=1, padx=(0, 4))
        self.mark.bind("<KeyRelease>", lambda _e: on_change())

    def set_error(self, bad: bool) -> None:
        self.mark.configure(border_color=ERROR if bad else BORDER)

    def value(self) -> str:
        return self.mark.get()

    def reset(self) -> None:
        self.mark.delete(0, "end")


class App(ctk.CTk):
    def __init__(self, store: RecordStore | None = None):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.store = store or RecordStore()
        self.title("Grade Manager")
        self.geometry("1160x760")
        self.minsize(1020, 680)
        self.configure(fg_color=BG)
        self.current: StudentRecord | None = None
        self.rows: list[CourseRow] = []
        self.stream = STREAM_NAMES[0]
        self.active = "entry"
        self._toast_job = None

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew", padx=28, pady=24)
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        self.entry_view = self._build_entry_view()
        self.records_view = self._build_records_view()
        self.toast_label = ctk.CTkLabel(
            self, text="", fg_color=SURFACE_2, corner_radius=10, text_color=TEXT,
            font=font(13), padx=16, pady=10,
        )
        self.bind("<Return>", self._on_return)
        self.show("entry")
        if self.store.recovered_from:
            self.after(400, lambda: self.toast(
                "The saved file could not be read. A backup copy was kept.", ERROR))

    # ----- layout -----------------------------------------------------
    def _build_sidebar(self) -> None:
        bar = ctk.CTkFrame(self, width=230, fg_color=SIDEBAR, corner_radius=0)
        bar.grid(row=0, column=0, sticky="nsw")
        bar.grid_propagate(False)
        ctk.CTkLabel(bar, text="Grade Manager", font=font(21, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=24, pady=(30, 2))
        ctk.CTkLabel(bar, text="Marks, averages and\nletter grades", font=font(12),
                     text_color=MUTED, justify="left").pack(anchor="w", padx=24)
        self.nav = {}
        for key, label in (("entry", "New entry"), ("records", "Records")):
            btn = ctk.CTkButton(
                bar, text=label, anchor="w", height=42, corner_radius=10,
                fg_color="transparent", hover_color=SURFACE_2, text_color=TEXT,
                font=font(14, "bold"), command=lambda k=key: self.show(k),
            )
            btn.pack(fill="x", padx=16, pady=(26 if key == "entry" else 4, 0))
            self.nav[key] = btn

        scale = ctk.CTkFrame(bar, fg_color="transparent")
        scale.pack(side="bottom", fill="x", padx=24, pady=(0, 26))
        ctk.CTkLabel(scale, text="Grading scale", font=font(12, "bold"),
                     text_color=MUTED).pack(anchor="w", pady=(0, 8))
        upper = 100
        for minimum, letter in GRADE_BANDS:
            line = ctk.CTkFrame(scale, fg_color="transparent")
            line.pack(fill="x", pady=2)
            ctk.CTkLabel(line, text=letter, width=22, font=font(13, "bold"),
                         text_color=GRADE_COLORS[letter]).pack(side="left")
            span = f"{minimum} to {upper}" if letter != "F" else f"below {upper + 1}"
            ctk.CTkLabel(line, text=span, font=font(12),
                         text_color=MUTED).pack(side="left")
            upper = minimum - 1
        ctk.CTkLabel(scale, text=f"Version {__version__}", font=font(11),
                     text_color=MUTED).pack(anchor="w", pady=(14, 0))

    def _card(self, parent) -> ctk.CTkFrame:
        return ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=16,
                            border_width=1, border_color=BORDER)

    def _page_header(self, parent, title: str, subtitle: str) -> ctk.CTkFrame:
        head = ctk.CTkFrame(parent, fg_color="transparent")
        ctk.CTkLabel(head, text=title, font=font(26, "bold"),
                     text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(head, text=subtitle, font=font(13),
                     text_color=MUTED).pack(anchor="w", pady=(2, 0))
        return head

    def _label(self, parent, text: str) -> ctk.CTkLabel:
        return ctk.CTkLabel(parent, text=text, font=font(12, "bold"), text_color=MUTED)

    def _entry(self, parent, placeholder: str) -> ctk.CTkEntry:
        return ctk.CTkEntry(
            parent, height=40, placeholder_text=placeholder,
            fg_color=SURFACE_2, border_color=BORDER, border_width=1,
            corner_radius=8, font=font(14),
        )

    # ----- entry view -------------------------------------------------
    def _build_entry_view(self) -> ctk.CTkFrame:
        view = ctk.CTkFrame(self.content, fg_color="transparent")
        view.grid_columnconfigure(0, weight=5, uniform="cols")
        view.grid_columnconfigure(1, weight=4, uniform="cols")
        view.grid_rowconfigure(1, weight=1)
        self._page_header(
            view, "New entry",
            "Choose a major, enter the marks and see the average and letter grade.",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 18))

        form = self._card(view)
        form.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        form.grid_columnconfigure(0, weight=1)
        form.grid_rowconfigure(6, weight=1)

        top = ctk.CTkFrame(form, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=22, pady=(22, 0))
        top.grid_columnconfigure(0, weight=3)
        top.grid_columnconfigure(1, weight=1)
        self._label(top, "Student name").grid(row=0, column=0, sticky="w")
        self._label(top, "Student ID").grid(row=0, column=1, sticky="w", padx=(10, 0))
        self.name_entry = self._entry(top, "e.g. Abebe Kebede")
        self.name_entry.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.id_entry = self._entry(top, "Auto")
        self.id_entry.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(6, 0))
        for entry in (self.name_entry, self.id_entry):
            entry.bind("<KeyRelease>", lambda _e: self._mark_stale())

        major_head = ctk.CTkFrame(form, fg_color="transparent")
        major_head.grid(row=1, column=0, sticky="ew", padx=22, pady=(20, 6))
        major_head.grid_columnconfigure(0, weight=1)
        self._label(major_head, "Major").grid(row=0, column=0, sticky="w")
        self.stream_btn = ctk.CTkSegmentedButton(
            major_head, values=list(STREAM_NAMES), command=self.set_stream,
            height=36, corner_radius=10, font=font(13, "bold"),
            fg_color=SURFACE_2, selected_color=ACCENT, selected_hover_color=ACCENT_HOVER,
            unselected_color=SURFACE_2, unselected_hover_color=BORDER,
            text_color=TEXT,
        )
        self.stream_btn.set(self.stream)
        self.stream_btn.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.marks_title = self._label(form, "")
        self.marks_title.grid(row=2, column=0, sticky="w", padx=22, pady=(16, 4))

        self.rows_frame = ctk.CTkFrame(form, fg_color="transparent")
        self.rows_frame.grid(row=3, column=0, sticky="new", padx=(18, 18))
        self.rows_frame.grid_columnconfigure(0, weight=1)
        self.build_rows()

        self.error_label = ctk.CTkLabel(
            form, text="", text_color=ERROR, font=font(12), justify="left",
            anchor="w", wraplength=440,
        )
        self.error_label.grid(row=4, column=0, sticky="ew", padx=22, pady=(10, 0))

        buttons = ctk.CTkFrame(form, fg_color="transparent")
        buttons.grid(row=5, column=0, sticky="ew", padx=22, pady=(14, 18))
        self.calc_btn = ctk.CTkButton(
            buttons, text="Calculate", height=42, width=130, corner_radius=10,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#0B0E18",
            font=font(14, "bold"), command=self.calculate,
        )
        self.calc_btn.pack(side="left")
        self.save_btn = ctk.CTkButton(
            buttons, text="Save record", height=42, width=130, corner_radius=10,
            fg_color=SURFACE_2, hover_color=BORDER, text_color=TEXT,
            text_color_disabled="#59627E", font=font(14, "bold"),
            state="disabled", command=self.save,
        )
        self.save_btn.pack(side="left", padx=10)
        ctk.CTkButton(
            buttons, text="Clear", height=42, width=80, corner_radius=10,
            fg_color="transparent", hover_color=SURFACE_2, text_color=MUTED,
            font=font(14), command=self.clear_form,
        ).pack(side="left")

        self.result_card = self._card(view)
        self.result_card.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        self.result_card.grid_columnconfigure(0, weight=1)
        self.result_body = ctk.CTkFrame(self.result_card, fg_color="transparent")
        self.result_body.pack(fill="both", expand=True, padx=24, pady=24)
        self.render_result(None)
        return view

    def build_rows(self, keep: dict[str, str] | None = None) -> None:
        """Show one mark field per course of the selected major."""
        for row in self.rows:
            row.frame.destroy()
        self.rows = []
        for i, course in enumerate(STREAMS[self.stream]):
            row = CourseRow(self.rows_frame, course, self._mark_stale)
            row.frame.grid(row=i, column=0, sticky="ew", pady=4)
            if keep and keep.get(course):
                row.mark.insert(0, keep[course])
            self.rows.append(row)
        self.marks_title.configure(text=f"{self.stream} courses, marks 0 to 100")

    def set_stream(self, stream: str) -> None:
        if stream == self.stream:
            return
        carried = {r.course: r.value() for r in self.rows if r.course in STREAMS[stream]}
        self.stream = stream
        self.build_rows(carried)
        self._clear_errors()
        self._mark_stale()

    def _mark_stale(self) -> None:
        """Editing the form invalidates the calculated result."""
        if self.current is not None:
            self.current = None
            self.save_btn.configure(state="disabled")

    def _clear_errors(self) -> None:
        self.error_label.configure(text="")
        for entry in (self.name_entry, self.id_entry):
            entry.configure(border_color=BORDER)
        for row in self.rows:
            row.set_error(False)

    def calculate(self) -> None:
        self._clear_errors()
        try:
            record = build_record(
                self.name_entry.get(), self.id_entry.get(), self.stream,
                [row.value() for row in self.rows], self.store.ids(),
            )
        except ValidationErrors as exc:
            self._show_errors(exc.errors)
            return
        self.current = record
        self.render_result(record)
        self.save_btn.configure(state="normal")

    def _show_errors(self, errors: dict[str, str]) -> None:
        self.current = None
        self.save_btn.configure(state="disabled")
        self.render_result(None)
        if "name" in errors:
            self.name_entry.configure(border_color=ERROR)
        if "id" in errors:
            self.id_entry.configure(border_color=ERROR)
        for key in errors:
            if key.startswith("mark:"):
                self.rows[int(key.split(":")[1])].set_error(True)
        self.error_label.configure(text="\n".join(errors.values()))

    def save(self) -> None:
        if self.current is None:
            return
        try:
            self.store.add(self.current)
        except DuplicateIdError as exc:
            self.toast(str(exc), ERROR)
            return
        except OSError:
            self.toast("The record could not be written to disk.", ERROR)
            return
        name = self.current.name
        self.clear_form()
        self.toast(f"Saved {name}.", GRADE_COLORS["A"])
        self.refresh_records()

    def clear_form(self) -> None:
        self.name_entry.delete(0, "end")
        self.id_entry.delete(0, "end")
        for row in self.rows:
            row.reset()
        self._clear_errors()
        self.current = None
        self.save_btn.configure(state="disabled")
        self.render_result(None)

    def render_result(self, record: StudentRecord | None, saved: bool = False) -> None:
        for child in self.result_body.winfo_children():
            child.destroy()
        body = self.result_body
        if record is None:
            ctk.CTkLabel(body, text="Result", font=font(16, "bold"),
                         text_color=TEXT).pack(anchor="w")
            ctk.CTkLabel(
                body, text="Fill in the form and select Calculate.\n"
                           "The average and grade appear here.",
                font=font(13), text_color=MUTED, justify="left",
            ).pack(anchor="w", pady=(8, 0))
            return
        color = GRADE_COLORS[record.grade]
        head = ctk.CTkFrame(body, fg_color="transparent")
        head.pack(fill="x")
        badge = ctk.CTkFrame(head, width=96, height=96, corner_radius=22,
                             fg_color=SURFACE_2, border_width=2, border_color=color)
        badge.pack(side="left")
        badge.pack_propagate(False)
        ctk.CTkLabel(badge, text=record.grade, font=font(44, "bold"),
                     text_color=color).place(relx=0.5, rely=0.5, anchor="center")
        info = ctk.CTkFrame(head, fg_color="transparent")
        info.pack(side="left", padx=18)
        ctk.CTkLabel(info, text=record.name, font=font(18, "bold"),
                     text_color=TEXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(info, text=f"{record.student_id}  |  {GRADE_LABELS[record.grade]}",
                     font=font(13), text_color=MUTED).pack(anchor="w")
        ctk.CTkLabel(info, text=record.stream, font=font(12, "bold"),
                     text_color=STREAM_COLORS.get(record.stream, MUTED)).pack(anchor="w")
        status = "Pass" if record.passed else "Fail"
        ctk.CTkLabel(info, text=status, font=font(12, "bold"), text_color=color,
                     fg_color=SURFACE_2, corner_radius=8, padx=10, pady=2,
                     ).pack(anchor="w", pady=(8, 0))

        avg = ctk.CTkFrame(body, fg_color=SURFACE_2, corner_radius=12)
        avg.pack(fill="x", pady=(20, 6))
        ctk.CTkLabel(avg, text="Average mark", font=font(12), text_color=MUTED
                     ).pack(side="left", padx=16, pady=14)
        ctk.CTkLabel(avg, text=f"{record.average:.2f}", font=font(24, "bold"),
                     text_color=TEXT).pack(side="right", padx=16)

        ctk.CTkLabel(body, text="Courses",
                     font=font(12, "bold"), text_color=MUTED).pack(anchor="w", pady=(14, 4))
        scroll = ctk.CTkScrollableFrame(
            body, fg_color="transparent", height=150,
            scrollbar_button_color=BORDER, scrollbar_button_hover_color=MUTED)
        scroll.pack(fill="both", expand=True)
        scroll.grid_columnconfigure(0, weight=1)
        for i, s in enumerate(record.subjects):
            scolor = GRADE_COLORS[s.grade]
            line = ctk.CTkFrame(scroll, fg_color="transparent")
            line.grid(row=i, column=0, sticky="ew", pady=5)
            line.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(line, text=s.name, font=font(13), text_color=TEXT,
                         anchor="w").grid(row=0, column=0, sticky="w")
            ctk.CTkLabel(line, text=f"{s.mark:g}", font=font(13, "bold"),
                         text_color=TEXT).grid(row=0, column=1, padx=(0, 12))
            ctk.CTkLabel(line, text=s.grade, font=font(13, "bold"), width=18,
                         text_color=scolor).grid(row=0, column=2)
            bar = ctk.CTkProgressBar(line, height=6, corner_radius=3,
                                     fg_color=SURFACE_2, progress_color=scolor)
            bar.set(s.mark / 100)
            bar.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 0))

    # ----- records view -----------------------------------------------
    def _build_records_view(self) -> ctk.CTkFrame:
        view = ctk.CTkFrame(self.content, fg_color="transparent")
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(3, weight=1)
        self._page_header(view, "Records", "Saved students grouped by major, with class statistics.").grid(
            row=0, column=0, sticky="w", pady=(0, 16))

        stats = ctk.CTkFrame(view, fg_color="transparent")
        stats.grid(row=1, column=0, sticky="ew")
        self.stat_labels = {}
        for i, (key, title) in enumerate((
            ("count", "Students"), ("mean", "Class average"),
            ("highest", "Highest average"), ("pass_rate", "Pass rate"),
        )):
            stats.grid_columnconfigure(i, weight=1, uniform="stat")
            card = self._card(stats)
            card.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0))
            ctk.CTkLabel(card, text=title, font=font(12), text_color=MUTED
                         ).pack(anchor="w", padx=18, pady=(14, 0))
            value = ctk.CTkLabel(card, text="-", font=font(24, "bold"), text_color=TEXT)
            value.pack(anchor="w", padx=18, pady=(0, 14))
            self.stat_labels[key] = value

        dist = self._card(view)
        dist.grid(row=2, column=0, sticky="ew", pady=12)
        self.dist_labels = {}
        for i, letter in enumerate(GRADES):
            dist.grid_columnconfigure(i, weight=1, uniform="dist")
            cell = ctk.CTkFrame(dist, fg_color="transparent")
            cell.grid(row=0, column=i, pady=10)
            ctk.CTkLabel(cell, text=letter, font=font(16, "bold"),
                         text_color=GRADE_COLORS[letter]).pack(side="left")
            count = ctk.CTkLabel(cell, text="0", font=font(16), text_color=TEXT)
            count.pack(side="left", padx=(8, 0))
            self.dist_labels[letter] = count

        table_card = self._card(view)
        table_card.grid(row=3, column=0, sticky="nsew")
        table_card.grid_columnconfigure(0, weight=1)
        table_card.grid_rowconfigure(1, weight=1)

        bar = ctk.CTkFrame(table_card, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=16, pady=14)
        self.search_entry = ctk.CTkEntry(
            bar, width=190, height=36,
            placeholder_text="Search name or ID", fg_color=SURFACE_2,
            border_color=BORDER, border_width=1, corner_radius=8, font=font(13),
        )
        self.search_entry.pack(side="left")
        self.search_entry.bind("<KeyRelease>", lambda _e: self.refresh_records())
        self.filter_btn = ctk.CTkSegmentedButton(
            bar, values=["All", *STREAM_NAMES], command=lambda _v: self.refresh_records(),
            height=36, corner_radius=10, font=font(12, "bold"), fg_color=SURFACE_2,
            selected_color=ACCENT, selected_hover_color=ACCENT_HOVER,
            unselected_color=SURFACE_2, unselected_hover_color=BORDER, text_color=TEXT,
        )
        self.filter_btn.set("All")
        self.filter_btn.pack(side="left", padx=(12, 0))
        for text, command, primary in (
            ("Export", self.export_csv, False),
            ("Delete", self.delete_selected, False),
            ("View", self.view_selected, True),
        ):
            ctk.CTkButton(
                bar, text=text, width=84, height=36, corner_radius=8, font=font(13, "bold"),
                fg_color=ACCENT if primary else SURFACE_2,
                hover_color=ACCENT_HOVER if primary else BORDER,
                text_color="#0B0E18" if primary else TEXT, command=command,
            ).pack(side="right", padx=(8, 0))

        style = ttk.Style(self)
        style.theme_use("clam")
        style.layout("Grades.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.configure("Grades.Treeview", background=SURFACE, fieldbackground=SURFACE,
                        foreground=TEXT, borderwidth=0, rowheight=40, font=(FONT, 11))
        style.configure("Grades.Treeview.Heading", background=SURFACE_2, foreground=MUTED,
                        relief="flat", borderwidth=0, font=(FONT, 10, "bold"), padding=(12, 8))
        style.map("Grades.Treeview", background=[("selected", ACCENT_DIM)],
                  foreground=[("selected", TEXT)])
        style.map("Grades.Treeview.Heading", background=[("active", SURFACE_2)])

        holder = ctk.CTkFrame(table_card, fg_color="transparent")
        holder.grid(row=1, column=0, sticky="nsew", padx=2, pady=(0, 6))
        holder.grid_columnconfigure(0, weight=1)
        holder.grid_rowconfigure(0, weight=1)
        columns = ("id", "name", "average", "grade")
        self.tree = ttk.Treeview(holder, columns=columns, show="headings",
                                 style="Grades.Treeview", selectmode="browse")
        for col, title, width, anchor in (
            ("id", "ID", 90, "w"), ("name", "Name", 280, "w"),
            ("average", "Average", 110, "center"), ("grade", "Grade", 90, "center"),
        ):
            self.tree.heading(col, text=title, anchor=anchor if anchor != "w" else "w")
            self.tree.column(col, width=width, anchor=anchor, stretch=col == "name")
        for letter, color in GRADE_COLORS.items():
            self.tree.tag_configure(letter, foreground=color)
        for stream_name, color in STREAM_COLORS.items():
            self.tree.tag_configure(f"g:{stream_name}", foreground=color, background=SURFACE_2)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ctk.CTkScrollbar(holder, command=self.tree.yview,
                                  button_color=BORDER, button_hover_color=MUTED)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Double-1>", lambda _e: self.view_selected())
        self.empty_label = ctk.CTkLabel(
            table_card, text="No records yet.\nSave a student from New entry.",
            font=font(13), text_color=MUTED, justify="center")
        self.refresh_records()
        return view

    def refresh_records(self) -> None:
        records = self.store.all()
        choice = self.filter_btn.get()
        only = None if choice == "All" else choice
        stats = class_stats(records, only)
        fmt = lambda v, suffix="": "-" if v is None else f"{v:.2f}{suffix}"
        self.stat_labels["count"].configure(text=str(stats["count"]))
        self.stat_labels["mean"].configure(text=fmt(stats["mean"]))
        self.stat_labels["highest"].configure(text=fmt(stats["highest"]))
        self.stat_labels["pass_rate"].configure(
            text="-" if stats["pass_rate"] is None else f"{stats['pass_rate']:.0f}%")
        for letter, label in self.dist_labels.items():
            label.configure(text=str(stats["distribution"][letter]))

        query = self.search_entry.get().strip().casefold()
        self.tree.delete(*self.tree.get_children())
        shown = 0
        for stream_name, members in group_by_stream(records).items():
            if only and stream_name != only:
                continue
            matches = [r for r in members if not query
                       or query in r.name.casefold() or query in r.student_id.casefold()]
            if not matches:
                continue
            group_stats = class_stats(members)
            self.tree.insert("", "end", iid=f"group:{stream_name}", tags=(f"g:{stream_name}",),
                             values=("", f"{stream_name}   |   {len(members)} student"
                                     f"{'' if len(members) == 1 else 's'}   |   average "
                                     f"{group_stats['mean']:.2f}", "", ""))
            for r in matches:
                self.tree.insert("", "end", iid=r.student_id, tags=(r.grade,), values=(
                    r.student_id, r.name, f"{r.average:.2f}", r.grade))
                shown += 1
        if shown == 0:
            if not records:
                text = "No records yet.\nSave a student from New entry."
            elif only and not any(r.stream == only for r in records):
                text = f"No {only} students yet."
            else:
                text = "No students match your search."
            self.empty_label.configure(text=text)
            self.empty_label.place(relx=0.5, rely=0.62, anchor="center")
        else:
            self.empty_label.place_forget()

    def _selected(self) -> StudentRecord | None:
        selection = self.tree.selection()
        if not selection or selection[0].startswith("group:"):
            self.toast("Select a student first.", ERROR)
            return None
        return self.store.get(selection[0])

    def view_selected(self) -> None:
        record = self._selected()
        if record is None:
            return
        self.show("entry")
        self.render_result(record, saved=True)

    def delete_selected(self) -> None:
        record = self._selected()
        if record is None:
            return
        if messagebox.askyesno("Delete record", f"Delete {record.name} ({record.student_id})?"):
            self.store.delete(record.student_id)
            self.refresh_records()
            self.toast(f"Deleted {record.name}.", MUTED)

    def export_csv(self) -> None:
        if not self.store.all():
            self.toast("There are no records to export.", ERROR)
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV file", "*.csv")],
            initialfile="grades.csv")
        if not path:
            return
        try:
            count = self.store.export_csv(path)
        except OSError:
            self.toast("The file could not be written. Choose another location.", ERROR)
            return
        self.toast(f"Exported {count} record{'s' if count != 1 else ''}.", GRADE_COLORS["A"])

    # ----- navigation and feedback ----------------------------------------
    def show(self, key: str) -> None:
        self.active = key
        self.entry_view.grid_forget()
        self.records_view.grid_forget()
        view = self.entry_view if key == "entry" else self.records_view
        view.grid(row=0, column=0, sticky="nsew")
        for name, btn in self.nav.items():
            btn.configure(fg_color=SURFACE_2 if name == key else "transparent")
        if key == "records":
            self.refresh_records()

    def _on_return(self, _event) -> None:
        if self.active == "entry":
            self.calculate()

    def toast(self, message: str, color: str = TEXT) -> None:
        if self._toast_job:
            self.after_cancel(self._toast_job)
        self.toast_label.configure(text=message, text_color=color)
        self.toast_label.place(relx=1.0, rely=1.0, anchor="se", x=-28, y=-24)
        self.toast_label.lift()
        self._toast_job = self.after(3200, self.toast_label.place_forget)


def main() -> None:
    App().mainloop()
