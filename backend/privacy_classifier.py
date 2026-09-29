"""Model-driven, validated column-level PHI/PII classification."""
import json

from llm_client import GENERATION_SEED, normalize_chat_kwargs


ALLOWED_CATEGORIES = {"NONE", "PII", "PHI"}
ALLOWED_RECORD_CONTEXTS = {
    "HIPAA_DESIGNATED_RECORD_SET",
    "SEPARATE_HEALTHCARE_ADMIN",
    "NON_HEALTHCARE",
}
DOB_FIELD_NAMES = {"birth_date", "date_of_birth", "dob"}

INDUSTRY_PRIVACY_GUIDANCE = {
    "healthcare": (
        "Apply the HIPAA designated-record-set distinction. Individually identifiable information "
        "about health, care, treatment, or healthcare payment is PHI. Identifying non-health fields "
        "such as a patient name, MRN, date of birth, address, phone, email, or insurance identifier "
        "are also PHI when maintained in the same designated record set. The same identifying fields "
        "are PII when maintained separately for a non-health purpose such as marketing, conference "
        "registration, transport contact-only coordination, parking, or a separate administrative "
        "contact list. Public provider directories and clinical code-set reference tables are not "
        "PHI merely because they are healthcare data."
    ),
    "fintech": (
        "PHI does not apply unless the field actually contains healthcare information. Customer "
        "identity, account/card identifiers, authentication data, transaction-to-person links, and "
        "personal financial account details are PII. Market prices, product definitions, merchant "
        "reference data, and non-personal aggregates are NONE. Do not relabel all confidential "
        "financial data as PII when it does not identify or link to a natural person."
    ),
    "edtech": (
        "PHI does not apply unless an actual health record is modeled. Student, guardian, and teacher "
        "identifiers/contact details are PII. Student-linked enrollment, attendance, grades, and "
        "learning records are PII because they are linkable educational records. Public course "
        "catalogs, curricula, and aggregate metrics are NONE."
    ),
    "transport": (
        "PHI does not apply unless an actual health record is modeled. Passenger, driver, consignee, "
        "contact, precise person-linked trip/location, ticket, and shipment-recipient identifiers are "
        "PII. Vehicle classes, route definitions, depot metadata, and non-person-linked operational "
        "events are NONE."
    ),
    "ecommerce": (
        "PHI does not apply unless an actual health record is modeled. Customer identifiers, contact "
        "details, loyalty accounts, shipping addresses, and customer-linked orders are PII. Product "
        "catalog data, inventory facts, generic order states, and non-person-linked aggregates are NONE."
    ),
    "telecom": (
        "PHI does not apply unless an actual health record is modeled. Subscriber identity/contact "
        "details, phone numbers, device or account identifiers linkable to a subscriber, precise "
        "location, and subscriber-linked usage records are PII. Network topology, equipment models, "
        "tariff definitions, and aggregate performance metrics are NONE."
    ),
    "generic": (
        "Use the supplied business domain. PHI applies only to individually linkable healthcare "
        "information. PII applies only to information that identifies, contacts, locates, authenticates, "
        "or is reasonably linkable to a natural person. Confidential business data without a natural-"
        "person link is NONE for this PHI/PII taxonomy."
    ),
}

_SYSTEM_PROMPT = """You are a privacy classification specialist.
Classify every supplied data-model field using its field semantics, entity
meaning, business requirement, industry, and row context.

Return STRICT JSON only:
{
  "entities": [
    {
      "entity": "exact supplied entity name",
      "record_context": "HIPAA_DESIGNATED_RECORD_SET | SEPARATE_HEALTHCARE_ADMIN | NON_HEALTHCARE",
      "context_rationale": "specific one-sentence reason this entity belongs to that record context",
      "fields": [
        {
          "field": "exact supplied field name",
          "category": "NONE | PII | PHI",
          "rationale": "specific one-sentence evidence for this field in this entity"
        }
      ]
    }
  ]
}

Classification definitions:
- PII: information that directly identifies, authenticates, contacts, locates,
  or is reasonably linkable to a natural person outside a healthcare context.
  Examples include a person's name, personal email/phone/address, government
  identifier, financial account identifier, precise location, or biometric.
- PHI: individually identifiable information maintained in a HIPAA designated
  record set. This includes health status, care, treatment, medication,
  diagnosis, procedure, laboratory result, clinical event, healthcare payment,
  and identifying non-health fields maintained in that same record set.
- PII: information that identifies or is linkable to a person but is not
  maintained in a designated record set and does not relate to that person's
  health, care, treatment, or healthcare payment.
- NONE: no supported PHI or PII meaning in the supplied context.

Required reasoning rules:
- Classify from meaning and context, never from an entity-level Restricted
  label alone.
- Do not classify every field in a sensitive entity. Status codes, reference
  codes, generic timestamps, measures, and technical metadata are NONE unless
  their supplied semantics make them person-identifying or health information.
- Do not classify a field merely because its name ends in "_id", "_key",
  "_sk", or because it is PK/FK/BK. Determine what the identifier identifies.
- Every system-generated surrogate key and surrogate-key reference is NONE,
  including fields ending in "_sk" and fields whose role contains SURROGATE.
  These are technical warehouse keys with no intrinsic personal or clinical
  meaning. Never classify them as PHI or PII.
- A source/business patient, member, person, account, subscriber, or customer
  identifier is PHI in a designated healthcare record and PII in a separate
  non-health or administrative record.
- A foreign key is classified from what it references: PII when it carries a
  person/business identifier, but NONE when it carries only an opaque internal
  surrogate key.
- A diagnosis/procedure/lab/medication/service-date field on an individual
  healthcare event is PHI. The same code on a public/reference definition
  table is NONE.
- Date of birth is PHI in a designated healthcare record and PII in a separate
  contact/administrative record. A generic created_at/updated_at timestamp is
  normally NONE.
- Project-specific date policy: no date, date-time, timestamp, period-start,
  period-end, service-date, encounter-date, admission/discharge-date,
  effective-date, measurement-date, or result-date field is PHI except date of
  birth. Classify all non-DOB date/time fields as NONE even when they occur in
  a designated healthcare record.
- A provider NPI or public professional identifier is not patient PHI and is
  not personal PII merely because it identifies a professional.
- Aggregated statistics and public/reference metadata are NONE when they
  cannot identify or be linked to an individual.
- When the supplied semantics do not support a sensitive classification, use
  NONE and state the missing evidence. Do not invent possible values or uses.
- Include every supplied entity and every supplied field exactly once. Do not
  add, rename, omit, or reorder entities or fields.
- Follow the supplied industry privacy guidance. Industry changes the meaning
  and regulatory context, but never overrides the concrete field and row
  semantics.
- PHI is not a synonym for sensitive or regulated. Outside healthcare, use PHI
  only when the modeled field actually contains individually linkable health
  information.
- PII is not a synonym for confidential business data. A trade secret, product
  metric, internal code, or aggregate remains NONE unless it identifies or is
  reasonably linkable to a natural person.
- The rationale must name the concrete semantic reason; generic statements
  such as "sensitive data" or "may contain PII" are invalid.
- For every healthcare entity, first decide whether it is part of a HIPAA
  designated record set, a separate healthcare administrative/non-health
  dataset, or non-healthcare reference data. Use that record context
  consistently across its fields. Do not infer designated-record-set status
  merely because the organization is a healthcare provider.
"""


class PrivacyClassificationError(ValueError):
    """Raised when the classifier response is incomplete or inconsistent."""


def _parse_json(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PrivacyClassificationError(f"privacy classifier returned invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise PrivacyClassificationError("privacy classifier response must be a JSON object")
    return value


def validate_classifications(response: dict, entities: list[dict]) -> dict[str, list[dict]]:
    response_entities = response.get("entities")
    if not isinstance(response_entities, list):
        raise PrivacyClassificationError("privacy classifier response is missing entities")

    expected_entities = [entity["name"] for entity in entities]
    actual_entities = [item.get("entity") for item in response_entities if isinstance(item, dict)]
    if actual_entities != expected_entities:
        raise PrivacyClassificationError(
            "privacy classifier entities do not exactly match the generated model"
        )

    validated = {}
    for entity, classified_entity in zip(entities, response_entities):
        record_context = str(classified_entity.get("record_context", "")).strip().upper()
        context_rationale = str(classified_entity.get("context_rationale", "")).strip()
        if record_context not in ALLOWED_RECORD_CONTEXTS:
            raise PrivacyClassificationError(
                f"invalid record context {record_context!r} for {entity['name']}"
            )
        if len(context_rationale) < 20:
            raise PrivacyClassificationError(
                f"record context rationale is not specific enough for {entity['name']}"
            )
        classified_fields = classified_entity.get("fields")
        if not isinstance(classified_fields, list):
            raise PrivacyClassificationError(
                f"privacy classifier fields are missing for {entity['name']}"
            )

        expected_fields = [field[0] for field in entity.get("fields", [])]
        actual_fields = [item.get("field") for item in classified_fields if isinstance(item, dict)]
        if actual_fields != expected_fields:
            raise PrivacyClassificationError(
                f"privacy classifier fields do not exactly match {entity['name']}"
            )

        normalized_fields = []
        for item in classified_fields:
            category = str(item.get("category", "")).strip().upper()
            rationale = str(item.get("rationale", "")).strip()
            if category not in ALLOWED_CATEGORIES:
                raise PrivacyClassificationError(
                    f"invalid privacy category {category!r} for {entity['name']}.{item.get('field')}"
                )
            if len(rationale) < 20:
                raise PrivacyClassificationError(
                    f"privacy rationale is not specific enough for {entity['name']}.{item.get('field')}"
                )
            field_name = str(item.get("field", ""))
            field_type = str(entity.get("fields", [])[len(normalized_fields)][1]).upper()
            type_tokens = set(field_type.replace("-", " ").split())
            is_surrogate = field_name.lower().endswith("_sk") or "SURROGATE" in type_tokens
            normalized_name = field_name.lower()
            is_dob = normalized_name in DOB_FIELD_NAMES
            is_date_field = (
                "DATE" in field_type
                or "TIME" in field_type
                or "date" in normalized_name
                or "time" in normalized_name
                or "period_start" in normalized_name
                or "period_end" in normalized_name
            )
            if is_surrogate and category != "NONE":
                raise PrivacyClassificationError(
                    f"surrogate key column {entity['name']}.{item.get('field')} must be NONE"
                )
            if is_date_field and not is_dob and category != "NONE":
                raise PrivacyClassificationError(
                    f"non-DOB date column {entity['name']}.{item.get('field')} must be NONE"
                )
            if record_context == "HIPAA_DESIGNATED_RECORD_SET" and category == "PII":
                raise PrivacyClassificationError(
                    f"{entity['name']}.{item.get('field')} cannot be PII inside a HIPAA designated record set"
                )
            if record_context != "HIPAA_DESIGNATED_RECORD_SET" and category == "PHI":
                raise PrivacyClassificationError(
                    f"{entity['name']}.{item.get('field')} cannot be PHI outside a HIPAA designated record set"
                )
            normalized_fields.append({
                "field": item["field"],
                "category": category,
                "rationale": rationale,
            })
        validated[entity["name"]] = {
            "record_context": record_context,
            "context_rationale": context_rationale,
            "fields": normalized_fields,
        }
    return validated


def classify_fields(client, deployment: str, requirement: str, industry: str, entities: list[dict]) -> None:
    industry_guidance = INDUSTRY_PRIVACY_GUIDANCE.get(
        industry, INDUSTRY_PRIVACY_GUIDANCE["generic"]
    )
    payload = {
        "business_requirement": requirement,
        "industry": industry,
        "industry_privacy_guidance": industry_guidance,
        "entities": [
            {
                "name": entity["name"],
                "definition": entity.get("definition", ""),
                "classification": entity.get("classification", ""),
                "domain_concept": entity.get("clinical_concept", ""),
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
        raise PrivacyClassificationError(f"privacy classifier model call failed: {exc}") from exc
    classifications = validate_classifications(_parse_json(raw_text), entities)

    for entity in entities:
        classification = classifications[entity["name"]]
        entity["privacyContext"] = classification["record_context"]
        entity["privacyContextRationale"] = classification["context_rationale"]
        entity["privacyClassifications"] = classification["fields"]
        categories = {item["category"] for item in entity["privacyClassifications"]}
        if "PHI" in categories:
            entity["classification"] = "Restricted / PHI"
        elif "PII" in categories:
            entity["classification"] = "Restricted / PII"
        elif entity.get("classification") not in {"Internal", "Public"}:
            entity["classification"] = "Internal"
