"""M6b intentionally narrow review-note command policy.

The planner cannot invent a write. Only an explicit user's leading verb
enters the protected save_review_note path. Parsed text is stored verbatim;
it is never interpreted as code, a policy override or a model prompt.
"""

import re


_PREFIX = re.compile(
    r"^\s*(?:请)?(?:帮我)?\s*"
    r"(?:保存审核备注|保存审查备注|记录审核备注|保存评审备注)"
)
_COMMAND = re.compile(
    r"^\s*(?:请)?(?:帮我)?\s*"
    r"(?:保存审核备注|保存审查备注|记录审核备注|保存评审备注)"
    r"\s*[:：]\s*(?P<note>.*?)\s*$",
    re.DOTALL,
)


def is_review_note_command(query: str) -> bool:
    return bool(_PREFIX.match(query))


def parse_review_note(query: str) -> str:
    matched = _COMMAND.fullmatch(query)
    if matched is None:
        raise ValueError("请使用“保存审核备注：具体内容”的明确格式。")
    note = matched.group("note").strip()
    if not (1 <= len(note) <= 500) or "\x00" in note:
        raise ValueError("审核备注必须包含 1–500 个有效字符。")
    return note
