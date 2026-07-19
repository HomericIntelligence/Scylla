# Thinking Mode Configuration

## Default Configuration

Scylla has thinking mode **DISABLED BY DEFAULT** to optimize for efficiency and cost control.

This is configured in `.claude/settings.json`:

```json
{
  "alwaysThinkingEnabled": false
}
```

## Why Thinking Mode is Disabled

Per the AGENTS.md guidelines, thinking mode should only be used for:

- Designing evaluation protocols and experiment methodology
- Analyzing benchmark results and identifying patterns
- Planning multi-tier comparison studies
- Debugging complex evaluation failures
- Statistical analysis and interpretation

Most tasks in Scylla (metric calculations, test generation, data collection, configuration updates) do NOT require extended thinking and are more efficient without it.

## How to Enable Thinking Mode

### Method 1: Toggle During Session (Tab Key)

Press the **Tab** key during a Claude Code session to enable thinking mode. This toggle is sticky across sessions until you disable it again.

### Method 2: Temporary Enable with `/t` Command

Use the `/t` command to temporarily disable thinking for a single prompt (useful if thinking was previously enabled).

### Method 3: Keywords in Message

Include special keywords in your message to trigger thinking for that specific request:

- `think` - Low thinking level
- `think hard` or `megathink` - Medium thinking level
- `think harder` or `ultrathink` - Maximum thinking level

Example:

```
"Please ultrathink about the statistical significance of these benchmark results."
```

### Method 4: Update Settings File (Permanent Change)

To enable thinking mode by default (NOT recommended for this project), edit `.claude/settings.json`:

```json
{
  "alwaysThinkingEnabled": true
}
```

**WARNING:** This overrides the project default and is NOT recommended unless you have a specific reason.

## Thinking Budget Guidelines

When thinking mode IS enabled (rare cases), follow these budget guidelines from AGENTS.md:

| Task Type | Budget | Examples | Rationale |
|-----------|--------|----------|-----------|
| **Simple** | None | Update config | Mechanical changes |
| **Standard** | 5K-10K | Add test case | Well-defined |
| **Complex** | 10K-20K | Design experiment | Dependencies |
| **Analysis** | 20K-50K | Interpret results | Deep analysis |
| **Research** | 50K+ | New methodology | Novel design |

## Best Practices

1. **Default to NO thinking** - Only enable when explicitly needed
2. **Use keywords** for one-off thinking requests rather than enabling globally
3. **Disable after use** - If you enable thinking with Tab, remember to disable it when done
4. **Document why** - If you need thinking enabled, document the reason in your PR or issue

## Troubleshooting

**Problem:** Thinking mode seems enabled even though settings say disabled
**Solution:** Press Tab key to toggle it off (the toggle is sticky across sessions)

**Problem:** Tab key not working to toggle thinking
**Solution:** Known bug in some versions (`v2.0.67`). Use `/config` command to manually toggle.

## References

- [How to Toggle Thinking in Claude Code](https://claudelog.com/faqs/how-to-toggle-thinking-in-claude-code/)
- [Configuration and Documentation for Thinking Mode Issue](https://github.com/anthropics/claude-code/issues/7668)
- [Per-Command Thinking Mode Configuration Request](https://github.com/anthropics/claude-code/issues/11272)
