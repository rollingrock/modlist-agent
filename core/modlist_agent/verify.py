"""Prove the build works, using a signal the agent does not produce.

The rule from docs/VERIFICATION.md: an agent's own report is the weakest possible
evidence. What counts is a plugin inside the built instance answering an HTTP request
from a running game.

Three outcomes, never two. "No response and no crash" is INCONCLUSIVE, not failure —
learned the hard way when a missing dependency produced a modal dialog and an unbounded
hang with no crash and no error code.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum


class Outcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


@dataclass
class Result:
    outcome: Outcome
    detail: str
    evidence: dict | None = None

    @property
    def exit_code(self) -> int:
        return {Outcome.PASS: 0, Outcome.FAIL: 1, Outcome.INCONCLUSIVE: 2}[self.outcome]


def preflight(manifest, inst) -> tuple[list[str], list[str]]:
    """Check declared dependency files exist BEFORE launching.

    This check exists because of one specific incident: the VR Address Library was
    missing, CommonLibF4 popped a message box, and the game hung with no crash and no
    log line. Cheap to check, and it converts an unbounded hang into a sentence.

    Returns (absent_mods, missing_files). They are different problems: an absent mod
    means the build is incomplete, while an installed mod missing a file it declares
    means the install is broken.
    """
    absent, missing = [], []
    for e in manifest.installable():
        if not e.virtualised:
            continue
        d = inst.mods / e.name
        if not d.exists():
            absent.append(f"{e.id} (mods/{e.name}/)")
            continue
        for rel in e.raw.get("verify") or []:
            if rel.endswith("/"):
                continue
            if not (d / rel.replace("/", "\\")).exists():
                missing.append(f"{e.id}: declares {rel}, not present in mods/{e.name}/")
    return absent, missing


def call(port: int, tool: str, body: dict, timeout: float = 5.0) -> dict | None:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/tool/{tool}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except (urllib.error.URLError, OSError, ValueError):
        return None


def launch(inst, title: str) -> subprocess.Popen:
    return subprocess.Popen(
        [str(inst.exe), "-p", inst.profile, f"moshortcut://:{title}"],
        cwd=str(inst.path),
    )


def run(manifest, inst, *, timeout: int = 180, launch_title: str | None = None,
        partial: bool = False) -> Result:
    port = inst.platform.devbench_port

    absent, missing = preflight(manifest, inst)
    if missing:
        return Result(Outcome.FAIL,
                      "installed mods are missing files they declare; refusing to launch:\n  "
                      + "\n  ".join(missing))
    if absent and not partial:
        return Result(Outcome.FAIL,
                      f"{len(absent)} mod(s) in the recipe are not installed; refusing to "
                      "launch. A pass here would not mean the recipe works.\n  "
                      + "\n  ".join(absent)
                      + "\n  Use --partial to verify an incomplete build deliberately.")
    if absent:
        print(f"  (partial: {len(absent)} recipe mod(s) not installed — a pass proves the "
              "instance and harness, NOT the recipe)")

    if call(port, "ping", {}, timeout=2):
        return Result(Outcome.INCONCLUSIVE,
                      f"something already answers on :{port} — cannot attribute a pass to "
                      "this build. Close the running game and retry.")

    title = launch_title or inst.platform.extender_loader.split("_")[0].upper()
    launch(inst, title)

    deadline = time.time() + timeout
    while time.time() < deadline:
        state = call(port, "inspect", {"kind": "state"})
        if state:
            ev = {"state": state, "ping": call(port, "ping", {})}
            scene = call(port, "inspect", {"kind": "scene"})
            if scene:
                ev["scene"] = scene
            ok = state.get("exe", "").lower() == inst.platform.game_exe.lower()
            return Result(
                Outcome.PASS if ok else Outcome.FAIL,
                f"{state.get('plugin')} answered on :{port} — exe={state.get('exe')} "
                f"vr={state.get('vr')} extender={state.get('extender')} "
                f"frame={state.get('frame')}",
                ev,
            )
        time.sleep(3)

    # Do not invent a cause. Point at the one signal that discriminates.
    log = inst.platform.extender_loader.split("_")[0]
    return Result(
        Outcome.INCONCLUSIVE,
        f"no response on :{port} within {timeout}s, and no crash was observed.\n"
        f"  This is NOT a diagnosed failure. Check, in order:\n"
        f"    1. a modal dialog waiting for a click (a missing dependency looks like a hang)\n"
        f"    2. Documents\\My Games\\{inst.platform.mo2_short_name}\\F4SE\\{log}.log —\n"
        f"       does it end mid plugin-load? that names the plugin that died\n"
        f"    3. whether a headset or the SteamVR null driver is available\n"
        f"       (core\\tools\\steamvr-null.ps1 -Status)\n"
        f"    4. does {log}.log name ZERO plugins, while the instance clearly has them?\n"
        f"       Then the extender scanned the plugin directory before usvfs existed and\n"
        f"       read the bare game dir. Compare {log}_loader.log against\n"
        f"       {log}_steam_loader.log: if the plain loader's is the fresh one, the\n"
        f"       loader needs Platform.extender_args (-forcesteamloader). The game boots\n"
        f"       to the main menu looking perfectly healthy, which is why this one hides.",
    )


def save_evidence(result: Result, path: pathlib.Path) -> None:
    if not result.evidence:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(
        {"outcome": result.outcome.value, "detail": result.detail, **result.evidence},
        indent=2), encoding="utf-8")
