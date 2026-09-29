"""Reference-standard library for the Catalog view.

Built-in interoperability/metadata standards grouped by industry, each with a
short plain-language description of what it is and when to use it. This is the
source of truth the Catalog tab reads to explain "what each standard means".

Custom standards a user adds through the Catalog UI are stored separately in
session_store (custom_standard table) and merged on top of these at read time,
so the seed list stays clean and user additions survive restarts.
"""

# industry key -> list of {name, description}. Industry keys match
# prompts.INDUSTRY_LABELS / the frontend Industry selector.
BUILTIN_STANDARDS: dict[str, list[dict]] = {
    "healthcare": [
        {"name": "FHIR R5 + enterprise glossary",
         "description": "HL7 FHIR R5 resources (Patient, Coverage, Claim, Observation) for clinical/claims interoperability, mapped to enterprise glossary terms."},
        {"name": "OMOP CDM 5.5 + enterprise glossary",
         "description": "OHDSI Observational Medical Outcomes Partnership common data model for standardized observational and population analytics."},
        {"name": "Enterprise glossary only",
         "description": "Align to internal certified business terms only — no external clinical standard crosswalk."},
    ],
    "fintech": [
        {"name": "ISO 20022 + enterprise glossary",
         "description": "Global standard for financial messaging (payments, cards, securities) with rich structured business data."},
        {"name": "FIBO (Financial Industry Business Ontology)",
         "description": "EDM Council ontology describing financial instruments, legal entities, and contracts for shared semantics."},
        {"name": "BIAN service landscape",
         "description": "Banking Industry Architecture Network reference model of banking capabilities and service domains."},
    ],
    "edtech": [
        {"name": "IMS Global Caliper Analytics",
         "description": "1EdTech Caliper framework for capturing and exchanging learning activity (learning events) across tools."},
        {"name": "xAPI (Experience API)",
         "description": "Experience API for recording learner statements (actor-verb-object) to a Learning Record Store."},
        {"name": "SCORM 2004",
         "description": "Shareable Content Object Reference Model for packaging and tracking e-learning course content."},
    ],
    "transport": [
        {"name": "GTFS (General Transit Feed Specification)",
         "description": "Open format for public-transit schedules, stops, and routes consumed by trip-planning systems."},
        {"name": "IATA NDC",
         "description": "IATA New Distribution Capability XML standard for airline offer and order distribution."},
        {"name": "UN/EDIFACT",
         "description": "UN electronic data interchange standard for freight, customs, and logistics messages (e.g. IFTMIN, IFTSTA)."},
    ],
    "ecommerce": [
        {"name": "GS1 / EPCIS",
         "description": "GS1 identifiers (GTIN, GLN) and EPCIS event standard for product identity and supply-chain visibility."},
        {"name": "schema.org Product/Offer",
         "description": "Web vocabulary for describing products, offers, and orders — used for structured data and catalog interop."},
        {"name": "UNSPSC",
         "description": "United Nations Standard Products and Services Code for classifying products and services in procurement."},
    ],
    "telecom": [
        {"name": "TM Forum SID (Information Framework)",
         "description": "Shared Information/Data model for OSS/BSS — customers, products, services, and resources."},
        {"name": "3GPP data model",
         "description": "3rd Generation Partnership Project network and subscriber data definitions for mobile networks."},
        {"name": "MEF LSO",
         "description": "MEF Lifecycle Service Orchestration model for standardized connectivity service management."},
    ],
    "generic": [
        {"name": "Enterprise glossary only",
         "description": "Align to internal certified business terms only, with no external industry standard."},
        {"name": "ISO/IEC 11179 metadata registry",
         "description": "International standard for describing and registering data elements and their metadata consistently."},
    ],
}

INDUSTRY_LABELS = {
    "healthcare": "Healthcare",
    "fintech": "Financial services",
    "edtech": "Education",
    "transport": "Transport & logistics",
    "ecommerce": "E-commerce & retail",
    "telecom": "Telecommunications",
    "generic": "Other / general business",
}
