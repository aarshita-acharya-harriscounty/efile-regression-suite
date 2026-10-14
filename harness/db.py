"""Read-only LawBase_Design access. Nothing here writes."""
import pyodbc

from .config import CONNECTION_STRING

_cx = None


def connect(timeout=15):
    """Module-level single connection. Failure is raised, never swallowed - an
    unreachable DB must fail a run loudly rather than skip tests into a green pass."""
    global _cx
    if _cx is None:
        _cx = pyodbc.connect(CONNECTION_STRING, timeout=timeout)
    return _cx


def query(sql, params=()):
    cur = connect().cursor()
    cur.execute(sql, params)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def one(sql, params=()):
    rows = query(sql, params)
    return rows[0] if rows else None


def case_by_cause(cause):
    return one("SELECT Serial, Cause FROM dbo.TAXLIT0 WHERE Cause = ?", (str(cause),))


def case_by_serial(case_serial):
    return one("SELECT Serial, Cause FROM dbo.TAXLIT0 WHERE Serial = ?", (case_serial,))


def filing(serial):
    return one(
        """SELECT Serial, CaseSerial, FilingTeam, FilingStatus, EnvelopeNum, LastError,
                  FilingDescription, FilingCode, FilingType, Filertype, FeeAmount,
                  EfileLocationPk, clientRefNum, EfileAttyID
             FROM dbo.TAXLIT13 WHERE Serial = ?""",
        (serial,),
    )


def filings_for_case(case_serial):
    return query(
        """SELECT Serial, CaseSerial, FilingTeam, FilingStatus, EnvelopeNum, LastError,
                  FilingDescription
             FROM dbo.TAXLIT13 WHERE CaseSerial = ? ORDER BY Serial""",
        (case_serial,),
    )


def document_count(filing_serial):
    return one(
        "SELECT COUNT(*) AS n FROM dbo.TAXLIT13A WHERE PageSerial = ?", (filing_serial,)
    )["n"]


def pick_list(pick_name):
    return query(
        """SELECT PICK_NAME, PICK_VALUE, ExtraInfo1, ExtraInfo2, ExtraInfo4, Inactive
             FROM dbo.PICK_LIST WHERE PICK_NAME = ? ORDER BY PICK_VALUE""",
        (pick_name,),
    )


def table_exists(name):
    return (
        one(
            "SELECT COUNT(*) AS n FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?",
            (name,),
        )["n"]
        > 0
    )


def column_width(table, column):
    row = one(
        """SELECT CHARACTER_MAXIMUM_LENGTH AS w FROM INFORMATION_SCHEMA.COLUMNS
             WHERE TABLE_NAME = ? AND COLUMN_NAME = ?""",
        (table, column),
    )
    return row["w"] if row else None


def serve_by_values(case_serial):
    """TAXLIT2A.ServeBy per defendant - drives which citation service branch is requested."""
    return query(
        """SELECT t2.Serial AS PartySerial, t2.LitRole, a.Serial AS TaxLit2ASerial, a.ServeBy
             FROM dbo.TAXLIT2 t2
             LEFT JOIN dbo.TAXLIT2A a ON a.PageSerial = t2.Serial
            WHERE t2.CaseSerial = ? AND t2.LitRole IN ('Defendant', 'Primary Defendant')
              AND ISNULL(t2.InActive, 'N') <> 'Y'
            ORDER BY t2.Serial""",
        (case_serial,),
    )
