"""
Cross-field validation engine — direct port of the workbook's Warnings row formula.

All 8 validation rules from the workbook are implemented here as independent checks.
Returns a list of human-readable warning strings (empty list = no issues).
"""
from __future__ import annotations
from dataclasses import dataclass
from models.drive import DriveResultGranular, DriveResultExact, DriveResultGrouped


@dataclass
class DriveMarketValues:
    """Flat representation of all computed market values for a single drive."""
    granular: DriveResultGranular | None
    exact: DriveResultExact | None
    grouped: DriveResultGrouped | None
    cross_50: bool | None           # None = not yet computed
    opp_35: bool | None
    opp_20: bool | None
    sack: bool | None
    fair_catch: bool | None         # None = N/A (non-punt)
    td_scorer: str | None           # None = N/A (non-TD), "" = missing
    # NFL only — None = not applicable (CFB)
    passing_20_plus: bool | None
    rushing_10_plus: bool | None
    play_20_plus: bool | None
    fourth_down_conversion: bool | None
    is_nfl: bool = True


def validate_drive(values: DriveMarketValues) -> list[str]:
    """
    Run all workbook validation rules against computed market values.
    Returns list of warning strings. Empty = clean.
    """
    warnings: list[str] = []

    if values.granular is None:
        return ["Drive result not yet determined"]

    # Rule 1: End of Half must be Void in all three tiers
    if values.granular == DriveResultGranular.END_OF_HALF:
        if values.exact not in (DriveResultExact.VOID, None):
            warnings.append("End of Half should be Void (Drive Result Exact)")
        if values.grouped not in (DriveResultGrouped.VOID, None):
            warnings.append("End of Half should be Void (Drive Result Grouped)")

    # Rule 2: TD drives must cross all three yard lines
    if values.granular in (DriveResultGranular.RUSHING_TD, DriveResultGranular.PASSING_TD):
        missing = []
        if values.cross_50 is False:
            missing.append("Cross50")
        if values.opp_35 is False:
            missing.append("Opp35")
        if values.opp_20 is False:
            missing.append("Opp20")
        if missing:
            warnings.append(f"TD drive should cross all yard lines (missing: {', '.join(missing)})")

    # Rule 3: Opp20=Yes implies Opp35 and Cross50 must be Yes
    if values.opp_20 is True:
        if values.opp_35 is False:
            warnings.append("Opp20=Yes implies Opp35 must also be Yes")
        if values.cross_50 is False:
            warnings.append("Opp20=Yes implies Cross50 must also be Yes")

    # Rule 4: Cross50=No implies Opp35 and Opp20 must be No
    if values.cross_50 is False:
        if values.opp_35 is True:
            warnings.append("Cross50=No implies Opp35 must be No")
        if values.opp_20 is True:
            warnings.append("Cross50=No implies Opp20 must be No")

    # Rule 5 (NFL only — Punt Fair Catch is not a CFB market):
    # Non-punt drives must have Fair Catch = N/A
    if values.is_nfl and values.granular != DriveResultGranular.PUNT and values.fair_catch is not None:
        warnings.append("Non-punt drive: Fair Catch should be N/A")

    # Rule 6 (NFL only — TD Scorer is not a CFB market):
    # Non-TD drives must have TD Scorer = N/A
    if values.is_nfl and values.granular not in (DriveResultGranular.RUSHING_TD, DriveResultGranular.PASSING_TD):
        if values.td_scorer is not None and values.td_scorer != "N/A":
            warnings.append("Non-TD drive: TD Scorer should be N/A")

    # Rule 7 (NFL only — TD Scorer is not a CFB market):
    # TD drives must have TD Scorer populated
    if values.is_nfl and values.granular in (DriveResultGranular.RUSHING_TD, DriveResultGranular.PASSING_TD):
        if values.td_scorer == "" or values.td_scorer is None:
            warnings.append("TD drive: TD Scorer is missing")

    # Rule 8 (NFL only): 20+ Passing Play=Yes implies 20+ Play must be Yes
    if values.is_nfl and values.passing_20_plus is True and values.play_20_plus is False:
        warnings.append("20+ Yard Passing Play=Yes implies 20+ Yard Play must also be Yes")

    return warnings


def validate_completeness(values: DriveMarketValues) -> list[str]:
    """
    Check which required fields are still blank/None.
    Mirrors the workbook's Status=Incomplete logic.
    """
    missing = []
    required_universal = {
        "Drive Result Granular": values.granular,
        "Cross 50": values.cross_50,
        "Opp 35": values.opp_35,
        "Opp 20": values.opp_20,
        "Sack": values.sack,
    }
    for name, val in required_universal.items():
        if val is None:
            missing.append(name)

    if values.is_nfl:
        # Fair Catch and TD Scorer are NFL-only markets.
        required_nfl = {
            "Fair Catch": values.fair_catch,
            "TD Scorer": values.td_scorer,
            "20+ Passing Play": values.passing_20_plus,
            "10+ Rushing Play": values.rushing_10_plus,
            "20+ Play": values.play_20_plus,
            "4th Down Conversion": values.fourth_down_conversion,
        }
        for name, val in required_nfl.items():
            if val is None:
                missing.append(name)

    return missing
