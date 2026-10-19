"""Optional official MCP Python SDK v2 adapter (stdlib validator remains unchanged).

Install via: pip install -e '.[mcp]'
Run: olympus-mcp-sdk --workspace .
Requires host compatibility and integration testing; not a production server.
"""
from __future__ import annotations
from pathlib import Path
from .mcp import _dispatch as _raw_dispatch


def _dispatch(name, args, root):
    try:
        return _raw_dispatch(name, args, root)
    except (KeyError, ValueError, TypeError, OSError) as exc:
        from mcp.server.mcpserver.exceptions import ToolError
        raise ToolError(str(exc)) from exc


def create_server(workspace):
    try:
        from mcp.server import MCPServer
    except ImportError as exc:
        raise RuntimeError('Official MCP SDK missing. Install with pip install -e ".[mcp]"') from exc
    root = Path(workspace).resolve()
    if not root.is_dir(): raise ValueError('Workspace not found')
    server = MCPServer('Olympus ERP')

    @server.tool()
    def list_templates() -> list[str]:
        """List illustrative ERP migration templates."""
        return _dispatch('list_templates', {}, root)

    @server.tool()
    def profile_file(path: str, sheet: str = '') -> dict:
        """Read CSV/XLSX file headers and null counts within the workspace."""
        return _dispatch('profile_file', {'path': path, 'sheet': sheet or None}, root)

    @server.tool()
    def suggest_mapping(path: str, template: str) -> dict:
        """Suggest mappings for human review; do not certify a vendor format."""
        return _dispatch('suggest_mapping', {'path': path, 'template': template}, root)

    @server.tool()
    def check(spec: str) -> dict:
        """Run deterministic migration scan and report findings, without writing cleaned files."""
        return _dispatch('check', {'spec': spec}, root)

    @server.tool()
    def build(spec: str, output: str, require_signoff: bool = True) -> dict:
        """Build import review files and local report, requiring current human mapping-spec approval by default."""
        return _dispatch('build', {'spec': spec, 'output': output, 'require_signoff': require_signoff, 'pdf': True}, root)

    @server.tool()
    def assess_project(project: str) -> dict:
        """Identify ERP discovery gaps, risks, and questions without inventing business facts."""
        return _dispatch('assess_project', {'project': project}, root)

    @server.tool()
    def draft_erp_roadmap(project: str) -> str:
        """Create a preliminary human-reviewable discovery and implementation roadmap."""
        return _dispatch('draft_erp_roadmap', {'project': project}, root)

    @server.tool()
    def draft_uat(project: str) -> tuple[str, list]:
        """Produce UAT scenarios, not executed or approved test results."""
        return _dispatch('draft_uat', {'project': project}, root)

    @server.tool()
    def draft_cutover(project: str) -> str:
        """Produce a draft cutover plan; production authorization remains external."""
        return _dispatch('draft_cutover', {'project': project}, root)

    @server.tool()
    def generate_erp_pack(project: str, output: str) -> dict:
        """Write consultant draft deliverables in a new workspace directory only."""
        return _dispatch('generate_erp_pack', {'project': project, 'output': output}, root)

    @server.tool()
    def reconcile_exports(source: str, target: str, source_key: str, target_key: str,
                          source_amount: str, target_amount: str, tolerance: str = '0.01') -> dict:
        """Read-only Poseidon comparison of source and trial-load keys, row counts and amounts."""
        return _dispatch('reconcile_exports', locals().copy(), root)

    @server.tool()
    def uat_status(project: str) -> dict:
        """Clio: show claimed UAT results and any stale project/evidence fingerprints."""
        return _dispatch('uat_status', {'project': project}, root)

    @server.tool()
    def incident_list() -> dict:
        """Argus: list manual incidents from the local workspace."""
        return _dispatch('incident_list', {}, root)

    @server.tool()
    def incident_create(title: str, severity: str, owner: str) -> dict:
        """Create a manually reported local ERP support issue. Does not call external systems."""
        return _dispatch('incident_create', {'title':title, 'severity':severity, 'owner':owner}, root)

    @server.tool()
    def go_live_gate(project: str) -> dict:
        """Report missing independent evidence; never authorize a production go-live."""
        return _dispatch('go_live_gate', {'project':project}, root)

    return server


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description='Olympus ERP official MCP SDK v2 local stdio adapter')
    p.add_argument('--workspace', default='.')
    args=p.parse_args(argv)
    create_server(args.workspace).run()


if __name__ == '__main__': main()
