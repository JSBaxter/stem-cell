from __future__ import annotations

import asyncio

from server import create_app


def test_server_tools_dispatch_to_domain_and_repository(tmp_path):
    db_path = tmp_path / "queue.db"
    app = create_app(str(db_path))

    async def run():
        health_result = await app.call_tool("health", {})
        stats_result = await app.call_tool("stats", {})

        assert health_result.structured_content["ok"] is True
        assert stats_result.structured_content["task_count_total"] == 0

        add_result = await app.call_tool(
            "add_idea",
            {"title": "Add server layer", "notes": "Need MCP dispatch."},
        )
        added = add_result.structured_content["result"][0]
        task_id = added["task"]["id"]

        await app.call_tool(
            "scope_task",
            {
                "task_id": task_id,
                "description": "Implement server.py",
                "context": "Final MCP layer",
                "priority": 5,
            },
        )

        claim_result = await app.call_tool(
            "claim_task",
            {"agent_id": "claude-code"},
        )
        claimed = claim_result.structured_content["result"][0]
        session_id = claimed["session"]["id"]

        tool_call_result = await app.call_tool(
            "log_tool_calls_summary",
            {
                "session_id": session_id,
                "tool_calls_summary": {"web.search": 1, "git": 2},
                "tokens": {"tokens_in": 6, "tokens_out": 3},
            },
        )

        await app.call_tool(
            "request_feature",
            {
                "title": "Add dashboard",
                "kind": "guidance_gap",
                "detail": "Need a higher-level queue view.",
                "task_id": task_id,
                "session_id": session_id,
                "agent_id": "claude-code",
                "model_name": "gpt-5.5",
            },
        )

        task_result = await app.call_tool("get_task", {"task_id": task_id})
        feature_result = await app.call_tool("list_feature_requests", {})
        stats_result = await app.call_tool("stats", {})

        assert task_result.structured_content["task"]["id"] == task_id
        assert task_result.structured_content["sessions"][0]["id"] == session_id
        assert (
            tool_call_result.structured_content["result"][0]["session"][
                "tool_calls_summary"
            ]["git"]
            == 2
        )
        assert feature_result.structured_content["result"][0]["task_id"] == task_id
        assert (
            stats_result.structured_content["tool_calls_summary_totals"]["web.search"]
            == 1
        )

    asyncio.run(run())


def test_resolve_feature_request_tool_marks_resolved(tmp_path):
    db_path = tmp_path / "queue.db"
    app = create_app(str(db_path))

    async def run():
        await app.call_tool(
            "request_feature",
            {
                "title": "Discard me",
                "kind": "guidance_gap",
                "detail": "Stale; was already addressed.",
            },
        )
        listed = (await app.call_tool("list_feature_requests", {})).structured_content[
            "result"
        ]
        fr_id = listed[0]["id"]

        idea = await app.call_tool(
            "add_idea", {"title": "Followup task for FR conversion"}
        )
        followup_task_id = idea.structured_content["result"][0]["task"]["id"]
        await app.call_tool(
            "scope_task",
            {
                "task_id": followup_task_id,
                "description": "the conversion target",
                "context": "carved from a feature request",
                "priority": 50,
            },
        )

        # Discard path
        await app.call_tool(
            "resolve_feature_request",
            {
                "feature_request_id": fr_id,
                "resolution": "discarded",
                "note": "Won't fix.",
            },
        )

        # Convert-to-task path on a fresh FR
        await app.call_tool(
            "request_feature",
            {
                "title": "Convert me",
                "kind": "repetitive_work",
                "detail": "becomes a task",
            },
        )
        all_frs = (await app.call_tool("list_feature_requests", {})).structured_content[
            "result"
        ]
        fr_to_convert = next(fr for fr in all_frs if fr["title"] == "Convert me")["id"]
        await app.call_tool(
            "resolve_feature_request",
            {
                "feature_request_id": fr_to_convert,
                "resolution": "converted_to_task",
                "task_id": followup_task_id,
            },
        )

        resolved = (
            await app.call_tool("list_feature_requests", {"status": "resolved"})
        ).structured_content["result"]
        by_id = {fr["id"]: fr for fr in resolved}
        assert by_id[fr_id]["resolution"] == "discarded"
        assert by_id[fr_id]["resolution_task_id"] is None
        assert by_id[fr_to_convert]["resolution"] == "converted_to_task"
        assert by_id[fr_to_convert]["resolution_task_id"] == followup_task_id

    asyncio.run(run())


def test_metadata_query_tools_are_exposed(tmp_path):
    db_path = tmp_path / "queue.db"
    app = create_app(str(db_path))

    async def run():
        add_result = await app.call_tool("add_idea", {"title": "Visibility task"})
        task_id = add_result.structured_content["result"][0]["task"]["id"]
        await app.call_tool(
            "scope_task",
            {
                "task_id": task_id,
                "description": "expose metadata tools",
                "context": "visibility",
                "priority": 70,
            },
        )
        claim_result = await app.call_tool("claim_task", {"agent_id": "claude-code"})
        session_id = claim_result.structured_content["result"][0]["session"]["id"]
        await app.call_tool(
            "log_tool_calls_summary",
            {
                "session_id": session_id,
                "tool_calls_summary": {"Bash": 2, "exec_command": 3},
            },
        )
        await app.call_tool(
            "close_session",
            {
                "session_id": session_id,
                "outcome": "completed",
                "summary": "wrap",
                "decision_notes": "kept the read tools thin",
            },
        )

        open_result = await app.call_tool("list_open_sessions", {})
        notes_result = await app.call_tool("list_session_notes", {})
        activity_result = await app.call_tool("agent_activity", {})
        canonical_result = await app.call_tool("tool_calls_canonical", {})

        assert open_result.structured_content["result"] == []
        notes = notes_result.structured_content["result"]
        assert len(notes) == 1
        assert notes[0]["decision_notes"] == "kept the read tools thin"
        activity = activity_result.structured_content["result"]
        assert activity[0]["agent_id"] == "claude-code"
        # Bash + exec_command both fold onto canonical "bash" at write time.
        assert activity[0]["tool_calls"] == {"bash": 5}
        assert canonical_result.structured_content["counts"]["bash"] == 5
        assert canonical_result.structured_content["aliases"] == {}

    asyncio.run(run())
