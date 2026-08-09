from app.core.token_counter import count_messages_tokens, count_tokens


class TestTokenCounter:
    def test_empty_string(self):
        assert count_tokens("") >= 1  # min 1

    def test_short_text_positive(self):
        n = count_tokens("I have a headache")
        assert n > 0

    def test_longer_text_more_tokens(self):
        short = count_tokens("pain")
        long = count_tokens("I have had severe chest pain radiating to my left arm for the past hour")
        assert long > short

    def test_messages_tokens_includes_overhead(self):
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        total = count_messages_tokens(msgs)
        # Each message has 4 overhead + content tokens + 2 reply primer
        assert total > count_tokens("hello") + count_tokens("hi")

    def test_empty_messages_list(self):
        assert count_messages_tokens([]) == 2  # just the reply primer

    def test_max_token_gate_logic(self):
        # Simulate the gate check from triage.py
        from app.core.config import settings
        short_msg = "headache"
        long_msg = "x " * 1000  # definitely over 400 tokens
        assert count_tokens(short_msg) < settings.max_input_tokens
        assert count_tokens(long_msg) > settings.max_input_tokens
