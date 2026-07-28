# Cursor v3.0 Execution Playbook

## Critical prompt tips

1. **Context is king**
   - Use focused context such as `@folder l1_rules` before requesting changes.
   - Avoid dumping the entire codebase into a prompt.
2. **Test-driven delivery**
   - Add: "Write pytest for this. Target 90%+ coverage."
   - Banking audit flows should always ship with verifiable tests.
3. **GPU optimization**
   - Add: "Optimize for 4x A100 with vLLM, tensor parallelism, and batching."
4. **RBI logging**
   - Add: "Use structured JSON logging with `txn_id`, `timestamp`, `model_version`."

## 12-step implementation plan

1. Build L1 + data connectors (CBS CSV reader + initial RBI rules)
2. Expand L1 rules and quality checks
3. Build L2 LLM + PDF reader
4. Fine-tune LLM on synthetic/anonymized transaction narratives
5. Build L3 causal pipeline with DoWhy
6. Add graph intelligence on NetworkX
7. Build L4 LangGraph agent + core tools
8. Expand Layer-4 toolset and policy feedback loops
9. Add fraud simulator + RL integration
10. Harden simulator outputs and adversarial scenarios
11. Build dashboard + immutable audit trail
12. Add federated simulation + RBI scenario testing

## Banking gotchas

- Never use real customer data in prompts; generate anonymized samples first.
- For uncertain L2 outputs, return `need_more_data: true` instead of guessing.
- Commit after each layer milestone and tag major checkpoints.
- Cache Z3 proofs and re-prove only when relevant features change.
