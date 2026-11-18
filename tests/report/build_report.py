"""Build the non-functional test report (URS Section 4.4) from test results and manual checks.

    python tests/report/build_report.py --junit reports/ --out docs/test-report/TEST-REPORT.md
    python tests/report/build_report.py --check     # the mapping still matches the code

Inputs (all in docs/test-report/):
    requirements.json    the 29 requirements, copied from the final URS
    evidence.yaml        which CI tests, stack tests and manual checks verify each one
    manual-results.yaml  results of the manual checks (and of the integration suite, STACK)
and JUnit XML files from the test runs: junit-gateway.xml, junit-merchant.xml (pytest
--junitxml) and junit-checkout.xml (vitest --reporter=junit).

A requirement is Pass when every CI test named for it passed and every manual check has a
passing newest result; Fail when any of them failed; otherwise Pending (manual checks not yet
done) or Not run (no test results given).
"""
import argparse
import ast
import datetime as dt
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs" / "test-report"
SERVICE_DIRS = {"gateway": ROOT / "gateway", "simulator": ROOT / "simulator",
                "merchant": ROOT / "merchant", "checkout": ROOT / "frontend" / "checkout",
                "dashboard": ROOT / "frontend" / "dashboard",
                "integration": ROOT / "tests" / "integration"}
CI_SERVICES = {"gateway", "simulator", "merchant", "checkout", "dashboard"}
VITEST = {"checkout", "dashboard"}

PASS, FAIL, PENDING, NOT_RUN = "Pass", "Fail", "Pending", "Not run"


# --- inputs ---------------------------------------------------------------------------------

def load_inputs():
    reqs = json.loads((DOCS / "requirements.json").read_text())
    evidence = yaml.safe_load((DOCS / "evidence.yaml").read_text()) or {}
    manual = yaml.safe_load((DOCS / "manual-results.yaml").read_text()) or {}
    return reqs, evidence, manual


def ref_parts(entry):
    """{'gateway': 'apps/x/tests.py::test_y'} -> ('gateway', 'apps/x/tests.py', 'test_y')."""
    (service, ref), = entry.items()
    path, name = ref.split("::", 1)
    return service, path, name


def read_junit(folder: Path | None):
    """{(service, path, name): 'passed'|'failed'|'skipped'} from every junit-*.xml in folder."""
    results = {}
    if folder is None or not folder.exists():
        return results
    for file in sorted(folder.glob("junit-*.xml")):
        service = file.stem.removeprefix("junit-")
        root = ET.parse(file).getroot()
        for case in root.iter("testcase"):
            classname, name = case.get("classname", ""), case.get("name", "")
            if service in VITEST:  # vitest: classname = file, name = "describe > it"
                path, name = classname, name.split(" > ")[-1]
            else:  # pytest: classname = dotted module, name may carry [params]
                path = classname.replace(".", "/") + ".py"
                name = name.split("[", 1)[0]
            if case.find("failure") is not None or case.find("error") is not None:
                outcome = "failed"
            elif case.find("skipped") is not None:
                outcome = "skipped"
            else:
                outcome = "passed"
            key = (service, path, name)
            # A parametrised test passes only if every case passed.
            if results.get(key) != "failed":
                results[key] = "failed" if outcome == "failed" else (
                    results.get(key) if results.get(key) == "passed" else outcome)
    return results


def suite_totals(folder: Path | None):
    totals = {}
    if folder is None or not folder.exists():
        return totals
    for file in sorted(folder.glob("junit-*.xml")):
        root = ET.parse(file).getroot()
        cases = list(root.iter("testcase"))
        failed = sum(1 for c in cases if c.find("failure") is not None
                     or c.find("error") is not None)
        skipped = sum(1 for c in cases if c.find("skipped") is not None)
        totals[file.stem.removeprefix("junit-")] = (len(cases) - failed - skipped, failed,
                                                    skipped)
    return totals


# --- --check: every named test and manual check exists --------------------------------------

def test_exists(service, path, name) -> bool:
    file = SERVICE_DIRS[service] / path
    if not file.exists():
        return False
    source = file.read_text()
    if file.suffix == ".py":
        tree = ast.parse(source)
        return any(isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == name
                   for n in ast.walk(tree))
    return f'it("{name}"' in source or f"it('{name}'" in source


def check(reqs, evidence, manual) -> list[str]:
    problems = []
    ids = [r["id"] for r in reqs["requirements"]]
    procedures = set(re.findall(r"^## (M-[A-Z]{3}-\d{2}):", (DOCS / "MANUAL-TESTS.md")
                                .read_text(), flags=re.MULTILINE))
    for rid in ids:
        if rid not in evidence:
            problems.append(f"{rid}: missing from evidence.yaml")
    for rid, ev in evidence.items():
        if rid not in ids:
            problems.append(f"{rid}: in evidence.yaml but not a URS requirement")
            continue
        ev = ev or {}
        if not (ev.get("ci") or ev.get("manual")):
            problems.append(f"{rid}: no CI test and no manual check")
        for kind in ("ci", "stack"):
            for entry in ev.get(kind) or []:
                service, path, name = ref_parts(entry)
                if kind == "ci" and service not in CI_SERVICES:
                    problems.append(f"{rid}: {service} tests do not run in CI")
                if not test_exists(service, path, name):
                    problems.append(f"{rid}: {service}: {path}::{name} not found")
        for mid in ev.get("manual") or []:
            if mid not in procedures:
                problems.append(f"{rid}: {mid} has no procedure in MANUAL-TESTS.md")
            if mid not in manual:
                problems.append(f"{rid}: {mid} missing from manual-results.yaml")
    for entries in manual.values():
        for item in entries or []:
            if str(item.get("result", "")).lower() not in ("pass", "fail"):
                problems.append(f"manual-results.yaml: result must be pass or fail: {item}")
    return problems


# --- the report -----------------------------------------------------------------------------

def newest(entries):
    return (entries or [None])[-1]


def assess(ev, junit, manual, have_junit):
    """(status, ci_line, manual_line, details) for one requirement."""
    ev = ev or {}
    ci = []
    for entry in ev.get("ci") or []:
        service, path, name = ref_parts(entry)
        ci.append((service, path, name, junit.get((service, path, name), "not run")))
    stack_result = newest(manual.get("STACK"))
    stack = [(*ref_parts(e), (stack_result or {}).get("result", "not run"))
             for e in ev.get("stack") or []]
    checks = [(mid, newest(manual.get(mid))) for mid in ev.get("manual") or []]

    ci_passed = sum(1 for *_, outcome in ci if outcome == "passed")
    ci_failed = any(outcome == "failed" for *_, outcome in ci)
    manual_failed = any(r and str(r.get("result")).lower() == "fail" for _, r in checks)
    manual_open = any(r is None for _, r in checks)
    if ci_failed or manual_failed:
        status = FAIL
    elif ci and (not have_junit or ci_passed < len(ci)):
        status = NOT_RUN
    elif manual_open:
        status = PENDING
    else:
        status = PASS
    ci_line = f"{ci_passed}/{len(ci)} passed" if ci else "none"
    if checks:
        done = [r for _, r in checks if r]
        manual_line = ", ".join(
            f"{mid}: {r['result']} ({r.get('date', '')})" if r else f"{mid}: to do"
            for mid, r in checks)
        if not done:
            manual_line = ", ".join(f"{mid}: to do" for mid, _ in checks)
    else:
        manual_line = "none needed"
    return status, ci_line, manual_line, ci, stack, checks


def short(text, limit=90):
    text = text.replace("|", "/")
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "..."


def build(reqs, evidence, manual, junit, totals, have_junit) -> str:
    now = dt.datetime.now(dt.UTC).astimezone(dt.timezone(dt.timedelta(hours=8)))
    sha = os.environ.get("GITHUB_SHA", "")[:7] or "local"
    run_url = ""
    if os.environ.get("GITHUB_RUN_ID"):
        run_url = (f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/"
                   f"{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/"
                   f"{os.environ['GITHUB_RUN_ID']}")
    rows = {r["id"]: r for r in reqs["requirements"]}
    assessed = {rid: assess(evidence.get(rid), junit, manual, have_junit) for rid in rows}
    count = {s: 0 for s in (PASS, PENDING, FAIL, NOT_RUN)}
    must = {s: 0 for s in count}
    for rid, (status, *_rest) in assessed.items():
        count[status] += 1
        if rows[rid]["priority"] == "Must":
            must[status] += 1

    out = [
        "# Non-functional test report (URS Section 4.4)",
        "",
        f"Generated {now:%d %b %Y, %H:%M} (Singapore time) from commit `{sha}`"
        + (f", [CI run]({run_url})" if run_url else "") + ". Do not edit by hand: change "
        "`evidence.yaml` or `manual-results.yaml` and rebuild "
        "(`python tests/report/build_report.py`).",
        "",
        (f"**{count[PASS]} of {len(rows)} requirements pass**, {count[PENDING]} wait for "
        f"manual checks, {count[FAIL]} fail and {count[NOT_RUN]} were not run. Of the "
        f"{sum(must.values())} Must requirements, {must[PASS]} pass."),
        "",
        "| Status | All | Must | Should |",
        "| --- | ---: | ---: | ---: |",
    ]
    for status in (PASS, PENDING, FAIL, NOT_RUN):
        out.append(f"| {status} | {count[status]} | {must[status]} | "
                   f"{count[status] - must[status]} |")
    if totals:
        out += ["", "Test suites in this run:", "",
                "| Suite | Passed | Failed | Skipped |", "| --- | ---: | ---: | ---: |"]
        for suite, (passed, failed, skipped) in totals.items():
            out.append(f"| {suite} | {passed} | {failed} | {skipped} |")
    stack = newest(manual.get("STACK"))
    out += ["", "Integration suite against the running stack (tests/integration): "
            + (f"{stack['result']} on {stack.get('date')}, {stack.get('environment', '')}."
               if stack else "not recorded yet.")]

    for group in reqs["groups"]:
        members = [r for r in reqs["requirements"] if r["id"].split("-")[1] == group["prefix"]]
        out += ["", f"## {group['name']} (Table {group['table']})", "",
                "| ID | Priority | Requirement | Automated (CI) | Manual | Status |",
                "| --- | --- | --- | --- | --- | --- |"]
        for r in members:
            status, ci_line, manual_line, *_ = assessed[r["id"]]
            out.append(f"| {r['id']} | {r['priority']} | {short(r['requirement'])} | "
                       f"{ci_line} | {manual_line} | **{status}** |")

    out += ["", "## Evidence per requirement"]
    for r in reqs["requirements"]:
        status, _, _, ci, stack_tests, checks = assessed[r["id"]]
        out += ["", f"### {r['id']}: {status}", "",
                f"{r['requirement']} ({r['priority']}; source {r['source']})", "",
                f"*Acceptance ({r['verification']}):* {r['acceptance']}", ""]
        for service, path, name, outcome in ci:
            out.append(f"- CI, {service}: `{path}::{name}`: {outcome}")
        for service, path, name, outcome in stack_tests:
            out.append(f"- Stack, {service}: `{path}::{name}`: {outcome} (integration run)")
        for mid, result in checks:
            if result:
                detail = "; ".join(str(result[k]) for k in ("figures", "notes", "evidence")
                                   if result.get(k))
                out.append(f"- Manual, {mid} ([procedure](MANUAL-TESTS.md)): "
                           f"**{result['result']}** on {result.get('date')} by "
                           f"{result.get('by', '?')}, {result.get('environment', '')}"
                           + (f". {detail}" if detail else ""))
            else:
                out.append(f"- Manual, {mid} ([procedure](MANUAL-TESTS.md)): to do")
    return "\n".join(out) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--junit", type=Path, default=None, help="folder with junit-*.xml")
    parser.add_argument("--out", type=Path, default=DOCS / "TEST-REPORT.md")
    parser.add_argument("--check", action="store_true", help="only check the mapping")
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 if any requirement fails (CI uses this)")
    args = parser.parse_args(argv)

    reqs, evidence, manual = load_inputs()
    problems = check(reqs, evidence, manual)
    if problems:
        print("The test report mapping is out of date:", *problems, sep="\n  ")
        return 1
    if args.check:
        print(f"Mapping OK: {len(reqs['requirements'])} requirements, every named test and "
              "manual check exists.")
        return 0
    junit = read_junit(args.junit)
    report = build(reqs, evidence, manual, junit, suite_totals(args.junit), bool(junit))
    args.out.write_text(report)
    summary = report.split("\n\n")[2]
    print(summary)
    print(f"Written to {args.out}")
    failed = [rid for rid in evidence if f"### {rid}: {FAIL}" in report]
    if args.strict and failed:
        print("Failing requirements:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
