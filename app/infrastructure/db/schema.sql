PRAGMA foreign_keys = ON;

-- =========================================================
-- Справочники
-- =========================================================

CREATE TABLE IF NOT EXISTS Teachers (
    id_teacher INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL UNIQUE,
    commentary TEXT,
    max_pairs_per_day_hard INTEGER NOT NULL DEFAULT 6,
    max_pairs_per_day_soft INTEGER NOT NULL DEFAULT 4,
    needs_method_day INTEGER NOT NULL DEFAULT 1 CHECK (needs_method_day IN (0, 1))
);

CREATE TABLE IF NOT EXISTS Subjects (
    id_subject INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS StudentGroups (
    id_group INTEGER PRIMARY KEY AUTOINCREMENT,
    group_name TEXT NOT NULL UNIQUE,
    year INTEGER,
    quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    education_form TEXT NOT NULL DEFAULT 'full-time'
);

CREATE TABLE IF NOT EXISTS Classes (
    id_class INTEGER PRIMARY KEY AUTOINCREMENT,
    room_number TEXT NOT NULL UNIQUE,
    room_type TEXT NOT NULL,
    room_types_json TEXT,
    capacity INTEGER NOT NULL DEFAULT 0,
    building TEXT
);
-- =========================================================
-- Преподаватель <-> дисциплина
-- =========================================================

CREATE TABLE IF NOT EXISTS TeacherSubjects (
    teacher_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    can_lecture INTEGER NOT NULL DEFAULT 1 CHECK (can_lecture IN (0, 1)),
    can_practice INTEGER NOT NULL DEFAULT 1 CHECK (can_practice IN (0, 1)),
    can_computer_practice INTEGER NOT NULL DEFAULT 1 CHECK (can_computer_practice IN (0, 1)),
    can_lab INTEGER NOT NULL DEFAULT 1 CHECK (can_lab IN (0, 1)),
    PRIMARY KEY (teacher_id, subject_id),
    FOREIGN KEY (teacher_id) REFERENCES Teachers(id_teacher) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES Subjects(id_subject) ON DELETE CASCADE
);

-- =========================================================
-- Календарь / недели / таймслоты
-- =========================================================

CREATE TABLE IF NOT EXISTS AcademicCalendar (
    id_calendar INTEGER PRIMARY KEY AUTOINCREMENT,
    academic_year TEXT NOT NULL,
    semester INTEGER NOT NULL CHECK (semester IN (1, 2)),
    start_date TEXT,
    end_date TEXT,
    week_type_mode INTEGER NOT NULL DEFAULT 1,
    comment TEXT,
    UNIQUE (academic_year, semester)
);

CREATE TABLE IF NOT EXISTS SemesterWeeks (
    id_week INTEGER PRIMARY KEY AUTOINCREMENT,
    calendar_id INTEGER NOT NULL,
    week_number_in_semester INTEGER NOT NULL CHECK (week_number_in_semester > 0),
    week_type INTEGER NOT NULL CHECK (week_type IN (1, 2)),
    is_study_week INTEGER NOT NULL DEFAULT 1 CHECK (is_study_week IN (0, 1)),
    comment TEXT,
    FOREIGN KEY (calendar_id) REFERENCES AcademicCalendar(id_calendar) ON DELETE CASCADE,
    UNIQUE (calendar_id, week_number_in_semester)
);

CREATE TABLE IF NOT EXISTS TimeSlots (
    id_slot INTEGER PRIMARY KEY AUTOINCREMENT,
    week_id INTEGER NOT NULL,
    day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),
    pair_number INTEGER NOT NULL CHECK (pair_number > 0),
    start_time TEXT,
    end_time TEXT,
    is_lunch_break INTEGER NOT NULL DEFAULT 0 CHECK (is_lunch_break IN (0, 1)),
    FOREIGN KEY (week_id) REFERENCES SemesterWeeks(id_week) ON DELETE CASCADE,
    UNIQUE (week_id, day_of_week, pair_number)
);

CREATE TABLE IF NOT EXISTS TeacherAvailability (
    calendar_id INTEGER NOT NULL,
    teacher_id INTEGER NOT NULL,
    slot_id INTEGER NOT NULL,
    is_available INTEGER NOT NULL DEFAULT 1 CHECK (is_available IN (0, 1)),
    PRIMARY KEY (calendar_id, teacher_id, slot_id),
    FOREIGN KEY (calendar_id) REFERENCES AcademicCalendar(id_calendar) ON DELETE CASCADE,
    FOREIGN KEY (teacher_id) REFERENCES Teachers(id_teacher) ON DELETE CASCADE,
    FOREIGN KEY (slot_id) REFERENCES TimeSlots(id_slot) ON DELETE CASCADE
);

-- =========================================================
-- Учебный план
-- =========================================================

CREATE TABLE IF NOT EXISTS CurriculumItems (
    id_curriculum INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    part_type TEXT NOT NULL
        CHECK (part_type IN ('lecture', 'practice', 'computer_practice', 'lab')),
    required_room_type TEXT NOT NULL,
    hours_total_year INTEGER NOT NULL DEFAULT 0 CHECK (hours_total_year >= 0),
    comment TEXT,
    FOREIGN KEY (group_id) REFERENCES StudentGroups(id_group) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES Subjects(id_subject) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS CurriculumSemesterPlan (
    id_plan INTEGER PRIMARY KEY AUTOINCREMENT,
    curriculum_id INTEGER NOT NULL,
    calendar_id INTEGER NOT NULL,
    hours_in_semester INTEGER NOT NULL DEFAULT 0 CHECK (hours_in_semester >= 0),
    credits REAL,
    spread_mode TEXT NOT NULL DEFAULT 'auto_even',
    comment TEXT,
    FOREIGN KEY (curriculum_id) REFERENCES CurriculumItems(id_curriculum) ON DELETE CASCADE,
    FOREIGN KEY (calendar_id) REFERENCES AcademicCalendar(id_calendar) ON DELETE CASCADE,
    UNIQUE (curriculum_id, calendar_id)
);

CREATE TABLE IF NOT EXISTS WeeklyLoadPlan (
    id_week_plan INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL,
    week_id INTEGER NOT NULL,
    hours_this_week INTEGER NOT NULL DEFAULT 0 CHECK (hours_this_week >= 0),
    comment TEXT,
    FOREIGN KEY (plan_id) REFERENCES CurriculumSemesterPlan(id_plan) ON DELETE CASCADE,
    FOREIGN KEY (week_id) REFERENCES SemesterWeeks(id_week) ON DELETE CASCADE,
    UNIQUE (plan_id, week_id)
);

-- =========================================================
-- Правила
-- =========================================================

CREATE TABLE IF NOT EXISTS SchedulingRules (
    id_rule INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_profile_key TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL
);

-- =========================================================
-- Варианты расписания
-- =========================================================

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

CREATE TABLE IF NOT EXISTS ScheduleEntries (
    id_schedule INTEGER PRIMARY KEY AUTOINCREMENT,
    variant_id INTEGER NOT NULL,
    event_id INTEGER,
    slot_id INTEGER NOT NULL,
    group_id INTEGER,
    teacher_id INTEGER NOT NULL,
    curriculum_id INTEGER NOT NULL,
    room_id INTEGER NOT NULL,
    is_locked INTEGER NOT NULL DEFAULT 0 CHECK (is_locked IN (0, 1)),
    comment TEXT,
    FOREIGN KEY (variant_id) REFERENCES ScheduleVariants(id_variant) ON DELETE CASCADE,
    FOREIGN KEY (slot_id) REFERENCES TimeSlots(id_slot) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES StudentGroups(id_group) ON DELETE SET NULL,
    FOREIGN KEY (teacher_id) REFERENCES Teachers(id_teacher) ON DELETE RESTRICT,
    FOREIGN KEY (curriculum_id) REFERENCES CurriculumItems(id_curriculum) ON DELETE RESTRICT,
    FOREIGN KEY (room_id) REFERENCES Classes(id_class) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS ScheduleLocks (
    id_lock INTEGER PRIMARY KEY AUTOINCREMENT,
    variant_id INTEGER NOT NULL,
    schedule_id INTEGER NOT NULL,
    event_id INTEGER,
    lock_slot INTEGER NOT NULL DEFAULT 1 CHECK (lock_slot IN (0, 1)),
    lock_teacher INTEGER NOT NULL DEFAULT 1 CHECK (lock_teacher IN (0, 1)),
    lock_class INTEGER NOT NULL DEFAULT 1 CHECK (lock_class IN (0, 1)),
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

-- =========================================================
-- Индексы
-- =========================================================

CREATE INDEX IF NOT EXISTS idx_teacher_availability_teacher_slot
    ON TeacherAvailability(teacher_id, slot_id);

CREATE INDEX IF NOT EXISTS idx_teacher_availability_calendar_teacher
    ON TeacherAvailability(calendar_id, teacher_id);

CREATE INDEX IF NOT EXISTS idx_curriculum_group
    ON CurriculumItems(group_id);

CREATE INDEX IF NOT EXISTS idx_curriculum_subject
    ON CurriculumItems(subject_id);

CREATE INDEX IF NOT EXISTS idx_semester_plan_calendar
    ON CurriculumSemesterPlan(calendar_id);

CREATE INDEX IF NOT EXISTS idx_weekly_plan_plan
    ON WeeklyLoadPlan(plan_id);

CREATE INDEX IF NOT EXISTS idx_weekly_plan_week
    ON WeeklyLoadPlan(week_id);

CREATE INDEX IF NOT EXISTS idx_timeslots_week
    ON TimeSlots(week_id);

CREATE INDEX IF NOT EXISTS idx_schedule_entries_variant
    ON ScheduleEntries(variant_id);

CREATE INDEX IF NOT EXISTS idx_schedule_entries_variant_slot
    ON ScheduleEntries(variant_id, slot_id);

CREATE INDEX IF NOT EXISTS idx_schedule_entries_variant_group_slot
    ON ScheduleEntries(variant_id, group_id, slot_id);

CREATE INDEX IF NOT EXISTS idx_schedule_entries_variant_teacher_slot
    ON ScheduleEntries(variant_id, teacher_id, slot_id);

CREATE INDEX IF NOT EXISTS idx_schedule_entries_variant_room_slot
    ON ScheduleEntries(variant_id, room_id, slot_id);

CREATE INDEX IF NOT EXISTS idx_schedule_entries_variant_curriculum
    ON ScheduleEntries(variant_id, curriculum_id);

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

-- =========================================================
-- Базовый профиль правил
-- =========================================================

INSERT OR IGNORE INTO SchedulingRules(rule_profile_key, payload_json)
VALUES (
    'balanced',
    '{
        "teacher_hard_max_pairs": 6,
        "teacher_soft_max_pairs": 4,
        "allow_lunch_gap": true,
        "lunch_gap_min_pair": 2,
        "lunch_gap_max_pair": 3,
        "allow_student_gaps": false,
        "min_pairs_students_per_day": 2,
        "max_pairs_students_per_day": 5,
        "consider_method_day": true,
        "w_teacher_over_soft": 700,
        "w_teacher_gaps": 150,
        "w_students_gaps": 600,
        "w_students_day_load": 500,
        "w_method_day": 250,
        "w_lecture_late": 70,
        "lecture_preferred_last_pair": 2
    }'
);