import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Object storage initializes its thumbnail directory during import. Tests must
# not depend on the production container mount at /data/thumbnails.
os.environ.setdefault("THUMBNAIL_DIR", "/tmp/clipbandit-test-thumbnails")
