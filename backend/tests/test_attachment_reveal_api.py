from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import attachments as attachments_api
from app.main import app
from app.storage import database as database_module
from app.storage.repository import Repository


class AttachmentRevealApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.database_patch = patch.object(database_module, "DATA_DIR", self.root)
        self.path_patch = patch.object(
            database_module,
            "DATABASE_PATH",
            self.root / "app.db",
        )
        self.archive_patch = patch.object(
            attachments_api,
            "ATTACHMENT_DIR",
            self.root / "招投标公告",
        )
        self.database_patch.start()
        self.path_patch.start()
        self.archive_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        self.archive_patch.stop()
        self.path_patch.stop()
        self.database_patch.stop()
        self.temporary_directory.cleanup()

    def test_reveals_only_the_archived_project_pdf(self) -> None:
        pdf = self.root / "招投标公告" / "服务器采购" / "招标文件.pdf"
        pdf.parent.mkdir(parents=True)
        pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
        repository = Repository()
        repository.create_task("task-reveal", "服务器采购", "once")
        repository.save_run(
            {
                "task_id": "task-reveal",
                "run_id": "run-reveal",
                "status": "completed",
                "projects": [
                    {
                        "project_id": "project-reveal",
                        "documents": [
                            {
                                "notice": {
                                    "attachments": [
                                        {
                                            "attachment_id": "attachment-reveal",
                                            "local_path": str(pdf),
                                        }
                                    ]
                                }
                            }
                        ],
                    }
                ],
            }
        )

        with patch.object(attachments_api, "_reveal_in_file_manager") as reveal:
            response = self.client.post(
                "/api/runs/run-reveal/projects/project-reveal/"
                "attachments/attachment-reveal/reveal"
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["filename"], "招标文件.pdf")
        reveal.assert_called_once_with(pdf.resolve())

    def test_rejects_a_path_outside_the_archive(self) -> None:
        pdf = self.root / "outside.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
        repository = Repository()
        repository.create_task("task-outside", "服务器采购", "once")
        repository.save_run(
            {
                "task_id": "task-outside",
                "run_id": "run-outside",
                "status": "completed",
                "projects": [
                    {
                        "project_id": "project-outside",
                        "documents": [
                            {
                                "notice": {
                                    "attachments": [
                                        {
                                            "attachment_id": "attachment-outside",
                                            "local_path": str(pdf),
                                        }
                                    ]
                                }
                            }
                        ],
                    }
                ],
            }
        )

        response = self.client.post(
            "/api/runs/run-outside/projects/project-outside/"
            "attachments/attachment-outside/reveal"
        )

        self.assertEqual(response.status_code, 403, response.text)


if __name__ == "__main__":
    unittest.main()
