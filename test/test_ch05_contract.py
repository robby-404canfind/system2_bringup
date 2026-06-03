import json
import unittest

from pydantic import ValidationError

from system2_bringup.context_builder import ContextBuilder
from system2_bringup.plan_models import HighLevelPlan
from system2_bringup.schema_validator import SchemaValidator


LOCATIONS = [
    "office_entrance",
    "cabinet",
    "workstation",
    "pallet",
    "fire_extinguisher",
    "lobby",
    "charging_station",
]
PATROL_ROUTES = [
    "hall_loop",
    "hall_short_loop",
    "safety_inspection_loop",
]


def _validator() -> SchemaValidator:
    return SchemaValidator(semantic_locations=LOCATIONS, patrol_routes=PATROL_ROUTES)


class Ch05ContractTest(unittest.TestCase):
    def test_follow_minus_one_target_id_contract_is_valid(self):
        plan = HighLevelPlan.model_validate(
            {
                "version": "1.0.0",
                "mission_id": "test-follow",
                "intent": "scan then follow person",
                "steps": [
                    {
                        "task": "scan",
                        "params": {"duration_sec": 15, "sweep_deg": 360},
                    },
                    {
                        "task": "follow",
                        "params": {
                            "target_class": "person",
                            "target_id": -1,
                            "target_distance_m": 1.5,
                            "max_time_sec": 30,
                        },
                    },
                ],
            }
        )

        self.assertTrue(_validator().validate(plan).ok)
        self.assertEqual(plan.steps[1].params.target_id, -1)

    def test_follow_null_target_id_is_rejected(self):
        with self.assertRaises(ValidationError):
            HighLevelPlan.model_validate(
                {
                    "version": "1.0.0",
                    "mission_id": "test-follow-null",
                    "intent": "invalid follow",
                    "steps": [
                        {
                            "task": "follow",
                            "params": {
                                "target_class": "person",
                                "target_id": None,
                                "target_distance_m": 1.5,
                                "max_time_sec": 30,
                            },
                        }
                    ],
                }
            )

    def test_report_requires_status_param(self):
        with self.assertRaises(ValidationError):
            HighLevelPlan.model_validate(
                {
                    "version": "1.0.0",
                    "mission_id": "test-report",
                    "intent": "invalid report",
                    "steps": [{"task": "report", "params": {}}],
                }
            )

    def test_assess_scene_plan_contract_is_valid(self):
        plan = HighLevelPlan.model_validate(
            {
                "version": "1.0.0",
                "mission_id": "test-assess",
                "intent": "inspect cabinet and report suspicious person",
                "steps": [
                    {
                        "task": "go_to",
                        "params": {"location": "cabinet"},
                    },
                    {
                        "task": "assess_scene",
                        "params": {
                            "query": "suspicious person near cabinet",
                            "timeout_sec": 30,
                        },
                    },
                    {
                        "task": "report",
                        "params": {"status": "latest_assessment"},
                    },
                ],
            }
        )

        self.assertTrue(_validator().validate(plan).ok)
        self.assertEqual(plan.steps[1].task, "assess_scene")

    def test_follow_query_plan_contract_is_valid(self):
        plan = HighLevelPlan.model_validate(
            {
                "version": "1.0.0",
                "mission_id": "test-follow-query",
                "intent": "follow person wearing blue clothes",
                "steps": [
                    {
                        "task": "follow_query",
                        "params": {
                            "target_query": "person wearing blue clothes",
                            "target_distance_m": 1.5,
                            "max_time_sec": 30,
                            "resolve_timeout_sec": 20,
                        },
                    }
                ],
            }
        )

        self.assertTrue(_validator().validate(plan).ok)
        self.assertEqual(plan.steps[0].params.target_query, "person wearing blue clothes")

    def test_perception_context_text_uses_ch04_raw_shape(self):
        builder = ContextBuilder()
        builder.update_perception(
            json.dumps(
                {
                    "frame_w": 640,
                    "frame_h": 480,
                    "objects": [
                        {
                            "id": 1,
                            "class": "person",
                            "confidence": 0.85,
                            "center": {"x": 320, "y": 240},
                            "bbox": {"x": 200, "y": 100, "w": 240, "h": 280},
                            "direction": "center",
                            "range_m": 2.5,
                        }
                    ],
                    "vlm_scene": {
                        "scene_summary": "복도에 두 사람이 대화 중",
                        "social_hints": [
                            {
                                "type": "avoid_between_people",
                                "confidence": 0.82,
                                "reason": "two_people_talking",
                            }
                        ],
                    },
                },
                ensure_ascii=False,
            )
        )

        text = builder.build()

        self.assertIn("[Perception]", text)
        self.assertIn("person (id=1, center, 2.5m, conf=0.85)", text)
        self.assertIn("[Social Navigation]", text)
        self.assertIn("avoid_between_people", text)
        self.assertIn("두 사람 사이 통과 금지", text)

    def test_social_hint_can_be_recorded_without_forced_detour(self):
        plan = HighLevelPlan.model_validate(
            {
                "version": "1.0.0",
                "mission_id": "test-social-hint",
                "intent": "go to cabinet and record social hint",
                "constraints": ["avoid_between_people"],
                "steps": [
                    {"task": "go_to", "params": {"location": "cabinet"}},
                ],
            }
        )

        self.assertTrue(_validator().validate(plan).ok)
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].params.location, "cabinet")
        self.assertIn("avoid_between_people", plan.constraints)


if __name__ == "__main__":
    unittest.main()
