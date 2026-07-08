"""
QC Comparator — compares the rules engine expected result against the
system result (from the sportsbook platform) for every market on every drive.

System results are stored as plain dicts keyed by drive_id → market_name → value.
The comparator is completely stateless — call compare_drive() any time.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from rules.engine import EvaluatedDrive
from qc.status import QCStatus


@dataclass
class QCResult:
    market: str
    expected: str           # what the rules engine computed
    system: str             # what the sportsbook platform shows ("" = not entered)
    status: QCStatus
    note: str = ""          # human-readable explanation of any mismatch


@dataclass
class DriveQC:
    drive_id: str
    drive_label: str
    team_abbrev: str
    sequence: int
    results: list[QCResult] = field(default_factory=list)

    @property
    def mismatch_count(self) -> int:
        return sum(1 for r in self.results if r.status == QCStatus.MISMATCH)

    @property
    def pending_count(self) -> int:
        return sum(1 for r in self.results if r.status == QCStatus.PENDING)

    @property
    def has_issues(self) -> bool:
        return self.mismatch_count > 0

    @property
    def overall_status(self) -> QCStatus:
        statuses = {r.status for r in self.results}
        if QCStatus.MISMATCH in statuses:
            return QCStatus.MISMATCH
        if QCStatus.MISSING_DATA in statuses:
            return QCStatus.MISSING_DATA
        if QCStatus.PENDING in statuses:
            return QCStatus.PENDING
        return QCStatus.MATCH


def _compare_value(expected: str, system: str, market: str) -> QCResult:
    """Compare a single expected vs system value and return a QCResult."""
    if not system:
        return QCResult(
            market=market,
            expected=expected,
            system="",
            status=QCStatus.PENDING,
            note="System result not yet entered",
        )

    if expected in ("", "Unknown"):
        return QCResult(
            market=market,
            expected=expected,
            system=system,
            status=QCStatus.MISSING_DATA,
            note="Rules engine could not compute expected result",
        )

    if expected == "N/A":
        return QCResult(
            market=market,
            expected="N/A",
            system=system,
            status=QCStatus.NOT_APPLICABLE,
        )

    # Normalise for comparison — case-insensitive, strip whitespace
    exp_norm = expected.strip().lower()
    sys_norm = system.strip().lower()

    if exp_norm == sys_norm:
        return QCResult(market=market, expected=expected, system=system, status=QCStatus.MATCH)

    # Boolean aliases
    _YES = {"yes", "y", "true", "1"}
    _NO  = {"no",  "n", "false", "0"}
    if (exp_norm in _YES and sys_norm in _YES) or (exp_norm in _NO and sys_norm in _NO):
        return QCResult(market=market, expected=expected, system=system, status=QCStatus.MATCH)

    return QCResult(
        market=market,
        expected=expected,
        system=system,
        status=QCStatus.MISMATCH,
        note=f"Expected '{expected}' but system shows '{system}'",
    )


def _bool_str(value: bool | None) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "N/A"


def compare_drive(evaluated: EvaluatedDrive, system: dict[str, str]) -> DriveQC:
    """
    Compare every market for a single drive.

    Args:
        evaluated:  Output of rules.engine.evaluate_drive()
        system:     Dict mapping market name → system result string.
                    Pass {} for a drive with no system data yet (all Pending).

    Returns:
        DriveQC containing one QCResult per market.
    """
    results: list[QCResult] = []

    def get(market_key: str) -> str:
        return system.get(market_key, "")

    # ── Core result markets ──────────────────────────────────────────
    results.append(_compare_value(
        evaluated.result_granular, get("Drive Result Granular"), "Drive Result Granular"
    ))
    results.append(_compare_value(
        evaluated.result_exact, get("Drive Result Exact"), "Drive Result Exact"
    ))
    results.append(_compare_value(
        evaluated.result_grouped, get("Drive Result Grouped"), "Drive Result Grouped"
    ))

    # ── Yard-line markets ────────────────────────────────────────────
    results.append(_compare_value(
        _bool_str(evaluated.cross_50), get("Drive Crosses 50"), "Drive Crosses 50"
    ))
    results.append(_compare_value(
        _bool_str(evaluated.opp_35), get("Drive Crosses Opposing 35"), "Drive Crosses Opposing 35"
    ))
    results.append(_compare_value(
        _bool_str(evaluated.opp_20), get("Drive Crosses Opposing 20"), "Drive Crosses Opposing 20"
    ))

    # ── Play markets ─────────────────────────────────────────────────
    results.append(_compare_value(
        _bool_str(evaluated.sack), get("Sack This Drive"), "Sack This Drive"
    ))
    results.append(_compare_value(
        _bool_str(evaluated.fair_catch), get("Punt Fair Catch"), "Punt Fair Catch"
    ))

    # ── NFL-only markets ─────────────────────────────────────────────
    if evaluated.is_nfl:
        results.append(_compare_value(
            _bool_str(evaluated.passing_20_plus),
            get("20+ Yard Passing Play"), "20+ Yard Passing Play"
        ))
        results.append(_compare_value(
            _bool_str(evaluated.rushing_10_plus),
            get("10+ Yard Rushing Play"), "10+ Yard Rushing Play"
        ))
        results.append(_compare_value(
            _bool_str(evaluated.play_20_plus),
            get("20+ Yard Play"), "20+ Yard Play"
        ))
        results.append(_compare_value(
            _bool_str(evaluated.fourth_down_conversion),
            get("4th Down Conversion"), "4th Down Conversion"
        ))

    # ── Scoring markets ──────────────────────────────────────────────
    # TD Scorer: only compare when it matters (non-N/A expected)
    if evaluated.td_scorer not in ("N/A", ""):
        results.append(_compare_value(
            evaluated.td_scorer, get("TD Scorer"), "TD Scorer"
        ))
    else:
        results.append(QCResult(
            market="TD Scorer",
            expected=evaluated.td_scorer or "N/A",
            system=get("TD Scorer"),
            status=QCStatus.NOT_APPLICABLE if evaluated.td_scorer == "N/A" else QCStatus.MISSING_DATA,
        ))

    return DriveQC(
        drive_id=evaluated.drive_id,
        drive_label=evaluated.drive_label,
        team_abbrev=evaluated.team_abbrev,
        sequence=evaluated.sequence,
        results=results,
    )


def compare_all_drives(
    evaluated_drives: list[EvaluatedDrive],
    system_results: dict[str, dict[str, str]],
) -> list[DriveQC]:
    """
    Compare every drive in a game.

    Args:
        evaluated_drives: Output of rules.engine.evaluate_all_drives()
        system_results:   Nested dict: drive_id → {market → system_value}

    Returns:
        List of DriveQC in original drive sequence order.
    """
    return [
        compare_drive(ev, system_results.get(ev.drive_id, {}))
        for ev in evaluated_drives
    ]


def get_all_mismatches(drive_qcs: list[DriveQC]) -> list[tuple[DriveQC, QCResult]]:
    """Return flat list of (drive, result) tuples where status is MISMATCH."""
    mismatches = []
    for dqc in drive_qcs:
        for result in dqc.results:
            if result.status == QCStatus.MISMATCH:
                mismatches.append((dqc, result))
    return mismatches
