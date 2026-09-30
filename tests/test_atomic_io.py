"""Crash-safe export writes and the testable runner entry point."""

import csv
import io
import json
import sys
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ecommerce.atomic_io import append_csv_atomic, write_text_atomic
from ecommerce.kaidee_scraper import HISTORY_FIELDS, append_history, write_snapshot
from run_marketplace import main as marketplace_main

ROW = {"listing_id": "1", "title": "Camera, \"mint\"", "location": "Bang Kapi, \"BKK\"", "price_thb": 1500, "url": "https://www.kaidee.com/product-1"}


def test_write_text_atomic_keeps_previous_file_when_replace_fails(tmp_path):
    target = tmp_path / "snap.csv"
    target.write_text("previous", encoding="utf-8")
    with patch("ecommerce.atomic_io.os.replace", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            write_text_atomic(target, "partial")
    assert target.read_text(encoding="utf-8") == "previous"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["snap.csv"]


def test_snapshot_render_failure_keeps_old_snapshot(tmp_path):
    write_snapshot([ROW], "2026-09-01T00:00:00Z", tmp_path)
    before = (tmp_path / "kaidee_classifieds.csv").read_text(encoding="utf-8")
    with patch("ecommerce.kaidee_scraper.render_csv", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            write_snapshot([ROW], "2026-09-02T00:00:00Z", tmp_path)
    assert (tmp_path / "kaidee_classifieds.csv").read_text(encoding="utf-8") == before


def test_history_appends_with_single_header_and_quotes(tmp_path):
    append_history([ROW], "2026-09-01T00:00:00Z", tmp_path)
    append_history([{**ROW, "listing_id": "2"}], "2026-09-02T00:00:00Z", tmp_path)
    with (tmp_path / "kaidee_classifieds_history.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [r["listing_id"] for r in rows] == ["1", "2"]
    assert rows[0]["location"] == 'Bang Kapi, "BKK"'
    assert [r["captured_at"] for r in rows] == ["2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z"]


def test_history_append_repairs_missing_trailing_newline(tmp_path):
    path = tmp_path / "h.csv"
    path.write_text(",".join(HISTORY_FIELDS), encoding="utf-8")
    append_csv_atomic(path, [{"listing_id": "9"}], HISTORY_FIELDS)
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [r["listing_id"] for r in rows] == ["9"]


def test_main_rejects_output_dir_that_is_a_file(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    with redirect_stderr(io.StringIO()):
        with pytest.raises(SystemExit) as ctx:
            marketplace_main(["--output-dir", str(blocker), "--dry-run"])
    assert ctx.value.code == 2


def test_main_dry_run_json(tmp_path, capsys):
    assert marketplace_main(["--output-dir", str(tmp_path), "--dry-run", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["status"] == "dry-run"
    assert list(tmp_path.iterdir()) == []
