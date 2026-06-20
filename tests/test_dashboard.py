import importlib.util
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "roles/airplay/files/airplay_dashboard.py"
_spec = importlib.util.spec_from_file_location("airplay_dashboard", SRC)
db = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(db)


def test_percent_to_db_endpoints():
    assert db.percent_to_db(100) == 0.0
    assert db.percent_to_db(0) == -144.0  # mute
    assert db.percent_to_db(50) == -15.0


def test_percent_to_db_clamps():
    assert db.percent_to_db(150) == 0.0
    assert db.percent_to_db(-5) == -144.0
