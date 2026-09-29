"""Model-driven index recommendations with strict structural validation."""
import json
import re

from llm_client import GENERATION_SEED, normalize_chat_kwargs


TRADITIONAL_INDEX_DIALECTS = {"PostgreSQL", "SQL Server", "Oracle"}

_SYSTEM_PROMPT = """You are a senior database performance engineer.
Recommend only high-value indexes supported by the supplied business
requirement and canonical data model.

Return STRICT JSON only:
{
  "entities": [
    {
      "entity": "exact supplied entity name",
      "indexes": [
        {
          "name": "lower_snake_case index name beginning with idx_ or uidx_",
          "columns": ["exact supplied field name in left-to-right index order"],
          "unique": false,
          "access_pattern": "specific join/filter/order/range pattern this index supports",
          "rationale": "specific reason this column order is useful"
        }
      ]
    }
  ]
}

Rules:
- Include every supplied entity exactly once and in the supplied order. Use an
  empty indexes array when no additional index is justified.
- Recommend zero to five indexes per entity.
- Do not recommend an index solely because a field is PHI or PII.
- Do not recommend the primary/surrogate key by itself; its constraint already
  provides an index in conventional relational platforms.
- Do not duplicate a table's complete business-key column sequence; its UNIQUE
  constraint already provides an index.
- Prioritize foreign keys used in joins and composite indexes matching concrete
  access patterns implied by the requirement.
- For composite indexes, place equality/join columns first, followed by range
  or ordering columns. Column order must be justified.
- Do not recommend a standalone index on a boolean, generic status/type/flag,
  large text/description, or low-cardinality field unless the requirement
  provides a selective access pattern; prefer a composite index when suitable.
- Do not create redundant indexes where one recommendation is only a leftmost
  prefix of another recommendation on the same entity.
- Use unique=true only for a distinct uniqueness rule not already represented
  by the PK or business key.
- Every column must exist on that entity. Do not invent included columns,
  expressions, partial predicates, functions, or platform-specific syntax.
- access_pattern and rationale must be concrete and at least one sentence.
- The selected SQL dialect affects implementation, not logical column choice.
"""


class IndexRecommendationError(ValueError):
    """Raised when index recommendations are incomplete or unsafe."""


def _parse_json(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise IndexRecommendationError(f"index recommender returned invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise IndexRecommendationError("index recommender response must be a JSON object")
    return value


def _field_tokens(type_hint: str) -> set[str]:
    return set(re.split(r"[^A-Z0-9]+", str(type_hint).upper())) - {""}


def validate_recommendations(response: dict, entities: list[dict]) -> dict[str, list[dict]]:
    response_entities = response.get("entities")
    if not isinstance(response_entities, list):
        raise IndexRecommendationError("index recommender response is missing entities")

    expected_entities = [entity["name"] for entity in entities]
    actual_entities = [item.get("entity") for item in response_entities if isinstance(item, dict)]
    if actual_entities != expected_entities:
        raise IndexRecommendationError("index recommender entities do not exactly match the model")

    validated = {}
    global_names = set()
    for entity, recommended_entity in zip(entities, response_entities):
        indexes = recommended_entity.get("indexes")
        if not isinstance(indexes, list) or len(indexes) > 5:
            raise IndexRecommendationError(f"invalid index list for {entity['name']}")

        field_names = [field[0] for field in entity.get("fields", [])]
        primary_key = [
            name for name, type_hint in entity.get("fields", [])
            if "PK" in _field_tokens(type_hint)
        ]
        business_key = [
            name for name, type_hint in entity.get("fields", [])
            if "BK" in _field_tokens(type_hint)
        ]
        seen_sequences = []
        normalized = []
        for item in indexes:
            name = str(item.get("name", "")).strip().lower()
            columns = item.get("columns")
            unique = item.get("unique")
            access_pattern = str(item.get("access_pattern", "")).strip()
            rationale = str(item.get("rationale", "")).strip()

            if not re.fullmatch(r"(?:idx|uidx)_[a-z0-9_]+", name):
                raise IndexRecommendationError(f"invalid index name {name!r} for {entity['name']}")
            if name in global_names:
                raise IndexRecommendationError(f"duplicate index name {name}")
            if not isinstance(columns, list) or not 1 <= len(columns) <= 4:
                raise IndexRecommendationError(f"invalid columns for index {name}")
            if len(columns) != len(set(columns)) or any(column not in field_names for column in columns):
                raise IndexRecommendationError(f"index {name} contains duplicate or unknown columns")
            if unique is not True and unique is not False:
                raise IndexRecommendationError(f"index {name} unique must be boolean")
            if columns == primary_key or columns == business_key:
                raise IndexRecommendationError(f"index {name} duplicates an existing key constraint")
            if len(access_pattern) < 20 or len(rationale) < 20:
                raise IndexRecommendationError(f"index {name} needs a specific access pattern and rationale")
            if any(
                columns == existing
                or columns == existing[:len(columns)]
                or existing == columns[:len(existing)]
                for existing in seen_sequences
            ):
                raise IndexRecommendationError(f"index {name} is redundant with another recommendation")

            global_names.add(name)
            seen_sequences.append(columns)
            normalized.append({
                "name": name,
                "columns": columns,
                "unique": unique,
                "access_pattern": access_pattern,
                "rationale": rationale,
            })
        validated[entity["name"]] = normalized
    return validated


def recommend_indexes(
    client,
    deployment: str,
    requirement: str,
    industry: str,
    dialect: str,
    entities: list[dict],
) -> None:
    payload = {
        "business_requirement": requirement,
        "industry": industry,
        "sql_dialect": dialect,
        "entities": [
            {
                "name": entity["name"],
                "definition": entity.get("definition", ""),
                "fields": [
                    {"name": field_name, "type_and_role": type_hint}
                    for field_name, type_hint in entity.get("fields", [])
                ],
            }
            for entity in entities
        ],
    }
    kwargs = normalize_chat_kwargs(
        model=deployment,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, indent=2)},
        ],
        temperature=0,
        seed=GENERATION_SEED,
    )
    try:
        response = client.chat.completions.create(**kwargs)
        raw_text = response.choices[0].message.content
    except Exception as exc:
        raise IndexRecommendationError(f"index recommender model call failed: {exc}") from exc
    recommendations = validate_recommendations(_parse_json(raw_text), entities)
    for entity in entities:
        entity["indexRecommendations"] = recommendations[entity["name"]]


def _table_name(entity_name: str) -> str:
    snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", entity_name)
    return re.sub(r"[^A-Za-z0-9]+", "_", snake).strip("_").lower()


def build_index_ddl(entities: list[dict], dialect: str) -> str:
    recommendations = [
        (entity, index)
        for entity in entities
        for index in entity.get("indexRecommendations", [])
    ]
    if not recommendations:
        return "-- No additional indexes were justified by the modeled access patterns."

    lines = [f"-- Index recommendations for {dialect}"]
    for entity, index in recommendations:
        table = _table_name(entity["name"])
        columns = ", ".join(index["columns"])
        lines.extend([
            "",
            f"-- Access pattern: {index['access_pattern']}",
            f"-- Rationale: {index['rationale']}",
        ])
        if dialect in TRADITIONAL_INDEX_DIALECTS:
            unique = "UNIQUE " if index["unique"] else ""
            lines.append(f"CREATE {unique}INDEX {index['name']} ON {table} ({columns});")
        elif dialect == "Snowflake":
            lines.append(
                f"-- Snowflake: consider CLUSTER BY ({columns}) on {table} after validating pruning benefit and table size."
            )
        elif dialect == "Databricks":
            lines.append(
                f"-- Databricks: consider OPTIMIZE {table} ZORDER BY ({columns}) after validating workload benefit."
            )
        else:
            unique = "UNIQUE " if index["unique"] else ""
            lines.append(f"CREATE {unique}INDEX {index['name']} ON {table} ({columns});")
    return "\n".join(lines)


def build_index_summary(entities: list[dict], dialect: str) -> str:
    """A comment-only header block listing every recommended index up front.

    Rendered at the very top of the DDL artifact so reviewers see the indexing
    strategy immediately, while the executable CREATE INDEX statements stay
    after the CREATE TABLEs (an index cannot be created before its table)."""
    recommendations = [
        (entity, index)
        for entity in entities
        for index in entity.get("indexRecommendations", [])
    ]
    if not recommendations:
        return "-- Recommended indexes: none justified by the modeled access patterns."

    lines = [
        "-- ============================================================",
        f"-- Recommended indexes ({len(recommendations)}) for {dialect}",
        "-- Executable statements are emitted after the table definitions below.",
        "-- ============================================================",
    ]
    for entity, index in recommendations:
        table = _table_name(entity["name"])
        columns = ", ".join(index["columns"])
        kind = "UNIQUE " if index["unique"] else ""
        lines.append(f"--   {kind}{index['name']}: {table} ({columns})")
    return "\n".join(lines)
