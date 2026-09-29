// Offline sample — only used if the backend/LLM is unreachable, and always
// shown with a clearly labeled "offline sample" banner (see setMode()).
const sampleEntities = [
  {
    name: "Member", badge: "REUSE 96%", definition: "A person eligible for or enrolled in a health benefit plan.", match: "MEMBER_CORE · 96%", standard: "FHIR Patient", classification: "Restricted / PHI", rationale: "The approved asset covers enterprise member identity and avoids creating a second person identifier.",
    clinicalConcept: "Patient", standardsMapping: { fhir: "Patient", omop: { table: "PERSON", domain: "Person" } }, evidence: ["Same clinical concept (Patient)", "94% field overlap with MEMBER_CORE", "Same classification (Restricted / PHI)"],
    fields: [["member_id", "PK · STRING"], ["enterprise_person_id", "STRING"], ["birth_date", "DATE"], ["status_code", "STRING"]]
  },
  {
    name: "Coverage", badge: "REUSE 91%", definition: "A period during which a member is enrolled in a health plan product.", match: "MEMBER_COVERAGE · 91%", standard: "FHIR Coverage", classification: "Restricted / PHI", rationale: "The existing coverage asset already contains effective-dated enrollment and product references.",
    clinicalConcept: "Coverage", standardsMapping: { fhir: "Coverage", omop: { table: "PAYER_PLAN_PERIOD", domain: "Observation Period" } }, evidence: ["Same clinical concept (Coverage)", "88% field overlap with MEMBER_COVERAGE", "Same classification (Restricted / PHI)"],
    fields: [["coverage_id", "PK · STRING"], ["member_id", "FK · STRING"], ["plan_id", "FK · STRING"], ["effective_period", "DATERANGE"]]
  },
  {
    name: "Provider", badge: "REUSE 94%", definition: "A practitioner or organization responsible for delivering care.", match: "PROVIDER_DIRECTORY · 94%", standard: "FHIR Practitioner", classification: "Internal", rationale: "The enterprise directory is authoritative for provider identity, specialty, and organization affiliation.",
    clinicalConcept: "Provider", standardsMapping: { fhir: "Practitioner", omop: { table: "PROVIDER", domain: "Provider" } }, evidence: ["Same clinical concept (Provider)", "91% field overlap with PROVIDER_DIRECTORY", "Same classification (Internal)"],
    fields: [["provider_id", "PK · STRING"], ["npi", "STRING"], ["specialty_code", "STRING"], ["organization_id", "FK · STRING"]]
  },
  {
    name: "Clinical Event", badge: "REUSE 88%", definition: "A normalized clinical occurrence associated with a member and date.", match: "CLINICAL_EVENT · 88%", standard: "FHIR Observation", classification: "Restricted / PHI", rationale: "The candidate normalizes encounters and observations while preserving source provenance.",
    clinicalConcept: "Encounter", standardsMapping: { fhir: "Encounter", omop: { table: "VISIT_OCCURRENCE", domain: "Visit" } }, evidence: ["Same clinical concept (Encounter)", "85% field overlap with CLINICAL_EVENT", "Same classification (Restricted / PHI)"],
    fields: [["event_id", "PK · STRING"], ["member_id", "FK · STRING"], ["event_type", "STRING"], ["event_date", "DATE"]]
  },
  {
    name: "Quality Measure", badge: "NEW", definition: "A governed definition of a healthcare quality assessment.", match: "No direct match", standard: "FHIR Measure", classification: "Internal", rationale: "No approved enterprise asset represents versioned measure definitions at the required grain.",
    clinicalConcept: "MeasureReport", standardsMapping: { fhir: "MeasureReport", omop: { table: "OBSERVATION", domain: "Observation" } }, evidence: ["No approved enterprise asset shares this clinical concept"],
    fields: [["measure_id", "PK · STRING"], ["measure_version", "STRING"], ["measure_name", "STRING"], ["effective_year", "INTEGER"]]
  },
  {
    name: "Member Measure Result", badge: "EXTEND 72%", definition: "A member-level quality measure result for a defined measurement period.", match: "QUALITY_GAP_RESULT · 72%", standard: "FHIR MeasureReport", classification: "Restricted / PHI", rationale: "The closest asset has useful semantics but the grain differs; create a governed result entity and map the source.",
    clinicalConcept: "MeasureReport", standardsMapping: { fhir: "MeasureReport", omop: { table: "OBSERVATION", domain: "Observation" } }, evidence: ["Same clinical concept (MeasureReport)", "58% field overlap with QUALITY_GAP_RESULT", "Same classification (Restricted / PHI)"],
    fields: [["result_id", "PK · STRING"], ["member_id", "FK · STRING"], ["measure_id", "FK · STRING"], ["result_status", "STRING"]]
  }
];

const sampleReuseRows = [
  ["Member", "MEMBER_CORE", "Identity domain · Certified", 96, "Name, identifier grain, glossary term", "Reuse"],
  ["Provider", "PROVIDER_DIRECTORY", "Provider domain · Certified", 94, "NPI, specialty, organization", "Reuse"],
  ["Coverage", "MEMBER_COVERAGE", "Enrollment domain · Approved", 91, "Effective period, plan, member", "Reuse"],
  ["Clinical Event", "CLINICAL_EVENT", "Clinical domain · Approved", 88, "Event type, date, provenance", "Reuse"],
  ["Member Measure Result", "QUALITY_GAP_RESULT", "Quality domain · Approved", 72, "Measure id, gap status", "Extend"],
];

const sampleReviews = [
  ["warning", "!", "Measurement period requires a grain decision", "Choose calendar year, rolling 12 months, or measure-defined period before physical design."],
  ["warning", "!", "Result status has no approved value set", "Map result_status to an enterprise reference set or the FHIR MeasureReport status values."],
  ["info", "i", "Provider attribution needs an effective period", "Add start and end dates to preserve historical member-provider attribution."],
];

const sampleDataQualityRules = [
  { rule_id: "MEMBER_ID_NOT_NULL", entity: "Member", field: "member_id", rule_type: "NOT_NULL", severity: "ERROR", description: "Every member record must have an enterprise identifier.", validation_query: "SELECT * FROM MEMBER WHERE MEMBER_ID IS NULL;" },
  { rule_id: "COVERAGE_MEMBER_RI", entity: "Coverage", field: "member_id", rule_type: "REFERENTIAL_INTEGRITY", severity: "ERROR", description: "Every coverage record must reference an existing member.", validation_query: "SELECT child.* FROM COVERAGE child LEFT JOIN MEMBER parent ON child.MEMBER_ID = parent.MEMBER_ID WHERE child.MEMBER_ID IS NOT NULL AND parent.MEMBER_ID IS NULL;" },
  { rule_id: "MEASURE_RESULT_STATUS_REQUIRED", entity: "Member Measure Result", field: "result_status", rule_type: "NOT_NULL", severity: "WARN", description: "A quality result must carry a result status.", validation_query: "SELECT * FROM MEMBER_MEASURE_RESULT WHERE RESULT_STATUS IS NULL;" },
];

const sampleArtifacts = {
  ddl: `-- Offline sample; not generated by a live model\nCREATE TABLE member_measure_result (\n  result_id VARCHAR NOT NULL PRIMARY KEY,\n  member_id VARCHAR NOT NULL,\n  measure_id VARCHAR NOT NULL,\n  measurement_start DATE NOT NULL,\n  measurement_end DATE NOT NULL,\n  result_status VARCHAR NOT NULL\n);`,
  dq_ddl: `-- Offline sample; not generated by a live model\nCREATE TABLE OCDP_PRD_OPTUMCARE_OPERATIONS_DB.VALIDATION.ONBOARDING_DQ_RULES (\n  RULE_ID VARCHAR(128) PRIMARY KEY,\n  ENTITY_NAME VARCHAR(256) NOT NULL,\n  FIELD_NAME VARCHAR(256),\n  RULE_TYPE VARCHAR(64) NOT NULL,\n  SEVERITY VARCHAR(16) NOT NULL,\n  RULE_DESCRIPTION VARCHAR(2000) NOT NULL,\n  CHECK_EXPRESSION VARCHAR(4000) NOT NULL,\n  VALIDATION_QUERY VARCHAR(8000) NOT NULL,\n  FORMAT_NAME VARCHAR(128),\n  ACTIVE_FLAG BOOLEAN NOT NULL\n);\n\n-- Example: SELECT * FROM MEMBER WHERE MEMBER_ID IS NULL;`,
  contract: `apiVersion: v3.2.0\nkind: DataContract\nid: member-quality-result\nname: Member Quality Result\nversion: 0.1.0\nstatus: draft\nschema:\n  - name: member_measure_result\n    properties:\n      - name: result_id\n        logicalType: string\n        required: true`,
  dictionary: `Entity,Attribute,Definition,Classification\nMember,member_id,Enterprise member identifier,Restricted\nCoverage,effective_period,Coverage eligibility period,Restricted\nQuality Measure,measure_version,Published measure version,Internal\nMember Measure Result,result_status,Quality assessment result,Restricted`
};

// Single source of truth for the Industry selector, its Reference standard
// options, its example prompts, and the Home "which standard should I use"
// guide table — every industry-aware UI surface reads from this map.
const INDUSTRY_STANDARDS = {
  healthcare: {
    label: "Healthcare",
    blurb: "Clinical and claims data \u2014 align to FHIR for interoperability and OMOP for observational analytics.",
    standards: ["FHIR R5 + enterprise glossary", "OMOP CDM 5.5 + enterprise glossary", "Enterprise glossary only"],
    examples: [
      ["Patient 360", "Create a longitudinal member data product for quality reporting. Connect member coverage, attributed providers, clinical events, and quality measures over time."],
      ["Medication adherence", "Model medication adherence for diabetic patients using prescription fills, clinical conditions, providers, and active insurance coverage."],
      ["ED utilization", "Design an emergency department utilization model that connects patients, encounters, diagnoses, procedures, providers, and payer coverage."],
    ],
  },
  fintech: {
    label: "Financial services",
    blurb: "Banking, payments, and risk data \u2014 align to ISO 20022 messaging and the FIBO ontology.",
    standards: ["ISO 20022 + enterprise glossary", "FIBO (Financial Industry Business Ontology)", "BIAN service landscape"],
    examples: [
      ["Customer 360", "Create a unified customer data product connecting accounts, transactions, cards, and risk scores across retail banking channels."],
      ["Fraud detection", "Model a fraud-detection feature store connecting transactions, devices, merchants, and dispute cases in near real time."],
      ["Loan servicing", "Design a loan servicing model connecting applicants, loan accounts, payment schedules, and delinquency status."],
    ],
  },
  edtech: {
    label: "Education",
    blurb: "Learner and course activity data \u2014 align to xAPI/Caliper for learning analytics interoperability.",
    standards: ["IMS Global Caliper Analytics", "xAPI (Experience API)", "SCORM 2004"],
    examples: [
      ["Learner 360", "Create a learner data product connecting enrollments, course activity, assessments, and completion status across programs."],
      ["Course engagement", "Model course engagement linking learners, content modules, video watch events, and quiz attempts over a term."],
      ["Credential tracking", "Design a model connecting learners, badges, certifications, and issuing institutions for credential verification."],
    ],
  },
  transport: {
    label: "Transport & logistics",
    blurb: "Fleet, route, and shipment data \u2014 align to GTFS for transit and EDIFACT/NDC for freight and travel.",
    standards: ["GTFS (General Transit Feed Specification)", "IATA NDC", "UN/EDIFACT"],
    examples: [
      ["Fleet 360", "Create a fleet operations data product connecting vehicles, drivers, routes, and maintenance events."],
      ["Shipment tracking", "Model shipment tracking connecting orders, carriers, shipments, checkpoints, and delivery exceptions."],
      ["Route performance", "Design a model connecting scheduled routes, trips, stops, and on-time performance metrics for transit planning."],
    ],
  },
  ecommerce: {
    label: "E-commerce & retail",
    blurb: "Product, order, and inventory data \u2014 align to GS1 identifiers and the schema.org product/offer vocabulary.",
    standards: ["GS1 / EPCIS", "schema.org Product/Offer", "UNSPSC"],
    examples: [
      ["Customer 360", "Create a customer data product connecting orders, carts, payments, and loyalty status across storefronts."],
      ["Catalog & inventory", "Model product catalog and inventory connecting SKUs, warehouses, stock levels, and supplier lead times."],
      ["Returns & fulfillment", "Design a model connecting orders, shipments, returns, and refund reasons for fulfillment operations."],
    ],
  },
  telecom: {
    label: "Telecommunications",
    blurb: "Subscriber, network, and usage data \u2014 align to TM Forum SID for OSS/BSS interoperability.",
    standards: ["TM Forum SID (Information Framework)", "3GPP data model", "MEF LSO"],
    examples: [
      ["Subscriber 360", "Create a subscriber data product connecting accounts, plans, devices, and usage events across mobile and broadband."],
      ["Network assurance", "Model network assurance connecting cell sites, alarms, incidents, and service impact for outage management."],
      ["Billing & usage", "Design a model connecting subscribers, rate plans, usage detail records, and invoices for billing reconciliation."],
    ],
  },
  generic: {
    label: "Other / general business",
    blurb: "Any other domain \u2014 use an enterprise glossary and ISO/IEC 11179 metadata conventions.",
    standards: ["Enterprise glossary only", "ISO/IEC 11179 metadata registry"],
    examples: [
      ["Customer 360", "Create a customer data product connecting accounts, interactions, and support tickets across channels."],
      ["Operations tracking", "Model core operational entities connecting orders, resources, and status events for process tracking."],
      ["Reference data governance", "Design a governed reference data model connecting business terms, codes, and their systems of record."],
    ],
  },
};

// Live state populated from the backend response (or the offline sample on failure).
let entities = [];
let reuseRows = [];
// Whether reuse-detection ran for this model (only when DDLs attached / catalog connected).
let reuseEnabled = false;
let reviews = [];
let dataQualityRules = [];
let artifacts = {};
// key: `${entityName}::${fieldName}` -> boolean, set only when a user manually
// overrides the isLikelyPhiField() heuristic from the entity-details popup.
let phiOverrides = {};
// Combined (backend + PHI access-control) rules currently shown in the DQ tab.
let renderedDqRules = [];
// Combined (backend + PHI privacy) findings currently shown in Design review.
let renderedReviews = [];
// Human-in-the-loop sign-off state, keyed by finding id -> {decision, reason, actor}.
// Loaded from the backend per session so decisions survive reloads.
let reviewResolutions = {};
// Index of the entity currently open in the entity-details popup, or null.
let openEntityIndex = null;
// "table" = just the open entity's DDL, "schema" = every table (replaces the old Schema (SQL) tab).
let entityDdlScope = "table";

// --- Multi-session conversations -------------------------------------------
// Each session is one conversation: a chat log plus the last generated model.
// The backend (SQLite via session_store.py) is the source of truth so
// conversations survive server restarts, not just page reloads; the frontend
// only caches the session list + the currently open session's detail.
let sessions = [];
let activeSessionId = null;
let activeSession = null;

const entityGrid = document.querySelector("#entityGrid");
const reuseTable = document.querySelector("#reuseTable");
const reviewList = document.querySelector("#reviewList");
const generateButton = document.querySelector("#generateButton");
const progressStrip = document.querySelector("#progressStrip");
const progressBar = document.querySelector("#progressBar");
const progressText = document.querySelector("#progressText");
const results = document.querySelector("#results");
const exportButton = document.querySelector("#exportButton");
const exportMenu = document.querySelector("#exportMenu");
const toast = document.querySelector("#toast");
const entityDialog = document.querySelector("#entityDialog");
const closeEntityDialog = document.querySelector("#closeEntityDialog");
const chatThread = document.querySelector("#chatThread");
const sessionList = document.querySelector("#sessionList");
const newChatButton = document.querySelector("#newChatButton");
const requirementInput = document.querySelector("#requirementInput");
const activeSessionBar = document.querySelector("#activeSessionBar");
const activeSessionNameInput = document.querySelector("#activeSessionNameInput");
const exitSessionButton = document.querySelector("#exitSessionButton");
const resetButton = document.querySelector("#resetButton");
const sessionCardGrid = document.querySelector("#sessionCardGrid");
const sessionManagerEmpty = document.querySelector("#sessionManagerEmpty");
const managerNewChatButton = document.querySelector("#managerNewChatButton");

function renderStandardsGuide() {
  const guide = document.querySelector("#standardsGuide");
  if (!guide) return;
  guide.innerHTML = Object.values(INDUSTRY_STANDARDS).map((industry) => `
    <div class="standards-guide-row">
      <strong>${industry.label}</strong>
      <span class="standards-guide-blurb">${industry.blurb}</span>
      <span class="standards-guide-tags">${industry.standards.map((s) => `<span class="chip">${s}</span>`).join("")}</span>
    </div>`).join("");
}

function applyIndustry(key) {
  const industry = INDUSTRY_STANDARDS[key] || INDUSTRY_STANDARDS.healthcare;
  const standardSelect = document.querySelector("#standardSelect");
  standardSelect.innerHTML = industry.standards.map((s) => `<option>${s}</option>`).join("");
  const presets = document.querySelector(".prompt-presets");
  presets.querySelectorAll("button[data-prompt]").forEach((btn) => btn.remove());
  industry.examples.forEach(([label, prompt]) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.dataset.prompt = prompt;
    btn.textContent = label;
    btn.addEventListener("click", () => {
      requirementInput.value = prompt;
      requirementInput.focus();
    });
    presets.appendChild(btn);
  });
}

document.querySelector("#industrySelect")?.addEventListener("change", (e) => applyIndustry(e.target.value));
renderStandardsGuide();
applyIndustry(document.querySelector("#industrySelect")?.value || "healthcare");

// Quick-fill chips shown once a model exists, offering common refine-message
// ideas so a follow-up "Send" doesn't require thinking one up from scratch.
document.querySelector("#followUpPresets")?.querySelectorAll("button[data-prompt]").forEach((btn) => {
  btn.addEventListener("click", () => {
    requirementInput.value = btn.dataset.prompt;
    requirementInput.focus();
  });
});

function decisionClass(badgeOrDecision) {
  const token = badgeOrDecision.toUpperCase();
  if (token.startsWith("REUSE")) return "reuse";
  if (token.startsWith("EXTEND")) return "extend";
  if (token.startsWith("REVIEW")) return "review";
  return "new";
}

const ENTITY_ICONS = ["◇", "▤", "✓", "◈", "▢", "◎", "⬡", "◆"];

function renderEntities() {
  entityGrid.innerHTML = entities.map((entity, index) => `
    <article class="entity-card ${index === 0 ? "selected" : ""}" data-entity="${index}" tabindex="0" role="button" aria-label="Inspect ${entity.name}">
      <header>
        <span class="entity-icon" aria-hidden="true">${ENTITY_ICONS[index % ENTITY_ICONS.length]}</span>
        <h3>${entity.name}</h3>
        <span class="decision-badge ${decisionClass(entity.badge)}">${entity.badge}</span>
        <span class="card-chevron" aria-hidden="true">›</span>
      </header>
      <p class="card-fieldline">${entity.fields.length} field${entity.fields.length === 1 ? "" : "s"}</p>
      <ul>${parseFields(entity).map((f) => `<li><span>${escHtml(f.name)}${f.isPhi ? ' <span class="phi-badge" title="PHI/PII">PHI</span>' : ""}</span><span>${escHtml(f.type)}</span></li>`).join("")}</ul>
    </article>`).join("");

  const reuseCount = entities.filter((entity) => entity.badge.startsWith("REUSE")).length;
  const extendCount = entities.filter((entity) => entity.badge.startsWith("EXTEND")).length;
  const reviewCount = entities.filter((entity) => entity.badge.startsWith("REVIEW")).length;
  const newCount = entities.filter((entity) => entity.badge.startsWith("NEW")).length;
  const phiColumnCount = entities.reduce((sum, entity) => sum + parseFields(entity).filter((f) => f.isPhi).length, 0);
  document.querySelector("#entityCount").textContent = entities.length;
  document.querySelector("#reuseCount").textContent = reuseCount;
  document.querySelector("#extendCount").textContent = extendCount;
  document.querySelector("#newCount").textContent = newCount;
  document.querySelector("#governanceReviewCount").textContent = reviewCount;
  document.querySelector("#phiColumnCount").textContent = phiColumnCount;
}

function matchTier(score) {
  const n = Number(score) || 0;
  if (n >= 90) return "high";
  if (n >= 70) return "medium";
  return "low";
}
function matchLabel(score) {
  const n = Number(score) || 0;
  const tier = matchTier(n);
  return tier === "high" ? "High" : tier === "medium" ? "Medium" : "Low";
}

function renderReuse() {
  reuseTable.innerHTML = reuseRows.map(([entity, asset, detail, score, evidence, decision]) => `
    <tr>
      <td><div class="reuse-cell-entity"><span class="entity-icon" aria-hidden="true">◇</span><div><strong>${entity}</strong></div></div></td>
      <td><div class="reuse-cell-asset"><strong>${asset}</strong><small>${detail}</small></div></td>
      <td><div class="match-indicator ${matchTier(score)}"><span class="match-dot"></span>${matchLabel(score)} (${score}%)</div></td>
      <td><div class="reuse-cell-evidence">${evidence}</div></td>
      <td><span class="decision-pill ${decisionClass(decision)}">${decision}</span></td>
    </tr>`).join("");
  document.querySelector("#reuseTabCount").textContent = reuseRows.length;
  document.querySelector("#reuseRecommendedCount").textContent = `${reuseRows.length} recommended`;
}

function reviewSeverity(type) {
  if (type === "privacy") return "privacy";
  if (type === "error") return "high";
  if (type === "warning") return "medium";
  return "low";
}

// One consolidated finding per entity that has PHI/PII columns, so privacy
// risk shows up in the same review queue instead of a separate RBAC screen.
function buildPrivacyFindings() {
  return entities
    .map((entity) => ({ entity, phiFields: parseFields(entity).filter((f) => f.isPhi) }))
    .filter(({ phiFields }) => phiFields.length)
    .map(({ entity, phiFields }) => [
      "privacy",
      "\u{1F512}",
      `${entity.name} exposes PHI/PII columns`,
      `${phiFields.map((f) => f.name).join(", ")} should be restricted to approved roles and exposed to general users only through a tokenized view. Review access in the entity's details popup.`,
    ]);
}

function renderReviews() {
  const ICONS = { warning: "!", info: "i", error: "\u00d7", privacy: "\u{1F512}" };
  renderedReviews = reviews.concat(buildPrivacyFindings());
  reviewList.innerHTML = renderedReviews.map((r) => {
    // Backend returns [type, title, detail]; offline sample uses [type, icon, title, detail].
    let type, icon, title, detail;
    if (r.length >= 4) { [type, icon, title, detail] = r; }
    else { [type, title, detail] = r; }
    icon = icon || ICONS[type] || "i";
    const severity = reviewSeverity(type);
    const severityLabel = severity === "high" ? "High" : severity === "medium" ? "Medium" : severity === "privacy" ? "Privacy" : "Low";
    const fid = findingId(title);
    const res = reviewResolutions[fid];
    const resolvedBlock = res ? renderResolvedBlock(res) : `
      <div class="review-resolve" data-fid="${fid}" data-title="${escapeHtml(title || "")}">
        <button type="button" class="review-resolve-open">Resolve <span aria-hidden="true">\u2192</span></button>
      </div>`;
    return `
    <article class="review-item ${type}${res ? " resolved" : ""}">
      <div class="review-top-pills"><span class="review-status-pill">${res ? "Resolved" : "Open"}</span><span class="review-severity-pill ${severity}">${severityLabel}</span></div>
      <h3>${title || ""}</h3>
      <div><p class="review-field-label">Issue</p><p>${detail || ""}</p></div>
      ${resolvedBlock}
    </article>`;
  }).join("");
  updateReviewProgress();
}

// Stable id for a finding derived from its title, so a resolution persists
// across reloads as long as the finding text is unchanged.
function findingId(title) {
  return (title || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80) || "finding";
}

function indexResolutions(list) {
  const out = {};
  (list || []).forEach((r) => { out[r.finding_id] = r; });
  return out;
}

const REVIEW_DECISION_LABELS = { mark_fixed: "Marked fixed", accept_risk: "Risk accepted", assign_review: "Assigned to review" };

function renderResolvedBlock(res) {
  const label = REVIEW_DECISION_LABELS[res.decision] || "Resolved";
  const when = res.created_at ? new Date(res.created_at).toLocaleString() : "";
  const reason = res.reason ? `<p class="review-resolve-reason">\u201c${escapeHtml(res.reason)}\u201d</p>` : "";
  return `<div class="review-resolved-note">
      <span class="review-resolved-badge">\u2713 ${label}</span>
      <span class="review-resolved-meta">by ${escapeHtml(res.actor || "You")}${when ? " \u00b7 " + when : ""}</span>
      ${reason}
    </div>`;
}

// Open the inline decision form for one finding (Mark fixed / Accept risk / Assign).
function openResolveForm(container) {
  const fid = container.dataset.fid;
  const title = container.dataset.title;
  container.innerHTML = `
    <div class="review-resolve-form">
      <label class="review-field-label" for="reason-${fid}">Decision reason (required to accept risk)</label>
      <input id="reason-${fid}" type="text" class="review-reason-input" placeholder="e.g. masked via tokenized view; owner signed off" />
      <div class="review-resolve-actions">
        <button type="button" class="review-decision" data-decision="mark_fixed" data-fid="${fid}" data-title="${escapeHtml(title)}">Mark fixed</button>
        <button type="button" class="review-decision danger" data-decision="accept_risk" data-fid="${fid}" data-title="${escapeHtml(title)}">Accept risk</button>
        <button type="button" class="review-decision" data-decision="assign_review" data-fid="${fid}" data-title="${escapeHtml(title)}">Assign to review</button>
        <button type="button" class="review-resolve-cancel">Cancel</button>
      </div>
    </div>`;
  container.querySelector(".review-reason-input")?.focus();
}

async function submitReviewDecision(btn) {
  if (!activeSessionId) { showToast("Open or generate a saved model first to record sign-off."); return; }
  const { decision, fid, title } = btn.dataset;
  const form = btn.closest(".review-resolve-form");
  const reason = form?.querySelector(".review-reason-input")?.value.trim() || "";
  if (decision === "accept_risk" && !reason) {
    showToast("A justification is required to accept risk.");
    form?.querySelector(".review-reason-input")?.focus();
    return;
  }
  form?.querySelectorAll("button").forEach((b) => { b.disabled = true; });
  try {
    const res = await fetch(`/api/governance/models/${activeSessionId}/reviews/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ findingId: fid, findingTitle: title, decision, reason }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not record the decision.");
    reviewResolutions[fid] = { ...data.resolution, created_at: new Date().toISOString() };
    renderReviews();
    showToast(`${REVIEW_DECISION_LABELS[decision]} \u2014 recorded in the governance audit trail`);
  } catch (err) {
    form?.querySelectorAll("button").forEach((b) => { b.disabled = false; });
    showToast(err.message || "Could not record the decision.");
  }
}

function updateReviewProgress() {
  const total = renderedReviews.length;
  const resolved = renderedReviews.filter((r) => {
    const title = r.length >= 4 ? r[2] : r[1];
    return Boolean(reviewResolutions[findingId(title)]);
  }).length;
  document.querySelector("#reviewTabCount").textContent = total;
  document.querySelector("#reviewScore").textContent = `${total} finding${total === 1 ? "" : "s"}`;
  document.querySelector("#reviewProgressLabel").textContent = `${resolved} / ${total}`;
  document.querySelector("#reviewProgressBar").style.width = `${total ? (resolved / total) * 100 : 0}%`;
}

function selectQualityRule(index) {
  const rule = renderedDqRules[index];
  if (!rule) return;
  document.querySelectorAll(".dq-rule-card").forEach((card) =>
    card.classList.toggle("selected", card.dataset.rule === String(index)));
  document.querySelector("#dqSelectedRule").textContent = rule.rule_id || `${rule.entity} ${rule.rule_type}`;
  document.querySelector("#dqSelectedDescription").textContent = rule.description || "Executable data quality check";
  document.querySelector("#dqQueryCode").textContent = rule.validation_query || "-- No query generated";
}

// PHI/PII tokenization view SQL, shared by the Data quality access-control
// rule and the "RBAC / tokenization SQL" export artifact.
function tokenizeExpr(dialect, column) {
  if (dialect === "SQL Server") return `dbo.tokenize_pii(${column})`;
  if (dialect === "Oracle") return `TOKENIZE_PII(${column})`;
  return `tokenize_pii(${column})`;
}

function buildTokenizedViewSql(entity, phiFields, dialect) {
  const table = tableName(entity.name);
  const phiNames = new Set(phiFields.map((f) => f.name));
  const projection = parseFields(entity).map((f) =>
    phiNames.has(f.name)
      ? `  ${tokenizeExpr(dialect, f.name)} AS ${f.name} /* PHI/PII TOKENIZED */`
      : `  ${f.name}`
  ).join(",\n");
  return [
    `-- Dialect: ${dialect}`,
    `-- Data steward / clinical analyst: full SELECT on ${table}.`,
    "-- General analyst: SELECT only on the tokenized view below.",
    `CREATE OR REPLACE VIEW ${table}_tokenized AS`,
    "SELECT",
    projection,
    `FROM ${table};`,
  ].join("\n");
}

function buildPhiAccessRules() {
  const dialect = (document.querySelector("#dialectSelect") || {}).value || "ANSI SQL";
  return entities.map((entity) => ({ entity, phiFields: parseFields(entity).filter((f) => f.isPhi) }))
    .filter(({ phiFields }) => phiFields.length)
    .map(({ entity, phiFields }) => ({
      rule_id: `${tableName(entity.name).toUpperCase()}_ACCESS_CONTROL`,
      rule_type: "ACCESS_CONTROL",
      severity: "ERROR",
      entity: entity.name,
      field: phiFields.map((f) => f.name).join(", "),
      description: `Restrict raw access to PHI/PII column(s) ${phiFields.map((f) => f.name).join(", ")}; expose only through a tokenized view.`,
      validation_query: buildTokenizedViewSql(entity, phiFields, dialect),
    }));
}

function buildRbacSqlArtifact() {
  const dialect = (document.querySelector("#dialectSelect") || {}).value || "ANSI SQL";
  const sections = entities.map((entity) => {
    const phiFields = parseFields(entity).filter((f) => f.isPhi);
    return phiFields.length ? buildTokenizedViewSql(entity, phiFields, dialect) : null;
  }).filter(Boolean);
  if (!sections.length) {
    return "-- No PHI/PII columns are currently flagged.\n-- Toggle a column's privacy status from an entity's details popup to generate tokenized-view SQL here.";
  }
  return [
    `-- RBAC / tokenization SQL for ${dialect}`,
    "-- Data steward / clinical analyst roles: full SELECT on the base table.",
    "-- General analyst role: SELECT only on the _tokenized view.",
    "",
    ...sections,
  ].join("\n\n");
}

function renderDataQuality() {
  artifacts.rbac_sql = buildRbacSqlArtifact();
  renderedDqRules = dataQualityRules.concat(buildPhiAccessRules());
  const errorCount = renderedDqRules.filter((rule) => String(rule.severity).toUpperCase() === "ERROR").length;
  const entityCount = new Set(renderedDqRules.map((rule) => rule.entity)).size;
  const phiRuleCount = renderedDqRules.filter((rule) => rule.rule_type === "ACCESS_CONTROL").length;
  document.querySelector("#dqTabCount").textContent = renderedDqRules.length;
  document.querySelector("#dqRuleCount").textContent = renderedDqRules.length;
  document.querySelector("#dqErrorCount").textContent = errorCount;
  document.querySelector("#dqEntityCount").textContent = entityCount;
  document.querySelector("#dqPhiCount").textContent = phiRuleCount;
  document.querySelector("#dqRuleList").innerHTML = renderedDqRules.length
    ? renderedDqRules.map((rule, index) => `
      <button class="dq-rule-card ${index === 0 ? "selected" : ""}" type="button" data-rule="${index}">
        <span class="dq-rule-top"><span class="dq-severity ${String(rule.severity).toLowerCase()}">${escHtml(rule.severity)}</span><span class="chip">${escHtml(rule.rule_type)}</span></span>
        <strong>${escHtml(rule.entity)}${rule.field ? ` · ${escHtml(rule.field)}` : ""}</strong>
        <small>${escHtml(rule.description)}</small>
      </button>`).join("")
    : '<div class="feature-note">No executable rules were generated for this model.</div>';
  if (renderedDqRules.length) selectQualityRule(0);
}

// ==========================================================================
//  ADDED FEATURES: ER diagram, DFD, Schema (SQL), Star/SF, Impact analysis.
//  Derived entirely from `entities` (+ `artifacts.ddl`) so the existing
//  backend and UI are untouched. All rendering is additive into new tabs.
// ==========================================================================
function escHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
function normName(s) { return String(s).toLowerCase().replace(/[^a-z0-9]/g, ""); }

function isRestrictedClassification(classification = "") {
  const normalized = String(classification).toLowerCase();
  return normalized.includes("phi") || normalized.includes("pii") || normalized.includes("restricted");
}

// Same-grain heuristic as backend classification: flags direct identifiers and
// clinical dates/ids on entities already classified Restricted/PHI/PII.
function isLikelyPhiField(fieldName, entity) {
  const name = String(fieldName).toLowerCase();
  const entityName = String(entity.name || "").toLowerCase();
  const concept = String(entity.clinicalConcept || entity.clinical_concept || "").toLowerCase();
  const directIdentifiers = [
    "ssn", "social_security", "medicare", "medicaid", "mrn", "medical_record",
    "person_id", "patient_id", "member_id", "subscriber_id", "enrollee_id",
    "first_name", "last_name", "full_name", "name", "dob", "birth_date", "date_of_birth",
    "email", "phone", "mobile", "address", "street", "city", "state", "zip", "postal",
  ];
  const clinicalDates = ["service_date", "event_date", "admit_date", "discharge_date", "fill_date", "result_date", "effective_period"];
  const clinicalEntity = ["patient", "member", "person", "encounter", "condition", "medication", "observation", "claim", "coverage"].some((token) =>
    entityName.includes(token) || concept.includes(token)
  );
  if (!isRestrictedClassification(entity.classification)) return false;
  if (directIdentifiers.some((token) => name.includes(token))) return true;
  return clinicalEntity && clinicalDates.some((token) => name.includes(token));
}

function isPhiField(field, entity) {
  const key = `${entity.name}::${field.name}`;
  return Object.prototype.hasOwnProperty.call(phiOverrides, key) ? phiOverrides[key] : isLikelyPhiField(field.name, entity);
}

function togglePhiField(entity, fieldName) {
  const key = `${entity.name}::${fieldName}`;
  const current = Object.prototype.hasOwnProperty.call(phiOverrides, key) ? phiOverrides[key] : isLikelyPhiField(fieldName, entity);
  phiOverrides[key] = !current;
}

function parseFields(entity) {
  return (entity.fields || []).map(([name, type]) => {
    // Token-based (not substring) so "SURROGATE"/"BILLING" etc never
    // false-match a bare PK/FK/BK tag.
    const tokens = new Set(String(type || "").toUpperCase().split(/[^A-Z0-9]+/).filter(Boolean));
    const field = { name, type, isPK: tokens.has("PK"), isFK: tokens.has("FK"), isBK: tokens.has("BK") };
    field.isPhi = isPhiField(field, entity);
    return field;
  });
}

function isMeasureType(type) {
  const t = String(type || "").toUpperCase();
  return t.includes("INT") || t.includes("DECIMAL") || t.includes("NUMBER") || t.includes("NUMERIC") || t.includes("FLOAT");
}

// Infer parent→child relationships from FK field names matching entity names.
function inferRelationships(ents = entities) {
  const byNorm = {};
  ents.forEach((e) => { byNorm[normName(e.name)] = e.name; });
  const rels = [];
  const seen = new Set();
  ents.forEach((e) => {
    parseFields(e).forEach((f) => {
      if (!f.isFK) return;
      // "sk" must be stripped too since surrogate FKs are named <parent>_sk;
      // without it "claim_line_sk" never normalizes to "claim_line" and a
      // fuzzy substring match can wrongly pick "claim" instead.
      const base = f.name.toLowerCase().replace(/_(id|key|code|fk|sid|sk|num)$/i, "");
      const cand = normName(base);
      let target = byNorm[cand];
      if (!target) {
        // Prefer the longest/most specific substring match instead of the
        // first one found, so "claimline" wins over "claim" for example.
        const fn = normName(f.name);
        let bestScore = 0;
        for (const [n, name] of Object.entries(byNorm)) {
          if (name === e.name) continue;
          let score = 0;
          if (n.length > 2 && fn.includes(n)) score = n.length;
          else if (cand.length > 2 && n.includes(cand)) score = cand.length;
          if (score > bestScore) { bestScore = score; target = name; }
        }
      }
      if (target && target !== e.name) {
        const key = target + "->" + e.name + ":" + f.name;
        if (!seen.has(key)) { seen.add(key); rels.push({ from: target, to: e.name, via: f.name }); }
      }
    });
  });
  return rels;
}

const F_COLORS = { source: "#f9a667", process: "#3d3c38", store: "#ff612b", consumer: "#d74120" };

// ---- ER diagram ----------------------------------------------------------
// Pure SVG builder so the same diagram can be drawn on the page and embedded
// in the exported PDF. Returns an <svg> string with a viewBox for scaling.
function buildErSvg(ents, rels) {
  const BW = 190, HEADER = 30, ROWH = 17, COLGAP = 60, ROWGAP = 92, PADX = 30, PADY = 24;
  const keyFieldsOf = (e) => parseFields(e).filter((f) => f.isPK || f.isFK || f.isBK).slice(0, 20);
  const maxRows = Math.max(1, ...ents.map((e) => keyFieldsOf(e).length));
  const BH = HEADER + maxRows * ROWH + 8;

  // Layered layout: referenced parents on top, FK-bearing children below, so
  // relationship arrows flow downward and rarely cross.
  const layerOf = {};
  const parentsOf = (name) => rels.filter((r) => r.to === name && r.from !== name).map((r) => r.from);
  const computeLayer = (name, guard) => {
    if (layerOf[name] != null) return layerOf[name];
    const ps = parentsOf(name).filter((p) => !guard.has(p));
    if (!ps.length) return (layerOf[name] = 0);
    let m = 0;
    ps.forEach((p) => { guard.add(p); m = Math.max(m, computeLayer(p, guard) + 1); guard.delete(p); });
    return (layerOf[name] = m);
  };
  ents.forEach((e) => computeLayer(e.name, new Set([e.name])));

  const byLayer = {};
  ents.forEach((e) => { (byLayer[layerOf[e.name]] ||= []).push(e); });
  const layerKeys = Object.keys(byLayer).map(Number).sort((a, b) => a - b);
  const maxPerLayer = Math.max(...layerKeys.map((k) => byLayer[k].length));
  const laneW = maxPerLayer * (BW + COLGAP) - COLGAP;

  const pos = {};
  layerKeys.forEach((k, rowIdx) => {
    const row = byLayer[k];
    const rowW = row.length * (BW + COLGAP) - COLGAP;
    const startX = PADX + (laneW - rowW) / 2;
    row.forEach((e, i) => { pos[e.name] = { x: startX + i * (BW + COLGAP), y: PADY + rowIdx * (BH + ROWGAP) }; });
  });
  const W = PADX * 2 + laneW;
  const H = PADY * 2 + layerKeys.length * (BH + ROWGAP) - ROWGAP;

  const hw = BW / 2, hh = BH / 2;
  const borderPoint = (cx, cy, tx, ty) => {
    const dx = tx - cx, dy = ty - cy;
    if (!dx && !dy) return { x: cx, y: cy };
    const scale = 1 / Math.max(Math.abs(dx) / hw, Math.abs(dy) / hh);
    return { x: cx + dx * scale, y: cy + dy * scale };
  };

  let svg = '<svg width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '" xmlns="http://www.w3.org/2000/svg">' +
    '<defs><marker id="erArrow" markerWidth="12" markerHeight="12" refX="10" refY="4" orient="auto" markerUnits="userSpaceOnUse">' +
    '<path d="M0,0 L10,4 L0,8 Z" fill="#8a8578"/></marker></defs>';

  // Edges: box border to box border with a gentle curve. A gap before the child
  // keeps the arrowhead visible (boxes are painted on top of the lines).
  rels.forEach((r) => {
    const a = pos[r.from], b = pos[r.to];
    if (!a || !b) return;
    const acx = a.x + hw, acy = a.y + hh, bcx = b.x + hw, bcy = b.y + hh;
    const p1 = borderPoint(acx, acy, bcx, bcy);
    const p2 = borderPoint(bcx, bcy, acx, acy);
    const dx = p2.x - p1.x, dy = p2.y - p1.y, dist = Math.hypot(dx, dy) || 1;
    const GAP = 11;
    const ex = p2.x - (dx / dist) * GAP, ey = p2.y - (dy / dist) * GAP;
    const midY = (p1.y + ey) / 2;
    svg += '<path d="M' + p1.x + ',' + p1.y + ' C' + p1.x + ',' + midY + ' ' + ex + ',' + midY + ' ' + ex + ',' + ey +
      '" fill="none" stroke="#b7b1a6" stroke-width="1.4" marker-end="url(#erArrow)"/>';
    const mx = (p1.x + ex) / 2, my = (p1.y + ey) / 2, lw = r.via.length * 6.2 + 8;
    svg += '<rect x="' + (mx - lw / 2) + '" y="' + (my - 8) + '" width="' + lw + '" height="15" rx="3" fill="#faf8f2" stroke="#e5e0d7"/>';
    svg += '<text x="' + mx + '" y="' + (my + 3) + '" text-anchor="middle" font-size="10" fill="#716f68" font-family="Segoe UI, sans-serif">' + escHtml(r.via) + "</text>";
  });

  ents.forEach((e) => {
    const p = pos[e.name];
    svg += '<rect x="' + p.x + '" y="' + p.y + '" width="' + BW + '" height="' + BH + '" rx="6" fill="#ffffff" stroke="#ff612b" stroke-width="1.4"/>';
    svg += '<rect x="' + p.x + '" y="' + p.y + '" width="' + BW + '" height="' + HEADER + '" rx="6" fill="#ffd1ab"/>';
    svg += '<text x="' + (p.x + 10) + '" y="' + (p.y + 20) + '" font-size="13" font-weight="700" fill="#3d3c38" font-family="Georgia, serif">' + escHtml(e.name) + "</text>";
    keyFieldsOf(e).forEach((f, i) => {
      const ty = p.y + HEADER + 14 + i * ROWH;
      const tag = f.isPK ? "PK" : f.isBK ? "BK" : "FK";
      const color = f.isPK ? "#d74120" : f.isBK ? "#3d3c38" : "#f9a667";
      svg += '<text x="' + (p.x + 10) + '" y="' + ty + '" font-size="10" font-weight="700" fill="' + color + '" font-family="Segoe UI, sans-serif">' + tag + "</text>";
      svg += '<text x="' + (p.x + 34) + '" y="' + ty + '" font-size="10" fill="#3d3c38" font-family="Segoe UI, sans-serif">' + escHtml(f.name) + "</text>";
    });
  });
  svg += "</svg>";
  return svg;
}

function renderER() {
  const rels = inferRelationships();
  document.querySelector("#erCanvas").innerHTML = buildErSvg(entities, rels);

  document.querySelector("#erRelCount").textContent = rels.length + " relationship" + (rels.length === 1 ? "" : "s");
  document.querySelector("#erTable").innerHTML = rels.length
    ? rels.map((r) => "<tr><td><strong>" + escHtml(r.from) + "</strong></td><td>" + escHtml(r.to) +
        "</td><td>" + escHtml(r.via) + "</td><td>one-to-many</td></tr>").join("")
    : '<tr><td colspan="4">No foreign-key relationships were inferred between these entities.</td></tr>';
}

// ---- DFD (top-to-bottom SVG) ---------------------------------------------
function buildDfdSvg(ents) {
  const layers = [
    { title: "External Sources", nodes: ["Source Systems"], cls: "source" },
    { title: "Process", nodes: ["Ingest & Validate"], cls: "process" },
    { title: "Data Stores", nodes: ents.map((e) => e.name), cls: "store" },
    { title: "Process", nodes: ["Serve Data Product"], cls: "process" },
    { title: "Consumers", nodes: ["Analytics & BI", "AI / ML", "Operational Apps", "Data Contracts"], cls: "consumer" },
  ];
  const BW = 150, BH = 44, HGAP = 26, ROWGAP = 18, VGAP = 58, PADX = 120, PADY = 22, CAP = 5;
  const maxNodes = Math.max(...layers.map((l) => l.nodes.length));
  const laneW = Math.min(CAP, maxNodes) * (BW + HGAP) - HGAP;
  const W = laneW + PADX + 40;

  let yCursor = PADY;
  const positioned = layers.map((layer) => {
    const n = layer.nodes.length, rowsN = Math.ceil(n / CAP) || 1;
    const nodes = layer.nodes.map((name, i) => {
      const row = Math.floor(i / CAP), colCount = row === rowsN - 1 ? n - row * CAP : CAP;
      const rowW = colCount * (BW + HGAP) - HGAP, startX = PADX + (laneW - rowW) / 2, col = i % CAP;
      const x = startX + col * (BW + HGAP), y = yCursor + row * (BH + ROWGAP);
      return { name, x, y, cx: x + BW / 2 };
    });
    const lh = rowsN * (BH + ROWGAP) - ROWGAP, rec = { ...layer, nodes, yTop: yCursor };
    yCursor += lh + VGAP;
    return rec;
  });
  const H = yCursor - VGAP + PADY;

  let svg = '<svg width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '" xmlns="http://www.w3.org/2000/svg">' +
    '<defs><marker id="dfdArrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">' +
    '<path d="M0,0 L8,3 L0,6 Z" fill="#c7c1b6"/></marker></defs>';
  const connect = (A, B) => A.length === 1 ? B.map((b) => [A[0], b]) : B.length === 1 ? A.map((a) => [a, B[0]]) : A.map((a, i) => [a, B[Math.min(i, B.length - 1)]]);
  for (let li = 0; li < positioned.length - 1; li++) {
    connect(positioned[li].nodes, positioned[li + 1].nodes).forEach(([a, b]) => {
      const y1 = a.y + BH, y2 = b.y, my = (y1 + y2) / 2;
      svg += '<path d="M' + a.cx + "," + y1 + " C" + a.cx + "," + my + " " + b.cx + "," + my + " " + b.cx + "," + y2 + '" fill="none" stroke="#d8d3ca" stroke-width="1.5" marker-end="url(#dfdArrow)"/>';
    });
  }
  positioned.forEach((layer) => {
    svg += '<text x="12" y="' + (layer.yTop + BH / 2 + 4) + '" fill="#716f68" font-size="11" font-family="Segoe UI, sans-serif">' + escHtml(layer.title) + "</text>";
    const color = F_COLORS[layer.cls];
    layer.nodes.forEach((node) => {
      const rx = layer.cls === "process" ? BH / 2 : 7;
      svg += '<rect x="' + node.x + '" y="' + node.y + '" width="' + BW + '" height="' + BH + '" rx="' + rx + '" fill="#ffffff" stroke="' + color + '" stroke-width="1.6"/>';
      if (layer.cls === "store") svg += '<rect x="' + node.x + '" y="' + node.y + '" width="5" height="' + BH + '" rx="2" fill="' + color + '"/>';
      const label = node.name.length > 19 ? node.name.slice(0, 18) + "…" : node.name;
      svg += '<text x="' + node.cx + '" y="' + (node.y + BH / 2 + 4) + '" text-anchor="middle" fill="#3d3c38" font-size="12" font-weight="600" font-family="Segoe UI, sans-serif">' + escHtml(label) + "</text>";
    });
  });
  svg += "</svg>";
  return svg;
}

function renderDFD() {
  document.querySelector("#dfdCanvas").innerHTML = buildDfdSvg(entities);
}

// ---- Schema (SQL) --------------------------------------------------------
function mapSqlType(typeHint, dialect) {
  const h = String(typeHint || "").toUpperCase();
  if (h.includes("DATERANGE") || h.includes("RANGE")) return "VARCHAR(64)";
  if (h.includes("DATE") || h.includes("TIMESTAMP")) return "DATE";
  if (h.includes("BOOL")) return dialect === "SQL Server" ? "BIT" : "BOOLEAN";
  if (h.includes("DECIMAL") || h.includes("NUMERIC") || h.includes("FLOAT")) return dialect === "Snowflake" ? "NUMBER(18,2)" : "DECIMAL(18,2)";
  if (h.includes("INT") || h.includes("NUMBER")) return dialect === "Snowflake" ? "NUMBER(38,0)" : dialect === "SQL Server" ? "INT" : "INTEGER";
  if (dialect === "SQL Server") return "NVARCHAR(256)";
  if (dialect === "Oracle") return "VARCHAR2(256)";
  return "VARCHAR(256)";
}

// Single-table CREATE TABLE with PK / FK / BK constraints inferred from the ER.
function buildEntityDDL(entity, dialect, pkOf, rels) {
  const t = tableName(entity.name);
  const fields = parseFields(entity);
  const cols = fields.map((f) => "  " + f.name + " " + mapSqlType(f.type, dialect) + (f.isPK ? " NOT NULL" : ""));
  const pks = fields.filter((f) => f.isPK).map((f) => f.name);
  if (pks.length) cols.push("  CONSTRAINT pk_" + t + " PRIMARY KEY (" + pks.join(", ") + ")");
  fields.filter((f) => f.isFK).forEach((f) => {
    const rel = rels.find((r) => r.to === entity.name && r.via === f.name);
    if (rel) {
      const pt = tableName(rel.from);
      const refCol = pkOf[rel.from] || (pt + "_id");
      cols.push("  CONSTRAINT fk_" + t + "_" + f.name + " FOREIGN KEY (" + f.name + ") REFERENCES " + pt + " (" + refCol + ")");
    }
  });
  const bks = fields.filter((f) => f.isBK).map((f) => f.name);
  if (bks.length) cols.push("  CONSTRAINT bk_" + t + " UNIQUE (" + bks.join(", ") + ")");
  return "CREATE TABLE " + t + " (\n" + cols.join(",\n") + "\n);";
}

// Deterministic DDL with PK / FK / NOT NULL constraints inferred from the ER.
function buildConstrainedDDL(dialect) {
  const rels = inferRelationships();
  const pkOf = {};
  entities.forEach((e) => { const pk = parseFields(e).find((f) => f.isPK); pkOf[e.name] = pk ? pk.name : null; });
  return entities.map((e) => buildEntityDDL(e, dialect, pkOf, rels)).join("\n\n");
}

// ---- Star / Snowflake ----------------------------------------------------
function tableName(name) { return name.replace(/(?<=[a-z0-9])(?=[A-Z])/g, "_").replace(/[^A-Za-z0-9]+/g, "_").toLowerCase().replace(/^_|_$/g, ""); }

function classifyDimensional(ents = entities) {
  const facts = [], dims = [];
  const factNames = new Set();
  ents.forEach((e) => {
    const fields = parseFields(e);
    const fkCount = fields.filter((f) => f.isFK).length;
    if (fkCount >= 2) factNames.add(e.name);
  });
  ents.forEach((e) => {
    const fields = parseFields(e);
    if (factNames.has(e.name)) {
      facts.push({
        name: e.name,
        measures: fields.filter((f) => !f.isPK && !f.isFK && isMeasureType(f.type)).map((f) => f.name),
        dimensions: fields.filter((f) => f.isFK).map((f) => {
          const base = f.name.toLowerCase().replace(/_(id|key|code|fk)$/i, "");
          return ents.find((x) => normName(x.name) === normName(base))?.name || base;
        }),
      });
    } else {
      const snow = fields.filter((f) => f.isFK).map((f) => {
        const base = f.name.toLowerCase().replace(/_(id|key|code|fk)$/i, "");
        const t = ents.find((x) => normName(x.name) === normName(base));
        return t && !factNames.has(t.name) ? t.name : null;
      }).filter(Boolean);
      dims.push({ name: e.name, attributes: fields.map((f) => f.name), snowflaked_to: [...new Set(snow)] });
    }
  });
  return { facts, dims };
}

function dimensionalDDL(c) {
  const lines = ["-- Dimensional (Star / Snowflake) schema", ""];
  c.dims.forEach((d) => {
    const t = tableName(d.name);
    lines.push("CREATE TABLE dim_" + t + " (");
    lines.push("  " + t + "_key NUMBER(38,0) NOT NULL,  -- surrogate key");
    lines.push("  " + t + "_id VARCHAR(255) NOT NULL,  -- natural key");
    lines.push("  CONSTRAINT pk_dim_" + t + " PRIMARY KEY (" + t + "_key)");
    lines.push(");", "");
  });
  c.facts.forEach((f) => {
    const t = tableName(f.name);
    const cols = ["  " + t + "_key NUMBER(38,0) NOT NULL"];
    f.dimensions.forEach((d) => cols.push("  " + tableName(d) + "_key NUMBER(38,0)"));
    (f.measures.length ? f.measures : ["record_count"]).forEach((m) => cols.push("  " + m + " NUMBER(18,2)"));
    cols.push("  CONSTRAINT pk_fact_" + t + " PRIMARY KEY (" + t + "_key)");
    lines.push("CREATE TABLE fact_" + t + " (", cols.join(",\n"), ");", "");
  });
  return lines.join("\n");
}

function renderStar() {
  const c = classifyDimensional();
  const snowflaked = c.dims.filter((d) => d.snowflaked_to.length).map((d) => d.name);
  document.querySelector("#starSummary").textContent =
    "Identified " + c.facts.length + " fact table(s) and " + c.dims.length + " dimension(s). Snowflaked: " +
    (snowflaked.join(", ") || "none") + ".";
  document.querySelector("#starFacts").innerHTML = c.facts.length
    ? c.facts.map((f) => '<div class="feature-card"><h3>★ ' + escHtml(f.name) + ' <small>fact</small></h3>' +
        "<div><strong>Measures:</strong> " + (f.measures.map((m) => '<span class="chip">' + escHtml(m) + "</span>").join(" ") || "record_count") + "</div>" +
        "<div style='margin-top:6px'><strong>Dimensions:</strong> " + (f.dimensions.map((d) => '<span class="chip alt">' + escHtml(d) + "</span>").join(" ") || "—") + "</div></div>").join("")
    : '<div class="feature-note">No fact tables detected (a fact needs 2+ foreign keys). This model is mostly reference/dimension data.</div>';
  document.querySelector("#starDims").innerHTML = c.dims.length
    ? c.dims.map((d) => "<tr><td><strong>" + escHtml(d.name) + "</strong></td><td>" + d.attributes.length + "</td><td>" +
        (d.snowflaked_to.length ? '<span class="chip alt">snowflaked → ' + escHtml(d.snowflaked_to.join(", ")) + "</span>" : "star (flat)") + "</td></tr>").join("")
    : '<tr><td colspan="3">None</td></tr>';
  document.querySelector("#starCode").textContent = dimensionalDDL(c);
}

// ---- Impact analysis -----------------------------------------------------
// Pure computation shared by the Impact tab and the PDF export.
function computeImpactRows(ents = entities, rels = inferRelationships(ents)) {
  const conceptOf = {};
  ents.forEach((e) => { conceptOf[e.name] = e.clinicalConcept || e.classification || "General"; });
  const deps = {};
  ents.forEach((e) => { deps[e.name] = new Set(); });
  rels.forEach((r) => { if (deps[r.from]) deps[r.from].add(r.to); });

  const transitive = (name) => {
    const seen = new Set(); const stack = [...(deps[name] || [])];
    while (stack.length) { const c = stack.pop(); if (seen.has(c)) continue; seen.add(c); stack.push(...(deps[c] || [])); }
    return seen;
  };

  return ents.map((e) => {
    const direct = [...(deps[e.name] || [])].sort();
    const downstream = [...transitive(e.name)].filter((x) => !direct.includes(x) && x !== e.name).sort();
    const generic = new Set([conceptOf[e.name], "Other", "General", "Internal", "Public"]);
    const domains = [...new Set([...direct, ...downstream].map((n) => conceptOf[n]))].filter((d) => d && !generic.has(d));
    const score = direct.length + downstream.length;
    const risk = score >= 4 ? "High" : score >= 1 ? "Medium" : "Low";
    return { name: e.name, concept: conceptOf[e.name], direct, downstream, domains, risk };
  }).sort((a, b) => ({ High: 0, Medium: 1, Low: 2 }[a.risk] - { High: 0, Medium: 1, Low: 2 }[b.risk]) || b.direct.length - a.direct.length);
}

function renderImpact() {
  const rows = computeImpactRows();
  const high = rows.filter((r) => r.risk === "High").length;
  document.querySelector("#impactSummary").textContent =
    entities.length + " entities analyzed · " + high + " high-risk. Changing a high-risk entity has the widest blast radius.";
  document.querySelector("#impactHelp").innerHTML =
    "<strong>How to read this:</strong> <em>Directly dependent</em> = tables with a foreign key straight to this one. " +
    "<em>Further downstream</em> = a second hop; \"none\" means the chain stops. <em>Impacted domains</em> = other business areas to notify.";
  const riskColor = (r) => r === "High" ? "#d74120" : r === "Medium" ? "#f9a667" : "#3d3c38";
  document.querySelector("#impactCards").innerHTML = rows.map((r) =>
    '<div class="feature-card"><div class="impact-head"><span class="risk-pill" style="border-color:' + riskColor(r.risk) + ';color:' + riskColor(r.risk) + '">' + r.risk + ' risk</span>' +
    "<strong>" + escHtml(r.name) + "</strong><small>concept: " + escHtml(r.concept) + "</small></div>" +
    '<div class="impact-line"><strong>Impacted domains:</strong> ' + (r.domains.length ? r.domains.map((d) => '<span class="chip warn">' + escHtml(d) + "</span>").join(" ") : "<em>only its own</em>") + "</div>" +
    '<div class="impact-line"><strong>Directly dependent:</strong> ' + (r.direct.map((d) => '<span class="chip alt">' + escHtml(d) + "</span>").join(" ") || "none") + "</div>" +
    '<div class="impact-line"><strong>Further downstream:</strong> ' + (r.downstream.map((d) => '<span class="chip">' + escHtml(d) + "</span>").join(" ") || "<em>none</em>") + "</div></div>").join("");
}

function renderFeatures() {
  try { renderER(); renderDFD(); renderDataQuality(); renderStar(); renderImpact(); }
  catch (err) { console.error("Feature render failed", err); }
}

function selectEntity(index) {
  const entity = entities[index];
  document.querySelectorAll(".entity-card").forEach((card) => card.classList.toggle("selected", card.dataset.entity === String(index)));
  document.querySelector("#selectedEntityName").textContent = entity.name;
  document.querySelector("#selectedEntityDefinition").textContent = entity.definition;
  document.querySelector("#selectedDecision").textContent = entity.badge;
  const statusDot = document.querySelector(".status-dot");
  statusDot.className = `status-dot ${decisionClass(entity.badge)}`;
  document.querySelector("#selectedMatch").textContent = entity.match;
  document.querySelector("#selectedConcept").textContent = entity.clinicalConcept || "Other";
  const mapping = entity.standardsMapping;
  document.querySelector("#selectedStandardsMapping").textContent = mapping
    ? `FHIR ${mapping.fhir || "\u2014"} \u00b7 OMOP ${mapping.omop?.table || "\u2014"}`
    : (entity.standard || "\u2014");
  const phiFieldCount = parseFields(entity).filter((f) => f.isPhi).length;
  document.querySelector("#selectedClassification").textContent = phiFieldCount
    ? `${entity.classification} \u00b7 ${phiFieldCount} PHI/PII column${phiFieldCount === 1 ? "" : "s"}`
    : entity.classification;
  document.querySelector("#selectedRationale").textContent = entity.rationale;
  const indexes = Array.isArray(entity.indexRecommendations) ? entity.indexRecommendations : [];
  const indexBlock = document.querySelector("#selectedIndexesBlock");
  if (indexBlock) {
    indexBlock.hidden = indexes.length === 0;
    document.querySelector("#selectedIndexes").innerHTML = indexes.map((ix) => {
      const cols = (ix.columns || []).join(", ");
      const tag = ix.unique ? '<span class="chip alt">UNIQUE</span> ' : "";
      const why = ix.access_pattern || ix.rationale || "";
      return `<li><code>${escHtml(cols)}</code> ${tag}<small>${escHtml(ix.name || "")}</small>${why ? `<span class="index-reco-why">${escHtml(why)}</span>` : ""}</li>`;
    }).join("");
  }
  document.querySelector("#selectedEvidence").innerHTML = (entity.evidence || []).map((item) => `<li>${item}</li>`).join("");

  const pctMatch = String(entity.badge).match(/(\d+)/);
  const pct = pctMatch ? Math.min(100, Number(pctMatch[1])) : 0;
  const circumference = 2 * Math.PI * 26;
  const gaugeFill = document.querySelector("#gaugeFill");
  gaugeFill.style.strokeDasharray = `${circumference}`;
  gaugeFill.style.strokeDashoffset = `${circumference - (circumference * pct) / 100}`;
  document.querySelector("#gaugeLabel").textContent = `${pct}%`;
  const reusedFieldCount = Math.round((entity.fields.length * pct) / 100);
  document.querySelector("#gaugeFieldSummary").textContent = entity.badge.startsWith("NEW")
    ? "No enterprise fields reused"
    : `${reusedFieldCount} of ${entity.fields.length} fields reused`;

  const chips = [`Source: ${entity.name}`];
  if (reuseEnabled && entity.clinicalConcept) chips.push("Glossary match");
  if (pct > 0) chips.push("Schema match");
  document.querySelector("#selectedEvidenceChips").innerHTML = chips.map((c) => `<span class="chip">${c}</span>`).join("");
}

function sampleValue(fieldName, typeHint, rowIndex) {
  const field = fieldName.toLowerCase();
  const type = String(typeHint || "").toUpperCase();
  if (field.includes("email")) return `member${rowIndex + 1}@example.org`;
  if (field.includes("phone")) return `555-010${rowIndex + 1}`;
  if (field.includes("date") || field.includes("period")) return rowIndex ? "2025-01-01" : "2024-01-01";
  if (field.includes("status")) return rowIndex ? "ACTIVE" : "PENDING";
  if (field.includes("year") || type.includes("INT")) return rowIndex ? "2025" : "2024";
  if (field.endsWith("_id") || field.endsWith("_key") || field.endsWith("_sk")) return `${field.toUpperCase()}_${String(rowIndex + 1).padStart(3, "0")}`;
  if (type.includes("BOOLEAN")) return rowIndex ? "TRUE" : "FALSE";
  if (field.includes("name")) return rowIndex ? "Jordan Lee" : "Alex Morgan";
  return rowIndex ? `Sample ${rowIndex + 1}` : "Sample value";
}

function columnDefinition(field, entity) {
  const normalized = field.name.toLowerCase().replace(/[^a-z0-9]/g, " ");
  if (field.isPK) return `System-generated surrogate key for each ${entity.name.toLowerCase()} record.`;
  if (field.isBK) return `Business/natural key identifying the ${entity.name.toLowerCase()} record in the source system.`;
  if (field.isFK) return `Identifier linking this ${entity.name.toLowerCase()} to its related parent entity.`;
  if (normalized.includes("email")) return "Email address used for contact or identity matching.";
  if (normalized.includes("date") || normalized.includes("period")) return "Date or period used to establish when the record applies.";
  if (normalized.includes("status")) return "Business lifecycle status for the record.";
  if (normalized.includes("name")) return "Human-readable business name or label.";
  return `Business attribute describing the ${entity.name.toLowerCase()} record.`;
}

function columnRole(field) {
  return field.isPK ? "Surrogate key" : field.isBK ? "Business key" : field.isFK ? "Foreign key" : "Attribute";
}

function columnPrivacyChip(field, entity) {
  return `<button type="button" class="privacy-toggle-chip ${field.isPhi ? "phi" : "not-phi"}" data-phi-toggle="${escHtml(entity.name)}::${escHtml(field.name)}" aria-pressed="${field.isPhi}">${field.isPhi ? "PHI/PII" : "\u2014"}</button>`;
}

function renderEntityDialogBody(index) {
  const entity = entities[index];
  if (!entity || !entityDialog) return;
  const fields = parseFields(entity);
  document.querySelector("#entityDialogTitle").textContent = entity.name;
  document.querySelector("#entityDialogDefinition").textContent = entity.definition || "No table definition was generated.";
  document.querySelector("#entityDialogMeta").innerHTML = [
    `<span><strong>Table</strong>${escHtml(tableName(entity.name).toUpperCase())}</span>`,
    `<span><strong>Classification</strong>${escHtml(entity.classification || "Unclassified")}</span>`,
    `<span><strong>Fields</strong>${fields.length}</span>`,
  ].join("");
  document.querySelector("#entityDictionaryBody").innerHTML = fields.map((field) => `
    <tr><td><strong>${escHtml(field.name)}</strong></td><td>${escHtml(field.type)}</td><td>${escHtml(columnRole(field))}</td><td>${columnPrivacyChip(field, entity)}</td><td>${escHtml(columnDefinition(field, entity))}</td></tr>`).join("");
  document.querySelector("#entitySamplesHead").innerHTML = `<tr>${fields.map((field) => `<th>${escHtml(field.name)}</th>`).join("")}</tr>`;
  document.querySelector("#entitySamplesBody").innerHTML = [0, 1, 2].map((rowIndex) =>
    `<tr>${fields.map((field) => `<td>${escHtml(sampleValue(field.name, field.type, rowIndex))}</td>`).join("")}</tr>`).join("");
  document.querySelector("#entitySampleCount").textContent = "3 rows";
  renderEntityDdl(entity);
}

// Same dialect selector and constraint logic the old Schema (SQL) tab used; scope toggle
// switches between just this entity and the full model (which the tab used to show).
function renderEntityDdl(entity) {
  const dialect = (document.querySelector("#dialectSelect") || {}).value || "ANSI SQL";
  document.querySelector("#entityDdlDialect").textContent = dialect;
  document.querySelectorAll(".ddl-scope-btn").forEach((btn) => btn.classList.toggle("active", btn.dataset.ddlScope === entityDdlScope));
  if (entityDdlScope === "schema") {
    const idx = entities.map((e) => indexStatementsFor(e, dialect)).filter(Boolean).join("\n\n");
    document.querySelector("#entityDdlCode").textContent = buildConstrainedDDL(dialect) + (idx ? `\n\n-- Recommended indexes\n${idx}` : "");
    return;
  }
  const rels = inferRelationships();
  const pkOf = {};
  entities.forEach((e) => { const pk = parseFields(e).find((f) => f.isPK); pkOf[e.name] = pk ? pk.name : null; });
  const idx = indexStatementsFor(entity, dialect);
  document.querySelector("#entityDdlCode").textContent = buildEntityDDL(entity, dialect, pkOf, rels) + (idx ? `\n\n-- Recommended indexes\n${idx}` : "");
}

// Client-side render of the model's index recommendations (from the server) as
// dialect-aware statements, appended below the CREATE TABLE so it shows on screen.
function indexStatementsFor(entity, dialect) {
  const recos = Array.isArray(entity.indexRecommendations) ? entity.indexRecommendations : [];
  if (!recos.length) return "";
  const t = tableName(entity.name);
  const traditional = ["PostgreSQL", "SQL Server", "Oracle"].includes(dialect);
  const lines = [];
  recos.forEach((ix) => {
    const cols = (ix.columns || []).join(", ");
    if (ix.access_pattern) lines.push(`-- Access pattern: ${ix.access_pattern}`);
    if (ix.rationale) lines.push(`-- Rationale: ${ix.rationale}`);
    if (traditional) {
      lines.push(`CREATE ${ix.unique ? "UNIQUE " : ""}INDEX ${ix.name} ON ${t} (${cols});`);
    } else if (dialect === "Snowflake") {
      lines.push(`-- ${ix.name}: consider CLUSTER BY (${cols}) on ${t}`);
    } else if (dialect === "Databricks") {
      lines.push(`-- ${ix.name}: consider OPTIMIZE ${t} ZORDER BY (${cols})`);
    } else {
      lines.push(`CREATE ${ix.unique ? "UNIQUE " : ""}INDEX ${ix.name} ON ${t} (${cols});`);
    }
    lines.push("");
  });
  return lines.join("\n").trim();
}

function openEntityDialog(index) {
  if (!entities[index] || !entityDialog) return;
  openEntityIndex = index;
  entityDdlScope = "table";
  selectEntity(index);
  renderEntityDialogBody(index);
  entityDialog.showModal();
}

document.querySelector(".ddl-scope-toggle").addEventListener("click", (event) => {
  const btn = event.target.closest("[data-ddl-scope]");
  if (!btn || !entities[openEntityIndex]) return;
  entityDdlScope = btn.dataset.ddlScope;
  renderEntityDdl(entities[openEntityIndex]);
});

document.querySelector("#entityDictionaryBody").addEventListener("click", (event) => {
  const toggle = event.target.closest("[data-phi-toggle]");
  if (!toggle) return;
  const [entityName, fieldName] = toggle.dataset.phiToggle.split("::");
  const entity = entities.find((e) => e.name === entityName);
  if (!entity) return;
  togglePhiField(entity, fieldName);
  renderEntityDialogBody(entities.indexOf(entity));
  renderEntities();
  renderDataQuality();
});



function showToast(message) {
  toast.textContent = message;
  toast.hidden = false;
  window.setTimeout(() => { toast.hidden = true; }, 2600);
}

function downloadArtifact(type) {
  const extensions = { ddl: "sql", index_ddl: "sql", dq_ddl: "sql", contract: "yaml", dictionary: "csv", rbac_sql: "sql" };
  const names = { ddl: "model-ddl", index_ddl: "index-recommendations", dq_ddl: "data-quality-rules", contract: "data-contract", dictionary: "data-dictionary", rbac_sql: "rbac-tokenization-sql" };
  const blob = new Blob([artifacts[type]], { type: "text/plain;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${names[type]}.${extensions[type]}`;
  link.click();
  URL.revokeObjectURL(link.href);
  exportMenu.hidden = true;
  showToast(`${link.download} downloaded`);
}

function setModeBanner(mode, detail) {
  const banner = document.querySelector("#modeBanner");
  if (!banner) return;
  banner.hidden = false;
  banner.className = `mode-banner ${mode}`;
  banner.textContent = mode === "live"
    ? `Live model response (deployment: ${detail})`
    : `Offline sample \u2014 LLM unavailable: ${detail}`;

  const title = document.querySelector("#statusBannerTitle");
  const desc = document.querySelector("#statusBannerDesc");
  if (title && desc) {
    if (mode === "live") {
      title.textContent = "Live model";
      desc.textContent = "This model is published and in use.";
    } else {
      title.textContent = "Offline sample";
      desc.textContent = `LLM unavailable \u2014 showing an illustrative sample: ${detail}`;
    }
  }
  const updated = document.querySelector("#statusUpdated");
  if (updated) {
    updated.textContent = `Last updated ${new Date().toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}`;
  }
}

function setDdlSourceBadge(source, dialect) {
  const badge = document.querySelector("#ddlSourceBadge");
  if (!badge) return;
  if (!source) {
    badge.hidden = true;
    return;
  }
  badge.hidden = false;
  badge.className = `ddl-source-badge ${source}`;
  badge.textContent = source === "llm-validated"
    ? `DDL: LLM-generated (${dialect}) \u00b7 validated`
    : `DDL: deterministic fallback (${dialect})`;
}

function animateProgress(labels) {
  let step = 0;
  progressStrip.hidden = false;
  const timer = window.setInterval(() => {
    if (step >= labels.length) return;
    progressText.textContent = labels[step][0];
    progressBar.style.width = `${labels[step][1]}%`;
    step += 1;
  }, 500);
  return () => window.clearInterval(timer);
}

async function loadSessions() {
  try {
    const res = await fetch("/api/sessions");
    const data = await res.json();
    sessions = data.sessions || [];
  } catch {
    sessions = [];
  }
}

function renderSessionList() {
  if (!sessionList) return;
  sessionList.innerHTML = "";
  sessions.forEach((s) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = `session-item ${s.session_id === activeSessionId ? "active" : ""}`;
    item.dataset.session = s.session_id;

    const title = document.createElement("span");
    title.className = "session-title";
    title.textContent = s.title || "New chat";
    item.appendChild(title);

    const del = document.createElement("span");
    del.className = "session-delete";
    del.dataset.deleteSession = s.session_id;
    del.title = "Delete conversation";
    del.setAttribute("aria-label", "Delete conversation");
    del.textContent = "\u00d7";
    item.appendChild(del);

    sessionList.appendChild(item);
  });
}

function appendChatBubbleDom(role, text) {
  const bubble = document.createElement("div");
  bubble.className = `chat-msg ${role}`;
  bubble.textContent = text;
  chatThread.appendChild(bubble);
}

function appendChatBubble(role, text) {
  chatThread.hidden = false;
  appendChatBubbleDom(role, text);
  chatThread.scrollTop = chatThread.scrollHeight;
}

function appendPendingBubble(text) {
  const bubble = document.createElement("div");
  bubble.className = "chat-msg pending";
  bubble.textContent = text;
  bubble.dataset.pending = "true";
  chatThread.hidden = false;
  chatThread.appendChild(bubble);
  chatThread.scrollTop = chatThread.scrollHeight;
}

function removePendingBubble() {
  chatThread.querySelector('[data-pending="true"]')?.remove();
}

// Swap the workspace-head's right-hand slot: plain "Reset" for a fresh draft,
// or the open conversation's (renameable) name + an "Exit" button once a
// session is loaded — same position, so users always know what's active.
function renderWorkspaceHeadActions() {
  const session = activeSession;
  const followUpPresets = document.querySelector("#followUpPresets");
  if (session) {
    resetButton.hidden = true;
    activeSessionBar.hidden = false;
    activeSessionNameInput.value = session.title || "New chat";
    if (followUpPresets) followUpPresets.hidden = false;
  } else {
    resetButton.hidden = false;
    activeSessionBar.hidden = true;
    if (followUpPresets) followUpPresets.hidden = true;
  }
}

function renderActiveSession() {
  const session = activeSession;
  const industry = session ? session.industry : "healthcare";
  const dialect = session ? session.dialect : "ANSI SQL";

  renderWorkspaceHeadActions();
  document.querySelector("#industrySelect").value = industry;
  applyIndustry(industry);
  if (session && session.standard) document.querySelector("#standardSelect").value = session.standard;
  document.querySelector("#dialectSelect").value = dialect;

  requirementInput.value = "";
  generateButton.querySelector("span").textContent = session ? "Send" : "Generate model";

  chatThread.innerHTML = "";
  const messages = session ? session.chat : [];
  messages.forEach((m) => appendChatBubbleDom(m.role, m.text));
  chatThread.hidden = messages.length === 0;

  if (session && session.model) {
    ({ entities, reuseRows, reviews, dataQualityRules, artifacts } = session.model);
    setModeBanner(session.model.mode, session.model.deployment);
    setDdlSourceBadge(session.model.ddlSource, session.model.dialect);
    results.hidden = false;
    renderEntities();
    renderReuse();
    renderReviews();
    selectEntity(0);
    renderFeatures();
  } else {
    entities = [];
    reuseRows = [];
    reviews = [];
    dataQualityRules = [];
    artifacts = {};
    results.hidden = true;
  }
}

async function switchToSession(id) {
  try {
    const res = await fetch(`/api/sessions/${id}`);
    if (!res.ok) throw new Error("Could not load that conversation.");
    activeSession = await res.json();
    reviewResolutions = indexResolutions(activeSession.reviewResolutions);
    activeSessionId = id;
  } catch {
    showToast("Could not load that conversation.");
    return;
  }
  renderSessionList();
  renderActiveSession();
}

function startNewChat() {
  activeSessionId = null;
  activeSession = null;
  renderSessionList();
  renderActiveSession();
  requirementInput.focus();
}

async function deleteSession(id) {
  try {
    await fetch(`/api/sessions/${id}`, { method: "DELETE" });
  } catch {
    showToast("Could not delete that conversation.");
    return;
  }
  if (activeSessionId === id) {
    activeSessionId = null;
    activeSession = null;
  }
  await loadSessions();
  renderSessionList();
  renderActiveSession();
}

async function renameSession(id, title) {
  try {
    await fetch(`/api/sessions/${id}/rename`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
  } catch {
    showToast("Could not rename that conversation.");
    return;
  }
  if (activeSessionId === id && activeSession) {
    activeSession.title = title;
    renderWorkspaceHeadActions();
  }
  await loadSessions();
  renderSessionList();
}

// ---- Attach existing DDL files (ride along with the first /api/generate) ----
let ddlFiles = [];
const ddlFileInput = document.querySelector("#ddlFileInput");
const ddlFileList = document.querySelector("#ddlFileList");
const attachBtn = document.querySelector("#attachBtn");
function renderChips() {
  if (!ddlFileList) return;
  ddlFileList.innerHTML = ddlFiles.map((f, i) =>
    `<li class="chip-file"><span>${f.name}</span>` +
    `<button type="button" class="fl-remove" data-i="${i}" aria-label="Remove ${f.name}">×</button></li>`).join("");
  if (attachBtn) attachBtn.classList.toggle("has-files", ddlFiles.length > 0);
}
function addDdlFiles(fileList) {
  const allowed = /\.(sql|txt|ddl)$/i;
  for (const f of fileList) {
    if (allowed.test(f.name) && !ddlFiles.some((x) => x.name === f.name && x.size === f.size)) ddlFiles.push(f);
  }
  renderChips();
}
if (attachBtn) attachBtn.addEventListener("click", () => ddlFileInput.click());
if (ddlFileInput) ddlFileInput.addEventListener("change", (e) => { addDdlFiles(e.target.files); ddlFileInput.value = ""; });
if (ddlFileList) ddlFileList.addEventListener("click", (e) => {
  const btn = e.target.closest(".fl-remove");
  if (btn) { ddlFiles.splice(Number(btn.dataset.i), 1); renderChips(); }
});

async function sendMessage() {
  const text = requirementInput.value.trim();
  const isFirstMessage = !activeSessionId;
  const hasFiles = isFirstMessage && ddlFiles && ddlFiles.length > 0;
  if (isFirstMessage && !hasFiles && text.length < 20) {
    showToast("Add a more specific business requirement, or attach DDL files.");
    return;
  }
  if (!isFirstMessage && text.length < 3) {
    showToast("Describe the change you want.");
    return;
  }

  const industry = document.querySelector("#industrySelect").value;
  const standard = document.querySelector("#standardSelect").value;
  const dialect = document.querySelector("#dialectSelect").value;

  const fileCount = hasFiles ? ddlFiles.length : 0;
  appendChatBubble("user", text || `Imported ${fileCount} DDL file(s)`);
  requirementInput.value = "";
  requirementInput.disabled = true;
  generateButton.disabled = true;
  appendPendingBubble(isFirstMessage ? (hasFiles ? "Importing your DDL model\u2026" : "Generating the model\u2026") : "Updating the model\u2026");

  try {
    const files = hasFiles
      ? await Promise.all(ddlFiles.map(async (f) => ({ name: f.name, content: await f.text() })))
      : [];
    const response = isFirstMessage
      ? await fetch("/api/generate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ requirement: text, industry, standard, dialect, files }),
        })
      : await fetch("/api/refine", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: activeSessionId, instruction: text, dialect }),
        });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || payload.error || `Request failed (${response.status})`);
    }

    activeSessionId = payload.sessionId;
    activeSession = { ...(activeSession || {}), title: payload.title || activeSession?.title, industry, dialect: payload.dialect || dialect };
    renderWorkspaceHeadActions();
    entities = payload.entities;
    reuseRows = payload.reuseRows;
    reuseEnabled = Boolean(payload.reuseEnabled);
    reviews = payload.reviews;
    reviewResolutions = {};
    dataQualityRules = payload.dataQualityRules || [];
    artifacts = payload.artifacts;
    setModeBanner("live", payload.deployment);
    setDdlSourceBadge(payload.ddlSource, payload.dialect);
    removePendingBubble();
    if (hasFiles) { ddlFiles = []; renderChips(); }
    appendChatBubble(
      "assistant",
      isFirstMessage
        ? (fileCount ? `Imported ${entities.length} entities from ${fileCount} DDL file(s).` : `Generated a draft model with ${entities.length} entities.`)
        : "Updated the model \u2014 tabs below now reflect this change."
    );
    results.hidden = false;
    renderEntities();
    renderReuse();
    renderReviews();
    selectEntity(0);
    renderFeatures();
    results.scrollIntoView({ behavior: "smooth", block: "start" });
    await loadSessions();
    renderSessionList();
  } catch (err) {
    if (isFirstMessage) {
      entities = sampleEntities;
      reuseRows = sampleReuseRows;
      reviews = sampleReviews;
      dataQualityRules = sampleDataQualityRules;
      artifacts = sampleArtifacts;
      setModeBanner("offline", err.message);
      setDdlSourceBadge(null);
      showToast("Backend unavailable \u2014 showing offline sample data.");
      results.hidden = false;
      renderEntities();
      renderReuse();
      renderReviews();
      selectEntity(0);
      renderFeatures();
    }
    removePendingBubble();
    appendChatBubble("error", err.message);
  } finally {
    requirementInput.disabled = false;
    generateButton.disabled = false;
    generateButton.querySelector("span").textContent = activeSessionId ? "Send" : "Generate model";
    requirementInput.focus();
  }
}

const comingSoonContent = {
  governance: {
    eyebrow: "GOVERNANCE \u00b7 PLANNED",
    title: "Governance",
    subtitle: "A single place to track approvals, ownership, and policy compliance across every governed model.",
    items: [
      ["Approval workflow", "Route draft models through steward and data-owner sign-off before they move from draft to published."],
      ["Policy checks", "Surface PHI/PII classification, retention, and access-control gaps found during design review, in one queue."],
      ["Audit trail", "Show who approved, extended, or reused which enterprise asset, and when."],
    ],
  },
  catalog: {
    eyebrow: "CATALOG \u00b7 PLANNED",
    title: "Catalog",
    subtitle: "Browse the enterprise assets ModelIQ matches against \u2014 certified entities, glossary terms, and standards mappings.",
    items: [
      ["Asset directory", "Search and filter certified/approved enterprise assets like MEMBER_CORE and PROVIDER_DIRECTORY."],
      ["Glossary explorer", "Inspect business definitions, domain concepts, and industry-standard mappings behind each asset."],
      ["Reuse analytics", "See which assets are reused most often across models, to guide future modeling decisions."],
    ],
  },
  settings: {
    eyebrow: "SETTINGS \u00b7 PLANNED",
    title: "Settings",
    subtitle: "Configure defaults for how ModelIQ generates and validates models.",
    items: [
      ["Defaults", "Set a default reference standard and target SQL dialect for new requirements."],
      ["Team access", "Manage who can generate, review, and approve drafts in your workspace."],
      ["Notifications", "Choose when to be notified about design-review findings or approval requests."],
    ],
  },
};

function showComingSoon(key, { updateUrl = true } = {}) {
  const content = comingSoonContent[key];
  if (!content) return;
  document.querySelector("#workspaceContent").hidden = true;
  document.querySelector("#homeGuide").hidden = true;
  document.querySelector("#sessionManager").hidden = true;
  document.querySelector("#governanceView").hidden = true;
  document.querySelector("#catalogView").hidden = true;
  const panel = document.querySelector("#comingSoon");
  panel.hidden = false;
  document.querySelector("#comingSoonEyebrow").textContent = content.eyebrow;
  document.querySelector("#comingSoonTitle").textContent = content.title;
  document.querySelector("#comingSoonSubtitle").textContent = content.subtitle;
  document.querySelector("#comingSoonList").innerHTML = content.items
    .map(([title, desc]) => `<li><strong>${title}</strong><span>${desc}</span></li>`)
    .join("");
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
  document.querySelector(`#nav${content.title}`)?.classList.add("active");
  if (updateUrl) setUrlPath(`/${key}`);
}

function showHomeGuide({ updateUrl = true } = {}) {
  document.querySelector("#workspaceContent").hidden = true;
  document.querySelector("#comingSoon").hidden = true;
  document.querySelector("#sessionManager").hidden = true;
  document.querySelector("#governanceView").hidden = true;
  document.querySelector("#catalogView").hidden = true;
  document.querySelector("#homeGuide").hidden = false;
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
  document.querySelector("#navHome").classList.add("active");
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (updateUrl) setUrlPath("/home");
}

function showWorkspace({ updateUrl = true } = {}) {
  document.querySelector("#comingSoon").hidden = true;
  document.querySelector("#homeGuide").hidden = true;
  document.querySelector("#sessionManager").hidden = true;
  document.querySelector("#governanceView").hidden = true;
  document.querySelector("#catalogView").hidden = true;
  document.querySelector("#workspaceContent").hidden = false;
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
  document.querySelector("#navLibrary").classList.add("active");
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (updateUrl) setUrlPath("/library");
}

function relativeTime(iso) {
  if (!iso) return "";
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

function renderSessionCards() {
  if (!sessionCardGrid) return;
  sessionCardGrid.innerHTML = "";
  sessionManagerEmpty.hidden = sessions.length > 0;
  sessions.forEach((s) => {
    const card = document.createElement("div");
    card.className = `session-card ${s.session_id === activeSessionId ? "active" : ""}`;

    const title = document.createElement("div");
    title.className = "session-card-title";
    title.textContent = s.title || "New chat";
    card.appendChild(title);

    const meta = document.createElement("div");
    meta.className = "session-card-meta";
    meta.textContent = `Updated ${relativeTime(s.updated_at)}`;
    card.appendChild(meta);

    const actions = document.createElement("div");
    actions.className = "session-card-actions";

    const open = document.createElement("button");
    open.type = "button";
    open.className = "primary-button";
    open.textContent = "Open";
    open.addEventListener("click", async () => {
      await switchToSession(s.session_id);
      showWorkspace();
    });
    actions.appendChild(open);

    const rename = document.createElement("button");
    rename.type = "button";
    rename.className = "icon-action";
    rename.title = "Rename";
    rename.setAttribute("aria-label", "Rename conversation");
    rename.textContent = "\u270e";
    rename.addEventListener("click", () => {
      const next = window.prompt("Rename conversation", s.title || "");
      if (next && next.trim()) renameSession(s.session_id, next.trim()).then(renderSessionCards);
    });
    actions.appendChild(rename);

    const del = document.createElement("button");
    del.type = "button";
    del.className = "icon-action";
    del.title = "Delete";
    del.setAttribute("aria-label", "Delete conversation");
    del.textContent = "\u00d7";
    del.addEventListener("click", async () => {
      await deleteSession(s.session_id);
      renderSessionCards();
    });
    actions.appendChild(del);

    card.appendChild(actions);
    sessionCardGrid.appendChild(card);
  });
}

async function showSessionManager({ updateUrl = true } = {}) {
  document.querySelector("#workspaceContent").hidden = true;
  document.querySelector("#homeGuide").hidden = true;
  document.querySelector("#comingSoon").hidden = true;
  document.querySelector("#governanceView").hidden = true;
  document.querySelector("#catalogView").hidden = true;
  document.querySelector("#sessionManager").hidden = false;
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
  document.querySelector("#navSessions").classList.add("active");
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (updateUrl) setUrlPath("/sessions");
  await loadSessions();
  renderSessionCards();
}

// --- Governance view ---------------------------------------------------------

const STATUS_META = {
  draft: { label: "Draft", cls: "draft" },
  approved: { label: "Approved", cls: "approved" },
  needs_revision: { label: "Needs revision", cls: "revision" },
};
let governanceModels = [];

function hideStandardPanels() {
  document.querySelector("#workspaceContent").hidden = true;
  document.querySelector("#homeGuide").hidden = true;
  document.querySelector("#comingSoon").hidden = true;
  document.querySelector("#sessionManager").hidden = true;
}

async function showGovernance({ updateUrl = true } = {}) {
  hideStandardPanels();
  document.querySelector("#catalogView").hidden = true;
  document.querySelector("#governanceView").hidden = false;
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
  document.querySelector("#navGovernance").classList.add("active");
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (updateUrl) setUrlPath("/governance");
  await loadGovernanceModels();
}

async function loadGovernanceModels() {
  const tbody = document.querySelector("#governanceTable");
  try {
    const res = await fetch("/api/governance/models");
    const data = await res.json();
    governanceModels = data.models || [];
  } catch {
    showToast("Could not load models.");
    governanceModels = [];
  }
  renderGovMetrics();
  document.querySelector("#governanceEmpty").hidden = governanceModels.length > 0;
  tbody.innerHTML = governanceModels.map((m) => {
    const meta = STATUS_META[m.status] || STATUS_META.draft;
    return `<tr data-session="${m.sessionId}">
      <td><strong>${escapeHtml(m.title)}</strong><small class="gov-sub">${escapeHtml(m.standard || "")}</small></td>
      <td>${escapeHtml(m.industry)}</td>
      <td>${m.stats.entities}</td>
      <td>${m.stats.phiColumns}</td>
      <td><span class="status-pill ${meta.cls}">${meta.label}</span></td>
      <td class="gov-actions">
        <button class="mini-button" data-act="policy">Policy checks</button>
        <button class="mini-button" data-act="approve">Approve</button>
        <button class="mini-button" data-act="revise">Needs revision</button>
        <button class="mini-button primary" data-act="pdf">Export PDF</button>
        <button class="mini-button" data-act="audit">Audit</button>
      </td>
    </tr>`;
  }).join("");
}

function renderGovMetrics() {
  const total = governanceModels.length;
  const approved = governanceModels.filter((m) => m.status === "approved").length;
  const pending = governanceModels.filter((m) => m.status !== "approved").length;
  const phi = governanceModels.reduce((n, m) => n + (m.stats.phiColumns || 0), 0);
  document.querySelector("#govMetrics").innerHTML = `
    <div class="gov-metric"><strong>${total}</strong><span>Models</span></div>
    <div class="gov-metric approved"><strong>${approved}</strong><span>Approved</span></div>
    <div class="gov-metric pending"><strong>${pending}</strong><span>Awaiting review</span></div>
    <div class="gov-metric phi"><strong>${phi}</strong><span>PHI/PII columns</span></div>`;
}

async function setModelStatus(sessionId, status) {
  try {
    const res = await fetch(`/api/governance/models/${sessionId}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    if (!res.ok) throw new Error();
    showToast(`Model marked ${STATUS_META[status].label}.`);
    await loadGovernanceModels();
  } catch {
    showToast("Could not update status.");
  }
}

async function openPolicyModal(sessionId) {
  const modal = document.querySelector("#policyModal");
  try {
    const res = await fetch(`/api/governance/models/${sessionId}/policy`);
    const data = await res.json();
    const findings = data.findings || [];
    document.querySelector("#policyModalTitle").textContent = `Policy checks · ${data.title || ""}`;
    document.querySelector("#policyCounts").innerHTML = `
      <span class="policy-count high">${data.counts.high} high</span>
      <span class="policy-count privacy">${data.counts.privacy} privacy</span>
      <span class="policy-count low">${data.counts.low} low</span>`;
    document.querySelector("#policyEmpty").hidden = findings.length > 0;
    document.querySelector("#policyList").innerHTML = findings.map((f) => `
      <div class="policy-item ${f.severity}">
        <span class="policy-sev">${f.severity}</span>
        <div><strong>${escapeHtml(f.policy)}${f.entity ? ` · ${escapeHtml(f.entity)}` : ""}</strong>
        <p>${escapeHtml(f.detail)}</p></div>
      </div>`).join("");
    modal.hidden = false;
  } catch {
    showToast("Could not run policy checks.");
  }
}

async function toggleAuditPanel(sessionId = null) {
  const panel = document.querySelector("#govAuditPanel");
  if (!panel.hidden && !sessionId) { panel.hidden = true; return; }
  try {
    const url = sessionId ? `/api/governance/audit?session_id=${sessionId}` : "/api/governance/audit";
    const res = await fetch(url);
    const data = await res.json();
    const events = data.events || [];
    document.querySelector("#govAuditTitle").textContent = sessionId ? "Audit trail · this model" : "Audit trail";
    document.querySelector("#auditEmpty").hidden = events.length > 0;
    document.querySelector("#auditList").innerHTML = events.map((e) => `
      <li class="audit-item">
        <div class="audit-dot"></div>
        <div><strong>${escapeHtml(e.action)}</strong>
        <p>${escapeHtml(e.detail || "")}${e.title ? ` · <em>${escapeHtml(e.title)}</em>` : ""}</p>
        <small>${escapeHtml(e.actor || "You")} · ${relativeTime(e.created_at)}</small></div>
      </li>`).join("");
    panel.hidden = false;
    panel.scrollIntoView({ behavior: "smooth" });
  } catch {
    showToast("Could not load audit trail.");
  }
}

// Export a full generated model as a formatted, print-to-PDF document. Uses the
// browser's own print pipeline (Save as PDF) so it works offline with no deps.
async function exportModelPdf(sessionId) {
  let model, meta;
  try {
    const res = await fetch(`/api/sessions/${sessionId}`);
    if (!res.ok) throw new Error();
    const data = await res.json();
    model = data.model;
    meta = data;
  } catch {
    showToast("Could not load the model for export.");
    return;
  }
  if (!model) { showToast("This model has no content to export."); return; }
  const gm = governanceModels.find((m) => m.sessionId === sessionId);
  if (gm) meta.status = gm.status;
  const html = buildModelPdfHtml(model, meta);
  const win = window.open("", "_blank");
  if (!win) { showToast("Allow pop-ups to export the PDF."); return; }
  win.document.open();
  win.document.write(html);
  win.document.close();
  win.focus();
  setTimeout(() => win.print(), 400);
  try { await fetch("/api/governance/audit"); } catch { /* best-effort */ }
}

function buildModelPdfHtml(model, meta) {
  const esc = escapeHtml;
  const ents = model.entities || [];
  const reviews = model.reviews || [];
  const reuseRows = model.reuseRows || [];
  const dq = model.dataQualityRules || [];
  const artifacts = model.artifacts || {};
  const now = new Date().toLocaleString();

  const rels = inferRelationships(ents);
  const dim = classifyDimensional(ents);
  const impact = computeImpactRows(ents, rels);
  const phiCols = ents.reduce((n, e) => n + parseFields(e).filter((f) => f.isPhi).length, 0);
  const statusLabel = { approved: "Approved", needs_revision: "Needs revision", draft: "Draft" }[meta.status] || "Draft";

  const logo = '<svg viewBox="0 0 32 32" width="34" height="34" xmlns="http://www.w3.org/2000/svg">' +
    '<rect x="3" y="3" width="8" height="8" rx="2" fill="#002677"/><rect x="21" y="3" width="8" height="8" rx="2" fill="#002677"/>' +
    '<rect x="3" y="21" width="8" height="8" rx="2" fill="#ff612b"/><rect x="17" y="17" width="12" height="12" rx="3" fill="#002677"/>' +
    '<path d="M9.5 10.5 18 18M25 10.5 22.4 17M10.5 24.5 17.5 22.5" stroke="#ff612b" stroke-width="1.8" stroke-linecap="round"/></svg>';

  const entitySections = ents.map((e) => {
    const flds = parseFields(e);
    const fieldRows = flds.map((f) => {
      const key = f.isPK ? "PK" : f.isFK ? "FK" : f.isBK ? "BK" : "";
      return `<tr><td>${esc(f.name)}${f.isPhi ? ' <span class="phi">PHI/PII</span>' : ""}</td><td>${esc(f.type || "")}</td><td class="k">${key}</td></tr>`;
    }).join("");
    const evidence = (e.evidence || []).map((v) => `<li>${esc(v)}</li>`).join("");
    return `<div class="ent">
      <h3>${esc(e.name)} <span class="badge">${esc(e.badge || "")}</span></h3>
      <p class="def">${esc(e.definition || "")}</p>
      <table class="meta"><tbody>
        <tr><th>Classification</th><td>${esc(e.classification || "—")}</td><th>Domain concept</th><td>${esc(e.clinicalConcept || "—")}</td></tr>
        <tr><th>Enterprise match</th><td>${esc(e.match || "—")}</td><th>Reference standard</th><td>${esc(e.standard || "—")}</td></tr>
      </tbody></table>
      <table class="fields"><thead><tr><th>Field</th><th>Type</th><th>Key</th></tr></thead><tbody>${fieldRows}</tbody></table>
      ${evidence ? `<p class="sub">Reuse evidence</p><ul>${evidence}</ul>` : ""}
      ${e.rationale ? `<p class="rationale"><strong>Rationale.</strong> ${esc(e.rationale)}</p>` : ""}
    </div>`;
  }).join("");

  const relRows = rels.length
    ? rels.map((r) => `<tr><td><strong>${esc(r.from)}</strong></td><td>${esc(r.to)}</td><td>${esc(r.via)}</td><td>one-to-many</td></tr>`).join("")
    : `<tr><td colspan="4" class="muted">No foreign-key relationships were inferred between these entities.</td></tr>`;

  const reuseTable = reuseRows.map((r) => `<tr>${r.map((c) => `<td>${esc(String(c))}</td>`).join("")}</tr>`).join("");

  const reviewRows = reviews.map((r) => {
    const a = Array.isArray(r) ? r : [];
    const type = String(a[0] || "").toLowerCase();
    const titleText = a.length >= 3 ? a[a.length - 2] : a[1] || "";
    const title = esc(titleText);
    const detail = esc(a[a.length - 1] || "");
    const res = (meta.reviewResolutions || []).find((x) => x.finding_id === findingId(titleText));
    const signoff = res
      ? `<br><span class="signoff">✓ ${esc(REVIEW_DECISION_LABELS[res.decision] || "Resolved")} by ${esc(res.actor || "You")}${res.reason ? ` — “${esc(res.reason)}”` : ""}</span>`
      : "";
    return `<tr><td class="rv ${esc(type)}">${esc(type)}</td><td><strong>${title}</strong><br>${detail}${signoff}</td></tr>`;
  }).join("");

  const dqRows = dq.map((d) =>
    `<tr><td>${esc(d.entity || "")}</td><td>${esc(d.field || "—")}</td><td>${esc(d.rule_type || "")}</td><td>${esc(d.severity || "")}</td><td>${esc(d.description || "")}</td></tr>`).join("");

  const factCards = dim.facts.length
    ? dim.facts.map((f) => `<div class="card"><strong>★ ${esc(f.name)} <span class="tag">fact</span></strong>
        <div><em>Measures:</em> ${f.measures.length ? f.measures.map(esc).join(", ") : "record_count"}</div>
        <div><em>Dimensions:</em> ${f.dimensions.map(esc).join(", ") || "—"}</div></div>`).join("")
    : `<p class="muted">No fact tables detected (a fact needs 2+ foreign keys); this model is mostly reference/dimension data.</p>`;
  const dimRows = dim.dims.length
    ? dim.dims.map((d) => `<tr><td><strong>${esc(d.name)}</strong></td><td>${d.attributes.length}</td><td>${d.snowflaked_to.length ? "snowflaked → " + esc(d.snowflaked_to.join(", ")) : "star (flat)"}</td></tr>`).join("")
    : `<tr><td colspan="3" class="muted">None</td></tr>`;
  const dimDdl = esc(dimensionalDDL(dim));

  const impactRows = impact.map((r) =>
    `<tr><td><strong>${esc(r.name)}</strong></td><td class="risk-${r.risk.toLowerCase()}">${r.risk}</td><td>${r.direct.map(esc).join(", ") || "none"}</td><td>${r.downstream.map(esc).join(", ") || "none"}</td><td>${r.domains.map(esc).join(", ") || "—"}</td></tr>`).join("");

  const ddl = esc(artifacts.ddl || "");
  const contract = esc(artifacts.contract || "");
  const dictionary = esc(artifacts.dictionary || "");

  const section = (title, body) => body ? `<section class="sec"><h2>${title}</h2>${body}</section>` : "";

  return `<!doctype html><html><head><meta charset="utf-8"><title>${esc(meta.title || "Model")} — ModelIQ</title>
  <style>
    @page { size: A4; margin: 0; }
    * { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; }
    body { font-family: 'Segoe UI', Arial, sans-serif; color: #1a2233; font-size: 11.5px; line-height: 1.45; counter-reset: sec; padding: 13mm 14mm; }
    h1 { color: #002677; font-size: 22px; margin: 0; }
    h2 { color: #002677; font-size: 15px; margin: 0 0 8px; padding-bottom: 4px; border-bottom: 2px solid #ff612b; counter-increment: sec; page-break-after: avoid; }
    h2::before { content: counter(sec) ".\\00a0\\00a0"; color: #ff612b; }
    h3 { font-size: 13px; margin: 0 0 3px; color: #10233f; page-break-after: avoid; }
    .sec { margin: 0 0 18px; }
    .sec:last-child { margin-bottom: 0; }
    p { margin: 0 0 6px; }
    .sub { font-size: 10px; text-transform: uppercase; letter-spacing: .4px; color: #45536b; margin: 8px 0 2px; }
    .muted { color: #6b7688; }
    /* Cover masthead */
    .mast { display: flex; align-items: center; gap: 12px; border-bottom: 3px solid #002677; padding-bottom: 12px; margin-bottom: 4px; }
    .mast .brand { font-size: 12px; color: #6b7688; letter-spacing: .3px; }
    .mast .brand b { display: block; font-size: 18px; color: #002677; letter-spacing: 0; }
    .cover-meta { width: 100%; margin: 12px 0 6px; }
    .cover-meta td { border: 0; padding: 3px 0; }
    .cover-meta .lbl { color: #6b7688; text-transform: uppercase; font-size: 9.5px; letter-spacing: .4px; width: 90px; }
    .pill { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 10px; font-weight: 700; }
    .pill.approved { background: #dcefe3; color: #1c6b41; }
    .pill.draft { background: #eef1f8; color: #002677; }
    .pill.needs_revision { background: #fbe6de; color: #a3341c; }
    .kpis { display: flex; gap: 8px; margin: 14px 0 2px; }
    .kpi { flex: 1; border: 1px solid #d7dce6; border-radius: 8px; padding: 8px 10px; text-align: center; }
    .kpi strong { display: block; font-size: 18px; color: #002677; }
    .kpi span { font-size: 9px; color: #6b7688; text-transform: uppercase; letter-spacing: .3px; }
    table { width: 100%; border-collapse: collapse; margin: 4px 0 6px; }
    th, td { border: 1px solid #d7dce6; padding: 4px 7px; text-align: left; vertical-align: top; }
    th { background: #f2f5fb; font-size: 10px; text-transform: uppercase; letter-spacing: .3px; color: #45536b; }
    td.k { font-weight: 700; color: #002677; width: 40px; }
    table.meta th { width: 105px; }
    .ent { page-break-inside: avoid; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px dashed #e0e4ec; }
    .ent:last-child { border-bottom: 0; }
    .badge { font-size: 9px; background: #eef1f8; color: #002677; padding: 2px 7px; border-radius: 10px; vertical-align: middle; }
    .def { color: #45536b; margin: 1px 0 6px; }
    .rationale { color: #45536b; margin-top: 4px; }
    .phi { font-size: 8px; background: #fbe6de; color: #a3341c; padding: 1px 5px; border-radius: 8px; font-weight: 700; }
    .rv { text-transform: capitalize; font-weight: 700; white-space: nowrap; width: 74px; }
    .rv.privacy, .rv.high { color: #c0392b; }
    .rv.warning { color: #b9770e; }
    .risk-high { color: #c0392b; font-weight: 700; }
    .risk-medium { color: #b9770e; font-weight: 700; }
    .risk-low { color: #45536b; font-weight: 700; }
    .card { border: 1px solid #d7dce6; border-radius: 8px; padding: 8px 10px; margin: 0 0 6px; }
    .card .tag { font-size: 9px; background: #ffe7d3; color: #a3341c; padding: 1px 6px; border-radius: 8px; }
    .diagram { border: 1px solid #e0e4ec; border-radius: 8px; padding: 10px; margin: 4px 0 6px; text-align: center; page-break-inside: avoid; background: #fcfbf8; }
    .diagram svg { max-width: 100%; height: auto; }
    ul { margin: 2px 0 4px 16px; padding: 0; }
    li { margin: 1px 0; }
    pre { background: #0f1c33; color: #dbe6ff; padding: 11px 12px; border-radius: 8px; white-space: pre-wrap; font-size: 10px; line-height: 1.4; overflow-wrap: anywhere; margin: 4px 0; font-family: 'Cascadia Code', Consolas, monospace; }
    .foot { margin-top: 18px; font-size: 8.5px; color: #9aa2b1; display: flex; justify-content: space-between; border-top: 1px solid #e6e9f0; padding-top: 4px; }
    .noprint { text-align: right; margin-bottom: 10px; }
    .noprint button { background: #002677; color: #fff; border: 0; border-radius: 6px; padding: 8px 16px; font-size: 12px; cursor: pointer; }
    @media print { .noprint { display: none; } }
  </style></head><body>
  <div class="noprint"><button onclick="window.print()">Print / Save as PDF</button></div>

  <div class="mast">
    ${logo}
    <div class="brand">ModelIQ<b>${esc(meta.title || "Data model")}</b></div>
  </div>
  <table class="cover-meta"><tbody>
    <tr><td class="lbl">Industry</td><td>${esc(meta.industry || "—")}</td><td class="lbl">Standard</td><td>${esc(meta.standard || "—")}</td></tr>
    <tr><td class="lbl">SQL dialect</td><td>${esc(meta.dialect || "—")}</td><td class="lbl">Status</td><td><span class="pill ${esc(meta.status || "draft")}">${esc(statusLabel)}</span></td></tr>
    <tr><td class="lbl">Generated</td><td>${esc(now)}</td><td class="lbl">Classification</td><td>Confidential — synthetic metadata</td></tr>
  </tbody></table>

  <div class="kpis">
    <div class="kpi"><strong>${ents.length}</strong><span>Entities</span></div>
    <div class="kpi"><strong>${rels.length}</strong><span>Relationships</span></div>
    <div class="kpi"><strong>${reuseRows.length}</strong><span>Reuse matches</span></div>
    <div class="kpi"><strong>${reviews.length}</strong><span>Review findings</span></div>
    <div class="kpi"><strong>${dq.length}</strong><span>DQ rules</span></div>
    <div class="kpi"><strong>${phiCols}</strong><span>PHI/PII cols</span></div>
  </div>

  ${section("Entities", entitySections || '<p class="muted">No entities.</p>')}
  ${section("Entity–relationship diagram", `<div class="diagram">${buildErSvg(ents, rels)}</div>
    <table><thead><tr><th>Parent (one)</th><th>Child (many)</th><th>Via foreign key</th><th>Cardinality</th></tr></thead><tbody>${relRows}</tbody></table>`)}
  ${section("Data flow diagram", `<div class="diagram">${buildDfdSvg(ents)}</div>`)}
  ${section("Star / Snowflake schema", `${factCards}
    <table><thead><tr><th>Dimension</th><th>Attributes</th><th>Normalization</th></tr></thead><tbody>${dimRows}</tbody></table>
    <p class="sub">Dimensional DDL</p><pre>${dimDdl}</pre>`)}
  ${reuseTable ? section("Reuse evidence", `<table><thead><tr><th>Proposed entity</th><th>Existing asset</th><th>Context</th><th>Match %</th><th>Fields</th><th>Decision</th></tr></thead><tbody>${reuseTable}</tbody></table>`) : ""}
  ${reviewRows ? section("Design review", `<table><thead><tr><th>Severity</th><th>Finding</th></tr></thead><tbody>${reviewRows}</tbody></table>`) : ""}
  ${dqRows ? section("Data quality rules", `<table><thead><tr><th>Entity</th><th>Field</th><th>Rule</th><th>Severity</th><th>Description</th></tr></thead><tbody>${dqRows}</tbody></table>`) : ""}
  ${impactRows ? section("Impact analysis", `<table><thead><tr><th>Entity</th><th>Risk</th><th>Directly dependent</th><th>Further downstream</th><th>Impacted domains</th></tr></thead><tbody>${impactRows}</tbody></table>`) : ""}
  ${ddl ? section("SQL DDL", `<pre>${ddl}</pre>`) : ""}
  ${contract ? section("Data contract", `<pre>${contract}</pre>`) : ""}
  ${dictionary ? section("Data dictionary", `<pre>${dictionary}</pre>`) : ""}

  <div class="foot"><span>ModelIQ · ${esc(meta.title || "Data model")}</span><span>Confidential — synthetic metadata only</span></div>
  </body></html>`;
}

function escapeHtml(str) {
  return String(str ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Governance table + panel event wiring (delegated).
document.querySelector("#governanceTable")?.addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-act]");
  if (!btn) return;
  const sessionId = btn.closest("tr")?.dataset.session;
  if (!sessionId) return;
  const act = btn.dataset.act;
  if (act === "policy") openPolicyModal(sessionId);
  else if (act === "approve") setModelStatus(sessionId, "approved");
  else if (act === "revise") setModelStatus(sessionId, "needs_revision");
  else if (act === "pdf") exportModelPdf(sessionId);
  else if (act === "audit") toggleAuditPanel(sessionId);
});
document.querySelector("#governanceRefresh")?.addEventListener("click", loadGovernanceModels);
document.querySelector("#governanceAuditToggle")?.addEventListener("click", () => toggleAuditPanel());
document.querySelector("#govAuditClose")?.addEventListener("click", () => { document.querySelector("#govAuditPanel").hidden = true; });
document.querySelector("#policyModalClose")?.addEventListener("click", () => { document.querySelector("#policyModal").hidden = true; });
document.querySelector("#policyModal")?.addEventListener("click", (e) => { if (e.target.id === "policyModal") e.target.hidden = true; });

// --- Catalog view ------------------------------------------------------------

async function showCatalog({ updateUrl = true } = {}) {
  hideStandardPanels();
  document.querySelector("#governanceView").hidden = true;
  document.querySelector("#catalogView").hidden = false;
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
  document.querySelector("#navCatalog").classList.add("active");
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (updateUrl) setUrlPath("/catalog");
  await loadCatalog();
}

async function loadCatalog() {
  const container = document.querySelector("#catalogGroups");
  try {
    const res = await fetch("/api/catalog/standards");
    const data = await res.json();
    const groups = data.catalog || [];
    container.innerHTML = groups.map((g) => `
      <div class="catalog-group">
        <div class="catalog-group-head"><h2>${escapeHtml(g.label)}</h2><span>${g.standards.length} standard${g.standards.length === 1 ? "" : "s"}</span></div>
        <div class="std-list">
          ${g.standards.map((s) => `
            <div class="std-card">
              <div class="std-card-top">
                <strong>${escapeHtml(s.name)}</strong>
                ${s.builtin ? `<span class="std-tag builtin">Built-in</span>` : `<span class="std-tag custom">Custom</span>`}
              </div>
              <p>${escapeHtml(s.description || "No description provided.")}</p>
              ${s.builtin ? "" : `<button class="mini-button danger" data-del-standard="${s.id}">Remove</button>`}
            </div>`).join("")}
        </div>
      </div>`).join("");
    // Refresh the workspace standard dropdown so custom standards are usable when generating.
    mergeCustomStandards(groups);
  } catch {
    showToast("Could not load the catalog.");
  }
}

// Fold custom standards from the catalog into INDUSTRY_STANDARDS so the
// workspace Reference-standard selector offers them for new models.
function mergeCustomStandards(groups) {
  groups.forEach((g) => {
    if (!INDUSTRY_STANDARDS[g.industry]) {
      INDUSTRY_STANDARDS[g.industry] = { label: g.label, blurb: "", standards: [], examples: [] };
    }
    const names = g.standards.map((s) => s.name);
    INDUSTRY_STANDARDS[g.industry].standards = names.length ? names : INDUSTRY_STANDARDS[g.industry].standards;
  });
  const current = document.querySelector("#industrySelect")?.value;
  if (current) applyIndustry(current);
}

document.querySelector("#addStandardButton")?.addEventListener("click", () => {
  const form = document.querySelector("#addStandardForm");
  form.hidden = !form.hidden;
});
document.querySelector("#asfCancel")?.addEventListener("click", () => {
  document.querySelector("#addStandardForm").hidden = true;
});
document.querySelector("#asfIndustrySelect")?.addEventListener("change", (e) => {
  document.querySelector("#asfNewIndustryGroup").hidden = e.target.value !== "__new__";
});
document.querySelector("#addStandardForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  let industry = document.querySelector("#asfIndustrySelect").value;
  if (industry === "__new__") {
    industry = (document.querySelector("#asfNewIndustry").value || "").trim().toLowerCase().replace(/\s+/g, "_");
  }
  const name = document.querySelector("#asfName").value.trim();
  const description = document.querySelector("#asfDescription").value.trim();
  if (!industry || !name) { showToast("Industry and standard name are required."); return; }
  try {
    const res = await fetch("/api/catalog/standards", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ industry, name, description }),
    });
    if (!res.ok) throw new Error();
    document.querySelector("#asfName").value = "";
    document.querySelector("#asfDescription").value = "";
    document.querySelector("#asfNewIndustry").value = "";
    document.querySelector("#addStandardForm").hidden = true;
    showToast("Standard added to catalog.");
    await loadCatalog();
  } catch {
    showToast("Could not add the standard.");
  }
});
document.querySelector("#catalogGroups")?.addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-del-standard]");
  if (!btn) return;
  try {
    const res = await fetch(`/api/catalog/standards/${btn.dataset.delStandard}`, { method: "DELETE" });
    if (!res.ok) throw new Error();
    showToast("Standard removed.");
    await loadCatalog();
  } catch {
    showToast("Could not remove the standard.");
  }
});

// Keep the address bar in sync with the active nav tab (Home/Library/Sessions/
// Governance/Catalog/Settings) using the History API, so refreshing or sharing
// a link lands back on the same view. See ROUTES below for path -> view.
const ROUTES = {
  "/": () => showWorkspace({ updateUrl: false }),
  "/home": () => showHomeGuide({ updateUrl: false }),
  "/library": () => showWorkspace({ updateUrl: false }),
  "/sessions": () => showSessionManager({ updateUrl: false }),
  "/governance": () => showGovernance({ updateUrl: false }),
  "/catalog": () => showCatalog({ updateUrl: false }),
  "/settings": () => showComingSoon("settings", { updateUrl: false }),
};

let suppressUrlUpdate = false;
function setUrlPath(path) {
  if (suppressUrlUpdate || location.pathname === path) return;
  history.pushState({ path }, "", path);
}

function renderRouteFromLocation() {
  (ROUTES[location.pathname] || ROUTES["/"])();
}

window.addEventListener("popstate", () => {
  suppressUrlUpdate = true;
  renderRouteFromLocation();
  suppressUrlUpdate = false;
});

document.querySelector("#navGovernance").addEventListener("click", (e) => { e.preventDefault(); showGovernance(); });
document.querySelector("#navCatalog").addEventListener("click", (e) => { e.preventDefault(); showCatalog(); });
document.querySelector("#navSettings").addEventListener("click", (e) => { e.preventDefault(); showComingSoon("settings"); });
document.querySelector("#navHome").addEventListener("click", (e) => { e.preventDefault(); showHomeGuide(); });
document.querySelector("#navLibrary").addEventListener("click", (e) => { e.preventDefault(); showWorkspace(); });
document.querySelector("#navSessions").addEventListener("click", (e) => { e.preventDefault(); showSessionManager(); });
document.querySelector("#comingSoonBack").addEventListener("click", showWorkspace);
document.querySelector("#homeGetStartedButton").addEventListener("click", () => {
  showWorkspace();
  document.querySelector("#requirementInput").focus();
});
newChatButton?.addEventListener("click", startNewChat);
managerNewChatButton?.addEventListener("click", () => {
  startNewChat();
  showWorkspace();
});
exitSessionButton?.addEventListener("click", () => {
  startNewChat();
  showSessionManager();
});
activeSessionNameInput?.addEventListener("change", () => {
  const next = activeSessionNameInput.value.trim();
  if (activeSessionId && next && next !== activeSession?.title) {
    renameSession(activeSessionId, next);
  }
});
activeSessionNameInput?.addEventListener("keydown", (event) => {
  if (event.key === "Enter") activeSessionNameInput.blur();
});
sessionList?.addEventListener("click", (event) => {
  const del = event.target.closest("[data-delete-session]");
  if (del) {
    event.stopPropagation();
    deleteSession(del.dataset.deleteSession);
    return;
  }
  const item = event.target.closest(".session-item");
  if (item) switchToSession(item.dataset.session);
});
sessionList?.addEventListener("dblclick", (event) => {
  const item = event.target.closest(".session-item");
  if (!item) return;
  const current = sessions.find((s) => s.session_id === item.dataset.session);
  const next = window.prompt("Rename conversation", current?.title || "");
  if (next && next.trim()) renameSession(item.dataset.session, next.trim());
});
requirementInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((item) => {
      item.classList.toggle("active", item === tab);
      item.setAttribute("aria-selected", String(item === tab));
    });
    document.querySelectorAll(".tab-panel").forEach((panel) => {
      const active = panel.id === `${tab.dataset.tab}Panel`;
      panel.classList.toggle("active", active);
      panel.hidden = !active;
    });
  });
});

entityGrid.addEventListener("click", (event) => {
  const card = event.target.closest(".entity-card");
  if (card) openEntityDialog(Number(card.dataset.entity));
});
entityGrid.addEventListener("keydown", (event) => {
  const card = event.target.closest(".entity-card");
  if (card && (event.key === "Enter" || event.key === " ")) {
    event.preventDefault();
    openEntityDialog(Number(card.dataset.entity));
  }
});
closeEntityDialog.addEventListener("click", () => entityDialog.close());
entityDialog.addEventListener("click", (event) => {
  if (event.target === entityDialog) entityDialog.close();
});
generateButton.addEventListener("click", sendMessage);
document.querySelector("#generateDraftButton").addEventListener("click", sendMessage);
document.querySelector("#viewEvidenceButton").addEventListener("click", () => {
  document.querySelector('.tab[data-tab="reuse"]').click();
});
document.querySelector("#resetButton").addEventListener("click", () => {
  results.hidden = true;
  document.querySelector("#requirementInput").focus();
  showToast("Draft reset");
});
document.querySelector("#themeButton").addEventListener("click", () => document.body.classList.toggle("high-contrast"));
exportButton.addEventListener("click", () => { exportMenu.hidden = !exportMenu.hidden; });
exportMenu.addEventListener("click", (event) => {
  const type = event.target.dataset.export;
  if (type) downloadArtifact(type);
});
document.querySelector("#exportQualityBtn").addEventListener("click", () => downloadArtifact("dq_ddl"));
document.querySelector("#copyQualityQueryBtn").addEventListener("click", () =>
  copyFeatureText(document.querySelector("#dqQueryCode").textContent, null, "Validation query"));
document.querySelector("#dqRuleList").addEventListener("click", (event) => {
  const card = event.target.closest(".dq-rule-card");
  if (card) selectQualityRule(Number(card.dataset.rule));
});
reviewList.addEventListener("click", (event) => {
  const openBtn = event.target.closest(".review-resolve-open");
  if (openBtn) { openResolveForm(openBtn.closest(".review-resolve")); return; }
  const decisionBtn = event.target.closest(".review-decision");
  if (decisionBtn) { submitReviewDecision(decisionBtn); return; }
  if (event.target.closest(".review-resolve-cancel")) { renderReviews(); return; }
});

// Copy buttons for the added Star/SF DDL panel and the entity popup's DDL section.
function copyFeatureText(text, btn, label) {
  navigator.clipboard.writeText(text).then(() => showToast((label || "Copied") + " copied to clipboard"));
}
document.querySelector("#copyStarBtn").addEventListener("click", () =>
  copyFeatureText(document.querySelector("#starCode").textContent, null, "Dimensional DDL"));
document.querySelector("#copyEntityDdlBtn").addEventListener("click", () =>
  copyFeatureText(document.querySelector("#entityDdlCode").textContent, null, entityDdlScope === "schema" ? "Full schema DDL" : "Table DDL"));
// Re-render the popup's DDL when the dialect changes (after a draft exists).
document.querySelector("#dialectSelect").addEventListener("change", () => {
  if (!entities.length) return;
  if (entityDialog && entityDialog.open && entities[openEntityIndex]) renderEntityDdl(entities[openEntityIndex]);
});

// Restore the conversation list from the backend on load and open the most
// recently updated one (if any), otherwise start with an empty composer.
loadSessions().then(() => {
  renderSessionList();
  if (sessions.length) {
    switchToSession(sessions[0].session_id);
  } else {
    renderActiveSession();
  }
  // Render whichever tab the URL points to (deep link / refresh), without
  // pushing a redundant history entry for the URL we're already on.
  suppressUrlUpdate = true;
  renderRouteFromLocation();
  suppressUrlUpdate = false;
  // Fold any custom catalog standards into the workspace dropdown up front.
  fetch("/api/catalog/standards")
    .then((r) => r.json())
    .then((d) => mergeCustomStandards(d.catalog || []))
    .catch(() => {});
});