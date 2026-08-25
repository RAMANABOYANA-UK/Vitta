"""Regression tests for P0 #4 — CMS CSV loading must not drop letter-prefixed codes.

_load_cms_csv split every row into an alpha_map/numeric_map, even for the
single-category ICD-10 and modifier files where alpha_map was None. Because every
ICD-10 code begins with a letter, a full CMS icd10.csv loaded ZERO codes; alpha
modifiers (LT/RT/GA/XU) were dropped from modifiers.csv too. All tests below load
zero rows under the old routing and therefore fail against it.
"""

from __future__ import annotations

from pathlib import Path

from app.services.reference_data import ReferenceDataService


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_cms_icd10_csv_loads_letter_prefixed_codes(tmp_path: Path) -> None:
    _write(
        tmp_path / "icd10.csv",
        "code,description,status\n"
        "E11.9,Type 2 diabetes,active\n"
        "Z99.11,Dependence on respirator,active\n",
    )
    svc = ReferenceDataService(data_dir=tmp_path).load()
    assert svc.is_valid_icd10("E11.9")
    # A code not in the bundled proxy set — proves it came from the CSV.
    assert svc.is_valid_icd10("Z99.11")


def test_cms_modifiers_csv_loads_alpha_modifiers(tmp_path: Path) -> None:
    _write(
        tmp_path / "modifiers.csv",
        "code,description,status\n"
        "LT,Left side,active\n"
        "XU,Unusual non-overlapping service,active\n",
    )
    svc = ReferenceDataService(data_dir=tmp_path).load()
    assert svc.is_valid_modifier("LT")
    assert svc.is_valid_modifier("XU")  # not in bundle → proves CSV load


def test_cms_cpt_hcpcs_split_still_works(tmp_path: Path) -> None:
    _write(
        tmp_path / "cpt_hcpcs.csv",
        "code,description,status\n"
        "99999,Some new CPT,active\n"
        "J9999,Some new HCPCS drug,active\n",
    )
    svc = ReferenceDataService(data_dir=tmp_path).load()
    assert svc.is_valid_cpt_hcpcs("99999")  # numeric → _cpt
    assert svc.is_valid_cpt_hcpcs("J9999")  # alpha  → _hcpcs


def test_deprecated_status_flags_inactive(tmp_path: Path) -> None:
    _write(
        tmp_path / "icd10.csv",
        "code,description,status\nA00.0,Cholera,retired\n",
    )
    svc = ReferenceDataService(data_dir=tmp_path).load()
    rec = svc.lookup_icd10("A00.0")
    assert rec is not None
    assert rec.is_deprecated is True
    assert rec.is_active is False


def test_empty_code_rows_are_skipped_without_aborting_file(tmp_path: Path) -> None:
    """A blank code must be skipped (not raise IndexError on code[0], which under
    the old broad-except would have aborted the whole file load)."""
    _write(
        tmp_path / "icd10.csv",
        "code,description,status\n"
        ",Missing code,active\n"
        "E11.9,Type 2 diabetes,active\n",
    )
    svc = ReferenceDataService(data_dir=tmp_path).load()
    assert svc.is_valid_icd10("E11.9")
