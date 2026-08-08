import logging

logger = logging.getLogger(__name__)

_TIKTOKEN_AVAILABLE = False
_encoder = None


def _try_load_encoder():
    global _TIKTOKEN_AVAILABLE, _encoder
    try:
        import tiktoken
        # gpt-4o / gpt-4o-mini both use o200k_base; fall back to cl100k_base for fine-tunes
        for encoding_name in ("o200k_base", "cl100k_base"):
            try:
                _encoder = tiktoken.get_encoding(encoding_name)
                _TIKTOKEN_AVAILABLE = True
                logger.info("Token counter using tiktoken encoding=%s", encoding_name)
                return
            except Exception:
                continue
    except ImportError:
        pass

    logger.warning(
        "tiktoken unavailable — using character-based token approximation (chars/4). "
        "Install tiktoken for accurate counts."
    )


_try_load_encoder()


def count_tokens(text: str) -> int:
    """
    Returns an accurate token count when tiktoken is available, otherwise
    approximates at chars/4 (conservative — real token count is usually lower).
    """
    if _TIKTOKEN_AVAILABLE and _encoder is not None:
        return len(_encoder.encode(text))
    # Conservative estimate: chars/2 over-counts for English but is safer for
    # CJK/Arabic where chars/4 severely under-counts. Better to reject borderline
    # inputs than to let a 600-token Arabic message slip past a 400-token gate.
    return max(1, len(text) // 2)


def count_messages_tokens(messages: list[dict]) -> int:
    """
    Estimates token count for a list of {role, content} dicts.
    Adds 4 tokens per message for role + structural overhead.
    """
    total = 0
    for msg in messages:
        total += 4  # role + structural tokens
        total += count_tokens(msg.get("content", ""))
    total += 2  # reply primer
    return total
