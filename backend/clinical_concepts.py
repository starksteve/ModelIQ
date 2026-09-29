"""Canonical clinical concept registry: the semantic layer that sits between
free-text requirements and the two standards ModelIQ aligns to (FHIR for
interoperability, OMOP for observational/analytics use). Kept as a small,
deterministic lookup table rather than letting the LLM invent standard
mappings, so FHIR/OMOP names are always consistent and never hallucinated.

CDISC SDTM/ADaM is intentionally out of scope for now — ModelIQ's focus is
enterprise healthcare / patient-360 / observational analytics, not clinical
trial submission data.
"""

# name -> { fhir_resource, omop_table, omop_domain, synonyms }
# synonyms are used to bias RAG matching toward the right concept even when the
# requirement uses lay/clinical terms rather than the canonical concept name
# (e.g. "heart attack" -> Condition, "insulin" -> Medication).
CANONICAL_CONCEPTS: dict[str, dict] = {
    "Patient": {
        "fhir_resource": "Patient",
        "omop_table": "PERSON",
        "omop_domain": "Person",
        "synonyms": ["member", "person", "individual", "patient", "enrollee", "subscriber"],
    },
    "Encounter": {
        "fhir_resource": "Encounter",
        "omop_table": "VISIT_OCCURRENCE",
        "omop_domain": "Visit",
        "synonyms": ["visit", "admission", "clinical event", "hospitalization", "office visit"],
    },
    "Condition": {
        "fhir_resource": "Condition",
        "omop_table": "CONDITION_OCCURRENCE",
        "omop_domain": "Condition",
        "synonyms": [
            "diagnosis", "disease", "problem list", "diabetes", "hypertension",
            "myocardial infarction", "heart attack", "mi", "condition",
        ],
    },
    "Medication": {
        "fhir_resource": "MedicationDispense",
        "omop_table": "DRUG_EXPOSURE",
        "omop_domain": "Drug",
        "synonyms": ["drug", "prescription", "pharmacy", "insulin", "rx", "medication", "dispensed"],
    },
    "Observation": {
        "fhir_resource": "Observation",
        "omop_table": "MEASUREMENT",
        "omop_domain": "Measurement",
        "synonyms": ["lab result", "vital sign", "measurement", "test result", "observation", "labs"],
    },
    "Procedure": {
        "fhir_resource": "Procedure",
        "omop_table": "PROCEDURE_OCCURRENCE",
        "omop_domain": "Procedure",
        "synonyms": ["surgery", "operation", "intervention", "procedure"],
    },
    "Coverage": {
        "fhir_resource": "Coverage",
        "omop_table": "PAYER_PLAN_PERIOD",
        "omop_domain": "Observation Period",
        "synonyms": ["insurance", "enrollment", "benefit plan", "coverage", "eligibility"],
    },
    "Provider": {
        "fhir_resource": "Practitioner",
        "omop_table": "PROVIDER",
        "omop_domain": "Provider",
        "synonyms": ["practitioner", "clinician", "physician", "doctor", "provider"],
    },
    "Claim": {
        "fhir_resource": "Claim",
        "omop_table": "COST",
        "omop_domain": "Cost",
        "synonyms": ["reimbursement", "billing", "claim"],
    },
    "MeasureReport": {
        "fhir_resource": "MeasureReport",
        "omop_table": "OBSERVATION",
        "omop_domain": "Observation",
        "synonyms": ["quality measure", "care gap", "measure result", "quality gap"],
    },
    "InsurancePlan": {
        "fhir_resource": "InsurancePlan",
        "omop_table": "PAYER_PLAN_PERIOD",
        "omop_domain": "Payer Plan",
        "synonyms": ["plan product", "benefit plan", "line of business"],
    },
    "Other": {
        "fhir_resource": None,
        "omop_table": None,
        "omop_domain": None,
        "synonyms": [],
    },
}


def standards_mapping(concept: str) -> dict:
    entry = CANONICAL_CONCEPTS.get(concept, CANONICAL_CONCEPTS["Other"])
    return {
        "fhir": entry["fhir_resource"],
        "omop": {"table": entry["omop_table"], "domain": entry["omop_domain"]},
    }


def infer_concept(name: str, definition: str) -> str:
    """Deterministic keyword fallback if the LLM omits/mis-names clinical_concept."""
    text = f"{name} {definition}".lower()
    for concept, entry in CANONICAL_CONCEPTS.items():
        if concept == "Other":
            continue
        if any(synonym in text for synonym in entry["synonyms"]):
            return concept
    return "Other"


def expand_query_text(name: str, definition: str, concept: str) -> str:
    """Augment the embedding query with the resolved concept and its synonyms so
    RAG matching is concept-aware rather than purely literal-text similarity."""
    entry = CANONICAL_CONCEPTS.get(concept)
    if not entry or concept == "Other":
        return f"{name}: {definition}"
    synonym_hint = ", ".join(entry["synonyms"][:5])
    return f"{name}: {definition} (clinical concept: {concept}; also known as: {synonym_hint})"
