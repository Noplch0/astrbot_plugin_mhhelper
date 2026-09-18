"""Sanity-check metadata.yaml to keep AstrBot install-from-GitHub working."""
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_metadata_yaml_exists():
    assert (REPO_ROOT / "metadata.yaml").is_file()


def test_metadata_yaml_parses():
    with (REPO_ROOT / "metadata.yaml").open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict)


def test_metadata_name_matches_repo_dir():
    with (REPO_ROOT / "metadata.yaml").open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert data["name"] == "astrbot_plugin_mhhelper"


def test_metadata_version_semver():
    with (REPO_ROOT / "metadata.yaml").open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    v = data["version"]
    parts = v.split(".")
    assert len(parts) == 3, f"version {v!r} not semver"
    for p in parts:
        assert p.isdigit(), f"version segment {p!r} not numeric"


def test_data_directory_present():
    assert (REPO_ROOT / "data" / "monsters").is_dir()
    assert (REPO_ROOT / "data" / "skills").is_dir()