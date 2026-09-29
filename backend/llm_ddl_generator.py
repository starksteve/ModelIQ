"""LLM-driven DDL generation for a selectable SQL dialect.

This is intentionally separate from artifact_builder.build_ddl(), which stays
in place as the deterministic fallback/baseline. The flow is:

    entities (canonical model) -> LLM produces dialect-specific DDL
                                -> ddl_validator checks it
                                -> caller falls back to artifact_builder
                                   if the LLM output doesn't pass validation

Keeping the LLM out of "requirement -> raw SQL -> execute" entirely: it only
ever sees the already-resolved, already-reviewed entity list, and its output
is always validated before use.
"""
import json
import re

from llm_client import GENERATION_SEED, normalize_chat_kwargs

SUPPORTED_DIALECTS = [
    "ANSI SQL",
    "Snowflake",
    "PostgreSQL",
    "SQL Server",
    "Oracle",
    "Databricks",
]

_SYSTEM_PROMPT = """You are a senior data engineer generating SQL DDL from an \
already-approved canonical data model. Output ONLY `CREATE TABLE` statements \
(one per entity, in the order given) as raw SQL - no markdown fences, no \
commentary, no other statement types (no INSERT/UPDATE/DELETE/DROP/ALTER/GRANT).

Rules:
- Table and column names: UPPER_SNAKE_CASE, derived from the entity/field names given.
- Every field in the input must appear as a column in the output.
- Mark the field tagged PK - SURROGATE in the input with `PRIMARY KEY` inline;
  mark foreign keys with a trailing `-- FK` comment on that column's line (do
  not add REFERENCES clauses unless the target table is unambiguous from the
  field name).
- Fields tagged BK in the input are the business/natural key: do NOT mark them
  PRIMARY KEY. Instead add one table-level `UNIQUE (...)` constraint per table
  listing all of that table's BK column(s) together (composite if more than one).
- Choose SQL types appropriate for the target dialect and the given type hints
  (e.g. STRING/CODE -> VARCHAR, DATE -> DATE, JSON -> the dialect's JSON/VARIANT
  type, DATERANGE -> VARCHAR(64)).
- Target SQL dialect for this request: {dialect}.
"""


def _build_messages(entities: list[dict], dialect: str) -> list[dict]:
    canonical = [
        {
            "name": entity["name"],
            "fields": [{"name": f, "type": t} for f, t in entity["fields"]],
        }
        for entity in entities
    ]
    return [
        {"role": "system", "content": _SYSTEM_PROMPT.format(dialect=dialect)},
        {"role": "user", "content": json.dumps({"entities": canonical}, indent=2)},
    ]


def _strip_code_fence(text: str) -> str:
    match = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text.strip()


def generate_llm_ddl(client, deployment: str, entities: list[dict], dialect: str) -> str:
    """Calls the LLM to produce dialect-specific DDL. Raises on any API error;
    caller is responsible for falling back to the deterministic builder."""
    messages = _build_messages(entities, dialect)
    chat_kwargs = normalize_chat_kwargs(model=deployment, messages=messages, temperature=0.1, seed=GENERATION_SEED)
    response = client.chat.completions.create(**chat_kwargs)
    raw_text = response.choices[0].message.content or ""
    return _strip_code_fence(raw_text)
