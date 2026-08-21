# iFaceoff repository guidance

## Documentation is part of every project change

`docs/ifaceoff-vault/` is the canonical project archive and interview-review
book. It contains exactly 15 flat Markdown chapters: one overview, six
implementation volumes, the interview question book, and seven appendices.
Do not recreate module MOCs, generated status stubs, Bases, Canvas, or nested
topic directories.

Any change to application code, models, migrations, APIs, UI routes,
infrastructure, configuration, tests, security controls, or operational
behaviour must update the book in the same change:

1. Use `scripts/doc_sync_map.json` to find the canonical volume and the exact
   `##` section for every affected source domain. The substantive diff must
   fall inside that section; changing an unrelated paragraph does not count.
2. Refresh the chapter's `updated`, `last_verified`, and `verified_commit`
   properties when its evidence changes. Keep implementation claims labelled
   as implemented, partial, legacy-compatible, target-design, or
   pending-verification.
3. Append the change and its verification evidence to
   `docs/ifaceoff-vault/12-项目变更日志.md`.
4. Update API, data, security, testing, failure, recovery, screenshots, or
   runbook passages affected by the same change. A generated fact index never
   substitutes for the explanatory chapter.
5. If a source change genuinely has no reader-visible documentation impact,
   record the exact scope, reason, and reviewer in the changelog as an
   exemption. Do not use a placeholder exemption.

Explanatory prose is hand-maintained. `scripts/build_project_facts.py` may only
generate `09-代码-API-数据事实索引.md`; no generator may overwrite the six
volumes or interview answers. Current code and verified runtime evidence take
precedence over historical notes.

Mermaid, UML, and other architecture diagrams must use Chinese for visible
labels. When an English technical term is necessary, keep it together with a
Chinese explanation, for example `Publisher Confirm（发布确认）`; internal node
identifiers may remain ASCII because they are not rendered.

Run before handoff:

```powershell
python scripts/build_project_facts.py --check
python scripts/check_docs_sync.py --check-vault
python scripts/build_docs_inventory.py --check
python -m unittest discover -s scripts/tests -v
```

For a staged local change also run:

```powershell
python scripts/check_docs_sync.py --staged
```

Never copy credentials, tokens, database dumps, production user data, real
resumes, private chat, or unredacted prompts into the Vault. Screenshots must
come from the current application with synthetic data and be registered in
`13-截图证据清单.md`; incomplete pages stay labelled `current-partial`.
