import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "apply-to-jobs"


def test_bundled_skill_metadata_and_linked_resources_are_complete():
    entry = (SKILL / "SKILL.md").read_text()
    metadata = yaml.safe_load(entry.split("---", 2)[1])
    assert metadata["name"] == "apply-to-jobs"
    assert metadata["description"]
    interface = yaml.safe_load((SKILL / "agents" / "openai.yaml").read_text())["interface"]
    assert "$apply-to-jobs" in interface["default_prompt"]
    for path in [SKILL / "SKILL.md", *sorted((SKILL / "references").glob("*.md"))]:
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
            if "://" not in target and not target.startswith("#"):
                assert (path.parent / target.split("#")[0]).is_file(), (path, target)
    assert (SKILL / "LICENSE").is_file()
    assert (ROOT / "THIRD_PARTY_NOTICES.md").is_file()
