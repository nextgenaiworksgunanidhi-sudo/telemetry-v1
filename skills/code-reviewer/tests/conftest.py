import sys
from pathlib import Path

# Add scripts/ to path so _telemetry package is importable from tests
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
