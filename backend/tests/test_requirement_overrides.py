import unittest

from app.workflow.nodes.requirement import understand_requirement


class RequirementOverrideTest(unittest.TestCase):
    def test_confirmed_region_override_is_normalized_and_applied(self) -> None:
        result = understand_requirement(
            {
                "task_id": "task-region-override",
                "query": "项目",
                "frequency": "once",
                "requested_region": "上海",
                "steps": [],
            }
        )

        self.assertEqual(result["task_spec"]["regions"], ["上海市"])

    def test_confirmed_subject_override_becomes_search_topic(self) -> None:
        result = understand_requirement(
            {
                "task_id": "task-subject-override",
                "query": "项目",
                "frequency": "once",
                "requested_subject": "充电桩建设",
                "steps": [],
            }
        )

        self.assertEqual(result["task_spec"]["topic"], "充电桩建设")
        self.assertEqual(result["task_spec"]["keywords"], ["充电桩建设"])

    def test_query_without_time_constraint_keeps_publication_range_open(self) -> None:
        result = understand_requirement(
            {
                "task_id": "task-open-time-range",
                "query": "这个服务器",
                "frequency": "once",
                "requested_subject": "服务器",
                "steps": [],
            }
        )

        self.assertIsNone(result["task_spec"]["time_range_start"])
        self.assertIsNone(result["task_spec"]["time_range_end"])


if __name__ == "__main__":
    unittest.main()
