"""
Centralized path configuration for CRS.

OSS-CRS mode with directly mounted volumes.
All paths are configurable via environment variables with sensible defaults.
"""

import os
from pathlib import Path

__all__ = ["CRSPaths"]


class CRSPaths:
    """Centralized path configuration for CRS."""

    # Core directories
    SRC_DIR = Path(os.environ.get("SRC_DIR", "/src"))
    OUT_DIR = Path(os.environ.get("OUT", os.environ.get("OUT_DIR", "/out")))

    # OSS-CRS artifacts directory
    OSS_CRS_ARTIFACTS_DIR = Path(os.environ.get("OSS_CRS_ARTIFACTS_DIR", "/artifacts"))

    # Legacy paths (for compatibility)
    RESULTS_DIR = Path(os.environ.get("RESULTS_DIR", "/results"))
    ARTIFACT_DIR = Path(os.environ.get("ARTIFACT_DIR", "/artifact"))

    @classmethod
    def get_repo_dir(cls) -> Path:
        """Get actual project source code directory.

        Priority:
        1. Explicit REPO_DIR env var
        2. /src/{CRS_TARGET}/ (OSS-CRS mode)
        3. /src/ (fallback)
        """
        if os.environ.get("REPO_DIR"):
            return Path(os.environ.get("REPO_DIR"))
        project_name = os.environ.get("CRS_TARGET")
        if project_name:
            project_path = Path(f"/src/{project_name}")
            if project_path.exists():
                return project_path
        return cls.SRC_DIR

    @classmethod
    def is_oss_crs_mode(cls) -> bool:
        """Detect if running in OSS-CRS mode (CRS_NAME is set)."""
        return bool(os.environ.get("CRS_NAME"))

    @classmethod
    def get_diff_path(cls) -> Path | None:
        """Get diff file path for delta mode.

        Priority:
        1. DIFF_FILE env var
        2. /ref.diff (OSS-CRS standard)
        3. /src/ref.diff (legacy)
        """
        if os.environ.get("DIFF_FILE"):
            path = Path(os.environ.get("DIFF_FILE"))
            if path.exists():
                return path

        if Path("/ref.diff").exists():
            return Path("/ref.diff")

        if (cls.SRC_DIR / "ref.diff").exists():
            return cls.SRC_DIR / "ref.diff"

        return None

    @classmethod
    def get_pov_dir(cls) -> Path:
        """Get POV output directory."""
        if cls.is_oss_crs_mode():
            return cls.OSS_CRS_ARTIFACTS_DIR / "povs"
        return cls.RESULTS_DIR / "pov"

    @classmethod
    def get_corpus_dir(cls) -> Path:
        """Get corpus output directory."""
        if cls.is_oss_crs_mode():
            return cls.OSS_CRS_ARTIFACTS_DIR / "corpus"
        return cls.RESULTS_DIR / "corpus"

    @classmethod
    def get_crs_data_dir(cls) -> Path:
        """Get CRS-specific data directory."""
        if cls.is_oss_crs_mode():
            return cls.OSS_CRS_ARTIFACTS_DIR / "crs-data"
        return cls.ARTIFACT_DIR

    @classmethod
    def get_seed_share_dir(cls) -> Path | None:
        """Get seed share directory (ensemble mode)."""
        if os.environ.get("SEED_SHARE_DIR"):
            path = Path(os.environ.get("SEED_SHARE_DIR"))
            if path.exists():
                return path
        seed_share = Path("/seed_share_dir")
        if seed_share.exists():
            return seed_share
        return None
