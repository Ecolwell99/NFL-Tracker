from __future__ import annotations
from enum import Enum


class QCStatus(Enum):
    MATCH = "Match"
    MISMATCH = "Mismatch"
    PENDING = "Pending"          # system result not yet entered
    MISSING_DATA = "Missing Data"  # rules engine could not compute expected
    NOT_APPLICABLE = "N/A"       # market does not apply (e.g. CFB-only, non-TD)


# Display config for UI rendering
QC_STATUS_COLOR = {
    QCStatus.MATCH:          "#00cc44",
    QCStatus.MISMATCH:       "#cc2200",
    QCStatus.PENDING:        "#ccaa00",
    QCStatus.MISSING_DATA:   "#888888",
    QCStatus.NOT_APPLICABLE: "#444444",
}

QC_STATUS_TEXT_COLOR = {
    QCStatus.MATCH:          "#000000",
    QCStatus.MISMATCH:       "#ffffff",
    QCStatus.PENDING:        "#000000",
    QCStatus.MISSING_DATA:   "#ffffff",
    QCStatus.NOT_APPLICABLE: "#ffffff",
}
