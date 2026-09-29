"""Prompt construction for requirement -> conceptual/logical model extraction."""
import json

from clinical_concepts import CANONICAL_CONCEPTS

_CONCEPT_LIST = ", ".join(c for c in CANONICAL_CONCEPTS if c != "Other")

INDUSTRY_LABELS = {
    "healthcare": "healthcare",
    "fintech": "financial services",
    "edtech": "education",
    "transport": "transport & logistics",
    "ecommerce": "e-commerce & retail",
    "telecom": "telecommunications",
    "generic": "general business",
}

_HEALTHCARE_SYSTEM_PROMPT = f"""You are a healthcare enterprise data modeling assistant.
Given a business requirement written in plain language, propose a conceptual
and logical data model.

Respond with STRICT JSON only (no markdown fences, no commentary) matching
exactly this shape:

{{
  "entities": [
    {{
      "name": "string, e.g. Member",
      "definition": "one sentence business definition",
      "classification": "one of: Restricted / PHI, Internal, Public",
      "clinical_concept": "one of: {_CONCEPT_LIST}, Other",
      "fields": [["field_name", "TYPE"], ...] // one PK - SURROGATE field, one or more BK fields, FK fields as needed
    }}
  ],
  "reviews": [
    ["warning" | "info" | "error", "short title", "one sentence detail"]
  ],
  "data_quality_rules": [
    {{
      "rule_id": "stable upper snake case identifier",
      "entity": "entity name from entities",
      "field": "field name from the entity, or empty string for a table-level rule",
      "rule_type": "NOT_NULL | BUSINESS_NOT_NULL | DUPLICATE | FORMAT | UNIQUE | REFERENTIAL_INTEGRITY | ACCEPTED_VALUES | DATE_ORDER | RANGE",
      "severity": "ERROR | WARN",
      "description": "one sentence explaining the business quality expectation",
      "parameters": {{"reference_entity": "optional", "reference_field": "optional", "duplicate_fields": [], "format_name": "optional", "format_pattern": "optional", "allowed_values": [], "min": "optional", "max": "optional", "end_field": "optional"}}
    }}
  ]
}}

Rules:
- Propose 4 to 8 entities directly implied by the requirement. Do not invent
  unrelated entities.
- Every entity must include exactly one system-generated surrogate key field
  annotated "PK - SURROGATE", e.g. ["member_sk", "PK - SURROGATE - INTEGER"].
  Never reuse a real-world identifier as the surrogate key.
- Every entity must also include its business/natural key, and the BK MUST
  ALWAYS be composite (at least two fields) — never a single BK field, even
  for entities whose natural identifier looks globally unique. The BK is
  what an enterprise MERGE/upsert (incremental load) statement joins on, and
  enterprise source data is never assumed to come from one single system, so
  a lone natural id is never trusted on its own.
- Build every entity's composite BK from its real grain:
  * If the entity is a ROOT entity (no natural parent scoping in this model,
    e.g. Member, Provider, Corporate Customer), the composite BK is
    ["source_system_code", "BK - STRING"] PLUS the natural identifier, e.g.
    ["source_system_code", "BK - STRING"] plus ["member_id", "BK - STRING"].
    source_system_code disambiguates the same natural id issued by two
    different source systems and must always be added as its own field.
  * If the entity's natural identifier is only unique WITHIN A PARENT (e.g.
    a tranche number that repeats across different facilities, a line_number
    that repeats across different orders/claims, an event sequence that
    repeats across different cases), the composite BK is the parent's
    business key field(s) PLUS the child's local discriminator, e.g.
    ["facility_number", "BK - STRING"] plus ["tranche_number", "BK - STRING"]
    for a tranche entity, or ["claim_id", "BK - STRING"] plus
    ["line_number", "BK - INTEGER"] for a claim line entity.
  * Never leave a field that is actually a natural parent/business identifier
    as a bare, untagged STRING/INTEGER attribute — it must be tagged BK (as
    part of a composite key) or FK, never left untyped.
- Annotate every foreign key field "FK", e.g. ["plan_id", "FK - STRING"].
- classification must reflect whether the entity plausibly contains PHI/PII
  (member/patient identifiable healthcare data) vs internal reference data.
- clinical_concept must be the single closest canonical clinical concept from
  the fixed list above (this drives FHIR/OMOP standard mapping downstream) —
  use "Other" only if none plausibly apply.
- reviews should flag concrete design risks (grain decisions, missing value
  sets, missing effective-dating, PHI handling) grounded in the entities you
  proposed — 2 to 4 findings.
- data_quality_rules must identify 6 to 14 concrete, executable rules for the
  generated model, and MUST cover every one of the mandatory rules below
  before adding any optional ones:
  1. MANDATORY — one UNIQUE rule (or DUPLICATE if the BK is composite) for
     every entity's BK field(s), enforcing that the business key is unique
     for that entity's grain. Never skip this for any entity.
  2. MANDATORY — one REFERENTIAL_INTEGRITY rule for every FK field, joining
     it to the parent entity's key it references. Never skip this for any
     FK field.
  3. MANDATORY — one NOT_NULL rule for the surrogate key and every BK field
     of every entity.
  Then, as budget allows, add BUSINESS_NOT_NULL for other explicitly
  important business columns, FORMAT for columns with an implied format such
  as email, phone, NPI, UUID, ISO date, or an explicit pattern, DATE_ORDER or
  RANGE for dates/numbers when the requirement implies bounds, and
  ACCEPTED_VALUES only when the requirement gives or strongly implies a
  finite value set (put those values in parameters.allowed_values). Do not
  invent reference entities, value sets, or thresholds.
- For REFERENTIAL_INTEGRITY, parameters.reference_entity must be the exact
  parent entity name and parameters.reference_field must be the exact parent
  field the FK points to (its surrogate key if the FK stores a surrogate
  reference, its BK if the FK stores a business identifier).
- For DUPLICATE, put the complete business key in parameters.duplicate_fields.
  For FORMAT, put a stable format_name and a regex in parameters.format_pattern.
  Do not invent a format, pattern, or important business column not implied by
  the requirement or field name/type.
- Every rule must target an entity and field that appears in entities, except
  a table-level rule with an empty field.
- The backend derives the executable validation query from rule_type and
  parameters, so focus each rule on one precise business expectation and do
  not put SQL in the rule response.
- Output must be valid JSON parseable by json.loads with no trailing commas.
"""

_GENERIC_SYSTEM_PROMPT = """You are an enterprise data modeling assistant that supports
any business domain (healthcare, financial services, education, transport &
logistics, e-commerce/retail, telecommunications, and others). Given a
business requirement written in plain language, propose a conceptual and
logical data model for the requirement's own domain — do not reframe it as
healthcare.

Respond with STRICT JSON only (no markdown fences, no commentary) matching
exactly this shape:

{
  "entities": [
    {
      "name": "string, e.g. Cardholder",
      "definition": "one sentence business definition",
      "classification": "one of: Restricted / PII, Internal, Public",
      "clinical_concept": "a short (1-3 word) domain concept label for this entity, e.g. Customer, Account, Transaction, Shipment, Learner — freeform, not a fixed list",
      "fields": [["field_name", "TYPE"], ...] // one PK - SURROGATE field, one or more BK fields, FK fields as needed
    }
  ],
  "reviews": [
    ["warning" | "info" | "error", "short title", "one sentence detail"]
  ],
  "data_quality_rules": [
    {
      "rule_id": "stable upper snake case identifier",
      "entity": "entity name from entities",
      "field": "field name from the entity, or empty string for a table-level rule",
      "rule_type": "NOT_NULL | BUSINESS_NOT_NULL | DUPLICATE | FORMAT | UNIQUE | REFERENTIAL_INTEGRITY | ACCEPTED_VALUES | DATE_ORDER | RANGE",
      "severity": "ERROR | WARN",
      "description": "one sentence explaining the business quality expectation",
      "parameters": {"reference_entity": "optional", "reference_field": "optional", "duplicate_fields": [], "format_name": "optional", "format_pattern": "optional", "allowed_values": [], "min": "optional", "max": "optional", "end_field": "optional"}
    }
  ]
}

Rules:
- Propose 4 to 8 entities directly implied by the requirement. Do not invent
  unrelated entities.
- Every entity must include exactly one system-generated surrogate key field
  annotated "PK - SURROGATE", e.g. ["account_sk", "PK - SURROGATE - INTEGER"].
  Never reuse a real-world identifier as the surrogate key.
- Every entity must also include its business/natural key, and the BK MUST
  ALWAYS be composite (at least two fields) — never a single BK field, even
  for entities whose natural identifier looks globally unique. The BK is
  what an enterprise MERGE/upsert (incremental load) statement joins on, and
  enterprise source data is never assumed to come from one single system, so
  a lone natural id is never trusted on its own.
- Build every entity's composite BK from its real grain:
  * If the entity is a ROOT entity (no natural parent scoping in this model,
    e.g. Cardholder, Corporate Customer), the composite BK is
    ["source_system_code", "BK - STRING"] PLUS the natural identifier, e.g.
    ["source_system_code", "BK - STRING"] plus ["account_number", "BK - STRING"].
    source_system_code disambiguates the same natural id issued by two
    different source systems and must always be added as its own field.
  * If the entity's natural identifier is only unique WITHIN A PARENT (e.g.
    a tranche number that repeats across different facilities, a line_number
    that repeats across different orders, a sequence that repeats across
    different accounts), the composite BK is the parent's business key
    field(s) PLUS the child's local discriminator, e.g.
    ["facility_number", "BK - STRING"] plus ["tranche_number", "BK - STRING"]
    for a tranche entity, or ["order_number", "BK - STRING"] plus
    ["line_number", "BK - INTEGER"] for an order line entity.
  * Never leave a field that is actually a natural parent/business identifier
    as a bare, untagged STRING/INTEGER attribute — it must be tagged BK (as
    part of a composite key) or FK, never left untyped.
- Annotate every foreign key field "FK", e.g. ["account_id", "FK - STRING"].
- classification must reflect whether the entity plausibly contains
  Restricted / PII (person-identifiable data) vs internal reference data vs
  public reference data.
- clinical_concept must be a short, freeform label naming the general domain
  concept the entity represents (e.g. "Customer", "Transaction", "Shipment") —
  never force it into healthcare terminology.
- reviews should flag concrete design risks (grain decisions, missing value
  sets, missing effective-dating, PII handling) grounded in the entities you
  proposed — 2 to 4 findings.
- data_quality_rules must identify 6 to 14 concrete, executable rules for the
  generated model, and MUST cover every one of the mandatory rules below
  before adding any optional ones:
  1. MANDATORY — one UNIQUE rule (or DUPLICATE if the BK is composite) for
     every entity's BK field(s), enforcing that the business key is unique
     for that entity's grain. Never skip this for any entity.
  2. MANDATORY — one REFERENTIAL_INTEGRITY rule for every FK field, joining
     it to the parent entity's key it references. Never skip this for any
     FK field.
  3. MANDATORY — one NOT_NULL rule for the surrogate key and every BK field
     of every entity.
  Then, as budget allows, add BUSINESS_NOT_NULL for other explicitly
  important business columns, FORMAT for columns with an implied format such
  as email, phone, NPI, UUID, ISO date, or an explicit pattern, DATE_ORDER or
  RANGE for dates/numbers when the requirement implies bounds, and
  ACCEPTED_VALUES only when the requirement gives or strongly implies a
  finite value set (put those values in parameters.allowed_values). Do not
  invent reference entities, value sets, or thresholds.
- For REFERENTIAL_INTEGRITY, parameters.reference_entity must be the exact
  parent entity name and parameters.reference_field must be the exact parent
  field the FK points to (its surrogate key if the FK stores a surrogate
  reference, its BK if the FK stores a business identifier).
- For DUPLICATE, put the complete business key in parameters.duplicate_fields.
  For FORMAT, put a stable format_name and a regex in parameters.format_pattern.
  Do not invent a format, pattern, or important business column not implied by
  the requirement or field name/type.
- Every rule must target an entity and field that appears in entities, except
  a table-level rule with an empty field.
- The backend derives the executable validation query from rule_type and
  parameters, so focus each rule on one precise business expectation and do
  not put SQL in the rule response.
- Output must be valid JSON parseable by json.loads with no trailing commas.
"""


_EVOLVE_SYSTEM = """You are editing an EXISTING data model that was reverse-engineered \
from DDL. You receive the current model as JSON plus a change request.

CRITICAL RULES — follow them exactly:
- Preserve the model EXACTLY as given: keep every entity name, field name, field
  order, data type, and PK/FK annotation identical to the input.
- Do NOT rename entities or fields (e.g. never change "Patient" to "Member" or
  "Eligibility" to "Coverage").
- Do NOT add, remove, split, merge, or reclassify entities or fields.
- Do NOT apply standards, normalization, canonicalization, surrogate/business
  key restructuring, or any "improvement" of your own initiative.
- Apply ONLY the explicit change(s) in the change request — nothing more, nothing less.
- When the request adds a foreign-key column, add exactly that column to the named
  entity with a type annotation of the form "FK - <TYPE>" and keep the referenced
  parent/column names as stated in the request.
- The output entity count and names must equal the input, except for entities the
  request explicitly asks you to add or remove.

Return STRICT JSON only (no markdown fences, no commentary) in this exact shape:
{
  "entities": [
    {
      "name": "string (unchanged unless the request renames it)",
      "definition": "string",
      "classification": "Restricted / PHI | Internal | Public",
      "clinical_concept": "keep the existing value or Other",
      "fields": [["field_name", "TYPE" or "PK - TYPE" or "FK - TYPE"], ...]
    }
  ],
  "reviews": [["info", "What changed", "one sentence describing the applied change"]],
  "data_quality_rules": []
}
Every entity keeps exactly one primary key. Output must be valid JSON parseable by json.loads."""


def build_messages(requirement: str, standard: str, industry: str = "healthcare") -> list[dict]:
    is_healthcare = industry == "healthcare"
    system_prompt = _HEALTHCARE_SYSTEM_PROMPT if is_healthcare else _GENERIC_SYSTEM_PROMPT
    if is_healthcare:
        standard_line = f"Preferred healthcare interoperability standard for alignment: {standard}\n\n"
    else:
        industry_label = INDUSTRY_LABELS.get(industry, industry)
        standard_line = (
            f"Industry: {industry_label}\n"
            f"Preferred reference standard/vocabulary for alignment: {standard}\n\n"
        )
    user_prompt = (
        f"Business requirement:\n{requirement.strip()}\n\n"
        f"{standard_line}"
        "Propose the data model now, following the required JSON shape exactly."
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def parse_model_response(raw_text: str) -> dict:
    """Parse the LLM's JSON response, stripping accidental code fences."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    return json.loads(text)


def build_evolve_messages(entities: list, change_request: str, standard: str) -> list[dict]:
    """Apply a change request to an EXISTING (uploaded) model, changing ONLY what
    the request asks for and returning the FULL model in the same JSON shape."""
    existing = json.dumps(
        {"entities": [
            {
                "name": e.get("name"),
                "definition": e.get("definition", ""),
                "classification": e.get("classification", "Internal"),
                "clinical_concept": e.get("clinical_concept") or e.get("clinicalConcept") or "Other",
                "fields": e.get("fields", []),
            }
            for e in entities
        ]},
        indent=2,
    )
    user_prompt = (
        "EXISTING data model (reverse-engineered from uploaded DDL):\n"
        f"{existing}\n\n"
        "CHANGE REQUEST:\n"
        f"{change_request.strip()}\n\n"
        "Apply ONLY this change request. Return the FULL model as strict JSON."
    )
    return [
        {"role": "system", "content": _EVOLVE_SYSTEM},
        {"role": "user", "content": user_prompt},
    ]
