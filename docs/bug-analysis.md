# Bug Analysis Report

> Generated from runtime log review and code inspection.

## Design Constraint (Intentional)

**Excel is written after every row on purpose.** This is a deliberate design decision to ensure progress is not lost if the process is interrupted mid-run. Do not change this to batch writes.

---

## 1. Readonly Input Fill Timeout

**Symptom:** `Page.fill: Timeout 30000ms exceeded. element is not editable`

**Root Cause:** `InputTextStep.execute()` calls `page.fill()` directly without checking if the target element is `readonly` or `disabled`. Many ElementUI components render `<input readonly>` and require clicking a dropdown to set the value.

**Location:** `core/steps/interaction.py:51`

**Fix:** Detect readonly/disabled state before attempting fill and log a clear error immediately instead of waiting 30s.

---

## 2. File Path Double-Concatenation

**Symptom:** `WinError 123: 'E:\...\视频\E:\...\视频\...'`

**Root Cause:** When `inputType == 'excel'`, the raw cell value may already be an absolute path. The code (or user config) sometimes prepends a base directory again. Also, trailing spaces in filenames (`...小满 .png`) cause `WinError 2`.

**Location:** `core/steps/interaction.py` (UploadFileStep, InputTextStep), `core/utils.py`

**Fix:**
- Strip whitespace from file paths before use.
- In upload steps, if the resolved path is already absolute, do not prepend another directory.

---

## 3. Dropdown Partial Match Ambiguity

**Symptom:** `Found Partial Match` selects the wrong item, e.g. "艾迪普传媒新闻前沿工作室" matches for query "艾迪普传媒".

**Root Cause:** `DropdownSelectStep` falls back to substring match (`part in text`) when exact match fails. In hierarchical dropdowns, a parent item often contains the child's text as a substring.

**Location:** `core/steps/interaction.py:209-216`

**Fix:** Improve partial match scoring or restrict partial match to child-level options only. Prefer exact matches and log clearly when falling back.

---

## 4. Excel Permission Denied

**Symptom:** `[Errno 13] Permission denied` on every row when Excel file is open in Microsoft Excel.

**Root Cause:** Windows file locking prevents `pandas.to_excel()` from overwriting an open file. With per-row writes, this becomes a high-frequency failure.

**Location:** `core/engine.py:611`

**Fix (within constraint):** Do not batch writes. Instead:
- Retry the write with exponential backoff (e.g. 3 retries, 1s delay).
- If all retries fail, log the failure prominently and continue execution so the user knows results were not persisted.
- Consider writing to a secondary timestamped backup file as a fallback.

---

## 5. Upload Step Path Normalization Missing

**Symptom:** File not found errors for paths with mixed slashes or trailing spaces.

**Root Cause:** `UploadFileStep` does not normalize or strip the resolved file path before passing to Playwright.

**Location:** `core/steps/interaction.py:107`

**Fix:** Apply `os.path.normpath()` and `.strip()` to file paths.

---

## Summary Table

| # | Bug | Severity | File | Fix Complexity |
|---|-----|----------|------|----------------|
| 1 | Readonly fill timeout | Medium | `core/steps/interaction.py` | Low |
| 2 | Path double-concatenation | Medium | `core/steps/interaction.py` | Low |
| 3 | Dropdown partial match ambiguity | Medium | `core/steps/interaction.py` | Medium |
| 4 | Excel permission denied | High | `core/engine.py` | Low |
| 5 | Path normalization missing | Low | `core/steps/interaction.py` | Low |
