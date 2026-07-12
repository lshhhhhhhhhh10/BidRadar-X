from pathlib import Path

import bidradar


ROOT = Path(__file__).resolve().parents[1]


def test_package_has_version() -> None:
    assert bidradar.__version__ == "0.1.0"


def test_required_collaboration_contracts_exist() -> None:
    required = [
        ROOT / "AGENTS.md",
        ROOT / "docs" / "CONTRACTS.md",
        ROOT / "docs" / "WORK_BREAKDOWN.md",
        ROOT / "docs" / "application" / "SUBMISSION_COPY.md",
        ROOT / "docs" / "application" / "REGISTRATION_SPRINT.md",
    ]
    assert all(path.is_file() for path in required)


def test_readme_does_not_claim_mvp_is_complete() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "尚未实现可运行系统" in readme

