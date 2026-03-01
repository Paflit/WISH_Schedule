-- app/infrastructure/db/schema.sql
-- Полная схема БД для системы оптимизации расписаний
-- SQLite dialect
PRAGMA foreign_keys = ON;

-- ===============================
-- 1. Справочники
-- ===============================

CREATE TABLE IF NOT EXISTS Teachers (
  id_teacher INTEGER PRIMARY KEY,
  full_name TEXT NOT NULL,
  commentary TEXT,
  max_pairs_per_day_hard INTEGER DEFAULT 6,
  max_pairs_per_day_soft INTEGER DEFAULT 4,
  needs_method_day INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS Subjects (
  id_subject INTEGER PRIMARY KEY,
  subject_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS StudentGroups (
  id_group INTEGER PRIMARY KEY,
  group_name TEXT NOT NULL,
  year INTEGER,
  quantity INTEGER NOT NULL,
  education_form TEXT DEFAULT 'full-time'
);

CREATE TABLE IF NOT EXISTS Classes (
  id_class INTEGER PRIMARY KEY,
  room_number TEXT NOT NULL,
  room_type TEXT NOT NULL,
  capacity INTEGER NOT NULL,
  building TEXT
);

CREATE TABLE IF NOT EXISTS TeacherSubjects (
  teacher_id INTEGER NOT NULL,
  subject_id INTEGER NOT NULL,
  PRIMARY KEY (teacher_id, subject_id),
  FOREIGN KEY (teacher_id) REFERENCES Teachers(id_teacher) ON DELETE CASCADE,
  FOREIGN KEY (subject_id) REFERENCES Subjects(id_subject) ON DELETE CASCADE
);

-- ===============================
-- 2. Календарь и таймслоты
-- ===============================

CREATE TABLE IF NOT EXISTS AcademicCalendar (
  id_calendar INTEGER PRIMARY KEY,
  academic_year TEXT NOT NULL,
  semester INTEGER NOT NULL,
  start_date TEXT,
  end_date TEXT,
  week_type_mode INTEGER DEFAULT 1,
  comment TEXT
);

CREATE TABLE IF NOT EXISTS SemesterWeeks (
  id_week INTEGER PRIMARY KEY,
  calendar_id INTEGER NOT NULL,
  week_number_in_semester INTEGER NOT NULL,
  week_type INTEGER DEFAULT 1,
  is_study_week INTEGER DEFAULT 1,
  comment TEXT,
  FOREIGN KEY (calendar_id) REFERENCES AcademicCalendar(id_calendar) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS TimeSlots (
  id_slot INTEGER PRIMARY KEY,
  week_id INTEGER NOT NULL,
  day_of_week INTEGER NOT NULL,
  pair_number INTEGER NOT NULL,
  start_time TEXT,
  end_time TEXT,
  is_lunch_break INTEGER DEFAULT 0,
  FOREIGN KEY (week_id) REFERENCES SemesterWeeks(id_week) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS TeacherAvailability (
  calendar_id INTEGER NOT NULL,
  teacher_id INTEGER NOT NULL,
  slot_id INTEGER NOT NULL,
  is_available INTEGER NOT NULL DEFAULT 1,
  comment TEXT,
  PRIMARY KEY (calendar_id, teacher_id, slot_id),
  FOREIGN KEY (calendar_id) REFERENCES AcademicCalendar(id_calendar) ON DELETE CASCADE,
  FOREIGN KEY (teacher_id) REFERENCES Teachers(id_teacher) ON DELETE CASCADE,
  FOREIGN KEY (slot_id) REFERENCES TimeSlots(id_slot) ON DELETE CASCADE
);

-- ===============================
-- 3. Учебный план
-- ===============================

CREATE TABLE IF NOT EXISTS CurriculumItems (
  id_curriculum INTEGER PRIMARY KEY,
  group_id INTEGER NOT NULL,
  subject_id INTEGER NOT NULL,
  part_type TEXT NOT NULL,
  required_room_type TEXT NOT NULL,
  hours_total_year INTEGER DEFAULT 0,
  comment TEXT,
  FOREIGN KEY (group_id) REFERENCES StudentGroups(id_group) ON DELETE CASCADE,
  FOREIGN KEY (subject_id) REFERENCES Subjects(id_subject) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS CurriculumSemesterPlan (
  id_plan INTEGER PRIMARY KEY,
  curriculum_id INTEGER NOT NULL,
  calendar_id INTEGER NOT NULL,
  hours_in_semester INTEGER NOT NULL,
  credits REAL,
  spread_mode TEXT DEFAULT 'auto_even',
  comment TEXT,
  FOREIGN KEY (curriculum_id) REFERENCES CurriculumItems(id_curriculum) ON DELETE CASCADE,
  FOREIGN KEY (calendar_id) REFERENCES AcademicCalendar(id_calendar) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS WeeklyLoadPlan (
  id_week_plan INTEGER PRIMARY KEY,
  plan_id INTEGER NOT NULL,
  week_id INTEGER NOT NULL,
  hours_this_week INTEGER NOT NULL,
  comment TEXT,
  UNIQUE (plan_id, week_id),
  FOREIGN KEY (plan_id) REFERENCES CurriculumSemesterPlan(id_plan) ON DELETE CASCADE,
  FOREIGN KEY (week_id) REFERENCES SemesterWeeks(id_week) ON DELETE CASCADE
);

-- ===============================
-- 4. Правила (опционально)
-- ===============================

CREATE TABLE IF NOT EXISTS SchedulingRules (
  id_rule_set INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  min_pairs_students_per_day INTEGER DEFAULT 2,
  max_pairs_students_per_day INTEGER DEFAULT 5,
  teacher_hard_max_pairs INTEGER DEFAULT 6,
  teacher_soft_max_pairs INTEGER DEFAULT 4,
  lecture_preferred_last_pair INTEGER DEFAULT 2,
  allow_student_gaps INTEGER DEFAULT 0,
  allow_lunch_gap INTEGER DEFAULT 1,
  lunch_gap_min_pair INTEGER DEFAULT 2,
  lunch_gap_max_pair INTEGER DEFAULT 3,
  consider_method_day INTEGER DEFAULT 1,
  comment TEXT
);

-- ===============================
-- 5. Расписание и варианты
-- ===============================

CREATE TABLE IF NOT EXISTS ScheduleVariants (
  id_variant INTEGER PRIMARY KEY,
  calendar_id INTEGER NOT NULL,
  rule_profile_key TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  name TEXT NOT NULL,
  objective_score INTEGER DEFAULT 0,
  status TEXT DEFAULT 'generated',
  comment TEXT,
  FOREIGN KEY (calendar_id) REFERENCES AcademicCalendar(id_calendar) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ScheduleEntries (
  id_schedule INTEGER PRIMARY KEY,
  variant_id INTEGER NOT NULL,
  slot_id INTEGER NOT NULL,
  group_id INTEGER,
  teacher_id INTEGER NOT NULL,
  curriculum_id INTEGER NOT NULL,
  room_id INTEGER NOT NULL,
  is_locked INTEGER DEFAULT 0,
  comment TEXT,
  FOREIGN KEY (variant_id) REFERENCES ScheduleVariants(id_variant) ON DELETE CASCADE,
  FOREIGN KEY (slot_id) REFERENCES TimeSlots(id_slot) ON DELETE CASCADE,
  FOREIGN KEY (group_id) REFERENCES StudentGroups(id_group) ON DELETE SET NULL,
  FOREIGN KEY (teacher_id) REFERENCES Teachers(id_teacher) ON DELETE CASCADE,
  FOREIGN KEY (curriculum_id) REFERENCES CurriculumItems(id_curriculum) ON DELETE CASCADE,
  FOREIGN KEY (room_id) REFERENCES Classes(id_class) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ScheduleLocks (
  id_lock INTEGER PRIMARY KEY,
  variant_id INTEGER NOT NULL,
  schedule_id INTEGER NOT NULL,
  lock_slot INTEGER DEFAULT 1,
  lock_teacher INTEGER DEFAULT 1,
  lock_class INTEGER DEFAULT 1,
  comment TEXT,
  FOREIGN KEY (variant_id) REFERENCES ScheduleVariants(id_variant) ON DELETE CASCADE,
  FOREIGN KEY (schedule_id) REFERENCES ScheduleEntries(id_schedule) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ScheduleEditsLog (
  id_edit INTEGER PRIMARY KEY,
  variant_id INTEGER NOT NULL,
  edited_at TEXT DEFAULT CURRENT_TIMESTAMP,
  edited_by TEXT,
  action TEXT,
  before_json TEXT,
  after_json TEXT,
  comment TEXT,
  FOREIGN KEY (variant_id) REFERENCES ScheduleVariants(id_variant) ON DELETE CASCADE
);

-- ===============================
-- Индексы для ускорения
-- ===============================

CREATE INDEX IF NOT EXISTS idx_timeslots_week ON TimeSlots(week_id, day_of_week, pair_number);
CREATE INDEX IF NOT EXISTS idx_entries_variant ON ScheduleEntries(variant_id);
CREATE INDEX IF NOT EXISTS idx_entries_slot ON ScheduleEntries(slot_id);
CREATE INDEX IF NOT EXISTS idx_entries_teacher ON ScheduleEntries(teacher_id);
CREATE INDEX IF NOT EXISTS idx_entries_group ON ScheduleEntries(group_id);
CREATE INDEX IF NOT EXISTS idx_availability_calendar ON TeacherAvailability(calendar_id);