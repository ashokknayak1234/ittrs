"""Package the canonical Python backend without uploading virtualenvs or tests."""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / ".worker-source"
TARGET.mkdir(exist_ok=True)
for name in (
    "worker.py",
    "main.py",
    "models.py",
    "pii_redactor.py",
    "sla_config.py",
    "llm_classifier.py",
    "supabase_client.py",
    "transport.py",
):
    source = ROOT / name
    if source.exists():
        shutil.copyfile(source, TARGET / name)
(TARGET / "config").mkdir(exist_ok=True)
shutil.copyfile(ROOT / "config/sla_rules.yaml", TARGET / "config/sla_rules.yaml")
