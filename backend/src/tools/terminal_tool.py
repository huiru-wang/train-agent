"""Terminal tool — lets the agent execute shell commands."""

import asyncio
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
async def terminal(command: str) -> str:
    """执行 shell 命令并返回输出。用于运行技能脚本、检查文件等。

    Args:
        command: 要执行的 shell 命令
    """
    logger.info("[Tool:terminal] executing: %s", command)

    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    output = stdout.decode("utf-8", errors="replace").strip()
    errors = stderr.decode("utf-8", errors="replace").strip()

    if process.returncode != 0:
        logger.error("[Tool:terminal] failed (rc=%d): %s", process.returncode, errors)
        combined = f"Exit code: {process.returncode}\n"
        if output:
            combined += f"stdout:\n{output}\n"
        if errors:
            combined += f"stderr:\n{errors}"
        return combined

    logger.info("[Tool:terminal] success (output=%d chars)", len(output))
    # Combine stdout + stderr (some tools write info to stderr)
    result = output
    if errors:
        result += f"\n{errors}"
    return result or "(no output)"
