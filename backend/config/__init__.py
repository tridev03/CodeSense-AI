"""backend.config package."""
import os

# Silence GitPython executable warning on machines where git is not in PATH
os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")
