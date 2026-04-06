-- Добавление поддержки деления группы на подгруппы
-- Дата: 2026-03-30

-- Добавляем флаг для деления группы на подгруппы
ALTER TABLE CurriculumItems ADD COLUMN split_into_subgroups INTEGER NOT NULL DEFAULT 0;

-- Добавляем поле для указания подгруппы (NULL = вся группа, 'A' = подгруппа А, 'B' = подгруппа Б)
ALTER TABLE CurriculumItems ADD COLUMN subgroup_label TEXT DEFAULT NULL;
