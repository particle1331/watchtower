"""Render saved CMS plans without allowing authored HTML or executable links."""

from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.footnote import footnote_plugin


def render_plan_markdown(source: str, section_id: str) -> str:
    parser = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])
    parser.use(dollarmath_plugin, allow_labels=False, allow_space=False, allow_digits=False, double_inline=True)
    parser.use(footnote_plugin)
    return parser.render(source, {"docId": section_id})
