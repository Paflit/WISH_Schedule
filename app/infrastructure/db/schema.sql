PRAGMA foreign_keys = ON;

-- ============================================================
-- Teachers / Subjects / Groups / Rooms
-- ============================================================

CREATE TABLE IF NOT EXISTS Teachers (
    id_teacher INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL UNIQUE,
    commentary TEXT,
    max_pairs_per_day_hard INTEGER NOT NULL DEFAULT 6,
    max_pairs_per_day_soft INTEGER NOT NULL DEFAULT 4,
    needs_method_day INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS Subjects (
    id_subject INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS TeacherSubjects (
    teacher_id INTEGER,
    subject_id INTEGER NOT NULL,
    can_lecture INTEGER NOT NULL DEFAULT 1,
    can_practice INTEGER NOT NULL DEFAULT 1,
    can_computer_practice INTEGER NOT NULL DEFAULT 1,
    can_lab INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (teacher_id, subject_id),
    FOREIGN KEY (teacher_id) REFERENCES Teachers(id_teacher) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES Subjects(id_subject) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS TeacherGroupAssignments (
    teacher_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    PRIMARY KEY (teacher_id, group_id),
    FOREIGN KEY (teacher_id) REFERENCES Teachers(id_teacher) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES StudentGroups(id_group) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS StudentGroups (
    id_group INTEGER PRIMARY KEY AUTOINCREMENT,
    group_name TEXT NOT NULL UNIQUE,
    year INTEGER,
    quantity INTEGER NOT NULL DEFAULT 0,
    education_form TEXT NOT NULL DEFAULT 'full-time'
);

CREATE TABLE IF NOT EXISTS Classes (
  id_class INTEGER PRIMARY KEY,
  room_number TEXT NOT NULL,
  room_type TEXT NOT NULL,
  room_types_json TEXT,
  capacity INTEGER NOT NULL,
  building TEXT
);

CREATE TABLE IF NOT EXISTS RoomSubjectAssignments (
    room_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    PRIMARY KEY (room_id, subject_id),
    FOREIGN KEY (room_id) REFERENCES Classes(id_class) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES Subjects(id_subject) ON DELETE CASCADE
);

-- ============================================================
-- Academic calendar
-- ============================================================

CREATE TABLE IF NOT EXISTS AcademicCalendar (
    id_calendar INTEGER PRIMARY KEY AUTOINCREMENT,
    academic_year TEXT NOT NULL,
    semester INTEGER NOT NULL,
    start_date TEXT,
    end_date TEXT,
    week_type_mode INTEGER NOT NULL DEFAULT 1,
    comment TEXT,
    UNIQUE (academic_year, semester)
);

CREATE TABLE IF NOT EXISTS SemesterWeeks (
    id_week INTEGER PRIMARY KEY AUTOINCREMENT,
    calendar_id INTEGER NOT NULL,
    week_number_in_semester INTEGER NOT NULL,
    week_type INTEGER NOT NULL,
    is_study_week INTEGER NOT NULL DEFAULT 1,
    comment TEXT,
    FOREIGN KEY (calendar_id) REFERENCES AcademicCalendar(id_calendar) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS TimeSlots (
    id_slot INTEGER PRIMARY KEY AUTOINCREMENT,
    week_id INTEGER NOT NULL,
    day_of_week INTEGER NOT NULL,
    pair_number INTEGER NOT NULL,
    start_time TEXT,
    end_time TEXT,
    is_lunch_break INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (week_id) REFERENCES SemesterWeeks(id_week) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS TeacherAvailability (
    calendar_id INTEGER NOT NULL,
    teacher_id INTEGER NOT NULL,
    slot_id INTEGER NOT NULL,
    is_available INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (calendar_id, teacher_id, slot_id),
    FOREIGN KEY (calendar_id) REFERENCES AcademicCalendar(id_calendar) ON DELETE CASCADE,
    FOREIGN KEY (teacher_id) REFERENCES Teachers(id_teacher) ON DELETE CASCADE,
    FOREIGN KEY (slot_id) REFERENCES TimeSlots(id_slot) ON DELETE CASCADE
);

-- ============================================================
-- Curriculum
-- ============================================================

CREATE TABLE IF NOT EXISTS CurriculumItems (
    id_curriculum INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    part_type TEXT NOT NULL,
    required_room_type TEXT NOT NULL,
    hours_total_year INTEGER NOT NULL DEFAULT 0,
    comment TEXT,
    FOREIGN KEY (group_id) REFERENCES StudentGroups(id_group) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES Subjects(id_subject) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS CurriculumSemesterPlan (
    id_plan INTEGER PRIMARY KEY AUTOINCREMENT,
    curriculum_id INTEGER NOT NULL,
    calendar_id INTEGER NOT NULL,
    hours_in_semester INTEGER NOT NULL DEFAULT 0,
    credits REAL,
    spread_mode TEXT NOT NULL DEFAULT 'auto_even',
    comment TEXT,
    FOREIGN KEY (curriculum_id) REFERENCES CurriculumItems(id_curriculum) ON DELETE CASCADE,
    FOREIGN KEY (calendar_id) REFERENCES AcademicCalendar(id_calendar) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS WeeklyLoadPlan (
    id_week_plan INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL,
    week_id INTEGER NOT NULL,
    hours_this_week INTEGER NOT NULL DEFAULT 0,
    comment TEXT,
    FOREIGN KEY (plan_id) REFERENCES CurriculumSemesterPlan(id_plan) ON DELETE CASCADE,
    FOREIGN KEY (week_id) REFERENCES SemesterWeeks(id_week) ON DELETE CASCADE
);

-- ============================================================
-- Schedule variants / entries / locks / edits
-- ============================================================

CREATE TABLE IF NOT EXISTS ScheduleVariants (
    id_variant INTEGER PRIMARY KEY AUTOINCREMENT,
    calendar_id INTEGER NOT NULL,
    rule_profile_key TEXT NOT NULL,
    name TEXT NOT NULL,
    objective_score INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'generated',
    comment TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (calendar_id) REFERENCES AcademicCalendar(id_calendar) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS GenerationDrafts (
    id_draft INTEGER PRIMARY KEY AUTOINCREMENT,
    calendar_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    comment TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (calendar_id) REFERENCES AcademicCalendar(id_calendar) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS GenerationDraftEntries (
    id_draft_entry INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    slot_id INTEGER NOT NULL,
    teacher_id INTEGER,
    room_id INTEGER,
    comment TEXT,
    FOREIGN KEY (draft_id) REFERENCES GenerationDrafts(id_draft) ON DELETE CASCADE,
    FOREIGN KEY (slot_id) REFERENCES TimeSlots(id_slot) ON DELETE CASCADE,
    FOREIGN KEY (teacher_id) REFERENCES Teachers(id_teacher) ON DELETE SET NULL,
    FOREIGN KEY (room_id) REFERENCES Classes(id_class) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS ScheduleEntries (
    id_schedule INTEGER PRIMARY KEY AUTOINCREMENT,
    variant_id INTEGER NOT NULL,
    event_id INTEGER,
    slot_id INTEGER NOT NULL,
    group_id INTEGER,
    teacher_id INTEGER,
    curriculum_id INTEGER NOT NULL,
    room_id INTEGER,
    is_locked INTEGER NOT NULL DEFAULT 0,
    comment TEXT,
    FOREIGN KEY (variant_id) REFERENCES ScheduleVariants(id_variant) ON DELETE CASCADE,
    FOREIGN KEY (slot_id) REFERENCES TimeSlots(id_slot) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES StudentGroups(id_group) ON DELETE SET NULL,
    FOREIGN KEY (teacher_id) REFERENCES Teachers(id_teacher) ON DELETE SET NULL,
    FOREIGN KEY (curriculum_id) REFERENCES CurriculumItems(id_curriculum) ON DELETE RESTRICT,
    FOREIGN KEY (room_id) REFERENCES Classes(id_class) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS ScheduleLocks (
    id_lock INTEGER PRIMARY KEY AUTOINCREMENT,
    variant_id INTEGER NOT NULL,
    schedule_id INTEGER NOT NULL,
    event_id INTEGER,
    lock_slot INTEGER NOT NULL DEFAULT 1,
    lock_teacher INTEGER NOT NULL DEFAULT 1,
    lock_class INTEGER NOT NULL DEFAULT 1,
    comment TEXT,
    FOREIGN KEY (variant_id) REFERENCES ScheduleVariants(id_variant) ON DELETE CASCADE,
    FOREIGN KEY (schedule_id) REFERENCES ScheduleEntries(id_schedule) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ScheduleEditsLog (
    id_edit INTEGER PRIMARY KEY AUTOINCREMENT,
    variant_id INTEGER NOT NULL,
    edited_by TEXT NOT NULL,
    action TEXT NOT NULL,
    before_json TEXT,
    after_json TEXT,
    comment TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (variant_id) REFERENCES ScheduleVariants(id_variant) ON DELETE CASCADE
);

-- ============================================================
-- Indexes
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_teacher_subjects_subject
    ON TeacherSubjects(subject_id);

CREATE INDEX IF NOT EXISTS idx_groups_name
    ON StudentGroups(group_name);

CREATE INDEX IF NOT EXISTS idx_classes_room_type
    ON Classes(room_type);

CREATE INDEX IF NOT EXISTS idx_calendar_semester
    ON AcademicCalendar(academic_year, semester);

CREATE INDEX IF NOT EXISTS idx_semester_weeks_calendar
    ON SemesterWeeks(calendar_id);

CREATE INDEX IF NOT EXISTS idx_semester_weeks_calendar_weeknum
    ON SemesterWeeks(calendar_id, week_number_in_semester);

CREATE INDEX IF NOT EXISTS idx_time_slots_week
    ON TimeSlots(week_id);

CREATE INDEX IF NOT EXISTS idx_time_slots_week_day_pair
    ON TimeSlots(week_id, day_of_week, pair_number);

CREATE INDEX IF NOT EXISTS idx_teacher_availability_teacher
    ON TeacherAvailability(teacher_id, slot_id);

CREATE INDEX IF NOT EXISTS idx_curriculum_group
    ON CurriculumItems(group_id);

CREATE INDEX IF NOT EXISTS idx_curriculum_subject
    ON CurriculumItems(subject_id);

CREATE INDEX IF NOT EXISTS idx_curriculum_part
    ON CurriculumItems(part_type);

CREATE INDEX IF NOT EXISTS idx_semester_plan_calendar
    ON CurriculumSemesterPlan(calendar_id);

CREATE INDEX IF NOT EXISTS idx_semester_plan_curriculum
    ON CurriculumSemesterPlan(curriculum_id);

CREATE INDEX IF NOT EXISTS idx_weekly_load_plan
    ON WeeklyLoadPlan(plan_id, week_id);

CREATE INDEX IF NOT EXISTS idx_schedule_variants_calendar
    ON ScheduleVariants(calendar_id);

CREATE INDEX IF NOT EXISTS idx_generation_drafts_calendar
    ON GenerationDrafts(calendar_id);

CREATE INDEX IF NOT EXISTS idx_generation_draft_entries_draft
    ON GenerationDraftEntries(draft_id);

CREATE INDEX IF NOT EXISTS idx_schedule_entries_variant
    ON ScheduleEntries(variant_id);

CREATE INDEX IF NOT EXISTS idx_schedule_entries_variant_slot
    ON ScheduleEntries(variant_id, slot_id);

CREATE INDEX IF NOT EXISTS idx_schedule_entries_group_slot
    ON ScheduleEntries(variant_id, group_id, slot_id);

CREATE INDEX IF NOT EXISTS idx_schedule_entries_teacher_slot
    ON ScheduleEntries(variant_id, teacher_id, slot_id);

CREATE INDEX IF NOT EXISTS idx_schedule_entries_room_slot
    ON ScheduleEntries(variant_id, room_id, slot_id);

CREATE INDEX IF NOT EXISTS idx_schedule_entries_event
    ON ScheduleEntries(event_id);

CREATE INDEX IF NOT EXISTS idx_schedule_locks_variant
    ON ScheduleLocks(variant_id);

CREATE INDEX IF NOT EXISTS idx_schedule_locks_schedule
    ON ScheduleLocks(schedule_id);

CREATE INDEX IF NOT EXISTS idx_schedule_locks_event
    ON ScheduleLocks(event_id);

CREATE INDEX IF NOT EXISTS idx_schedule_edits_variant
    ON ScheduleEditsLog(variant_id);
