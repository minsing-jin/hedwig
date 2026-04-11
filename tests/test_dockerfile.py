"""Tests for the deployment Dockerfile."""

from __future__ import annotations

import json
import pathlib
import re
import shlex


ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCKERFILE = ROOT / "Dockerfile"
VALID_INSTRUCTIONS = {
    "ADD",
    "ARG",
    "CMD",
    "COPY",
    "ENTRYPOINT",
    "ENV",
    "EXPOSE",
    "FROM",
    "HEALTHCHECK",
    "LABEL",
    "ONBUILD",
    "RUN",
    "SHELL",
    "STOPSIGNAL",
    "USER",
    "VOLUME",
    "WORKDIR",
}


def _read_instructions() -> list[str]:
    text = DOCKERFILE.read_text(encoding="utf-8")
    instructions: list[str] = []
    current: list[str] = []

    for raw_line in text.splitlines():
        stripped = raw_line.strip()

        if not current and (not stripped or stripped.startswith("#")):
            continue

        if stripped.startswith("#"):
            continue

        fragment = stripped[:-1].rstrip() if stripped.endswith("\\") else stripped
        current.append(fragment)

        if stripped.endswith("\\"):
            continue

        instructions.append(" ".join(part for part in current if part).strip())
        current = []

    assert not current, "Dockerfile ends with an unfinished line continuation"
    assert instructions, "Dockerfile is empty"
    return instructions


def _parse_json_array(args: str, instruction: str) -> list[str]:
    try:
        parsed = json.loads(args)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"{instruction} JSON form is invalid: {args}") from exc

    assert isinstance(parsed, list), f"{instruction} JSON form must be an array"
    assert parsed, f"{instruction} JSON form cannot be empty"
    assert all(isinstance(item, str) for item in parsed), (
        f"{instruction} JSON form must contain only strings"
    )
    return parsed


def _parse_shell_tokens(args: str, instruction: str) -> list[str]:
    try:
        return shlex.split(args)
    except ValueError as exc:
        raise AssertionError(f"{instruction} shell form is invalid: {args}") from exc


def _split_instruction(line: str) -> tuple[str, str]:
    parts = line.split(maxsplit=1)
    assert len(parts) == 2, f"Dockerfile instruction is missing arguments: {line}"
    return parts[0].upper(), parts[1]


def _validate_from(args: str) -> None:
    pattern = re.compile(
        r"^(--platform=\S+\s+)?\S+(?:\s+AS\s+[A-Za-z0-9._-]+)?$",
        re.IGNORECASE,
    )
    assert pattern.match(args), f"Invalid FROM syntax: {args}"


def _validate_copy_or_add(args: str, instruction: str) -> None:
    stripped = args.strip()
    assert stripped, f"{instruction} requires arguments"

    if stripped.startswith("["):
        parsed = _parse_json_array(stripped, instruction)
        assert len(parsed) >= 2, f"{instruction} JSON form needs source and destination"
        return

    tokens = _parse_shell_tokens(stripped, instruction)
    sources_and_dest = [token for token in tokens if not token.startswith("--")]
    assert len(sources_and_dest) >= 2, (
        f"{instruction} shell form needs source and destination"
    )


def _validate_env(args: str) -> None:
    tokens = _parse_shell_tokens(args, "ENV")
    assert tokens, "ENV requires arguments"
    if all("=" in token for token in tokens):
        return
    assert len(tokens) >= 2, "ENV requires a key and value"


def _validate_instruction(instruction: str, args: str) -> None:
    assert instruction in VALID_INSTRUCTIONS, f"Unknown Dockerfile instruction: {instruction}"

    stripped = args.strip()
    if instruction == "FROM":
        _validate_from(stripped)
        return
    if instruction in {"RUN", "WORKDIR"}:
        assert stripped, f"{instruction} requires arguments"
        return
    if instruction in {"CMD", "ENTRYPOINT"}:
        assert stripped, f"{instruction} requires arguments"
        if stripped.startswith("["):
            _parse_json_array(stripped, instruction)
        return
    if instruction in {"COPY", "ADD"}:
        _validate_copy_or_add(stripped, instruction)
        return
    if instruction == "ENV":
        _validate_env(stripped)
        return
    if instruction == "EXPOSE":
        ports = _parse_shell_tokens(stripped, instruction)
        assert ports, "EXPOSE requires at least one port"
        for port in ports:
            assert re.match(r"^\d+(?:/(tcp|udp))?$", port, re.IGNORECASE), (
                f"Invalid EXPOSE value: {port}"
            )
        return

    assert stripped, f"{instruction} requires arguments"


def test_dockerfile_exists():
    """Dockerfile must exist at project root."""
    assert DOCKERFILE.is_file()


def test_dockerfile_has_valid_instruction_syntax():
    """Dockerfile must parse into syntactically valid Docker instructions."""
    instructions = _read_instructions()

    first_instruction, _ = _split_instruction(instructions[0])
    assert first_instruction == "FROM", "First Dockerfile instruction must be FROM"

    for line in instructions:
        instruction, args = _split_instruction(line)
        _validate_instruction(instruction, args)
