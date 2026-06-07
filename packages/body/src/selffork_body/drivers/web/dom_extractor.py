"""DOM tree extractor for the Playwright web driver (M5 — ADR-005 §M5-C1).

Walks the live DOM via ``page.evaluate`` and returns a flat list of
interactive elements with bounding boxes + accessibility hints. Inspired by
browser-use's ``buildDomTree.js`` pattern, reimplemented in MIT-friendly form
without copying source.

Output rows::

    {
        "index": <int>,
        "tag": "button" | "a" | "input" | ...,
        "text": "<element text, trimmed to 100 chars>",
        "attrs": {
            "id": "...", "class": "...", "role": "...",
            "aria-label": "...", "name": "...", "type": "...",
        },
        "bbox": [x, y, w, h],
        "visible": true,
    }
"""

from __future__ import annotations

from typing import Any

__all__ = ["DOM_TREE_JS", "extract_dom_tree", "summarise_dom_tree"]


DOM_TREE_JS = r"""
(() => {
    const interactiveTags = new Set([
        'a', 'button', 'input', 'select', 'textarea', 'option', 'label',
        'summary', 'video', 'audio',
    ]);
    const elements = [];
    let index = 0;

    function isVisible(node) {
        if (!(node instanceof Element)) return false;
        const style = window.getComputedStyle(node);
        if (style.display === 'none' || style.visibility === 'hidden') return false;
        const rect = node.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }

    function isInteractive(node) {
        const tag = node.tagName ? node.tagName.toLowerCase() : '';
        if (interactiveTags.has(tag)) return true;
        if (typeof node.onclick === 'function') return true;
        const role = node.getAttribute && node.getAttribute('role');
        if (role && /(button|link|menuitem|tab|switch|checkbox|radio|combobox)/i.test(role)) return true;
        if (node.hasAttribute && node.hasAttribute('contenteditable')) return true;
        return false;
    }

    function walk(node) {
        if (!(node instanceof Element)) return;
        if (isInteractive(node) && isVisible(node)) {
            const rect = node.getBoundingClientRect();
            elements.push({
                index: index++,
                tag: node.tagName.toLowerCase(),
                text: (node.innerText || node.value || '').slice(0, 100),
                attrs: {
                    id: node.id || '',
                    class: node.className && typeof node.className === 'string' ? node.className.slice(0, 80) : '',
                    role: node.getAttribute('role') || '',
                    'aria-label': node.getAttribute('aria-label') || '',
                    name: node.getAttribute('name') || '',
                    type: node.getAttribute('type') || '',
                },
                bbox: [
                    Math.round(rect.x),
                    Math.round(rect.y),
                    Math.round(rect.width),
                    Math.round(rect.height),
                ],
                visible: true,
            });
        }
        for (const child of node.children || []) {
            walk(child);
        }
    }
    walk(document.body || document.documentElement);
    return elements;
})()
"""


async def extract_dom_tree(page: Any) -> list[dict[str, Any]]:
    """Run :data:`DOM_TREE_JS` against ``page`` and return the row list."""
    result: list[dict[str, Any]] = await page.evaluate(DOM_TREE_JS)
    return result


def summarise_dom_tree(rows: list[dict[str, Any]], *, limit: int = 60) -> str:
    """Render a compact, prompt-friendly summary of DOM rows.

    One line per element: ``[idx] <tag> "text" (id/class/role/aria) bbox=[x,y,w,h]``.
    Truncates to ``limit`` rows for prompt budget.
    """
    out: list[str] = []
    for row in rows[:limit]:
        attrs = row.get("attrs") or {}
        attr_bits = []
        for key in ("id", "name", "role", "aria-label"):
            v = attrs.get(key)
            if v:
                attr_bits.append(f"{key}={v}")
        attr_str = " ".join(attr_bits)
        bbox = row.get("bbox") or []
        text = (row.get("text") or "").replace("\n", " ").strip()
        out.append(f'[{row["index"]}] <{row["tag"]}> "{text}" {attr_str} bbox={bbox}')
    if len(rows) > limit:
        out.append(f"... ({len(rows) - limit} more rows truncated)")
    return "\n".join(out)
