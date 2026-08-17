# PhantomOS Recipes

Recipes are TOML files under `~/.phantom/recipes`.

PhantomOS uses a real TOML serializer when persisting recipes, so quotes, newlines, arrays, and other user values are encoded safely instead of being hand-built with Python `repr()`.

## Recipe skeleton

```toml
[recipe]
name = "my_recipe"
description = "Do a small workflow"
enabled = true

[trigger]
type = "schedule"
time = "09:00"
days = ["mon", "tue", "wed", "thu", "fri"]

[[steps]]
type = "app_activate"
app = "Safari"
delay_after = 0.5

[[steps]]
type = "url_open"
url = "https://github.com"
on_error = "abort"
```

## Built-in recipes

| Recipe | v0.1 trigger | Description |
| --- | --- | --- |
| `morning_opener` | Schedule – 09:00, Mon-Fri | Opens Safari/Gmail, Slack, and Code. |
| `error_auto_search` | Content match in Terminal | Copies the current error and searches the copied value. |
| `focus_mode` | Manual | Closes Slack and Discord, then shows a notification. |

Run manually:

```bash
phantom recipes list
phantom recipes run focus_mode
```

Manual execution uses an interactive approval callback. Background daemon execution remains deny-by-default whenever the configured trust mode requires approval and no approval callback exists.

## Daemon trigger sources in v0.1

The daemon currently emits:

- `app_switch`
- `content_match`
- `schedule`
- `idle`

The trigger engine contains evaluators for `hotkey` and `pattern_match`, but v0.1 does not advertise native daemon event sources for those trigger types.

## Supported step types

- `type_text`
- `press_key`
- `clipboard_copy`
- `clipboard_paste`
- `clipboard_set`
- `app_activate`
- `url_open`
- `file_open`
- `run_command`
- `wait`
- `notification`

## Conditions

Recipe conditions use a restricted AST evaluator. Supported expressions include constants, names, boolean operations, `not`, and basic comparisons.

Condition parse/evaluation errors **fail closed**: the recipe returns a failure rather than executing the guarded step.

## Clipboard variables

`{clipboard}` starts with the clipboard value observed at recipe start. After a successful `clipboard_copy` or `clipboard_set`, the runner updates that variable before later steps are interpolated.

This is what allows `error_auto_search` to search the value copied by its first step rather than stale pre-recipe clipboard state.
