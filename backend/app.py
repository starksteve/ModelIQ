"""FastAPI backend: requirement -> LLM-driven conceptual/logical model + RAG reuse
detection + deterministic artifact generation. Serves the existing frontend/
static frontend from the same origin so no CORS/file:// complications.
"""
import logging
import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import artifact_builder
import ddl_import
import ddl_validator
import index_recommender
import llm_ddl_generator
import privacy_classifier
import prompts
import session_store
import standards_library
from clinical_concepts import CANONICAL_CONCEPTS, infer_concept, standards_mapping
from llm_client import CHAT_DEPLOYMENT, GENERATION_SEED, get_client, is_configured, normalize_chat_kwargs
from rag.catalog import CATALOG_INDUSTRIES
from rag.retriever import best_match

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="ModelIQ API")

# Chat sessions (conversation history + last generated model) are persisted to a
# local SQLite file via session_store, so they survive server restarts and can be
# listed/resumed/deleted from the sidebar instead of living only in the browser.
session_store.init_db()


class GenerateRequest(BaseModel):
    requirement: str = ""
    industry: str = "healthcare"
    standard: str = "FHIR"
    dialect: str = "ANSI SQL"
    files: list[dict] = []  # optional [{name, content}] existing DDL to import/evolve


class RefineRequest(BaseModel):
    session_id: str
    instruction: str
    dialect: str | None = None


class RenameRequest(BaseModel):
    title: str


def _field_overlap_pct(entity_fields: list, catalog_fields: list[str]) -> int:
    entity_names = {re.sub(r"[^a-z0-9]", "", f[0].lower()) for f in entity_fields}
    catalog_names = {re.sub(r"[^a-z0-9]", "", f.lower()) for f in catalog_fields}
    if not catalog_names:
        return 0
    return round(100 * len(entity_names & catalog_names) / len(catalog_names))


def _is_restricted(classification: str) -> bool:
    return classification in ("Restricted / PHI", "Restricted / PII")


@app.get("/api/status")
def status():
    return {
        "llm_configured": is_configured(),
        "deployment": CHAT_DEPLOYMENT,
        "dialects": llm_ddl_generator.SUPPORTED_DIALECTS,
    }


def _finalize_model(model_output: dict, industry: str, standard: str, dialect: str, contract_context: str, client, reuse_enabled: bool = False) -> dict:
    """Shared post-processing for both a fresh /api/generate call and a follow-up
    /api/refine call: RAG reuse-detection, DQ rule enrichment, DDL/artifact build.

    Reuse-detection against the enterprise catalog only runs when reuse_enabled is
    True — i.e. when the user has attached existing DDLs or connected a catalog.
    Without a real source of existing assets, every entity is proposed as NEW
    rather than matched against the seeded reference catalog."""
    entities = model_output.get("entities", [])
    reviews = model_output.get("reviews", [])
    # Governed enrichment: model-driven, strictly-validated PHI/PII classification
    # and workload-driven index recommendations. Both raise on validation failure
    # so a governed model is never emitted with unverified privacy/index metadata.
    privacy_classifier.classify_fields(client, CHAT_DEPLOYMENT, contract_context, industry, entities)
    index_recommender.recommend_indexes(
        client, CHAT_DEPLOYMENT, contract_context, industry, dialect or "ANSI SQL", entities
    )
    dq_rules = artifact_builder.enrich_dq_rules(
        entities, model_output.get("data_quality_rules", [])
    )

    reuse_rows = []
    for entity in entities:
        # Standards mapping (FHIR/OMOP concept) is independent of reuse-detection
        # and is always computed; only catalog matching is gated by reuse_enabled.
        if industry == "healthcare":
            concept = entity.get("clinical_concept")
            if concept not in CANONICAL_CONCEPTS:
                concept = infer_concept(entity["name"], entity["definition"])
            entity["clinicalConcept"] = concept
            entity["standardsMapping"] = standards_mapping(concept)
        else:
            concept = entity.get("clinical_concept") or "Other"
            entity["clinicalConcept"] = concept
            entity["standardsMapping"] = None

        if reuse_enabled and industry in CATALOG_INDUSTRIES:
            match = best_match(entity["name"], entity["definition"], concept, industry=industry)
        else:
            match = None

        classification_conflict = bool(
            match and _is_restricted(entity.get("classification")) and not _is_restricted(match["classification"])
        )

        if match and classification_conflict:
            decision = "REVIEW"
        elif match and match["similarity_pct"] >= 75:
            decision = "REUSE"
        elif match and match["similarity_pct"] >= 45:
            decision = "EXTEND"
        else:
            decision = "NEW"

        if match and decision != "NEW":
            field_overlap = _field_overlap_pct(entity["fields"], match["fields"])
            evidence = []
            if match["concept_match"]:
                evidence.append(f"Same clinical concept ({concept})")
            evidence.append(f"{field_overlap}% field overlap with {match['asset_id']}")
            if classification_conflict:
                evidence.append(
                    f"Classification conflict: proposed {entity.get('classification')} vs. "
                    f"asset's {match['classification']} — needs governance review"
                )
            else:
                evidence.append(f"Same classification ({match['classification']})")

            entity["badge"] = f"{decision} {match['similarity_pct']}%"
            entity["match"] = f"{match['asset_id']} · {match['similarity_pct']}%"
            entity["standard"] = match["standard"]
            entity["evidence"] = evidence
            entity["rationale"] = (
                f"Closest enterprise asset is {match['asset_id']} ({match['domain']}, "
                f"{match['status']}) at {match['similarity_pct']}% similarity."
            )
            reuse_rows.append([
                entity["name"], match["asset_id"],
                f"{match['domain']} domain · {match['status']}",
                match["similarity_pct"],
                ", ".join(match["fields"][:3]), decision.title(),
            ])
        else:
            entity["badge"] = "NEW"
            entity["match"] = "No direct match"
            if match:
                entity["evidence"] = [f"Closest asset {match['asset_id']} shares too little to justify reuse ({match['similarity_pct']}%)"]
            elif not reuse_enabled:
                entity["evidence"] = ["Reuse detection runs only when you attach existing DDLs or connect a catalog — proposing as a new governed entity"]
            elif industry in CATALOG_INDUSTRIES:
                entity["evidence"] = ["No approved enterprise asset shares this domain concept"]
            else:
                industry_label = prompts.INDUSTRY_LABELS.get(industry, industry)
                entity["evidence"] = [f"No enterprise catalog coverage yet for the {industry_label} domain — proposing as a new governed entity"]
            entity.setdefault("standard", standard)
            entity["rationale"] = "No approved enterprise asset matched closely enough; propose as a new governed entity."

    dialect = dialect or "ANSI SQL"
    ddl_source = "deterministic"
    try:
        llm_ddl = llm_ddl_generator.generate_llm_ddl(client, CHAT_DEPLOYMENT, entities, dialect)
        is_valid, reasons = ddl_validator.validate_ddl(llm_ddl, entities)
        if is_valid:
            ddl = llm_ddl
            ddl_source = "llm-validated"
        else:
            logger.warning("LLM DDL failed validation (%s); using deterministic fallback.", reasons)
            ddl = artifact_builder.build_ddl(entities)
    except Exception as e:
        logger.warning("LLM DDL generation failed (%s); using deterministic fallback.", e)
        ddl = artifact_builder.build_ddl(entities)

    index_ddl = index_recommender.build_index_ddl(entities, dialect)
    index_summary = index_recommender.build_index_summary(entities, dialect)
    artifacts = {
        "ddl": f"{index_summary}\n\n{ddl}\n\n{index_ddl}",
        "index_ddl": index_ddl,
        "dq_ddl": artifact_builder.build_dq_ddl(entities, dq_rules),
        "contract": artifact_builder.build_contract(entities, contract_context),
        "dictionary": artifact_builder.build_dictionary(entities),
    }

    return {
        "mode": "live",
        "deployment": CHAT_DEPLOYMENT,
        "entities": entities,
        "reuseRows": reuse_rows,
        "reuseEnabled": reuse_enabled,
        "reviews": reviews,
        "dataQualityRules": dq_rules,
        "artifacts": artifacts,
        "ddlSource": ddl_source,
        "dialect": dialect,
    }


@app.post("/api/generate")
def generate(payload: GenerateRequest):
    requirement = payload.requirement.strip()
    industry = payload.industry or "healthcare"
    standard = payload.standard or "FHIR"
    dialect = payload.dialect or "ANSI SQL"
    client = get_client()

    # Path A: existing DDL uploaded -> import, and optionally evolve via the prompt.
    ddl_texts = [f.get("content", "") for f in (payload.files or []) if f.get("content")]
    combined = "\n\n".join(t for t in ddl_texts if t and t.strip())
    if combined.strip():
        entities, reviews = ddl_import.parse_ddl(combined)
        if not entities:
            raise HTTPException(status_code=400, detail="No CREATE TABLE statements found in the uploaded files.")
        model_output = {"entities": entities, "reviews": reviews, "data_quality_rules": []}
        evolved = False
        if requirement and client is not None:
            try:
                messages = prompts.build_evolve_messages(entities, requirement, standard)
                chat_kwargs = normalize_chat_kwargs(
                    model=CHAT_DEPLOYMENT, messages=messages, temperature=0.2, seed=GENERATION_SEED
                )
                resp = client.chat.completions.create(**chat_kwargs)
                out = prompts.parse_model_response(resp.choices[0].message.content)
                if out.get("entities"):
                    model_output = {
                        "entities": out["entities"],
                        "reviews": out.get("reviews", reviews),
                        "data_quality_rules": out.get("data_quality_rules", []),
                    }
                    evolved = True
            except Exception as e:  # noqa: BLE001 - keep the imported model on failure
                logger.warning("Evolve step failed (%s); returning imported model unchanged.", e)

        try:
            result = _finalize_model(model_output, industry, standard, dialect,
                                     requirement or "Imported data model", client, reuse_enabled=True)
        except (privacy_classifier.PrivacyClassificationError, index_recommender.IndexRecommendationError) as e:
            logger.error("Model governance enrichment failed during import: %s", e)
            raise HTTPException(status_code=502, detail=f"Model governance enrichment failed: {e}") from e
        result["mode"] = "imported"
        result["ddlSource"] = "evolved" if evolved else "uploaded"
        if not evolved:
            # Preserve the user's original DDL for a pure import, but keep the
            # governed index-recommendation section appended below it.
            result["artifacts"]["ddl"] = combined.strip() + "\n\n" + result["artifacts"]["index_ddl"]
        try:
            ctx = prompts.build_evolve_messages(result["entities"], requirement or "(imported)", standard)
            session_id = session_store.create_session(
                industry, standard, dialect, requirement or "Imported DDL model", ctx
            )
            session_store.update_session(session_id, llm_context=ctx, dialect=dialect, model_json=result)
            result["sessionId"] = session_id
            result["title"] = session_store.get_session(session_id)["title"]
        except Exception as e:  # noqa: BLE001 - session is best-effort
            logger.warning("Session persistence for import failed: %s", e)
        return result

    # Path B: no files -> generate a brand-new model from the requirement.
    if len(requirement) < 20:
        raise HTTPException(status_code=400, detail="Requirement must be at least 20 characters (or attach DDL files).")

    if client is None:
        raise HTTPException(
            status_code=503,
            detail="LLM not configured. Set OPENAI_BASE_URL and OPENAI_API_KEY "
                   "(free tier, e.g. Google Gemini or Groq) \u2014 or Azure OpenAI "
                   "credentials \u2014 in backend/.env.",
        )

    messages = prompts.build_messages(requirement, standard, industry)
    try:
        chat_kwargs = normalize_chat_kwargs(
            model=CHAT_DEPLOYMENT,
            messages=messages,
            temperature=0.2,
            seed=GENERATION_SEED,
        )
        response = client.chat.completions.create(**chat_kwargs)
        raw_text = response.choices[0].message.content
        model_output = prompts.parse_model_response(raw_text)
    except Exception as e:
        logger.error("LLM generation failed: %s", e)
        raise HTTPException(status_code=502, detail=f"LLM call failed: {e}") from e

    try:
        result = _finalize_model(model_output, industry, standard, dialect, requirement, client)
    except (privacy_classifier.PrivacyClassificationError, index_recommender.IndexRecommendationError) as e:
        logger.error("Model governance enrichment failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Model governance enrichment failed: {e}") from e

    session_id = session_store.create_session(
        industry, standard, dialect, requirement, messages + [{"role": "assistant", "content": raw_text}]
    )
    session_store.add_message(session_id, "user", requirement)
    session_store.add_message(session_id, "assistant", f"Generated a draft model with {len(result['entities'])} entities.")
    session_store.update_session(session_id, llm_context=messages + [{"role": "assistant", "content": raw_text}],
                                  dialect=dialect, model_json=result)
    result["sessionId"] = session_id
    result["title"] = session_store.get_session(session_id)["title"]
    return result


@app.post("/api/refine")
def refine(payload: RefineRequest):
    instruction = payload.instruction.strip()
    if len(instruction) < 3:
        raise HTTPException(status_code=400, detail="Describe the change you want.")

    session = session_store.get_session(payload.session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found or expired \u2014 generate a model first, then refine it.",
        )

    client = get_client()
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="LLM not configured. Set OPENAI_BASE_URL and OPENAI_API_KEY "
                   "(free tier, e.g. Google Gemini or Groq) \u2014 or Azure OpenAI "
                   "credentials \u2014 in backend/.env.",
        )

    dialect = payload.dialect or session["dialect"]
    messages = session["llm_context"] + [{
        "role": "user",
        "content": (
            "Apply this change to the model above and return the FULL updated model as "
            "STRICT JSON in the exact same shape as before (all entities, reviews, and "
            "data_quality_rules \u2014 not just the changed parts). Keep everything unchanged "
            "except what the requested change requires.\n\n"
            f"Requested change:\n{instruction}"
        ),
    }]
    try:
        chat_kwargs = normalize_chat_kwargs(
            model=CHAT_DEPLOYMENT,
            messages=messages,
            temperature=0.2,
            seed=GENERATION_SEED,
        )
        response = client.chat.completions.create(**chat_kwargs)
        raw_text = response.choices[0].message.content
        model_output = prompts.parse_model_response(raw_text)
    except Exception as e:
        logger.error("LLM refine failed: %s", e)
        raise HTTPException(status_code=502, detail=f"LLM call failed: {e}") from e

    try:
        result = _finalize_model(
            model_output, session["industry"], session["standard"], dialect, session["requirement"], client,
            reuse_enabled=bool((session.get("model") or {}).get("reuseEnabled")),
        )
    except (privacy_classifier.PrivacyClassificationError, index_recommender.IndexRecommendationError) as e:
        logger.error("Model governance enrichment failed during refine: %s", e)
        raise HTTPException(status_code=502, detail=f"Model governance enrichment failed: {e}") from e

    session_store.add_message(payload.session_id, "user", instruction)
    session_store.add_message(payload.session_id, "assistant", "Updated the model \u2014 tabs below now reflect this change.")
    session_store.update_session(
        payload.session_id,
        llm_context=messages + [{"role": "assistant", "content": raw_text}],
        dialect=dialect,
        model_json=result,
    )
    result["sessionId"] = payload.session_id
    return result


@app.get("/api/sessions")
def list_sessions():
    return {"sessions": session_store.list_sessions()}


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return {
        "sessionId": session["session_id"],
        "title": session["title"],
        "industry": session["industry"],
        "standard": session["standard"],
        "dialect": session["dialect"],
        "chat": [{"role": m["role"], "text": m["text"]} for m in session["chat"]],
        "model": session["model"],
        "reviewResolutions": session_store.list_review_resolutions(session_id),
    }


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    if not session_store.delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found.")
    return {"ok": True}


@app.put("/api/sessions/{session_id}/rename")
def rename_session(session_id: str, payload: RenameRequest):
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title cannot be empty.")
    if not session_store.rename_session(session_id, title):
        raise HTTPException(status_code=404, detail="Session not found.")
    return {"ok": True, "title": title}


# PHI/PII column heuristic — kept in sync with isLikelyPhiField() in
# frontend/app.js so the Governance PHI count matches the Model page's count
# (flags direct identifiers, plus clinical dates on clinical restricted entities).
_PHI_DIRECT_IDENTIFIERS = (
    "ssn", "social_security", "medicare", "medicaid", "mrn", "medical_record",
    "person_id", "patient_id", "member_id", "subscriber_id", "enrollee_id",
    "first_name", "last_name", "full_name", "name", "dob", "birth_date", "date_of_birth",
    "email", "phone", "mobile", "address", "street", "city", "state", "zip", "postal",
)
_PHI_CLINICAL_DATES = (
    "service_date", "event_date", "admit_date", "discharge_date", "fill_date",
    "result_date", "effective_period",
)
_PHI_CLINICAL_TOKENS = (
    "patient", "member", "person", "encounter", "condition", "medication",
    "observation", "claim", "coverage",
)


def _is_restricted_classification(classification: str) -> bool:
    n = (classification or "").lower()
    return "phi" in n or "pii" in n or "restricted" in n


def _is_phi_field(field_name: str, entity: dict) -> bool:
    if not _is_restricted_classification(entity.get("classification", "")):
        return False
    name = str(field_name).lower()
    if any(tok in name for tok in _PHI_DIRECT_IDENTIFIERS):
        return True
    entity_name = str(entity.get("name", "")).lower()
    concept = str(entity.get("clinicalConcept") or entity.get("clinical_concept") or "").lower()
    is_clinical = any(tok in entity_name or tok in concept for tok in _PHI_CLINICAL_TOKENS)
    return is_clinical and any(tok in name for tok in _PHI_CLINICAL_DATES)


def _phi_field_count(entity: dict) -> int:
    return sum(1 for f in entity.get("fields", []) if f and _is_phi_field(f[0], entity))


def _model_stats(model: dict) -> dict:
    entities = model.get("entities", []) if model else []
    phi_cols = 0
    reused = extended = new = 0
    for e in entities:
        badge = (e.get("badge") or "").upper()
        if badge.startswith("REUSE"):
            reused += 1
        elif badge.startswith("EXTEND"):
            extended += 1
        else:
            new += 1
        phi_cols += _phi_field_count(e)
    return {
        "entities": len(entities),
        "reused": reused,
        "extended": extended,
        "new": new,
        "phiColumns": phi_cols,
        "reviewCount": len(model.get("reviews", []) if model else []),
    }


def _policy_findings(model: dict) -> list[dict]:
    """Derive policy-compliance findings from a stored model: PHI/PII access
    control, classification conflicts, and privacy design-review items."""
    findings: list[dict] = []
    entities = model.get("entities", []) if model else []
    for e in entities:
        name = e.get("name", "Entity")
        classification = e.get("classification", "")
        badge = (e.get("badge") or "").upper()
        if _is_restricted(classification):
            findings.append({
                "severity": "high",
                "policy": "Access control & tokenization",
                "entity": name,
                "detail": f"{name} is classified {classification} — requires RBAC masking, "
                          f"tokenization, and retention rules before publish.",
            })
        if badge.startswith("REVIEW"):
            findings.append({
                "severity": "high",
                "policy": "Classification conflict",
                "entity": name,
                "detail": f"{name} classification conflicts with its matched enterprise asset — "
                          f"needs data-owner sign-off.",
            })
        if not e.get("standardsMapping") and not (e.get("standard") or "").strip():
            findings.append({
                "severity": "low",
                "policy": "Standards mapping",
                "entity": name,
                "detail": f"{name} has no reference-standard mapping recorded.",
            })
    for review in (model.get("reviews", []) if model else []):
        if not isinstance(review, (list, tuple)) or not review:
            continue
        rtype = str(review[0]).lower()
        # reviews are [type, title, detail] or [type, icon, title, detail]
        parts = list(review[1:])
        title, detail = (parts[-2], parts[-1]) if len(parts) >= 2 else (parts[0] if parts else "", "")
        if rtype in ("privacy", "high"):
            findings.append({
                "severity": "high" if rtype == "high" else "privacy",
                "policy": "Privacy design review",
                "entity": title,
                "detail": detail,
            })
    return findings


@app.get("/api/governance/models")
def governance_models():
    models = []
    for row in session_store.list_models():
        stats = _model_stats(row.get("model") or {})
        models.append({
            "sessionId": row["session_id"],
            "title": row["title"],
            "industry": row["industry"],
            "standard": row["standard"],
            "dialect": row["dialect"],
            "status": row.get("status", "draft"),
            "updatedAt": row["updated_at"],
            "createdAt": row["created_at"],
            "stats": stats,
        })
    return {"models": models}


class StatusRequest(BaseModel):
    status: str


_ALLOWED_STATUSES = {"draft", "approved", "needs_revision"}
_STATUS_LABELS = {"draft": "Draft", "approved": "Approved", "needs_revision": "Needs revision"}


@app.post("/api/governance/models/{session_id}/status")
def set_model_status(session_id: str, payload: StatusRequest):
    status = payload.status.strip().lower()
    if status not in _ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status.")
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Model not found.")
    if not session_store.set_status(session_id, status):
        raise HTTPException(status_code=404, detail="Model not found.")
    session_store.add_audit(
        session_id,
        f"Status set to {_STATUS_LABELS[status]}",
        f"Model '{session['title']}' marked {_STATUS_LABELS[status]}.",
    )
    return {"ok": True, "status": status}


@app.get("/api/governance/models/{session_id}/policy")
def governance_policy(session_id: str):
    session = session_store.get_session(session_id)
    if session is None or session.get("model") is None:
        raise HTTPException(status_code=404, detail="Model not found.")
    findings = _policy_findings(session["model"])
    counts = {
        "high": sum(1 for f in findings if f["severity"] == "high"),
        "privacy": sum(1 for f in findings if f["severity"] == "privacy"),
        "low": sum(1 for f in findings if f["severity"] == "low"),
    }
    session_store.add_audit(session_id, "Ran policy checks",
                            f"{len(findings)} policy finding(s) on '{session['title']}'.")
    return {"title": session["title"], "findings": findings, "counts": counts}


@app.get("/api/governance/audit")
def governance_audit(session_id: str | None = None):
    return {"events": session_store.list_audit(session_id)}


class ReviewResolveRequest(BaseModel):
    findingId: str
    findingTitle: str
    decision: str
    reason: str = ""


_REVIEW_DECISIONS = {
    "mark_fixed": "Marked fixed",
    "accept_risk": "Risk accepted",
    "assign_review": "Assigned to human review",
}


@app.post("/api/governance/models/{session_id}/reviews/resolve")
def resolve_review_finding(session_id: str, payload: ReviewResolveRequest):
    decision = payload.decision.strip().lower()
    if decision not in _REVIEW_DECISIONS:
        raise HTTPException(status_code=400, detail="Invalid decision.")
    finding_id = payload.findingId.strip()
    title = payload.findingTitle.strip()
    if not finding_id or not title:
        raise HTTPException(status_code=400, detail="Missing finding.")
    reason = payload.reason.strip()
    if decision == "accept_risk" and not reason:
        raise HTTPException(status_code=400, detail="A justification is required to accept risk.")
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Model not found.")
    session_store.set_review_resolution(session_id, finding_id, title, decision, reason)
    label = _REVIEW_DECISIONS[decision]
    detail = f"Review finding '{title}' — {label}." + (f" Reason: {reason}" if reason else "")
    session_store.add_audit(session_id, f"Review finding {label.lower()}", detail)
    return {
        "ok": True,
        "resolution": {
            "finding_id": finding_id,
            "finding_title": title,
            "decision": decision,
            "reason": reason,
            "actor": "You",
        },
    }
# --- Catalog: reference standards by industry --------------------------------

@app.get("/api/catalog/standards")
def catalog_standards(industry: str | None = None):
    industries = [industry] if industry else list(standards_library.INDUSTRY_LABELS.keys())
    out = []
    for key in industries:
        builtin = [
            {"id": None, "name": s["name"], "description": s["description"], "builtin": True}
            for s in standards_library.BUILTIN_STANDARDS.get(key, [])
        ]
        custom = [
            {"id": c["id"], "name": c["name"], "description": c["description"], "builtin": False}
            for c in session_store.list_custom_standards(key)
        ]
        out.append({
            "industry": key,
            "label": standards_library.INDUSTRY_LABELS.get(key, key),
            "standards": builtin + custom,
        })
    return {"catalog": out}


class StandardRequest(BaseModel):
    industry: str
    name: str
    description: str = ""


@app.post("/api/catalog/standards")
def add_catalog_standard(payload: StandardRequest):
    industry = payload.industry.strip().lower()
    name = payload.name.strip()
    if not industry or not name:
        raise HTTPException(status_code=400, detail="Industry and standard name are required.")
    standard_id = session_store.add_standard(industry, name, payload.description.strip())
    label = standards_library.INDUSTRY_LABELS.get(industry, industry)
    session_store.add_audit(None, "Added reference standard",
                            f"Added '{name}' to {label} catalog.")
    return {"ok": True, "id": standard_id}


@app.delete("/api/catalog/standards/{standard_id}")
def delete_catalog_standard(standard_id: int):
    if not session_store.delete_standard(standard_id):
        raise HTTPException(status_code=404, detail="Standard not found.")
    session_store.add_audit(None, "Removed reference standard", f"Removed custom standard #{standard_id}.")
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


# The frontend is a single-page app with client-side routing (nav tabs update
# the URL via history.pushState). These paths have no server-side content of
# their own; they just need index.html re-served so a direct load/refresh
# lands on the same JS bundle, which then renders the right view from the URL.
@app.get("/home")
@app.get("/library")
@app.get("/sessions")
@app.get("/governance")
@app.get("/catalog")
@app.get("/settings")
def spa_route():
    return FileResponse(FRONTEND_DIR / "index.html")


# Mounted last so the explicit /api routes above always take precedence.
app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="frontend")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "5000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
