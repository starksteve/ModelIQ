"""Parse uploaded SQL DDL into ModelIQ's entity structure.

Turns CREATE TABLE statements (any common dialect) into the same
{name, definition, classification, clinical_concept, fields[[name, type_hint]]}
shape the LLM produces, so imported models flow through the identical reuse /
artifact / diagram pipeline. Type hints embed PK / FK markers the rest of the
app already understands.
"""
from __future__ import annotations

import re

_PII_HINTS = ("name", "ssn", "dob", "birth", "email", "phone", "address", "mrn", "gender", "race", "ethnicity")

# Matches a CREATE ... TABLE header up to the table name (the column-list "(" may
# be preceded by clauses like CLUSTER BY (...), so it is located separately).
_HEADER_RE = re.compile(
    r"create\s+(?:or\s+replace\s+)?"
    r"(?:(?:transient|temporary|temp|volatile|global|local|iceberg|hybrid|dynamic)\s+)*"
    r"table\s+(?:if\s+not\s+exists\s+)?"
    r"([`\"\[\]\w\.\$]+)",
    re.IGNORECASE,
)


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"--[^\n]*", " ", sql)
    return sql


def _extract_balanced(text: str, open_idx: int) -> str | None:
    """Return the substring inside the parentheses starting at open_idx, honoring
    nested parens and quoted strings."""
    depth, i, n = 0, open_idx, len(text)
    in_s = in_d = False
    while i < n:
        ch = text[i]
        if in_s:
            if ch == "'":
                in_s = False
        elif in_d:
            if ch == '"':
                in_d = False
        elif ch == "'":
            in_s = True
        elif ch == '"':
            in_d = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1 : i]
        i += 1
    return None


def _find_column_paren(text: str, start: int) -> int:
    """From just after the table name, find the column-list '(' , skipping
    pre-column clauses such as CLUSTER BY (...). Returns -1 for CTAS/LIKE/CLONE
    (no column list) or if none is found."""
    i, n = start, len(text)
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if i >= n:
            return -1
        if text[i] == "(":
            return i
        # CTAS / clone / like / using template -> no parseable column list
        if re.match(r"(as|like|clone|using)\b", text[i:], re.IGNORECASE):
            return -1
        # CLUSTER BY (...) or CLUSTER BY LINEAR(...) sits before the column list.
        m = re.match(r"cluster\s+by\s*(?:[A-Za-z_]\w*\s*)?", text[i:], re.IGNORECASE)
        if m:
            i += m.end()
            if i < n and text[i] == "(":
                body = _extract_balanced(text, i)
                if body is None:
                    return -1
                i += len(body) + 2
            continue
        # Otherwise skip one clause word (and a '= value'); never eat a '(' here
        # so the real column list is preserved.
        w = re.match(r"[A-Za-z_][\w$]*", text[i:])
        if not w:
            return -1
        i += w.end()
        while i < n and text[i].isspace():
            i += 1
        if i < n and text[i] == "=":
            i += 1
            while i < n and text[i].isspace():
                i += 1
            v = re.match(r"'[^']*'|[^\s(;]+", text[i:])
            if v:
                i += v.end()
    return -1


def _pascal(raw: str) -> str:
    raw = raw.split(".")[-1].strip('"`[] ')
    return "".join(p.capitalize() for p in re.split(r"[_\s]+", raw)) or raw


def _split_columns(body: str) -> list[str]:
    parts, depth, cur = [], 0, ""
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts


def _classify(field_names: list[str]) -> str:
    joined = " ".join(field_names).lower()
    return "Restricted / PHI" if any(h in joined for h in _PII_HINTS) else "Internal"


def parse_ddl(sql_text: str) -> tuple[list[dict], list[list]]:
    """Return (entities, reviews) parsed from one or more DDL scripts."""
    entities: list[dict] = []
    sql_text = _strip_comments(sql_text)

    for match in _HEADER_RE.finditer(sql_text):
        table_raw = match.group(1)
        name = _pascal(table_raw)
        paren = _find_column_paren(sql_text, match.end())
        if paren == -1:
            continue
        body = _extract_balanced(sql_text, paren)
        if body is None:
            continue

        pk_cols: list[str] = []
        fk_cols: dict[str, str] = {}  # col -> referenced table
        columns: list[tuple[str, str]] = []  # (name, sql_type)

        for col in _split_columns(body):
            low = col.lower()
            # PRIMARY KEY (...) or CONSTRAINT <name> PRIMARY KEY (...)
            if "primary key" in low and low.startswith(("primary key", "constraint")):
                inside = re.search(r"primary\s+key\s*\((.*?)\)", col, re.IGNORECASE)
                if inside:
                    pk_cols += [c.strip('"`[] ') for c in inside.group(1).split(",")]
                continue
            if (low.startswith(("foreign key", "constraint"))) and "references" in low:
                m = re.search(
                    r"foreign\s+key\s*\((.*?)\).*?references\s+([`\"\[\]\w\.]+)",
                    col, re.IGNORECASE | re.DOTALL,
                )
                if m:
                    fcol = m.group(1).split(",")[0].strip('"`[] ')
                    fk_cols[fcol] = _pascal(m.group(2))
                continue
            if low.startswith(("unique", "check", "key ", "index")):
                continue
            tokens = col.split()
            if len(tokens) < 2:
                continue
            cname = tokens[0].strip('"`[] ')
            ctype = tokens[1].strip('"`[] ')
            columns.append((cname, ctype))
            if "primary key" in low:
                pk_cols.append(cname)
            inline = re.search(r"references\s+([`\"\[\]\w\.]+)", col, re.IGNORECASE)
            if inline:
                fk_cols[cname] = _pascal(inline.group(1))

        if not columns:
            continue

        fields = []
        for cname, ctype in columns:
            if cname in pk_cols:
                type_hint = f"PK - {ctype.upper()}"
            elif cname in fk_cols:
                type_hint = f"FK - {ctype.upper()}"
            else:
                type_hint = ctype.upper()
            fields.append([cname, type_hint])

        table_label = table_raw.split(".")[-1].strip('"`[] ')
        entities.append({
            "name": name,
            "definition": f"Imported table '{table_label}' reverse-engineered from uploaded DDL.",
            "classification": _classify([c for c, _ in columns]),
            "clinical_concept": "",  # blank -> resolve_entities infers the real concept
            "fields": fields,
        })

    reviews = _build_reviews(entities)
    return entities, reviews


def _build_reviews(entities: list[dict]) -> list[list]:
    """Deterministic design-review findings for an imported model."""
    reviews: list[list] = [[
        "info",
        f"Imported {len(entities)} table(s) from DDL",
        "This model was reverse-engineered from uploaded DDL; run reuse and impact checks before evolving it.",
    ]]
    for e in entities:
        has_pk = any("PK" in f[1].upper() for f in e["fields"])
        if not has_pk:
            reviews.append([
                "warning",
                f"No primary key detected on {e['name']}",
                "The parser found no PRIMARY KEY; confirm the grain and add a key before physical design.",
            ])
    pii = [e["name"] for e in entities if e["classification"] == "Restricted / PHI"]
    if pii:
        reviews.append([
            "warning",
            "PHI-bearing tables detected",
            f"{', '.join(pii)} appear to contain identifiable data; verify access controls and masking.",
        ])
    return reviews
