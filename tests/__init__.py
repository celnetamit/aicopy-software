import os
import tempfile

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
local_tmp = os.path.join(ROOT_DIR, "data", "tmp")
os.makedirs(local_tmp, exist_ok=True)
tempfile.tempdir = local_tmp

# Override DATABASE_URL to avoid using /tmp for tests
local_db = os.path.join(ROOT_DIR, "data", "manuscript_editor_test.sqlite3")
os.environ["DATABASE_URL"] = f"sqlite:///{local_db}"
