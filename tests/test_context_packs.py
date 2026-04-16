from crewops_core.lib.context_packs import build_context_pack, prepend_context_pack


def test_build_context_pack_has_expected_shape():
    pack = build_context_pack("Fix the summary output", "software")
    assert pack["task_ref"].startswith("software-")
    assert pack["task_type"] in {"implementation", "research", "content", "general"}
    assert pack["active_goal_summary"]
    assert "memory_backend" in pack
    assert "memory_refs" in pack


def test_prepend_context_pack_wraps_request():
    packed = prepend_context_pack("Write a follow-up note", "operations")
    assert "[CONTEXT_PACK]" in packed
    assert "User request:" in packed
    assert "Write a follow-up note" in packed
