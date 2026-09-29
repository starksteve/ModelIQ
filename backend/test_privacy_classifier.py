import unittest
import json

from privacy_classifier import (
    INDUSTRY_PRIVACY_GUIDANCE,
    PrivacyClassificationError,
    classify_fields,
    validate_classifications,
)


ENTITIES = [{
    "name": "Member",
    "fields": [
        ["member_sk", "PK - SURROGATE - INTEGER"],
        ["birth_date", "DATE"],
        ["status_code", "STRING"],
        ["service_date", "DATE"],
    ],
}]


class ValidateClassificationsTests(unittest.TestCase):
    def test_every_supported_industry_has_specific_guidance(self):
        self.assertEqual(
            set(INDUSTRY_PRIVACY_GUIDANCE),
            {"healthcare", "fintech", "edtech", "transport", "ecommerce", "telecom", "generic"},
        )
        self.assertIn("identifying non-health fields", INDUSTRY_PRIVACY_GUIDANCE["healthcare"].lower())
        for industry in {"fintech", "edtech", "transport", "ecommerce", "telecom"}:
            self.assertIn("PHI does not apply unless", INDUSTRY_PRIVACY_GUIDANCE[industry])

    def test_accepts_complete_specific_classification(self):
        result = validate_classifications({
            "entities": [{
                "entity": "Member",
                "record_context": "HIPAA_DESIGNATED_RECORD_SET",
                "context_rationale": "This patient entity is maintained as part of the clinical record used for care decisions.",
                "fields": [
                    {
                        "field": "member_sk",
                        "category": "NONE",
                        "rationale": "This is a system-generated surrogate key with no intrinsic personal meaning.",
                    },
                    {
                        "field": "birth_date",
                        "category": "PHI",
                        "rationale": "Date of birth is identifying information maintained in the designated patient record.",
                    },
                    {
                        "field": "status_code",
                        "category": "NONE",
                        "rationale": "This lifecycle code does not identify a person or describe their health.",
                    },
                    {
                        "field": "service_date",
                        "category": "NONE",
                        "rationale": "Project policy excludes non-birth date columns from PHI classification.",
                    },
                ],
            }],
        }, ENTITIES)

        self.assertEqual(result["Member"]["record_context"], "HIPAA_DESIGNATED_RECORD_SET")
        self.assertEqual(result["Member"]["fields"][0]["category"], "NONE")
        self.assertEqual(result["Member"]["fields"][1]["category"], "PHI")
        self.assertEqual(result["Member"]["fields"][2]["category"], "NONE")
        self.assertEqual(result["Member"]["fields"][3]["category"], "NONE")

    def test_rejects_missing_field(self):
        with self.assertRaisesRegex(PrivacyClassificationError, "do not exactly match"):
            validate_classifications({
                "entities": [{
                    "entity": "Member",
                    "record_context": "HIPAA_DESIGNATED_RECORD_SET",
                    "context_rationale": "This patient entity is maintained as part of the clinical record used for care decisions.",
                    "fields": [{
                        "field": "member_sk",
                        "category": "NONE",
                        "rationale": "This is a system-generated surrogate key with no intrinsic personal meaning.",
                    }],
                }],
            }, ENTITIES)

    def test_rejects_unknown_category(self):
        fields = [
            {
                "field": name,
                "category": "SECRET" if name == "status_code" else "NONE",
                "rationale": "The supplied semantics provide enough evidence for this classification.",
            }
            for name, _ in ENTITIES[0]["fields"]
        ]
        with self.assertRaisesRegex(PrivacyClassificationError, "invalid privacy category"):
            validate_classifications({
                "entities": [{
                    "entity": "Member",
                    "record_context": "HIPAA_DESIGNATED_RECORD_SET",
                    "context_rationale": "This patient entity is maintained as part of the clinical record used for care decisions.",
                    "fields": fields,
                }],
            }, ENTITIES)

    def test_rejects_sensitive_surrogate_key(self):
        fields = [
            {
                "field": name,
                "category": "PII" if name == "member_sk" else "NONE",
                "rationale": "This rationale is specific enough for validation and testing purposes.",
            }
            for name, _ in ENTITIES[0]["fields"]
        ]
        with self.assertRaisesRegex(PrivacyClassificationError, "surrogate key column .* must be NONE"):
            validate_classifications({
                "entities": [{
                    "entity": "Member",
                    "record_context": "HIPAA_DESIGNATED_RECORD_SET",
                    "context_rationale": "This patient entity is maintained as part of the clinical record used for care decisions.",
                    "fields": fields,
                }],
            }, ENTITIES)

    def test_rejects_non_dob_date_as_phi(self):
        fields = [
            {
                "field": name,
                "category": "PHI" if name == "service_date" else "NONE",
                "rationale": "This classification is intentionally used to verify the project date policy.",
            }
            for name, _ in ENTITIES[0]["fields"]
        ]
        with self.assertRaisesRegex(PrivacyClassificationError, "non-DOB date column .* must be NONE"):
            validate_classifications({
                "entities": [{
                    "entity": "Member",
                    "record_context": "HIPAA_DESIGNATED_RECORD_SET",
                    "context_rationale": "This patient entity is maintained as part of the clinical record used for care decisions.",
                    "fields": fields,
                }],
            }, ENTITIES)

    def test_rejects_pii_inside_designated_record_set(self):
        fields = [
            {
                "field": name,
                "category": "PII" if name == "birth_date" else "NONE",
                "rationale": "This field is evaluated using its role in the designated patient record.",
            }
            for name, _ in ENTITIES[0]["fields"]
        ]
        with self.assertRaisesRegex(PrivacyClassificationError, "cannot be PII inside"):
            validate_classifications({
                "entities": [{
                    "entity": "Member",
                    "record_context": "HIPAA_DESIGNATED_RECORD_SET",
                    "context_rationale": "This patient entity is maintained as part of the clinical record used for care decisions.",
                    "fields": fields,
                }],
            }, ENTITIES)

    def test_rejects_phi_outside_designated_record_set(self):
        fields = [
            {
                "field": name,
                "category": "PHI" if name == "birth_date" else "NONE",
                "rationale": "This field is evaluated in a separate administrative contact list.",
            }
            for name, _ in ENTITIES[0]["fields"]
        ]
        with self.assertRaisesRegex(PrivacyClassificationError, "cannot be PHI outside"):
            validate_classifications({
                "entities": [{
                    "entity": "Member",
                    "record_context": "SEPARATE_HEALTHCARE_ADMIN",
                    "context_rationale": "This entity is a contact-only administrative list separate from clinical records.",
                    "fields": fields,
                }],
            }, ENTITIES)

    def test_classifier_receives_selected_industry_policy(self):
        captured = {}

        class Completions:
            @staticmethod
            def create(**kwargs):
                captured.update(kwargs)
                content = json.dumps({
                    "entities": [{
                        "entity": "Member",
                        "record_context": "NON_HEALTHCARE",
                        "context_rationale": "This test entity is evaluated outside a healthcare designated record set.",
                        "fields": [
                            {
                                "field": name,
                                "category": "NONE",
                                "rationale": "The supplied semantics do not identify a person or describe health information.",
                            }
                            for name, _ in ENTITIES[0]["fields"]
                        ],
                    }],
                })
                return type("Response", (), {
                    "choices": [type("Choice", (), {
                        "message": type("Message", (), {"content": content})(),
                    })()],
                })()

        client = type("Client", (), {
            "chat": type("Chat", (), {"completions": Completions()})(),
        })()
        entities = [{"name": "Member", "definition": "Test", "fields": list(ENTITIES[0]["fields"])}]

        classify_fields(client, "gpt-5-mini", "Test requirement", "fintech", entities)

        payload = json.loads(captured["messages"][1]["content"])
        self.assertEqual(payload["industry"], "fintech")
        self.assertEqual(
            payload["industry_privacy_guidance"],
            INDUSTRY_PRIVACY_GUIDANCE["fintech"],
        )


if __name__ == "__main__":
    unittest.main()
