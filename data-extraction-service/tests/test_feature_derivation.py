"""Unit tests for P3 #16 — scoring features are derived from the bill, not
hardcoded constants.

Covers the feature-derivation helpers in ScoringService:
  * geography   <- provider state
  * provider_type <- place-of-service / provider-name keyword
  * payer       <- real payer name, projected stably onto the model's categories

These helpers are pure (they do not touch the ML models), so we instantiate the
ScoringService bypassing __init__ (which would train/load models).
"""

from __future__ import annotations

from app.models import ParsedBill
from app.services.scoring_service import ScoringService
from app.ml.synthetic_data import GEOGRAPHIES, PAYERS, PROVIDER_TYPES


def _svc() -> ScoringService:
    return object.__new__(ScoringService)


def _bill(provider=None, payer=None, pos=None) -> ParsedBill:
    from app.models import LineItem, Totals

    return ParsedBill(
        document_id="feature-test",
        status="analyzed",
        source_type="bill",
        provider=provider or {},
        payer=payer or {},
        line_items=[
            LineItem(id="li-1", cpt_hcpcs="99214", charge_amount=200.0,
                     place_of_service=pos),
        ],
        totals=Totals(billed=200.0),
    )


class TestGeographyDerivation:
    def test_uses_provider_state_when_present(self):
        svc = _svc()
        bill = _bill(provider={"name": "Memorial", "state": "CA"})
        assert svc._geography_for(bill, bill.line_items[0]) == "CA"

    def test_falls_back_to_configured_default(self):
        svc = _svc()
        bill = _bill(provider={"name": "Memorial"})  # no state
        # "NY" is the configured default in app.config.
        assert svc._geography_for(bill, bill.line_items[0]) == "NY"

    def test_unknown_state_ignored(self):
        svc = _svc()
        bill = _bill(provider={"name": "Memorial", "state": "ZZ"})
        assert svc._geography_for(bill, bill.line_items[0]) not in {"ZZ"}


class TestProviderTypeDerivation:
    def test_from_place_of_service(self):
        svc = _svc()
        bill = _bill(provider={"name": "Some Provider"}, pos="23")  # ER
        assert svc._provider_type_for(bill, bill.line_items[0]) == "emergency"

    def test_from_provider_name_keyword(self):
        svc = _svc()
        bill = _bill(provider={"name": "Springfield Radiology Center"})
        assert svc._provider_type_for(bill, bill.line_items[0]) == "radiology"

    def test_fallback_is_a_known_type(self):
        svc = _svc()
        bill = _bill(provider={"name": "Generic Name"}, pos=None)
        result = svc._provider_type_for(bill, bill.line_items[0])
        assert result in PROVIDER_TYPES


class TestPayerDerivation:
    def test_uses_real_payer_stably(self):
        svc = _svc()
        # Same payer name must map to the same category on every call.
        a = svc._payer_for(_bill(payer={"name": "Blue Cross Blue Shield TX"}))
        b = svc._payer_for(_bill(payer={"name": "Blue Cross Blue Shield TX"}))
        assert a == b
        assert a in PAYERS

    def test_default_when_no_payer(self):
        svc = _svc()
        bill = _bill(payer=None)
        assert svc._payer_for(bill) == "payer_a"

    def test_different_payers_are_not_degenerate_constant(self):
        svc = _svc()
        seen = {
            svc._payer_for(_bill(payer={"name": "Aetna"})),
            svc._payer_for(_bill(payer={"name": "UnitedHealthcare"})),
            svc._payer_for(_bill(payer={"name": "Cigna"})),
        }
        # At least not all identical to the single hardcoded value.
        assert seen != {"payer_a"}