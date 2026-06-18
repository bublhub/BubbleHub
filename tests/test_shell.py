from ageos.cli.shell import _interactive_args


def test_interactive_shell_args_force_interactive_mode() -> None:
    assert _interactive_args("/usr/bin/bash") == ["--noprofile", "--norc", "-i"]
    assert _interactive_args("/bin/zsh") == ["-f", "-i"]
    assert _interactive_args("/bin/sh") == ["-i"]
