from app.presentation.qt_app import run
from app.di import build_container

def main():
    container = build_container()
    container.calendar_repo.ensure_default_calendar(
        academic_year="2025/2026",
        include_saturday=False,
        pairs_per_day=8,
        weeks_in_semester=18,
    )
    container.curriculum_repo.rebuild_all_weekly_plans()
    #create_desktop_shortcut("PracticWISH")
    run(container)

if __name__ == "__main__":
    main()