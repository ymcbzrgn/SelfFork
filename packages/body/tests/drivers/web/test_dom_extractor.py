"""DOM extractor JS contract + summarise_dom_tree formatter."""

from __future__ import annotations

from selffork_body.drivers.web import DOM_TREE_JS, summarise_dom_tree


def test_dom_tree_js_walks_function_present() -> None:
    assert "interactiveTags" in DOM_TREE_JS
    assert "getBoundingClientRect" in DOM_TREE_JS
    assert "isVisible" in DOM_TREE_JS


def test_summarise_dom_tree_formats_each_row() -> None:
    rows = [
        {
            "index": 0,
            "tag": "button",
            "text": "Submit",
            "attrs": {
                "id": "submit-btn",
                "name": "",
                "role": "button",
                "aria-label": "Submit form",
            },
            "bbox": [10, 20, 100, 40],
            "visible": True,
        },
        {
            "index": 1,
            "tag": "input",
            "text": "",
            "attrs": {
                "id": "email",
                "name": "email",
                "role": "",
                "aria-label": "",
            },
            "bbox": [10, 80, 200, 30],
            "visible": True,
        },
    ]
    out = summarise_dom_tree(rows)
    lines = out.splitlines()
    assert lines[0].startswith("[0] <button>")
    assert "id=submit-btn" in lines[0]
    assert "role=button" in lines[0]
    assert "Submit" in lines[0]
    assert "[1] <input>" in lines[1]


def test_summarise_dom_tree_truncates_at_limit() -> None:
    rows = [
        {
            "index": i,
            "tag": "div",
            "text": f"row{i}",
            "attrs": {"id": "", "name": "", "role": "", "aria-label": ""},
            "bbox": [0, 0, 0, 0],
            "visible": True,
        }
        for i in range(20)
    ]
    out = summarise_dom_tree(rows, limit=5)
    lines = out.splitlines()
    assert lines[-1].startswith("... (15 more rows truncated)")
