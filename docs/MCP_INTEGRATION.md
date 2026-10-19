# MCP integration for Olympus ERP

## Client configuration

Install Olympus ERP in a Python environment, then have your client start `olympus mcp` as a stdio process (replace the paths):

```json
{
  "mcpServers": {
    "olympus-erp": {
      "command": "/full/path/to/.venv/bin/olympus",
      "args": ["mcp", "--workspace", "/full/path/to/your/project"]
    }
  }
}
```

On Windows the command is `C:\\full\\path\\to\\.venv\\Scripts\\olympus.exe`. The server speaks newline-delimited JSON-RPC (initialize, ping, tools/list, tools/call) and negotiates protocol versions 2024-11-05, 2025-03-26 and 2025-06-18. Test it with your client version before depending on it. An optional adapter for the official SDK is `olympus-mcp-sdk` (`pip install "olympus-erp[mcp]"`, 15 tools).

## Tools (26)

- **Hermes:** `list_templates`, `describe_template`, `profile_file`, `suggest_mapping`, `write_spec`, `check`, `build`
- **Mapping table (read-only):** `mapping_table`, `mapping_status`
- **Themis (read-only):** `signoff_status`
- **Planning drafts:** `assess_project`, `draft_erp_roadmap`, `draft_integration_design`, `draft_uat`, `draft_cutover`, `draft_training`, `draft_hypercare`, `model_roi`, `go_live_gate`, `generate_erp_pack`
- **Evidence:** `reconcile_exports`, `uat_status`, `project_summary`
- **Argus (workspace queue):** `incident_list`, `incident_create`, `incident_update`

## Permissions and human-only actions

All file paths are restricted to the workspace, and source paths inside TOML specs are checked too. `write_spec` never overwrites an existing spec. **AI tools cannot confirm mappings, sign off a spec, or record UAT results.** Those happen only in the dashboard or the CLI, by a person. `build` refuses until a human has confirmed the mapping table. `go_live_gate` reads evidence from the files next to the project and never returns GO.

Never point the server at your entire home folder. The trust boundary is the local machine: anything that can write files in the workspace could forge local evidence, so keep the workspace access-restricted.
