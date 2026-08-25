"""Reference data service — validates CPT/HCPCS/ICD-10/modifier codes against
CMS/AMA reference data (or a public/licensed proxy dataset).

For offline operation without the full CMS datasets, we bundle a small curated
proxy dataset of the most common codes. The service supports two modes:

1.  **Bundle** (default): a small built-in curated set of common codes.
2.  **CMS files**: overlay full CMS CPT/HCPCS/ICD-10/modifier CSVs from
    `data/reference/` if present (see `_load_cms_files` for expected columns).
"""

from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------
@dataclass
class CodeRecord:
    code: str
    description: str
    is_active: bool = True
    is_deprecated: bool = False
    source: str = "bundle"


# ---------------------------------------------------------------------------
# Built-in curated proxy dataset (common CPT / HCPCS / ICD-10 / modifiers)
# ---------------------------------------------------------------------------
# This is a small curated subset used for offline operation. In production you'd
# load the full CMS files (see load_cms_files). Keeping it accurate for the most
# common codes is important since these are the ones most likely to appear.
_COMMON_CPT: Dict[str, str] = {
    "99201": "Office/outpatient visit, new patient, 10 minutes",
    "99202": "Office/outpatient visit, new patient, 20 minutes",
    "99203": "Office/outpatient visit, new patient, 30 minutes",
    "99204": "Office/outpatient visit, new patient, 45 minutes",
    "99205": "Office/outpatient visit, new patient, 60 minutes",
    "99211": "Office/outpatient visit, established patient, 5 minutes",
    "99212": "Office/outpatient visit, established patient, 10 minutes",
    "99213": "Office/outpatient visit, established patient, 15 minutes",
    "99214": "Office/outpatient visit, established patient, 25 minutes",
    "99215": "Office/outpatient visit, established patient, 40 minutes",
    "99381": "Preventive medicine, new patient, age 0-1",
    "99382": "Preventive medicine, new patient, age 1-4",
    "99383": "Preventive medicine, new patient, age 5-11",
    "99384": "Preventive medicine, new patient, age 12-17",
    "99385": "Preventive medicine, new patient, age 18-39",
    "99391": "Preventive medicine, established patient, age 0-1",
    "99392": "Preventive medicine, established patient, age 1-4",
    "99393": "Preventive medicine, established patient, age 5-11",
    "99394": "Preventive medicine, established patient, age 12-17",
    "99395": "Preventive medicine, established patient, age 18-39",
    "93000": "ECG, routine, with interpretation and report",
    "93005": "ECG, routine, tracing only",
    "93010": "ECG, routine, interpretation and report only",
    "80048": "Basic metabolic panel",
    "80053": "Comprehensive metabolic panel",
    "80061": "Lipid panel",
    "85025": "CBC with differential",
    "81001": "Urinalysis, automated, with microscopy",
    "71045": "Chest X-ray, 1 view",
    "71046": "Chest X-ray, 2 views",
    "71250": "CT chest without contrast",
    "70450": "CT head without contrast",
    "74150": "CT abdomen without contrast",
    "76700": "Abdominal ultrasound, complete",
    "93306": "Echocardiogram, transthoracic, complete",
    "36415": "Venipuncture",
    "96372": "Therapeutic injection",
    "90471": "Immunization administration",
    "90658": "Influenza vaccine, 6 months and older, IM",
    "20610": "Joint injection, major joint",
    "J1100": "Dexamethasone sodium phosphate injection",
    "J1885": "Ketorolac tromethamine injection",
    "J2505": "Pegfilgrastim injection",
}

_COMMON_ICD10: Dict[str, str] = {
    "E11.9": "Type 2 diabetes mellitus without complications",
    "I10": "Essential (primary) hypertension",
    "J06.9": "Acute upper respiratory infection, unspecified",
    "J18.9": "Pneumonia, unspecified organism",
    "M54.5": "Low back pain",
    "M25.50": "Pain in joint, unspecified",
    "R10.9": "Unspecified abdominal pain",
    "R05": "Cough",
    "R51": "Headache",
    "Z00.00": "Encounter for general adult medical examination",
    "Z23": "Encounter for immunization",
    "G43.909": "Migraine, unspecified, not intractable",
    "M17.9": "Osteoarthritis of knee, unspecified",
    "F41.9": "Anxiety disorder, unspecified",
    "F32.9": "Major depressive disorder, single episode, unspecified",
    "N39.0": "Urinary tract infection, site not specified",
    "K21.9": "Gastro-esophageal reflux disease without esophagitis",
    "E78.5": "Hyperlipidemia, unspecified",
    "J45.909": "Unspecified asthma",
    "L60.0": "Ingrowing nail",
}

_COMMON_MODIFIERS: Dict[str, str] = {
    "25": "Significant, separately identifiable E/M service",
    "59": "Distinct procedural service",
    "76": "Repeat procedure by same physician",
    "77": "Repeat procedure by another physician",
    "78": "Unplanned return to operating room",
    "79": "Unrelated procedure by same physician during postoperative period",
    "LT": "Left side",
    "RT": "Right side",
    "50": "Bilateral procedure",
    "51": "Multiple procedures",
    "52": "Reduced services",
    "53": "Discontinued procedure",
    "GA": "Waiver of liability statement",
}

# Deprecated/retired codes to test flagging (subset of actual deprecated codes)
_DEPRECATED_CPT: Dict[str, str] = {
    "99201": "Office/outpatient visit, new patient, 10 minutes (retired 2021)",
    "99384": "Preventive medicine, new patient, age 12-17 (retired 2023)",
    "99394": "Preventive medicine, established patient, age 12-17 (retired 2023)",
}


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
class ReferenceDataService:
    """Loads and queries code reference data."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir: Path = data_dir or Path(settings.reference_data_dir)
        self._cpt: Dict[str, CodeRecord] = {}
        self._hcpcs: Dict[str, CodeRecord] = {}
        self._icd10: Dict[str, CodeRecord] = {}
        self._modifiers: Dict[str, CodeRecord] = {}
        self._loaded = False

    # --- Loading -----------------------------------------------------------
    def load(self, force: bool = False) -> "ReferenceDataService":
        """Load reference data. Uses the bundled dataset, then overlays any
        CMS files found in data_dir if present."""
        if self._loaded and not force:
            return self

        self._load_bundle()
        self._load_cms_files()
        self._loaded = True
        logger.info(
            "Reference data loaded: %d CPT, %d HCPCS, %d ICD-10, %d modifiers",
            len(self._cpt),
            len(self._hcpcs),
            len(self._icd10),
            len(self._modifiers),
        )
        return self

    def _load_bundle(self) -> None:
        for code, desc in _COMMON_CPT.items():
            rec = CodeRecord(code=code, description=desc, source="bundle")
            if code in _DEPRECATED_CPT:
                rec.is_active = False
                rec.is_deprecated = True
            # Distinguish HCPCS from CPT: HCPCS starts with a letter
            if code[0].isalpha():
                self._hcpcs[code] = rec
            else:
                self._cpt[code] = rec

        for code, desc in _COMMON_ICD10.items():
            self._icd10[code] = CodeRecord(
                code=code, description=desc, source="bundle"
            )

        for code, desc in _COMMON_MODIFIERS.items():
            self._modifiers[code] = CodeRecord(
                code=code, description=desc, source="bundle"
            )

    def _load_cms_files(self) -> None:
        """Load full CMS reference files if present (CSV).

        Expected columns:
          - cpt_hcpcs.csv:      code,description,long_description,status
          - icd10.csv:          code,description,long_description,status
          - modifiers.csv:      code,description,status

        cpt_hcpcs.csv is split by first character (numeric CPT vs letter-prefixed
        HCPCS); icd10.csv and modifiers.csv each load into a single map.
        """
        if not self.data_dir.exists():
            return

        self._load_cms_csv(
            self.data_dir / "cpt_hcpcs.csv", self._cpt, self._hcpcs
        )
        self._load_cms_csv(self.data_dir / "icd10.csv", self._icd10)
        self._load_cms_csv(self.data_dir / "modifiers.csv", self._modifiers)

    def _load_cms_csv(
        self,
        path: Path,
        primary_map: Dict[str, CodeRecord],
        alpha_map: Optional[Dict[str, CodeRecord]] = None,
    ) -> None:
        """Load one CMS CSV into a target map.

        For the combined CPT/HCPCS file, ``alpha_map`` receives letter-prefixed
        HCPCS codes while ``primary_map`` receives numeric CPT codes. For
        single-category files (ICD-10, modifiers) ``alpha_map`` is None and
        EVERY row goes to ``primary_map`` — including letter-prefixed codes such
        as ICD-10 'E11.9' or modifiers 'LT'/'RT'/'GA'.

        Previously the alpha/numeric split ran even when ``alpha_map`` was None,
        so letter-prefixed codes were routed to None and silently dropped. Since
        every ICD-10 code begins with a letter, a full CMS ``icd10.csv`` loaded
        ZERO codes. A file that exists but yields no usable rows now logs an
        error instead of failing silently.
        """
        if not path.exists():
            return
        loaded = 0
        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    code = row.get("code", "").strip()
                    if not code:
                        continue
                    desc = row.get("description", row.get("long_description", "")).strip()
                    status = row.get("status", "active").strip().lower()
                    is_active = status not in ("deprecated", "retired", "inactive")
                    rec = CodeRecord(
                        code=code,
                        description=desc,
                        is_active=is_active,
                        is_deprecated=not is_active,
                        source=str(path.name),
                    )
                    if alpha_map is not None and code[0].isalpha():
                        alpha_map[code] = rec
                    else:
                        primary_map[code] = rec
                    loaded += 1
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to load reference file %s: %s", path, exc)
            return
        if loaded == 0:
            logger.error(
                "Reference file %s exists but produced 0 usable codes — check it "
                "has a 'code' header column and at least one data row.",
                path,
            )
        else:
            logger.info("Loaded %d codes from %s", loaded, path.name)

    # --- Querying ----------------------------------------------------------
    def _normalize(self, code: str) -> str:
        return code.strip().upper()

    def lookup_cpt_hcpcs(self, code: str) -> Optional[CodeRecord]:
        """Look up a CPT or HCPCS code. Handles the ambiguity where a code may be
        numeric (CPT) or alpha (HCPCS)."""
        c = self._normalize(code)
        # HCPCS codes are alphanumeric (start with a letter); CPT are 5-digit
        if c and c[0].isalpha():
            return self._hcpcs.get(c) or self._cpt.get(c)
        return self._cpt.get(c) or self._hcpcs.get(c)

    def lookup_icd10(self, code: str) -> Optional[CodeRecord]:
        return self._icd10.get(self._normalize(code))

    def lookup_modifier(self, code: str) -> Optional[CodeRecord]:
        return self._modifiers.get(self._normalize(code))

    def is_valid_cpt_hcpcs(self, code: str) -> bool:
        return self.lookup_cpt_hcpcs(code) is not None

    def is_valid_icd10(self, code: str) -> bool:
        return self.lookup_icd10(code) is not None

    def is_valid_modifier(self, code: str) -> bool:
        return self.lookup_modifier(code) is not None

    @staticmethod
    def looks_like_cpt(code: str) -> bool:
        """Heuristic: is this code plausibly a CPT/HCPCS code?"""
        return bool(re.match(r"^[A-Z0-9]{5}$", code.strip().upper()))

    @staticmethod
    def looks_like_icd10(code: str) -> bool:
        """Heuristic: is this code plausibly an ICD-10 code?"""
        c = code.strip().upper()
        # Format: letter + up to 3 digits (some codes have no number, e.g. 'I10')
        # with optional decimal point and up to 2 more digits
        return bool(re.match(r"^[A-Z][0-9]{0,3}(?:\.[0-9]{0,2})?$", c))


def get_reference_data_service() -> ReferenceDataService:
    svc = ReferenceDataService()
    svc.load()
    return svc