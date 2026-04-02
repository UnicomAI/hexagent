"""Skill discovery and content loading.

SkillResolver scans configured directories on a Computer for skill
folders, parses SKILL.md frontmatter for metadata, and loads
skill content on demand (always fresh from disk).
"""

from __future__ import annotations

import logging
import shlex
from typing import TYPE_CHECKING

from hexagent.exceptions import SkillError
from hexagent.harness.skill_spec import parse_skill_md, validate_skill_dir_name
from hexagent.types import Skill

if TYPE_CHECKING:
    from hexagent.computer.base import Computer

logger = logging.getLogger(__name__)

DEFAULT_SKILL_PATHS: tuple[str, ...] = (
    "/mnt/skills",
    "~/.hexagent/skills",
    ".hexagent/skills",
)

_SKILL_FILENAMES = ("SKILL.md", "skill.md")
_SKILL_DELIMITER = "===SKILL_FILE==="


import os
from pathlib import Path

class SkillResolver:
    r"""维持一个内存注册表，负责技能的发现和加载。

    扫描宿主机（虚拟机外）的文件系统以获取技能元数据，并将结果缓存在内存中。
    这样可以利用 Python 原生的文件系统操作性能，避免频繁调用 WSL 的开销。
    """

    def __init__(
        self,
        computer: Computer,
        search_paths: tuple[str, ...] | list[str],
        host_search_paths: tuple[str, ...] | list[str] | None = None,
    ) -> None:
        """初始化解析器。

        Args:
            computer: 用于加载技能内容的 Computer 实例（通常是虚拟机内部）。
            search_paths: 虚拟机内部对应的技能扫描路径。
            host_search_paths: 宿主机上对应的物理路径。
        """
        self._computer = computer
        self._search_paths = tuple(search_paths)
        # 将 search_paths 映射到 host_search_paths
        self._host_search_paths = tuple(host_search_paths) if host_search_paths else ()
        self._skills: dict[str, Skill] = {}
        self._initialized = False

    @property
    def search_paths(self) -> tuple[str, ...]:
        """配置的虚拟机内部搜索路径。"""
        return self._search_paths

    async def has(self, name: str) -> bool:
        """如果 name 是已知技能，则返回 True。"""
        if not self._initialized:
            await self.discover()
        return name in self._skills

    async def get(self, name: str) -> Skill | None:
        """按名称获取技能。"""
        if not self._initialized:
            await self.discover()
        return self._skills.get(name)

    async def set_enabled(self, name: str, enabled: bool) -> None:
        """在内存中启用或禁用技能，不扫描磁盘。"""
        if name in self._skills:
            old_skill = self._skills[name]
            from hexagent.types import Skill
            self._skills[name] = Skill(
                name=old_skill.name,
                description=old_skill.description,
                path=old_skill.path,
                enabled=enabled
            )
            logger.info("[SkillResolver] Skill %s status updated: enabled=%s", name, enabled)

    async def add_skill_by_path(self, skill_path: str, host_path: str | None = None) -> Skill | None:
        """发现并添加特定路径下的单个技能。

        Args:
            skill_path: 虚拟机内部路径。
            host_path: 宿主机物理路径。
        """
        logger.info("[SkillResolver] Adding single skill from guest path: %s", skill_path)
        
        # 优先在宿主机侧读取元数据
        raw_content = None
        if host_path and os.path.isdir(host_path):
            for filename in _SKILL_FILENAMES:
                p = Path(host_path) / filename
                if p.is_file():
                    raw_content = p.read_text(encoding="utf-8")
                    break
        
        # 兜底：在虚拟机内部读取
        if not raw_content:
            for filename in _SKILL_FILENAMES:
                skill_file = f"{skill_path}/{filename}"
                result = await self._computer.run(f'cat "{skill_file}"')
                if result.exit_code == 0:
                    raw_content = result.stdout
                    break

        if not raw_content:
            logger.warning("[SkillResolver] No SKILL.md found in %s", skill_path)
            return None

        try:
            spec = parse_skill_md(raw_content)
            dir_basename = skill_path.rstrip("/").rsplit("/", 1)[-1]
            validate_skill_dir_name(spec.frontmatter.name, dir_basename)
        except SkillError as exc:
            logger.warning("[SkillResolver] Failed to parse skill in %s: %s", skill_path, exc)
            return None

        from hexagent.types import Skill
        fm = spec.frontmatter
        skill = Skill(name=fm.name, description=fm.description, path=skill_path, enabled=True)
        self._skills[fm.name] = skill
        logger.info("[SkillResolver] Added skill to registry: name=%s", fm.name)
        return skill

    async def remove_skill(self, name: str) -> None:
        """从内存注册表中移除技能。"""
        if name in self._skills:
            del self._skills[name]
            logger.info("[SkillResolver] Removed skill from registry: %s", name)

    async def discover(self, force: bool = False, disabled_names: set[str] | None = None) -> list[Skill]:
        """扫描搜索路径下的技能目录（一次性或强制扫描）。"""
        if self._initialized and not force:
            logger.debug("[SkillResolver] Discovery skipped (already initialized)")
            return list(self._skills.values())

        logger.info("[SkillResolver] Starting skill discovery from host filesystem...")
        self._skills.clear()
        discovered: list[Skill] = []

        # 遍历宿主机路径进行高效扫描
        for i, host_base in enumerate(self._host_search_paths):
            host_path = Path(host_base)
            if not host_path.is_dir():
                continue
            
            guest_base = self._search_paths[i] if i < len(self._search_paths) else None
            if not guest_base:
                continue

            # 仅遍历一级子目录
            for entry in host_path.iterdir():
                if not entry.is_dir():
                    continue
                
                # 检查是否有 SKILL.md
                raw_content = None
                for filename in _SKILL_FILENAMES:
                    md_file = entry / filename
                    if md_file.is_file():
                        raw_content = md_file.read_text(encoding="utf-8")
                        break
                
                if not raw_content:
                    continue

                try:
                    spec = parse_skill_md(raw_content)
                    validate_skill_dir_name(spec.frontmatter.name, entry.name)
                except SkillError:
                    continue

                fm = spec.frontmatter
                is_enabled = disabled_names is None or fm.name not in disabled_names
                
                # 构建虚拟机内部路径
                guest_path = f"{guest_base.rstrip('/')}/{entry.name}"
                
                from hexagent.types import Skill
                skill = Skill(name=fm.name, description=fm.description, path=guest_path, enabled=is_enabled)
                self._skills[fm.name] = skill
                discovered.append(skill)

        self._initialized = True
        logger.info("[SkillResolver] Host-side skill discovery complete, total_skills=%d", len(discovered))
        return discovered

    async def load_content(self, name: str) -> str:
        r"""加载技能的 markdown 内容（从虚拟机内部读取最新内容）。"""
        if name not in self._skills:
            msg = f"Skill not discovered: {name}"
            raise KeyError(msg)

        skill = self._skills[name]
        if not skill.enabled:
            logger.debug("[SkillResolver] Skipping load_content for disabled skill: %s", name)
            return ""

        # Try each accepted filename casing
        result = None
        for filename in _SKILL_FILENAMES:
            skill_file = f"{skill.path}/{filename}"
            result = await self._computer.run(f'cat "{skill_file}"')
            if result.exit_code == 0:
                break

        if result is None or result.exit_code != 0:
            msg = f"Failed to read SKILL.md in {skill.path}"
            raise RuntimeError(msg)

        try:
            spec = parse_skill_md(result.stdout)
        except SkillError as exc:
            msg = f"Failed to parse {skill.path}: {exc}"
            raise RuntimeError(msg) from exc

        return f"Base directory for this skill: {skill.path}\n\n{spec.body}"

    @staticmethod
    def _parse_batch_output(output: str) -> list[tuple[str, str]]:
        """Parse batched discovery output into (directory, content) pairs.

        Args:
            output: Raw stdout from the batched discovery command.

        Returns:
            List of (skill_dir, raw_skill_md_content) tuples.
        """
        delimiter_prefix = f"{_SKILL_DELIMITER}:"
        results: list[tuple[str, str]] = []
        chunks = output.split(delimiter_prefix)

        for chunk in chunks[1:]:  # skip everything before first delimiter
            newline_idx = chunk.find("\n")
            if newline_idx == -1:
                continue
            skill_dir = chunk[:newline_idx].strip()
            raw_content = chunk[newline_idx + 1 :].strip()
            if skill_dir and raw_content:
                results.append((skill_dir, raw_content))

        return results
