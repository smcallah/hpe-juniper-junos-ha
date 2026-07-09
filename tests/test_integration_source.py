"""Source-level compatibility checks that do not require Home Assistant installed."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
INTEGRATION = ROOT / "custom_components" / "junos_netconf"


class IntegrationSourceTest(unittest.TestCase):
    """Guard integration metadata and config-flow compatibility."""

    def test_manifest_version_is_current(self) -> None:
        """Expose feature updates to HACS through a new integration version."""
        manifest = json.loads((INTEGRATION / "manifest.json").read_text())
        self.assertEqual(manifest["version"], "0.1.9")

    def test_options_flow_does_not_assign_config_entry(self) -> None:
        """Use the config entry injected by current Home Assistant."""
        tree = ast.parse((INTEGRATION / "config_flow.py").read_text())
        assignments = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            and any(
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
                and target.attr == "config_entry"
                for target in (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
            )
        ]
        self.assertEqual(assignments, [])


if __name__ == "__main__":
    unittest.main()
