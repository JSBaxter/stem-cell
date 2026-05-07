from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_stdio_e2e_server_round_trip(tmp_path):
    db_path = tmp_path / "queue-e2e.db"
    project_dir = Path(__file__).resolve().parents[1]

    async def run():
        server = StdioServerParameters(
            command=sys.executable,
            args=[
                "server.py",
                "--db",
                str(db_path),
                "--transport",
                "stdio",
            ],
            cwd=str(project_dir),
        )

        async with stdio_client(server) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                init = await session.initialize()
                tools = await session.list_tools()

                assert init.serverInfo.name == "queue"
                assert any(tool.name == "add_idea" for tool in tools.tools)

                add_result = await session.call_tool(
                    "add_idea",
                    {"title": "E2E task", "notes": "Created through stdio MCP."},
                )
                task_id = add_result.structuredContent["result"][0]["task"]["id"]

                await session.call_tool(
                    "scope_task",
                    {
                        "task_id": task_id,
                        "description": "Scope the e2e task",
                        "context": "End-to-end test",
                        "priority": 10,
                    },
                )

                claim_result = await session.call_tool(
                    "claim_task",
                    {"agent_id": "claude-code"},
                )
                session_id = claim_result.structuredContent["result"][0]["session"][
                    "id"
                ]

                await session.call_tool(
                    "request_feature",
                    {
                        "title": "Add queue metrics",
                        "kind": "repetitive_work",
                        "detail": "Want a summary tool for repeated queue inspection.",
                        "task_id": task_id,
                        "session_id": session_id,
                        "agent_id": "claude-code",
                    },
                )

                task_result = await session.call_tool("get_task", {"task_id": task_id})
                feature_result = await session.call_tool("list_feature_requests", {})

                assert task_result.structuredContent["task"]["id"] == task_id
                assert task_result.structuredContent["sessions"][0]["id"] == session_id
                assert (
                    feature_result.structuredContent["result"][0]["task_id"] == task_id
                )

    asyncio.run(run())
