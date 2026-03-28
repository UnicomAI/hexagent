"""Skills API endpoints.

Skills are split across two root directories:

- **Bundled** (``bundled_skills_dir()``): examples/ and public/ skills that
  ship with the application source or PyInstaller package.  These are the
  skills the project provides out-of-the-box.
- **User data** (``skills_dir()``): private/ skills uploaded by the user,
  plus skills-inactive/ for disabled skills of any category.
"""

from __future__ import annotations

import logging
import shutil
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from clawwork.exceptions import SkillError
from clawwork.harness.skill_spec import parse_skill_md, validate_skill_dir_name

from clawwork_api.paths import bundled_skills_dir, skills_dir


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/skills", tags=["skills"])

# Bundled (read in dev, read-only in packaged builds)
_BUNDLED = bundled_skills_dir()
PUBLIC_DIR = _BUNDLED / "public"
EXAMPLES_DIR = _BUNDLED / "examples"

# User data (always writable)
_USER_DATA = skills_dir()
PRIVATE_DIR = _USER_DATA / "private"
INACTIVE_DIR = _USER_DATA.parent / "skills-inactive"

# Maps each category to its active directory so toggle/delete can iterate
# without hard-coding two different root paths.
_ACTIVE_DIRS: dict[str, Path] = {
    "public": PUBLIC_DIR,
    "private": PRIVATE_DIR,
}

ACCEPTED_EXTENSIONS = (".zip", ".skill")


def _list_skills(directory: Path) -> list[str]:
    """Return sorted list of skill folder names in a directory."""
    if not directory.is_dir():
        return []
    return sorted(
        d.name for d in directory.iterdir() if d.is_dir() and not d.name.startswith(".")
    )


def _find_skill_md(directory: Path) -> Path | None:
    """Find SKILL.md (case-insensitive) in a directory."""
    for p in directory.iterdir():
        if p.name.lower() == "skill.md":
            return p
    return None


@router.get("")
async def list_skills() -> dict[str, list[str]]:
    """Return all public, private, and example skills, plus disabled list.

    Public and examples are read from the bundled skills directory.
    Private skills and the disabled list come from user data.
    """
    inactive_public = _list_skills(INACTIVE_DIR / "public")
    inactive_private = _list_skills(INACTIVE_DIR / "private")
    return {
        "public": sorted(_list_skills(PUBLIC_DIR) + inactive_public),
        "private": sorted(_list_skills(PRIVATE_DIR) + inactive_private),
        "examples": _list_skills(EXAMPLES_DIR),
        "disabled": inactive_public + inactive_private,
    }


@router.post("/upload")
async def upload_skill(file: UploadFile = File(...)) -> dict[str, str]:
    """Upload a .zip or .skill file to install a private skill.

    The archive must contain a SKILL.md file with YAML frontmatter
    including skill name and description.
    """
    if not file.filename or not any(file.filename.endswith(ext) for ext in ACCEPTED_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail="Only .zip and .skill files are accepted.",
        )

    content = await file.read()

    with TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        zip_path = tmp_path / "upload.zip"
        zip_path.write_bytes(content)

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp_path / "extracted")
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="Invalid archive file.")

        extracted = tmp_path / "extracted"

        # Determine skill root: if there's exactly one top-level dir, use it
        top_items = [
            p for p in extracted.iterdir()
            if not p.name.startswith(".") and not p.name.startswith("__")
        ]
        if len(top_items) == 1 and top_items[0].is_dir():
            skill_name = top_items[0].name
            source = top_items[0]
        else:
            # Use filename (without extension) as skill name
            skill_name = file.filename.rsplit(".", 1)[0]
            source = extracted

        # Validate SKILL.md exists and conforms to Agent Skills spec
        skill_md_path = _find_skill_md(source)
        if not skill_md_path:
            raise HTTPException(
                status_code=400,
                detail="Archive must contain a SKILL.md file at the skill root.",
            )

        try:
            spec = parse_skill_md(skill_md_path.read_text(encoding="utf-8"))
        except SkillError as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid SKILL.md: {exc}"
            ) from exc

        # Directory name (if present) must match the declared skill name
        validated_name = spec.frontmatter.name
        if len(top_items) == 1 and top_items[0].is_dir():
            try:
                validate_skill_dir_name(validated_name, top_items[0].name)
            except SkillError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        skill_name = validated_name

        # Check for conflicts
        PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
        dest = PRIVATE_DIR / skill_name
        if dest.exists():
            raise HTTPException(
                status_code=409,
                detail=f'A skill named "{skill_name}" already exists. Delete it first or rename the zip.',
            )
        if (PUBLIC_DIR / skill_name).is_dir():
            raise HTTPException(
                status_code=409,
                detail=f'A built-in skill named "{skill_name}" already exists. Please rename the zip.',
            )
        shutil.copytree(source, dest)

    logger.info("Skill uploaded: %s", skill_name)
    return {"name": skill_name}


@router.delete("/{skill_name}")
async def delete_skill(skill_name: str) -> dict[str, str]:
    """Delete a skill.

    - Private skills are removed from the filesystem (active or inactive).
    - Built-in (public) skills are removed from active/inactive.
      The example copy (if any) remains in the examples directory.
    """
    # Check all possible locations
    candidates = [
        PRIVATE_DIR / skill_name,
        INACTIVE_DIR / "private" / skill_name,
        PUBLIC_DIR / skill_name,
        INACTIVE_DIR / "public" / skill_name,
    ]
    removed = False
    for candidate in candidates:
        if candidate.is_dir():
            shutil.rmtree(candidate)
            removed = True
            break

    if not removed:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_name}")

    logger.info("Skill deleted: %s", skill_name)
    return {"deleted": skill_name}


@router.post("/{skill_name}/install")
async def install_skill(skill_name: str) -> dict[str, str]:
    """Install an example skill by copying it to the public directory."""
    source = EXAMPLES_DIR / skill_name
    if not source.is_dir():
        raise HTTPException(status_code=404, detail=f"Example skill not found: {skill_name}")

    dest = PUBLIC_DIR / skill_name
    if dest.is_dir():
        raise HTTPException(
            status_code=409,
            detail=f'A built-in skill named "{skill_name}" already exists.',
        )

    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copytree(str(source), str(dest))
    logger.info("Skill installed from examples: %s", skill_name)
    return {"installed": skill_name}


class ToggleRequest(BaseModel):
    enabled: bool


@router.put("/{skill_name}/toggle")
async def toggle_skill(skill_name: str, body: ToggleRequest) -> dict[str, bool]:
    """Enable or disable a skill by moving it between active/inactive dirs."""
    if body.enabled:
        # Move from skills-inactive/ back to the appropriate active directory
        for subdir, active_dir in _ACTIVE_DIRS.items():
            inactive_path = INACTIVE_DIR / subdir / skill_name
            if inactive_path.is_dir():
                dest = active_dir / skill_name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(inactive_path), str(dest))
                logger.info("Skill enabled: %s", skill_name)
                return {"enabled": True}
        raise HTTPException(status_code=404, detail=f"Inactive skill not found: {skill_name}")
    else:
        # Move from active directory to skills-inactive/
        for subdir, active_dir in _ACTIVE_DIRS.items():
            active_path = active_dir / skill_name
            if active_path.is_dir():
                dest = INACTIVE_DIR / subdir / skill_name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(active_path), str(dest))
                logger.info("Skill disabled: %s", skill_name)
                return {"enabled": False}
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_name}")
