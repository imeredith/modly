import asyncio
import json
from pathlib import Path
import unittest
from unittest import mock

from services import codex_subscription as codex
import routers.agent as agent


class CodexTests(unittest.TestCase):
    def test_status_requires_chatgpt_login(self):
        for output, expected in [("Logged in using ChatGPT", True), ("Logged in using an API key", False)]:
            with mock.patch.object(codex, "_run", mock.AsyncMock(return_value=output)):
                self.assertEqual(asyncio.run(codex.status())["connected"], expected)

    def test_missing_cli_is_actionable(self):
        with mock.patch.object(codex.shutil, "which", return_value=None):
            result = asyncio.run(codex.status())
        self.assertFalse(result["connected"])
        self.assertIn("Install @openai/codex", result["message"])

    def test_cli_round_preserves_history_images_and_subscription_auth(self):
        recorded = {}

        async def run(args, **kwargs):
            recorded.update(args=args, **kwargs)
            root = Path(kwargs["cwd"])
            self.assertTrue(list(root.glob("image-*.png")))
            (root / "answer.json").write_text(json.dumps({"message": "Checking", "tool_calls": [
                {"name": "list_models", "arguments": "{}"}
            ]}))

        messages = [{"role": "user", "content": [
            {"type": "text", "text": "Generate from this"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,aGVsbG8="}},
        ]}]
        with mock.patch.object(codex, "_run", side_effect=run):
            result = asyncio.run(codex.complete(messages, agent.TOOLS, "test-model", "off"))
        self.assertIn('forced_login_method="chatgpt"', recorded["args"])
        self.assertIn("read-only", recorded["args"])
        self.assertIn("test-model", recorded["args"])
        self.assertIn("Generate from this", recorded["prompt"].decode())
        self.assertEqual(result["tool_calls"][0]["function"]["name"], "list_models")
        self.assertFalse(Path(recorded["cwd"]).exists())
        self.assertEqual(messages[0]["content"][1]["type"], "image_url")

    def test_invalid_tool_response_is_rejected(self):
        async def run(args, **kwargs):
            (Path(kwargs["cwd"]) / "answer.json").write_text(json.dumps({
                "message": "", "tool_calls": [{"name": "shell", "arguments": "{}"}]
            }))
        with mock.patch.object(codex, "_run", side_effect=run):
            with self.assertRaises(codex.CodexError):
                asyncio.run(codex.complete([], agent.TOOLS, "", "auto"))

    def test_chat_executes_modly_tools_then_returns_answer(self):
        async def collect():
            request = agent.AgentChatRequest(
                messages=[agent.ChatMessage(role="user", content="List workflows")],
                model="", provider=agent.ProviderConfig(type="codex"))
            return [e async for e in agent._chat_events(request)]

        complete = mock.AsyncMock(side_effect=[
            {"content": "", "tool_calls": [{"index": 0, "id": "c1", "type": "function",
             "function": {"name": "list_workflows", "arguments": "{}"}}]},
            {"content": "Found your workflow.", "tool_calls": []},
        ])
        with mock.patch.object(codex, "complete", complete), \
             mock.patch.object(agent, "execute_tool", mock.AsyncMock(return_value=("Workflow A", None))) as execute, \
             mock.patch.object(agent, "_claim_slot") as claim:
            events = asyncio.run(collect())
        execute.assert_awaited_once_with("list_workflows", {}, {})
        claim.assert_not_called()
        self.assertEqual(events[-1]["message"], "Found your workflow.")
        self.assertFalse(events[-1]["error"])
        self.assertIn("tool_done", [e["type"] for e in events])
        self.assertTrue(any(m["role"] == "tool" for m in complete.call_args.args[0]))

    def test_cli_failure_becomes_error_event(self):
        async def collect():
            request = agent.AgentChatRequest(messages=[], provider=agent.ProviderConfig(type="codex"))
            return [e async for e in agent._chat_events(request)]
        with mock.patch.object(codex, "complete", mock.AsyncMock(side_effect=codex.CodexError("Sign in again"))):
            events = asyncio.run(collect())
        self.assertTrue(events[-1]["error"])
        self.assertEqual(events[-1]["message"], "Sign in again")

    def test_subprocess_strips_api_keys_and_uses_stdin(self):
        proc = mock.Mock(returncode=0)
        proc.communicate = mock.AsyncMock(return_value=(b"ok", b""))
        create = mock.AsyncMock(return_value=proc)
        with mock.patch.object(codex, "_binary", return_value="/bin/codex"), \
             mock.patch.object(codex.asyncio, "create_subprocess_exec", create), \
             mock.patch.dict(codex.os.environ, {"OPENAI_API_KEY": "secret", "CODEX_API_KEY": "secret"}):
            self.assertEqual(asyncio.run(codex._run(["exec", "-"], prompt=b"hello")), "ok")
        env = create.call_args.kwargs["env"]
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("CODEX_API_KEY", env)
        proc.communicate.assert_awaited_once_with(b"hello")

    def test_timeout_and_cancellation_kill_the_child(self):
        for failure in (asyncio.TimeoutError(), asyncio.CancelledError()):
            proc = mock.Mock(returncode=None)
            proc.communicate = mock.AsyncMock(side_effect=failure)
            proc.wait = mock.AsyncMock()
            with mock.patch.object(codex, "_binary", return_value="/bin/codex"), \
                 mock.patch.object(codex.asyncio, "create_subprocess_exec", mock.AsyncMock(return_value=proc)):
                with self.assertRaises(type(failure)):
                    asyncio.run(codex._run(["exec"]))
            proc.kill.assert_called_once()
            proc.wait.assert_awaited_once()
