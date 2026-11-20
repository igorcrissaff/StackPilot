import os
import tempfile

os.environ.setdefault("METRICS_DB_PATH", os.path.join(tempfile.mkdtemp(), "metrics.db"))
