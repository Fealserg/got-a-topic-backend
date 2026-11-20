"""Run from backend root: .venv/bin/python scripts/export_openapi.py."""
import json
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from app.main import app
(root/'docs/openapi.json').write_text(json.dumps(app.openapi(),ensure_ascii=False,indent=2)+'\n')
print('Exported docs/openapi.json')
