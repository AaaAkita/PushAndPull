
def resolve_selector(selector):
    if not selector:
        return selector
    # Don't touch if it looks like a refined Playwright selector (e.g. chaining with >> or starting with internal engine prefix)
    if " >> " in selector or selector.startswith("text=") or selector.startswith("css=") or selector.startswith("xpath=") or selector.startswith("id="):
         return selector
    
    # Original logic for plain paths
    if selector.startswith('/') or selector.startswith('('):
        # Careful: (text="foo") >> ... starts with ( but shouldn't be xpath.
        # But we handled >> above. 
        # If it's just (something), and not chained, it's likely XPath group.
        return f"xpath={selector}"
    return selector

def replace_variables(text, row_data):
    """
    Replaces {ColumnName} in text with values from row_data.
    """
    if not text or not isinstance(text, str):
        return text
    
    # Simple replacement for {Column}
    for col, val in row_data.items():
        placeholder = f"{{{col}}}"
        if placeholder in text:
            val_str = str(val) if val is not None else ""
            text = text.replace(placeholder, val_str)
    return text
