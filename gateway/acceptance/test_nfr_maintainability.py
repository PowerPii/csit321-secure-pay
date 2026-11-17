"""URS 4.4.9 Maintainability: NFR-MNT-02, card data is reachable only through the vault.

Outside apps/vault, application code may use only the vault's public interface:
apps.vault.service (names without a leading underscore), apps.vault.fingerprint and
apps.vault.demo_cards. It may not import the vault's model or router, and may not query the
vault database itself. Tests are exempt: they inspect the vault on purpose.

The second half of the criterion, that the gateway's database role is refused when it reads
the card table, depends on the server's roles; see docs/test-report/MANUAL-TESTS.md.
"""
import ast
import re
from pathlib import Path

GATEWAY = Path(__file__).resolve().parents[1]
PUBLIC_MODULES = {"apps.vault.service", "apps.vault.fingerprint", "apps.vault.demo_cards"}
VAULT_QUERY = re.compile(r"""using\(\s*["']vault["']\s*\)|vault_storedcard|vault\.vault_""")


def _application_files():
    for folder in ("apps", "config"):
        for path in sorted((GATEWAY / folder).rglob("*.py")):
            rel = path.relative_to(GATEWAY).as_posix()
            if rel.startswith("apps/vault/") or "/migrations/" in rel:
                continue
            if path.name.startswith("test_") or path.name in ("tests.py", "conftest.py"):
                continue
            yield rel, path


def _violations(rel, source):
    found = []
    tree = ast.parse(source)
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            module = node.module
            for name in node.names:
                full = f"{module}.{name.name}"
                if module == "apps.vault":
                    target = full
                    aliases[name.asname or name.name] = target
                else:
                    target = module
                if target.startswith("apps.vault") and target not in PUBLIC_MODULES:
                    found.append(f"{rel}:{node.lineno} imports {full}")
                if module in PUBLIC_MODULES and name.name.startswith("_"):
                    found.append(f"{rel}:{node.lineno} imports private {full}")
        elif isinstance(node, ast.Import):
            for name in node.names:
                if name.name.startswith("apps.vault") and name.name not in PUBLIC_MODULES:
                    found.append(f"{rel}:{node.lineno} imports {name.name}")
        elif (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
              and aliases.get(node.value.id) in PUBLIC_MODULES and node.attr.startswith("_")):
            found.append(f"{rel}:{node.lineno} uses private {node.value.id}.{node.attr}")
    for n, line in enumerate(source.splitlines(), start=1):
        if VAULT_QUERY.search(line):
            found.append(f"{rel}:{n} queries the vault database directly")
    return found


def test_nfr_mnt_02_only_the_vault_touches_card_data():
    files = list(_application_files())
    assert len(files) > 50  # the scan really ran over the application
    problems = [p for rel, path in files for p in _violations(rel, path.read_text())]
    assert problems == []


def test_nfr_mnt_02_the_boundary_check_catches_a_violation():
    bad = (
        "from apps.vault.models import StoredCard\n"
        "from apps.vault import service as vault\n"
        "vault._decrypt(b'', 't')\n"
        "StoredCard.objects.using('vault').count()\n"
    )
    problems = _violations("apps/example.py", bad)
    assert len(problems) == 3, problems
