"""Regression tests for consolidated requirements include directives."""

from pathlib import Path


def _extract_requirement_paths(requirements_file: Path) -> list[Path]:
    """Return filesystem paths referenced via ``-r`` in a requirements file."""

    referenced_paths: list[Path] = []
    for raw_line in requirements_file.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-r "):
            relative_path = line.split(maxsplit=1)[1]
            referenced_paths.append((requirements_file.parent / relative_path).resolve())
    return referenced_paths


def test_referenced_service_requirements_exist():
    repo_root = Path(__file__).resolve().parents[1]
    requirement_files = [
        repo_root / "requirements" / "services.txt",
        repo_root / "requirements" / "services-dev.txt",
    ]

    missing_paths = []

    for requirements_file in requirement_files:
        for referenced_path in _extract_requirement_paths(requirements_file):
            if not referenced_path.exists():
                missing_paths.append((requirements_file, referenced_path))

    assert not missing_paths, (
        "The following requirements include directives point to missing files: "
        + ", ".join(
            f"{req_file.relative_to(repo_root)} -> {ref_path.relative_to(repo_root)}"
            for req_file, ref_path in missing_paths
        )
    )
