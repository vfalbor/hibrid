"""Tests de traducción de dialectos (Anthropic <-> interno). Sin red."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import dialects


def test_anthropic_string_content():
    body = {"model": "claude-opus-4-8", "max_tokens": 100, "system": "be brief",
            "messages": [{"role": "user", "content": "hola"}]}
    msgs = dialects.anthropic_to_messages(body)
    assert msgs[0].role == "system" and msgs[0].content == "be brief"
    assert msgs[1].role == "user" and msgs[1].content == "hola"


def test_anthropic_block_content():
    body = {"messages": [{"role": "user", "content": [
        {"type": "text", "text": "fix this"}, {"type": "text", "text": "function"}]}]}
    msgs = dialects.anthropic_to_messages(body)
    assert msgs[0].content == "fix this\nfunction"


def test_anthropic_system_blocks():
    body = {"system": [{"type": "text", "text": "you are"}, {"type": "text", "text": "hibrid"}],
            "messages": [{"role": "user", "content": "x"}]}
    msgs = dialects.anthropic_to_messages(body)
    assert msgs[0].role == "system" and "you are" in msgs[0].content


def test_result_to_anthropic_shape():
    out = dialects.result_to_anthropic(msg_id="msg_1", text="hi", model="local/qwen",
                                       input_tokens=5, output_tokens=2,
                                       hibrid_meta={"tier": "local_free"})
    assert out["type"] == "message" and out["role"] == "assistant"
    assert out["content"][0]["text"] == "hi"
    assert out["usage"] == {"input_tokens": 5, "output_tokens": 2}
    assert out["hibrid"]["tier"] == "local_free"


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    ok = 0
    for fn in fns:
        try:
            fn(); print(f"PASS {fn.__name__}"); ok += 1
        except Exception:
            print(f"FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{ok}/{len(fns)} dialect tests OK")
