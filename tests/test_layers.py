"""Lower layers never import higher ones: the layers and modules ARCHITECTURE.md gives."""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).parents[1] / "skill" / "scripts" / "fm27_editor"

# Each layer and the layers right below it, which it may use, and through them theirs.
USES = {
    "command line": ["requests"],
    "requests": ["nation rules"],
    "nation rules": ["award history"],
    "award history": ["edits"],
    "edits": ["definitions", "base database", "editor file", "json text"],
    "definitions": ["container"],
    "base database": ["database tables"],
    "database tables": ["container"],
    "editor file": ["change list"],
    "change list": ["container"],
    "container": ["binary"],
    "json text": ["binary"],
    "binary": [],
}

MODULES = {
    "command line": ["command_line"],
    "requests": [
        *("request", "plan", "planned", "preview", "explain", "words"),
        *("rule_plan", "rule_words", "history_plan", "history_words"),
    ],
    "nation rules": ["nation_rules", "rule_changes", "rule_shapes"],
    "award history": ["award_history"],
    "edits": [
        *("record_kinds", "record_fields", "record_changes", "setting_changes", "list_changes"),
        *("change_reading", "potential", "new_file", "person_lists", "person_codes"),
    ],
    "definitions": ["definition_files", "field_definitions", "rule_definitions"],
    "base database": [
        *("base_database", "people", "person_fields", "person_names", "playing_history"),
        *("people_lookup", "places", "place_lookup", "awards", "award_lookup"),
        *("name_tables", "named_records", "name_lookup"),
    ],
    "database tables": ["dat_tables"],
    "editor file": ["editor_file", "details"],
    "change list": ["change_list"],
    "container": ["container"],
    "json text": ["json_text"],
    "binary": ["binary"],
}

LAYER_OF = {module: layer for layer, modules in MODULES.items() for module in modules}


def _below(layer: str) -> set[str]:
    return {layer}.union(*(_below(lower) for lower in USES[layer]))


def _imported(source: str) -> set[str]:
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module == "fm27_editor":
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("fm27_editor."):
            imported.add(node.module.removeprefix("fm27_editor."))
        elif isinstance(node, ast.Import):
            imported.update(
                alias.name.removeprefix("fm27_editor.")
                for alias in node.names
                if alias.name.startswith("fm27_editor.")
            )
    return imported


def _above(layer: str, source: str) -> dict[str, str]:
    """The modules that the source imports from layers above `layer`, with their layers."""
    allowed = _below(layer)
    return {name: LAYER_OF[name] for name in _imported(source) if LAYER_OF[name] not in allowed}


def test_every_module_has_a_layer():
    modules = {path.stem for path in PACKAGE.glob("*.py")} - {"__init__"}

    assert modules == set(LAYER_OF)


@pytest.mark.parametrize("module", sorted(LAYER_OF))
def test_a_module_imports_only_its_layer_and_those_below(module):
    source = (PACKAGE / f"{module}.py").read_text(encoding="utf-8")

    assert not _above(LAYER_OF[module], source)


@pytest.mark.parametrize(
    "source",
    [
        "from fm27_editor.plan import Plan",
        "from fm27_editor import plan",
        "import fm27_editor.plan",
    ],
)
def test_an_import_of_a_higher_layer_is_found(source):
    assert _above("edits", source) == {"plan": "requests"}


def test_a_sibling_layer_is_not_below():
    assert _above("base database", "from fm27_editor.change_list import ChangeList") == {
        "change_list": "change list"
    }
