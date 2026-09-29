"""Deterministic artifact generation from a resolved entity list.

Kept separate from the LLM call on purpose: design-review artifacts must be
reproducible and syntactically valid every time, so they're built with plain
string templating over structured data rather than asked from the model.
"""
import re


DQ_RULE_TABLE = "OCDP_PRD_OPTUMCARE_OPERATIONS_DB.VALIDATION.ONBOARDING_DQ_RULES"


def _table_name(entity_name: str) -> str:
    # Split camelCase/PascalCase boundaries so "ClinicalEvent" -> CLINICAL_EVENT,
    # matching the UPPER_SNAKE_CASE convention the LLM is asked to use for DDL.
    snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", entity_name)
    return re.sub(r"[^A-Za-z0-9]+", "_", snake).strip("_").upper()


def _sql_type(type_hint: str) -> str:
    hint = type_hint.upper()
    if "DATE" in hint and "RANGE" not in hint:
        return "DATE"
    if "DATERANGE" in hint:
        return "VARCHAR(64)"
    if "INTEGER" in hint or "INT" == hint:
        return "INTEGER"
    return "VARCHAR(256)"


def _hint_tokens(type_hint: str) -> set[str]:
    # Word-split (not substring) so "SURROGATE"/"SUBSCRIPTION" etc never
    # false-match a bare "PK"/"BK"/"FK" tag.
    return set(re.split(r"[^A-Z0-9]+", type_hint.upper())) - {""}


def build_ddl(entities: list[dict]) -> str:
    statements = []
    for entity in entities:
        table = _table_name(entity["name"])
        lines = []
        business_key_cols = []
        for field_name, type_hint in entity["fields"]:
            col = field_name
            sql_type = _sql_type(type_hint)
            tokens = _hint_tokens(type_hint)
            suffix = " PRIMARY KEY" if "PK" in tokens else ""
            lines.append(f"  {col} {sql_type}{suffix}")
            if "BK" in tokens:
                business_key_cols.append(col)
        if business_key_cols:
            # Business/natural key(s): not the row's surrogate identity, but
            # still must be unique so incremental loads can MERGE on it.
            lines.append(f"  UNIQUE ({', '.join(business_key_cols)})")
        statements.append(f"CREATE TABLE {table} (\n" + ",\n".join(lines) + "\n);")
    return "\n\n".join(statements)


def build_contract(entities: list[dict], requirement: str) -> str:
    lines = [
        "apiVersion: v1",
        "kind: DataContract",
        "info:",
        f"  title: {requirement.strip()[:80]!r}",
        "  status: draft",
        "models:",
    ]
    for entity in entities:
        privacy_by_field = {
            item["field"]: item
            for item in entity.get("privacyClassifications", [])
        }
        lines.append(f"  {_table_name(entity['name'])}:")
        lines.append(f"    description: {entity['definition']!r}")
        lines.append(f"    classification: {entity['classification']!r}")
        lines.append(f"    privacyContext: {entity.get('privacyContext', 'UNCLASSIFIED')!r}")
        lines.append(f"    privacyContextRationale: {entity.get('privacyContextRationale', 'No model classification available.')!r}")
        lines.append("    fields:")
        for field_name, type_hint in entity["fields"]:
            privacy = privacy_by_field.get(field_name, {})
            lines.append(f"      {field_name}:")
            lines.append(f"        type: {type_hint!r}")
            lines.append(f"        privacyClassification: {privacy.get('category', 'UNCLASSIFIED')!r}")
            lines.append(f"        privacyRationale: {privacy.get('rationale', 'No model classification available.')!r}")
    return "\n".join(lines)


def build_dictionary(entities: list[dict]) -> str:
    rows = ["Entity,Attribute,Data Type,Key Role,Definition,Entity Classification,Privacy Context,Privacy Classification,Privacy Rationale"]
    for entity in entities:
        privacy_by_field = {
            item["field"]: item
            for item in entity.get("privacyClassifications", [])
        }
        for field_name, type_hint in entity["fields"]:
            privacy = privacy_by_field.get(field_name, {})
            rationale = _csv_quote(privacy.get("rationale", "No model classification available."))
            definition = _csv_quote(_column_definition(field_name, type_hint, entity))
            rows.append(
                f"{entity['name']},{field_name},{_sql_type(type_hint)},{_key_role(type_hint)},"
                f"{definition},{entity['classification']},"
                f"{entity.get('privacyContext', 'UNCLASSIFIED')},"
                f"{privacy.get('category', 'UNCLASSIFIED')},{rationale}"
            )
    return "\n".join(rows)


def _csv_quote(value) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _key_role(type_hint: str) -> str:
    tokens = _hint_tokens(type_hint)
    if "PK" in tokens:
        return "Surrogate key"
    if "BK" in tokens:
        return "Business key"
    if "FK" in tokens:
        return "Foreign key"
    return "Attribute"


def _column_definition(field_name: str, type_hint: str, entity: dict) -> str:
    """A per-column business definition derived from its key role and name.

    The LLM only emits (name, type) per field, so column-level text is built
    deterministically here rather than left as the repeated entity definition."""
    entity_label = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", entity["name"]).lower()
    tokens = _hint_tokens(type_hint)
    if "PK" in tokens:
        return f"System-generated surrogate key uniquely identifying each {entity_label} record."
    if "BK" in tokens:
        return f"Business/natural key identifying the {entity_label} record in the source system."
    if "FK" in tokens:
        base = re.sub(r"_(id|key|code|sk|fk)$", "", field_name.lower())
        related = base.replace("_", " ").strip() or "related"
        return f"Foreign key linking this {entity_label} to its related {related} record."
    normalized = re.sub(r"[^a-z0-9]", " ", field_name.lower())
    if "email" in normalized:
        return "Email address used for contact or identity matching."
    if "phone" in normalized:
        return "Telephone number used for contact."
    if "date" in normalized or "period" in normalized or "timestamp" in normalized or normalized.endswith(" at"):
        return f"Date or time establishing when this {entity_label} record applies."
    if "status" in normalized:
        return f"Business lifecycle status of the {entity_label} record."
    if "amount" in normalized or "balance" in normalized or "price" in normalized:
        return "Monetary amount recorded for this record."
    if "code" in normalized:
        return "Coded value classifying the record against a controlled list."
    if "name" in normalized:
        return "Human-readable business name or label."
    if "country" in normalized or "region" in normalized:
        return "Geographic location associated with the record."
    return f"Business attribute describing the {entity_label} record."



def _sql_literal(value) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _column_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", str(value)).strip("_").upper()


def _rule_expression(rule: dict) -> str:
    field = _column_name(rule.get("field", ""))
    rule_type = rule["rule_type"].upper()
    parameters = rule.get("parameters") or {}

    if rule_type == "NOT_NULL":
        return f"{field} IS NOT NULL"
    if rule_type == "BUSINESS_NOT_NULL":
        return f"{field} IS NOT NULL"
    if rule_type == "DUPLICATE":
        fields = [_column_name(value) for value in parameters.get("duplicate_fields", [])]
        fields = fields or [field]
        return f"COUNT(*) = COUNT(DISTINCT ({', '.join(fields)}))"
    if rule_type == "FORMAT":
        pattern = parameters.get("format_pattern", "")
        return f"REGEXP_LIKE(CAST({field} AS VARCHAR), {_sql_literal(pattern)})"
    if rule_type == "UNIQUE":
        return f"COUNT(*) = COUNT(DISTINCT {field})"
    if rule_type == "REFERENTIAL_INTEGRITY":
        parent_table = _table_name(parameters["reference_entity"])
        parent_field = re.sub(r"[^A-Za-z0-9]+", "_", parameters["reference_field"]).strip("_").upper()
        table = _table_name(rule["entity"])
        return f"ALL_VALUES_EXIST_IN({table}.{field}, {parent_table}.{parent_field})"
    if rule_type == "ACCEPTED_VALUES":
        values = parameters.get("allowed_values") or []
        return f"{field} IN ({', '.join(_sql_literal(value) for value in values)})"
    if rule_type == "DATE_ORDER":
        end_field = re.sub(r"[^A-Za-z0-9]+", "_", parameters["end_field"]).strip("_").upper()
        return f"{field} <= {end_field}"
    if rule_type == "RANGE":
        clauses = []
        if parameters.get("min") is not None:
            clauses.append(f"{field} >= {parameters['min']}")
        if parameters.get("max") is not None:
            clauses.append(f"{field} <= {parameters['max']}")
        return " AND ".join(clauses)
    return "TRUE"


def _validation_query(rule: dict) -> str:
    """Return a query that returns violating rows for the rule."""
    table = _table_name(rule["entity"])
    field = _column_name(rule.get("field", ""))
    rule_type = rule["rule_type"].upper()
    parameters = rule.get("parameters") or {}

    if rule_type == "NOT_NULL":
        return f"SELECT * FROM {table} WHERE {field} IS NULL;"
    if rule_type == "BUSINESS_NOT_NULL":
        return f"SELECT * FROM {table} WHERE {field} IS NULL;"
    if rule_type == "DUPLICATE":
        fields = [_column_name(value) for value in parameters.get("duplicate_fields", [])]
        fields = fields or [field]
        select_fields = ", ".join(fields)
        return f"SELECT {select_fields}, COUNT(*) AS DUPLICATE_COUNT FROM {table} GROUP BY {select_fields} HAVING COUNT(*) > 1;"
    if rule_type == "FORMAT":
        pattern = parameters.get("format_pattern", "")
        return f"SELECT * FROM {table} WHERE {field} IS NOT NULL AND NOT REGEXP_LIKE(CAST({field} AS VARCHAR), {_sql_literal(pattern)});"
    if rule_type == "UNIQUE":
        return f"SELECT {field}, COUNT(*) AS DUPLICATE_COUNT FROM {table} GROUP BY {field} HAVING COUNT(*) > 1;"
    if rule_type == "REFERENTIAL_INTEGRITY":
        parent_table = _table_name(parameters["reference_entity"])
        parent_field = re.sub(r"[^A-Za-z0-9]+", "_", parameters["reference_field"]).strip("_").upper()
        return f"SELECT child.* FROM {table} child LEFT JOIN {parent_table} parent ON child.{field} = parent.{parent_field} WHERE child.{field} IS NOT NULL AND parent.{parent_field} IS NULL;"
    if rule_type == "ACCEPTED_VALUES":
        values = parameters.get("allowed_values") or []
        return f"SELECT * FROM {table} WHERE {field} NOT IN ({', '.join(_sql_literal(value) for value in values)});"
    if rule_type == "DATE_ORDER":
        end_field = re.sub(r"[^A-Za-z0-9]+", "_", parameters["end_field"]).strip("_").upper()
        return f"SELECT * FROM {table} WHERE {field} > {end_field};"
    if rule_type == "RANGE":
        clauses = []
        if parameters.get("min") is not None:
            clauses.append(f"{field} < {parameters['min']}")
        if parameters.get("max") is not None:
            clauses.append(f"{field} > {parameters['max']}")
        return f"SELECT * FROM {table} WHERE {' OR '.join(clauses)};"
    return f"SELECT * FROM {table} WHERE FALSE;"


def enrich_dq_rules(entities: list[dict], rules: list[dict]) -> list[dict]:
    """Attach deterministic validation SQL to valid model-generated rules."""
    entity_lookup = {
        re.sub(r"[^a-z0-9]", "", entity["name"].lower()): entity
        for entity in entities
    }
    enriched = []
    for rule in rules:
        entity = entity_lookup.get(re.sub(r"[^a-z0-9]", "", str(rule.get("entity", "")).lower()))
        rule_type = str(rule.get("rule_type", "")).upper()
        if not entity or rule_type not in {
            "NOT_NULL", "BUSINESS_NOT_NULL", "DUPLICATE", "FORMAT", "UNIQUE",
            "REFERENTIAL_INTEGRITY", "ACCEPTED_VALUES", "DATE_ORDER", "RANGE"
        }:
            continue

        enriched_rule = dict(rule)
        enriched_rule["entity"] = entity["name"]
        enriched_rule["rule_type"] = rule_type
        field_lookup = {
            re.sub(r"[^a-z0-9]", "", field[0].lower()): field[0]
            for field in entity.get("fields", [])
        }
        field = field_lookup.get(re.sub(r"[^a-z0-9]", "", str(rule.get("field", "")).lower()))
        if not field:
            continue
        enriched_rule["field"] = field

        parameters = dict(rule.get("parameters") or {})
        if rule_type == "DUPLICATE":
            duplicate_fields = [
                field_lookup.get(re.sub(r"[^a-z0-9]", "", str(value).lower()))
                for value in parameters.get("duplicate_fields", [])
            ]
            if not duplicate_fields or any(value is None for value in duplicate_fields):
                continue
            parameters["duplicate_fields"] = duplicate_fields
        elif rule_type == "FORMAT":
            if not parameters.get("format_name") or not parameters.get("format_pattern"):
                continue
        elif rule_type == "REFERENTIAL_INTEGRITY":
            parent = entity_lookup.get(
                re.sub(r"[^a-z0-9]", "", str(parameters.get("reference_entity", "")).lower())
            )
            if not parent:
                continue
            parent_fields = {
                re.sub(r"[^a-z0-9]", "", parent_field[0].lower()): parent_field[0]
                for parent_field in parent.get("fields", [])
            }
            reference_field = parent_fields.get(
                re.sub(r"[^a-z0-9]", "", str(parameters.get("reference_field", "")).lower())
            )
            if not reference_field:
                continue
            parameters.update(reference_entity=parent["name"], reference_field=reference_field)
        elif rule_type == "DATE_ORDER":
            end_field = field_lookup.get(
                re.sub(r"[^a-z0-9]", "", str(parameters.get("end_field", "")).lower())
            )
            if not end_field or end_field == field:
                continue
            parameters["end_field"] = end_field
        elif rule_type == "ACCEPTED_VALUES" and not parameters.get("allowed_values"):
            continue
        elif rule_type == "RANGE" and parameters.get("min") is None and parameters.get("max") is None:
            continue

        enriched_rule["parameters"] = parameters
        enriched_rule["validation_query"] = _validation_query(enriched_rule)
        enriched.append(enriched_rule)
    return enriched


def build_dq_ddl(entities: list[dict], rules: list[dict]) -> str:
    """Create the onboarding rule registry and executable rule statements."""
    statements = [
        f"CREATE TABLE {DQ_RULE_TABLE} (\n"
        "  RULE_ID VARCHAR(128) PRIMARY KEY,\n"
        "  ENTITY_NAME VARCHAR(256) NOT NULL,\n"
        "  FIELD_NAME VARCHAR(256),\n"
        "  RULE_TYPE VARCHAR(64) NOT NULL,\n"
        "  SEVERITY VARCHAR(16) NOT NULL,\n"
        "  RULE_DESCRIPTION VARCHAR(2000) NOT NULL,\n"
        "  CHECK_EXPRESSION VARCHAR(4000) NOT NULL,\n"
        "  VALIDATION_QUERY VARCHAR(8000) NOT NULL,\n"
        "  FORMAT_NAME VARCHAR(128),\n"
        "  ACTIVE_FLAG BOOLEAN NOT NULL\n"
        ");"
    ]
    valid_entities = {entity["name"] for entity in entities}
    for rule in rules:
        if rule.get("entity") not in valid_entities:
            continue
        fields = [
            rule.get("rule_id", "DQ_RULE"), rule["entity"], rule.get("field", ""),
            rule["rule_type"].upper(), rule.get("severity", "WARN").upper(),
            rule.get("description", ""), _rule_expression(rule),
            rule.get("validation_query") or _validation_query(rule),
            (rule.get("parameters") or {}).get("format_name", ""),
        ]
        values = ", ".join(_sql_literal(value) for value in fields)
        statements.append(
            f"INSERT INTO {DQ_RULE_TABLE} "
            "(RULE_ID, ENTITY_NAME, FIELD_NAME, RULE_TYPE, SEVERITY, "
            f"RULE_DESCRIPTION, CHECK_EXPRESSION, VALIDATION_QUERY, FORMAT_NAME, ACTIVE_FLAG) VALUES ({values}, TRUE);"
        )
    return "\n\n".join(statements)
