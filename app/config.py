from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


# -------------------------------------------------------
# Default constants
# -------------------------------------------------------

DEFAULT_DB_FILENAME = "schedule.db"
DEFAULT_HOURS_PER_PAIR = 2
DEFAULT_TIME_LIMIT_SECONDS = 15
DEFAULT_VARIANTS_COUNT = 5
DEFAULT_RANDOM_SEED = 1


# -------------------------------------------------------
# AppConfig
# -------------------------------------------------------

@dataclass(frozen=True)
class AppConfig:
    """
    Центральная конфигурация приложения.
    Передаётся через DI во все use-cases.
    """

    # --- DB ---
    db_url: str

    # --- Solver ---
    hours_per_pair: int
    solver_time_limit_seconds: int
    solver_variants_count: int
    solver_random_seed: int

    # --- Files ---
    export_dir: Path
    import_dir: Path

    # --- UI ---
    app_title: str
    window_width: int
    window_height: int

    # --- Logging ---
    debug: bool

    # ---------------------------------------------------

    @staticmethod
    def load() -> "AppConfig":
        if getattr(sys, "frozen", False):
            default_base_dir = Path(sys.executable).resolve().parent
        else:
            default_base_dir = Path.cwd()

        base_dir = Path(os.getenv("APP_BASE_DIR", default_base_dir))
        data_dir = base_dir / "data"
        export_dir = base_dir / "exports"
        import_dir = base_dir / "imports"

        # создаём папки, если их нет
        data_dir.mkdir(parents=True, exist_ok=True)
        export_dir.mkdir(parents=True, exist_ok=True)
        import_dir.mkdir(parents=True, exist_ok=True)

        db_filename = os.getenv("APP_DB_FILENAME", DEFAULT_DB_FILENAME)
        selected_db_path = os.getenv("APP_DB_PATH")
        db_path = Path(selected_db_path) if selected_db_path else data_dir / db_filename

        db_url = os.getenv("APP_DB_URL", f"sqlite:///{db_path}")

        return AppConfig(
            # DB
            db_url=db_url,

            # Solver
            hours_per_pair=int(os.getenv("APP_HOURS_PER_PAIR", DEFAULT_HOURS_PER_PAIR)),
            solver_time_limit_seconds=int(
                os.getenv("APP_SOLVER_TIME_LIMIT", DEFAULT_TIME_LIMIT_SECONDS)
            ),
            solver_variants_count=int(
                os.getenv("APP_SOLVER_VARIANTS", DEFAULT_VARIANTS_COUNT)
            ),
            solver_random_seed=int(
                os.getenv("APP_SOLVER_RANDOM_SEED", DEFAULT_RANDOM_SEED)
            ),

            # Files
            export_dir=export_dir,
            import_dir=import_dir,

            # UI
            app_title=os.getenv("APP_TITLE", "PracticWISH — Schedule Optimizer"),
            window_width=int(os.getenv("APP_WINDOW_WIDTH", 1280)),
            window_height=int(os.getenv("APP_WINDOW_HEIGHT", 800)),

            # Logging
            debug=os.getenv("APP_DEBUG", "0") == "1",
        )

    # ---------------------------------------------------

    def as_dict(self) -> dict:
        return {
            "db_url": self.db_url,
            "hours_per_pair": self.hours_per_pair,
            "solver_time_limit_seconds": self.solver_time_limit_seconds,
            "solver_variants_count": self.solver_variants_count,
            "solver_random_seed": self.solver_random_seed,
            "export_dir": str(self.export_dir),
            "import_dir": str(self.import_dir),
            "app_title": self.app_title,
            "window_width": self.window_width,
            "window_height": self.window_height,
            "debug": self.debug,
        }
