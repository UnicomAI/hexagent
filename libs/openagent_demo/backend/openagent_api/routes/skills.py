"""Skills API endpoints."""

from __future__ import annotations

import logging
import shutil
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from openagent.exceptions import SkillError
from openagent.harness.skill_spec import parse_skill_md, validate_skill_dir_name


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/skills", tags=["skills"])

SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"
PUBLIC_DIR = SKILLS_DIR / "public"
USER_DIR = SKILLS_DIR / "user"
EXAMPLES_DIR = SKILLS_DIR / "examples"
INACTIVE_DIR = Path(__file__).resolve().parent.parent.parent / "skills-inactive"

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
    """Return all public, user, and example skills, plus disabled list.

    Active and inactive skills are merged into the public/user lists.
    The disabled list is derived from skills in the inactive directory.
    """
    inactive_public = _list_skills(INACTIVE_DIR / "public")
    inactive_user = _list_skills(INACTIVE_DIR / "user")
    return {
        "public": sorted(_list_skills(PUBLIC_DIR) + inactive_public),
        "user": sorted(_list_skills(USER_DIR) + inactive_user),
        "examples": _list_skills(EXAMPLES_DIR),
        "disabled": inactive_public + inactive_user,
    }


@router.post("/upload")
async def upload_skill(file: UploadFile = File(...)) -> dict[str, str]:
    """Upload a .zip or .skill file to install a user skill.

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
        USER_DIR.mkdir(parents=True, exist_ok=True)
        dest = USER_DIR / skill_name
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

    - User skills are removed from the filesystem (active or inactive).
    - Built-in (public) skills are removed from active/inactive.
      The example copy (if any) remains in the examples directory.
    """
    # Check all possible locations
    candidates = [
        USER_DIR / skill_name,
        INACTIVE_DIR / "user" / skill_name,
        PUBLIC_DIR / skill_name,
        INACTIVE_DIR / "public" / skill_name,
    ]
    removed = False
    for path in candidates:
        if path.is_dir():
            shutil.rmtree(path)
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
        # Move from skills-inactive/ back to skills/
        for subdir in ("public", "user"):
            inactive_path = INACTIVE_DIR / subdir / skill_name
            if inactive_path.is_dir():
                dest = SKILLS_DIR / subdir / skill_name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(inactive_path), str(dest))
                logger.info("Skill enabled: %s", skill_name)
                return {"enabled": True}
        raise HTTPException(status_code=404, detail=f"Inactive skill not found: {skill_name}")
    else:
        # Move from skills/ to skills-inactive/
        for subdir in ("public", "user"):
            active_path = SKILLS_DIR / subdir / skill_name
            if active_path.is_dir():
                dest = INACTIVE_DIR / subdir / skill_name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(active_path), str(dest))
                logger.info("Skill disabled: %s", skill_name)
                return {"enabled": False}
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_name}")
