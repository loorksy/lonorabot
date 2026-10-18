# Global Model Context Budgeting

The existing GlobalModelRouter admits each actual provider attempt separately. This includes normal Agent turns and background compaction. Configuration is global, never per Agent, Routine, or Skill.

## Preparation

After installing Python dependencies, run:

```bash
.venv/bin/python scripts/cache_model_tokenizers.py
```

The setup script, CI, and both Docker build definitions include this step. It downloads tiktoken's pinned, hash-verified encoding data during setup/build. Runtime admission uses a verified local cache, with no tokenizer/image download during a request. A missing/corrupt cache uses a conservative UTF-8 fallback and may reject requests that would fit with a tokenizer. Prepare the cache before serving traffic.

`TIKTOKEN_CACHE_DIR` may select a readable cache location. Container builds populate `/opt/lonora-tokenizers` and make it readable by the non-root service user. No credentials are stored in this cache.

## Global API

Authenticated, CSRF-protected owner settings:

- `GET /api/settings/models/context`
- `PUT /api/settings/models/context`

Default policy:

```json
{
  "maximum_input_tokens": 64000,
  "output_tokens": 4096,
  "safety_tokens": 1024,
  "image_tokens": 8192
}
```

These are admission-policy values, not claims about a model's capacity. A catalog-provided context window lowers the admitted input limit after output reservation and safety headroom. Catalog-provided maximum output lowers the output request. Without a model window, diagnostics explicitly report unknown capacity. The existing 120000-character cap remains an additional guard.

## Behavior and limitations

- Text uses the mapped local OpenAI encoding where supported. Other models use a labeled cached tokenizer proxy with a 20% margin; unavailable encoding data uses UTF-8 bytes. Provider framing and images remain estimates.
- Schemas and framing consume the input budget. Images use the configured allowance; this is not an exact per-provider visual-token calculation or verified upper bound for arbitrary images.
- Preserve mandatory system context, the latest user instruction, and complete latest tool exchanges. Reduce oversized result bodies only in the working copy, retaining existing effect identity fields. Unrepresentable mandatory context fails with `context_limit_exceeded` before provider execution.
- Every fallback rebuilds from the original working messages using its own model window. It does not reuse a context sized only for the primary model, change authority, or replay tools.
- All five provider adapters receive the output reservation for ordinary and streamed requests. Global policy and available catalog metadata must still match the selected provider/model's real supported limits.
- Existing usage rows retain `context_budget` diagnostics: estimator, declared capacity source, estimated input/schema/image allowances, reserved output, message counts, and actual usage when reported. These are separate from billed usage and contain no prompt, tool arguments, image bytes, or credentials. Missing actual usage is represented as unknown in these diagnostics.
- Numerical latency/load guarantees, real-provider calibration, advanced image accounting, and selective tool/schema loading are not established by this first integration.

No database migration or checkpoint-shape change is required. Rollback restores previous code; it must not replay external effects. These changes have local/scripted acceptance, not production deployment acceptance.
