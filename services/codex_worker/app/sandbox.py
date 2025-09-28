"""Run commands inside isolated containers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(slots=True)
class SandboxResult:
    """Result returned by a sandbox execution."""

    success: bool
    logs: str
    exit_code: int


class SandboxRunner:
    """Execute commands inside an ephemeral container."""

    def __init__(self, image: str, checkout_root: str) -> None:
        self._image = image
        self._checkout_root = Path(checkout_root)
        self._checkout_root.mkdir(parents=True, exist_ok=True)

    async def run(self, repository: str, commands: Sequence[str]) -> SandboxResult:
        """Execute the provided commands in an isolated container."""

        joined_commands = " && ".join(commands)
        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{self._checkout_root}:/workspace",
            "-e",
            f"CODEX_REPOSITORY={repository}",
            self._image,
            "bash",
            "-lc",
            joined_commands,
        ]
        process = await asyncio.create_subprocess_exec(
            *docker_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await process.communicate()
        output = stdout.decode("utf-8", errors="ignore")
        return SandboxResult(success=process.returncode == 0, logs=output, exit_code=process.returncode)
