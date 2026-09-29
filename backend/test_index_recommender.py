import unittest

from index_recommender import IndexRecommendationError, build_index_ddl, validate_recommendations


ENTITIES = [{
    "name": "Encounter",
    "fields": [
        ["encounter_sk", "PK - SURROGATE - INTEGER"],
        ["encounter_id", "BK - STRING"],
        ["member_id", "FK - STRING"],
        ["service_date", "DATE"],
        ["status_code", "STRING"],
    ],
}]


def response(indexes):
    return {"entities": [{"entity": "Encounter", "indexes": indexes}]}


class IndexRecommenderTests(unittest.TestCase):
    def test_accepts_join_and_range_index(self):
        result = validate_recommendations(response([{
            "name": "idx_encounter_member_service_date",
            "columns": ["member_id", "service_date"],
            "unique": False,
            "access_pattern": "Find a member's encounters within a requested service-date range.",
            "rationale": "Member equality is evaluated before the service-date range predicate.",
        }]), ENTITIES)
        self.assertEqual(result["Encounter"][0]["columns"], ["member_id", "service_date"])

    def test_rejects_primary_key_duplicate(self):
        with self.assertRaisesRegex(IndexRecommendationError, "existing key constraint"):
            validate_recommendations(response([{
                "name": "idx_encounter_sk",
                "columns": ["encounter_sk"],
                "unique": False,
                "access_pattern": "Lookup an encounter by its system-generated surrogate primary key.",
                "rationale": "The key directly identifies the physical encounter row.",
            }]), ENTITIES)

    def test_rejects_business_key_duplicate(self):
        with self.assertRaisesRegex(IndexRecommendationError, "existing key constraint"):
            validate_recommendations(response([{
                "name": "uidx_encounter_id",
                "columns": ["encounter_id"],
                "unique": True,
                "access_pattern": "Lookup an encounter using its source-system business identifier.",
                "rationale": "The source identifier uniquely addresses an encounter record.",
            }]), ENTITIES)

    def test_rejects_redundant_prefix(self):
        with self.assertRaisesRegex(IndexRecommendationError, "redundant"):
            validate_recommendations(response([
                {
                    "name": "idx_encounter_member",
                    "columns": ["member_id"],
                    "unique": False,
                    "access_pattern": "Join encounters to the member record using the member identifier.",
                    "rationale": "The foreign key supports the primary member-to-encounter join.",
                },
                {
                    "name": "idx_encounter_member_service_date",
                    "columns": ["member_id", "service_date"],
                    "unique": False,
                    "access_pattern": "Find a member's encounters within a requested service-date range.",
                    "rationale": "Member equality is evaluated before the service-date range predicate.",
                },
            ]), ENTITIES)

    def test_builds_postgresql_index_ddl(self):
        entities = [{**ENTITIES[0], "indexRecommendations": [{
            "name": "idx_encounter_member_service_date",
            "columns": ["member_id", "service_date"],
            "unique": False,
            "access_pattern": "Find a member's encounters within a requested service-date range.",
            "rationale": "Member equality is evaluated before the service-date range predicate.",
        }]}]
        ddl = build_index_ddl(entities, "PostgreSQL")
        self.assertIn(
            "CREATE INDEX idx_encounter_member_service_date ON encounter (member_id, service_date);",
            ddl,
        )

    def test_uses_snowflake_clustering_guidance(self):
        entities = [{**ENTITIES[0], "indexRecommendations": [{
            "name": "idx_encounter_member_service_date",
            "columns": ["member_id", "service_date"],
            "unique": False,
            "access_pattern": "Find a member's encounters within a requested service-date range.",
            "rationale": "Member equality is evaluated before the service-date range predicate.",
        }]}]
        ddl = build_index_ddl(entities, "Snowflake")
        self.assertNotIn("CREATE INDEX", ddl)
        self.assertIn("CLUSTER BY (member_id, service_date)", ddl)


if __name__ == "__main__":
    unittest.main()
