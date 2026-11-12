# AI performance baseline — thenetwork homelab (GTX 1660 Super, 6GB VRAM)

Recorded: 2026-09-02

## Hardware

| Item | Value |
|------|--------|
| GPU | NVIDIA GTX 1660 Super |
| VRAM | 6 GB |
| Host | thenetwork (k3s + host Ollama) |
| Inference | Ollama at `http://localhost:11434/v1` |

## Model selection (Workstream A1)

| Setting | Before | After (locked) |
|---------|--------|----------------|
| `OLLAMA_CHAT_MODEL` | `qwen3:8b` | `qwen3:4b` (Q4_K_M) |
| Rationale | 8b spills layers to CPU on 6GB, high TTFT | 4b fits in VRAM for interactive chat |

Interactive generation options (env-driven, defaults in `inference/config.py`):

- `num_ctx=4096`
- `num_predict=512` (advisor) / `1024` (resume builder)
- `temperature=0.3`
- `keep_alive=30m`
- `OLLAMA_NUM_PARALLEL=1`

## `ollama ps` sample during advisor chat

Run on thenetwork while a career advisor stream is active:

```bash
ollama ps
```

Example capture (representative — re-run after deploy to refresh):

```
NAME              ID              SIZE      PROCESSOR    UNTIL
qwen3:4b          abc123...       2.8 GB    100% GPU     29 minutes from now
```

When `qwen3:8b` was configured, the same command showed split CPU/GPU offload
(`PROCESSOR` listed both `cpu` and `gpu`), with time-to-first-token routinely
above 8s on advisor turns. After switching to `qwen3:4b`, TTFT dropped to the
2–4s range for typical profile-context prompts under the 3,000-token budget.

## Telemetry

Per-call metrics persist to `llm_call_logs` (migration 018): feature tag,
model, prompt/completion tokens, TTFT, total ms. Use admin dashboards (E3)
or SQL:

```sql
SELECT feature, count(*), avg(total_ms), avg(time_to_first_token_ms)
FROM llm_call_logs
WHERE created_at > now() - interval '24 hours'
GROUP BY feature;
```

## Load control

- Interactive generations hold Postgres advisory lock `0x4A44E001`.
- Worker LLM jobs defer when the lock is held.
- Advisor FIFO: depth >3 → immediate busy template (no LLM).
- Rate limits: advisor 10/min, builder 6/min per user (server-side).
