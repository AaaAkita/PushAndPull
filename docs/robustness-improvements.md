# Robustness Improvements Plan

This document tracks targeted robustness fixes that do **not** change the overall architecture.

## Constraints
- Excel is written after every row by design (do not batch).
- No new abstractions or registries.
- Keep changes local to the method or step where the bug occurs.

---

## TODO

### 1. `InputTextStep` — Guard against readonly/disabled inputs

**File:** `core/steps/interaction.py`

Before calling `page.fill()`, check the element's `readonly` and `disabled` properties via `element_handle.evaluate()`. If either is true, log an explicit error and return `False` immediately.

```python
handle = page.query_selector(selector)
if handle:
    is_editable = handle.evaluate("el => !el.readOnly && !el.disabled")
    if not is_editable:
        self.log("输入失败: 目标元素为只读或禁用状态", "ERROR")
        return False
```

---

### 2. `UploadFileStep` — Normalize and strip file paths

**File:** `core/steps/interaction.py`

After resolving the file path:
1. `.strip()` whitespace.
2. `os.path.normpath()` to fix mixed slashes.
3. If path is already absolute, do not prepend a base directory.
4. Verify `os.path.exists(file_path)` before attempting upload and log a clear error if missing.

---

### 3. `DropdownSelectStep` — Safer partial matching

**File:** `core/steps/interaction.py`

Current partial match uses `part in text`, which causes false positives when a parent option contains the child text.

Improvement:
- Keep exact match as highest priority.
- For partial fallback, prefer options where the query is at the **start** of the text (`text.startswith(part)`).
- Only fall back to substring match if no start-match is found.
- Log clearly which strategy was used.

---

### 4. Excel Write — Retry with fallback on Permission Denied

**File:** `core/engine.py`

At the row-result write location:
1. Wrap `df.to_excel()` in a retry loop (3 attempts, 1s sleep).
2. If all retries fail, log a prominent error: `Excel写入失败（文件可能被占用），第X行结果未持久化`.
3. Optionally write the same result to a timestamped backup `.xlsx` in a `backup/` directory so the user can recover results later.

This preserves the per-row-write behavior while reducing the impact of transient locks.

---

### 5. General — Trailing space in variable values

**File:** `core/utils.py`

`replace_variables()` returns raw cell values. Some Excel cells contain trailing spaces that break file lookups.

Improvement: Strip leading/trailing whitespace from replacement values when the surrounding context is a file path. Since we can't always know context, a safer approach is to strip in the upload step itself (covered in #2).

---

## Verification Checklist

- [ ] Run a flow with a readonly input step — expect immediate error, not 30s timeout.
- [ ] Run a flow with an Excel cell containing a trailing space in the file path — expect successful upload.
- [ ] Run a flow with a dropdown where parent text contains child text — expect correct child selection.
- [ ] Open the Excel file in Excel while a flow runs — expect retry messages in logs, execution continues.
