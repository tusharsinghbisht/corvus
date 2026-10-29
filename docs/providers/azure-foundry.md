# Azure Foundry adapter

Configuration reference for `src/corvus/providers/azure_foundry.py`. This is one model-provider integration, not part of Corvus's product identity or application stack.

## Private configuration

The CLI adapter reads `~/.config/corvus/azure_foundry.json`. The manual-triage worker uses the same adapter and configuration contract. Example structure only:

```json
{
  "endpoint": "https://YOUR_RESOURCE.openai.azure.com/openai/v1",
  "api_key": "SET_LOCALLY_DO_NOT_COMMIT",
  "model": "DeepSeek-V4-Flash",
  "max_tokens": 4096,
  "timeout_seconds": 120
}
```

Keep the file outside Git, with mode `0600`. The key is excluded from configuration representations. Unknown settings are rejected. Override the path with `--model-config PATH` or `CORVUS_FOUNDRY_CONFIG`; this is separate from the Wazuh connection configuration.

The `model` value is an exact deployment identifier. The implementation currently defaults to the deployment requested for the lab, `DeepSeek-V4-Flash`; it does not silently substitute or fall back to another model. Catalog availability does not establish that a deployment is callable.

## Worker deployment

Install the same configuration outside the VPS checkout at `~ubuntu/.config/corvus/app/analyst.json`, owned by UID/GID `10001:10001`, mode `0600`. `compose.analyst.yaml` mounts it read-only **only in the worker** and sets `CORVUS_FOUNDRY_CONFIG=/run/corvus/analyst.json`. Include that override on every Compose update; see [deployment](../deployment.md). Never mount it in API/web or expose it through frontend environment variables.

The requested deployment remains `DeepSeek-V4-Flash`. Configuration loading alone makes no request. Do not probe it with real evidence or run an analysis without separate explicit per-bundle approval. Transport availability is not yet proven by a successful real-evidence request.

## Transport constraints

- HTTPS `/openai/v1` endpoints under `.openai.azure.com` or `.services.ai.azure.com`, port 443.
- No URL credentials, query strings, fragments, redirects, or automatic retries.
- Standard system TLS trust and hostname verification. The indexer's legacy-CA accommodation does not apply.
- One non-streaming JSON completion request. Incomplete completions and tool calls fail explicitly.
- Input limit 1 MiB; provider response limit 2 MiB. Oversize input is rejected rather than silently truncated.
- Generated-token range 256–8,192; socket timeout 1–180 seconds. Defaults are shown above.
- Provider failures are operational errors, not fabricated investigation reports.

## Provider changes

The Analyst depends on the `AnalystModel` interface in `src/corvus/providers/__init__.py`, not this HTTP client. Another adapter can implement `complete(messages)` and return a `ModelReply`. Provider-specific configuration and transport belong in that adapter; evidence collection, report contracts, and application features should not depend on its brand or model name.

Today, the CLI and manual-triage worker's provider wiring select this implementation. Arbitrary-provider selection in the dashboard is not implemented. Changing to another provider requires implementing/selecting its adapter, not merely putting an unrelated endpoint in this configuration. Changing providers must not introduce hidden fallback, bypass external-processing approval, or drop run provenance.

Saved analysis artifacts retain the actual served model, token usage, prompt version, and timing. Those fields identify how a particular report was produced; they are not platform features or marketing claims. See [report workflow](../investigation-reports.md) for the provider-independent contract and safety limits.
