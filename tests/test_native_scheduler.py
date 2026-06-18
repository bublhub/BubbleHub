from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_scheduler_state_is_visible_across_processes(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["AGEOS_SCHEDULER_STATE"] = str(tmp_path / "scheduler.state")
    env["PYTHONPATH"] = str(repo_root)

    writer = """
from ageos.node.client import SchedulerClient
client = SchedulerClient.local()
agent_id = client.register_agent('/bin/agent', 0, 'default-instruct', pid=12345)
client.mark_model_loaded('mistral-instruct-small', 'default-instruct', 'llama', 9, 0, 23456, 51000)
print(agent_id)
"""
    reader = """
from ageos.node.client import SchedulerClient
snapshot = SchedulerClient.local().status_snapshot()
assert any(agent['binary'] == '/bin/agent' for agent in snapshot['agents']), snapshot
assert any(model['name'] == 'mistral-instruct-small' for model in snapshot['models']), snapshot
print('ok')
"""

    subprocess.run([sys.executable, "-c", writer], check=True, env=env, cwd=repo_root)
    result = subprocess.run(
        [sys.executable, "-c", reader],
        check=True,
        env=env,
        cwd=repo_root,
        text=True,
        capture_output=True,
    )

    assert "ok" in result.stdout
