from unittest.mock import Mock, patch

from ageos.engine.llama_backend import LlamaBackend
from ageos.engine.registry import ModelSpec


def test_llama_backend_uses_single_parallel_slot_by_default(monkeypatch) -> None:
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/malicious")
    model = ModelSpec(
        name="test",
        flavor="test",
        capability="instruct",
        tier="tiny",
        backend="llama",
        repo_id="repo/model",
        filename="model.gguf",
        ram_gb=1,
        vram_gb=0,
    )
    process = Mock()
    process.poll.return_value = None

    with (
        patch("ageos.engine.llama_backend.shutil.which", return_value="/usr/local/bin/llama-server"),
        patch("ageos.engine.llama_backend.subprocess.Popen", return_value=process) as popen,
        patch("ageos.engine.llama_backend._wait_for_http"),
    ):
        backend = LlamaBackend()
        backend.start(model, "/models/model.gguf")

    args = popen.call_args.args[0]
    env = popen.call_args.kwargs["env"]
    assert args[args.index("--ctx-size") + 1] == "32768"
    assert args[args.index("--parallel") + 1] == "1"
    assert "/tmp/malicious" not in env["LD_LIBRARY_PATH"]
    assert "/usr/local/bin" in env["LD_LIBRARY_PATH"]
