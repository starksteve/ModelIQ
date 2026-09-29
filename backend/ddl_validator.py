"""Deterministic validation of LLM-generated DDL before it is trusted.

Deliberately conservative: this is a lightweight structural/security check,
not a full SQL parser. Anything that fails these checks falls back to
artifact_builder.build_ddl() instead of being shown to the user.
"""
import re

from artifact_builder import _table_name

_FORBIDDEN_KEYWORDS = (
    "DROP", "DELETE", "TRUNCATE", "ALTER", "INSERT", "UPDATE",
    "GRANT", "REVOKE", "EXEC", "EXECUTE", "MERGE", "CALL",
)


def validate_ddl(sql: str, entities: list[dict]) -> tuple[bool, list[str]]:
    reasons = []

    if not sql or not sql.strip():
        return False, ["empty DDL"]

    upper_sql = sql.upper()

    for keyword in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", upper_sql):
            reasons.append(f"contains forbidden statement/keyword: {keyword}")

    create_table_count = len(re.findall(r"\bCREATE\s+TABLE\b", upper_sql))
    if create_table_count != len(entities):
        reasons.append(
            f"expected {len(entities)} CREATE TABLE statement(s), found {create_table_count}"
        )

    for entity in entities:
        table = _table_name(entity["name"])
        if table not in upper_sql:
            reasons.append(f"missing expected table {table}")
            continue
        for field_name, _ in entity["fields"]:
            column = re.sub(r"[^A-Za-z0-9]+", "_", field_name).strip("_").upper()
            if column not in upper_sql:
                reasons.append(f"missing expected column {table}.{column}")

    return (len(reasons) == 0, reasons)
