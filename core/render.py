def clean_tags(text):
    """Normalize + ordered-dedup a comma-separated tag string (lowercase)."""
    if not text:
        return ""
    tags = [t.strip().lower() for t in text.split(",")]
    tags = list(filter(None, tags))
    return ", ".join(list(dict.fromkeys(tags)))


def render_positive(state, schema, prompt_cfg):
    mode = prompt_cfg.get("render_mode", "tags")
    prefix = prompt_cfg.get("prefix", "") or ""
    suffix = prompt_cfg.get("suffix", "") or ""

    values = []
    for key in schema.renderable_keys:
        v = state.get(key)
        if v is None:
            continue
        v = str(v).strip()
        if v:
            values.append(v)
    body = ", ".join(values)

    if mode == "nl":
        return ", ".join(x for x in (prefix, body, suffix) if x)
    return clean_tags("%s, %s, %s" % (prefix, body, suffix))


def render_negative(state, prompt_cfg):
    neg_base = prompt_cfg.get("negative_base", "") or ""
    hints = state.get("negative_hints")
    hints = str(hints).strip() if hints else ""
    return clean_tags("%s, %s" % (neg_base, hints))
