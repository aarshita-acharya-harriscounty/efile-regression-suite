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


def filing_tracking_ids(filing_serial):
    """TAXLIT13A.TylerTrakingID is Tyler's FILINGID for the filing (one value, repeated on
    every document row), and TylerResponse is the raw JSON the submit wrote back:
    {"ENVELOPEID":"...","FILINGID":"...","Status":"Submitted"}.

    The distinction matters for GetFilingDetails: queried by ENVELOPEID it returns only an
    envelope-level summary with no filing fields at all, so an attorney/party echo can only be
    read back by FILINGID."""
    return query(
        """SELECT Serial, EfileOrd, TylerTrakingID, TylerResponse, TylerStatusPk
             FROM dbo.TAXLIT13A WHERE PageSerial = ? ORDER BY EfileOrd""",
        (filing_serial,),
    )


def filing_id(filing_serial):
    rows = [r for r in filing_tracking_ids(filing_serial) if (r["TylerTrakingID"] or "").strip()]
    return rows[0]["TylerTrakingID"].strip() if rows else None


def pick_list(pick_name):
    return query(
        """SELECT PICK_NAME, PICK_VALUE, ExtraInfo1, ExtraInfo2, ExtraInfo4, Inactive
             FROM dbo.PICK_LIST WHERE PICK_NAME = ? ORDER BY PICK_VALUE""",
        (pick_name,),
    )


def distinct_pick_name_prefixes(like):
    """Distinct PICK_NAME values matching `like`, truncated at the first '|'. Several
    cert-era lists (Filing Code, Party Type, ...) use a pipe-delimited composite PICK_NAME -
    see lawbase-efile-current-workflow.md's PICK_LIST conventions table - so this collapses
    those back to their list name the same way a human scanning PICK_NAME would. The three
    Design-era lists this suite cares about are plain (no '|'), so for them this is just
    PICK_NAME itself; detecting a '|' creeping onto one of them is drift worth flagging."""
    rows = query(
        """SELECT DISTINCT
                  LEFT(PICK_NAME, CASE WHEN CHARINDEX('|', PICK_NAME) = 0
                                        THEN LEN(PICK_NAME) ELSE CHARINDEX('|', PICK_NAME) - 1 END) AS prefix
             FROM dbo.PICK_LIST WHERE PICK_NAME LIKE ?""",
        (like,),
    )
    return {r["prefix"] for r in rows}


def pick_list_primary_key_columns():
    rows = query(
        """SELECT c.name AS col
             FROM sys.key_constraints kc
             JOIN sys.index_columns ic
               ON ic.object_id = kc.parent_object_id AND ic.index_id = kc.unique_index_id
             JOIN sys.columns c
               ON c.object_id = ic.object_id AND c.column_id = ic.column_id
            WHERE kc.parent_object_id = OBJECT_ID('dbo.PICK_LIST')
            ORDER BY ic.key_ordinal"""
    )
    return [r["col"] for r in rows]


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


# Deliberately a copy of the SQL in PjCosServiceContacts.ReadCos (PLB-1169), not a
# paraphrase of it. The COS rule is the part of PJ most easily broken by an unrelated data
# change, and a test that queried it "equivalently" would drift from the real resolver
# silently. If this diverges from the C# the test should be updated to match the C#, not the
# other way around (TESTING_RULES.md rule 9).
_COS_SQL = """
SELECT  tl2.Serial,
        tl2.DefNo,
        tl2.LitRole,
        tl2.AttyofRec,
        c0.SERIAL                AS PartyContactSerial,
        c0.name                  AS PartyName,
        COALESCE(NULLIF(LTRIM(RTRIM(c0.ServiceEmail)), ''),
                 NULLIF(LTRIM(RTRIM(c0.PrimaryEmail)), '')) AS PartyEmail,
        (SELECT STRING_AGG(NULLIF(LTRIM(RTRIM(a.ServeCert)), ''), ', ')
           FROM dbo.TaxLit2A a
          WHERE a.PageSerial = tl2.Serial)                  AS ServiceMethods,
        c9a.Serial               AS AttyC9Serial,
        NULLIF(LTRIM(RTRIM(c9a.FName)), '')                 AS AttyFirst,
        NULLIF(LTRIM(RTRIM(c9a.LName)), '')                 AS AttyLast,
        NULLIF(LTRIM(RTRIM(c9a.email)), '')                 AS AttyEmail,
        NULLIF(LTRIM(RTRIM(c9a.BarCode)), '')               AS AttyBar,
        NULLIF(LTRIM(RTRIM(c0a.name)), '')                  AS AttyFirmName,
        NULLIF(LTRIM(RTRIM(c0a.PrimaryEmail)), '')          AS AttyFirmEmail,
        NULLIF(LTRIM(RTRIM(tl2.Jurisdictions)), '')         AS Jurisdictions
FROM        dbo.TaxLit2  tl2
LEFT JOIN   dbo.CONTACT0 c0  ON c0.LINKSERIAL = tl2.LitPerson
LEFT JOIN   dbo.Contact9 c9a ON c9a.LinkSerial = tl2.AttyofRec
LEFT JOIN   dbo.CONTACT0 c0a ON c0a.SERIAL = c9a.CaseSerial
WHERE   tl2.CaseSerial = ?
  AND   tl2.CertOfService = 'Y'
  AND   ISNULL(tl2.InActive, 'N') <> 'Y'
ORDER BY tl2.DefNo, tl2.Serial
"""


def cos_rows(case_serial):
    """The Certificate of Service roster for a case - who PJ must serve, and how."""
    return query(_COS_SQL, (case_serial,))


def taxlit2_rows(case_serial):
    """Every party row on the case, COS or not. Used to prove the COS filter is the
    CertofService checkbox alone and not a role-based rule."""
    return query(
        """SELECT tl2.Serial, tl2.DefNo, tl2.LitRole, tl2.CertOfService, tl2.InActive,
                  tl2.AttyofRec, c0.name AS PartyName
             FROM dbo.TaxLit2 tl2
             LEFT JOIN dbo.CONTACT0 c0 ON c0.LINKSERIAL = tl2.LitPerson
            WHERE tl2.CaseSerial = ?
            ORDER BY tl2.DefNo, tl2.Serial""",
        (case_serial,),
    )


def distinct_serve_cert_values():
    """Every distinct TAXLIT2A.ServeCert value in Design, with its row count. ServeCert is
    multi-valued ('Email, USPS Regular'), so any equality test against 'Email' silently
    under-serves - this is the data that proves it."""
    return query(
        """SELECT LTRIM(RTRIM(ServeCert)) AS ServeCert, COUNT(*) AS n
             FROM dbo.TaxLit2A
            WHERE NULLIF(LTRIM(RTRIM(ServeCert)), '') IS NOT NULL
            GROUP BY LTRIM(RTRIM(ServeCert))
            ORDER BY COUNT(*) DESC"""
    )


def contact9(serial):
    return one(
        """SELECT Serial, LinkSerial, CaseSerial, FName, MInit, LName, email, BarCode
             FROM dbo.Contact9 WHERE Serial = ?""",
        (serial,),
    )


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
