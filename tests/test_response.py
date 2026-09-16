"""Unit tests for the reply contract every outbound message passes through.

The pipeline's behavior is tested at the webhook seam (tests/test_webhook.py);
this file covers the pure transformations that funnel applies, where the
interesting cases are text shapes rather than message flow.
"""

from bella.reply_language import ReplyLanguage
from bella.response import (
    Response,
    ResponsePolicy,
    ResponseSource,
    normalize_for_whatsapp,
    policy_from_urls,
    split_for_whatsapp,
)

FALLBACK = "Tive um probleminha técnico por aqui."


def policy(**overrides: object) -> ResponsePolicy:
    settings: dict[str, object] = {"fallback_text": FALLBACK}
    settings.update(overrides)
    return ResponsePolicy(**settings)  # type: ignore[arg-type]


def test_markdown_bold_becomes_whatsapp_bold() -> None:
    assert normalize_for_whatsapp("Use o **botão Gerar**") == "Use o *botão Gerar*"


def test_existing_whatsapp_formatting_is_left_alone() -> None:
    summary = '📋 *Título:* Erro no PDF\n🎯 *Esperado:* _sucesso_'
    assert normalize_for_whatsapp(summary) == summary


def test_headings_and_bullets_become_plain_whatsapp_text() -> None:
    normalized = normalize_for_whatsapp(
        "## Passos\n\n- abra a planilha\n- clique em Gerar\n\n---\n\nPronto!"
    )
    assert normalized == "*Passos*\n\n• abra a planilha\n• clique em Gerar\n\nPronto!"


def test_surviving_markdown_link_is_flattened() -> None:
    assert (
        normalize_for_whatsapp("Veja a [documentação](https://ok.example/docs)")
        == "Veja a documentação: https://ok.example/docs"
    )


def test_runs_of_blank_lines_collapse() -> None:
    assert normalize_for_whatsapp("um\n\n\n\n\ndois   \n") == "um\n\ndois"


def test_short_reply_is_one_message() -> None:
    assert split_for_whatsapp("oi", max_length=100) == ("oi",)


def test_long_reply_splits_on_the_paragraph_boundary() -> None:
    first = "a" * 60
    second = "b" * 60
    assert split_for_whatsapp(f"{first}\n\n{second}", max_length=80) == (first, second)


def test_long_reply_without_paragraphs_splits_on_a_sentence() -> None:
    text = "Primeira frase aqui. Segunda frase aqui. Terceira frase aqui."
    chunks = split_for_whatsapp(text, max_length=42)
    assert chunks[0] == "Primeira frase aqui. Segunda frase aqui."
    assert "".join(chunks).replace(" ", "") == text.replace(" ", "")


def test_unbreakable_text_is_hard_cut_rather_than_dropped() -> None:
    chunks = split_for_whatsapp("x" * 30, max_length=10, max_chunks=3)
    assert [len(chunk) for chunk in chunks] == [10, 10, 10]


def test_text_beyond_the_chunk_budget_is_marked_as_truncated() -> None:
    chunks = split_for_whatsapp("y" * 100, max_length=10, max_chunks=2)
    assert len(chunks) == 2
    assert chunks[-1].endswith("…")


def test_model_authored_text_loses_foreign_urls() -> None:
    finalized = policy(allowed_urls=("https://ok.example",)).finalize(
        Response(
            "Baixe em https://evil.example/x ou em https://ok.example agora",
            ResponseSource.ANSWERER,
        )
    )
    assert finalized == ("Baixe em ou em https://ok.example agora",)


def test_canned_text_keeps_its_own_links() -> None:
    contact = "Contato humano:\nhttps://senai.example/curso"
    finalized = policy().finalize(Response(contact, ResponseSource.CANNED))
    assert finalized == (contact,)


def test_empty_response_degrades_to_the_fallback_instead_of_an_empty_send() -> None:
    assert policy().finalize(Response("   ", ResponseSource.ANSWERER)) == (FALLBACK,)


def test_fallback_follows_the_reply_language() -> None:
    localized = policy(translations={"en": "Something went wrong."})
    finalized = localized.finalize(
        Response("", ResponseSource.ANSWERER, ReplyLanguage.ENGLISH)
    )
    assert finalized == ("Something went wrong.",)


def test_blank_allowlist_entries_are_dropped() -> None:
    built = policy_from_urls(FALLBACK, ("", "  ", "https://ok.example"))
    assert built.allowed_urls == ("https://ok.example",)


def test_an_empty_allowlist_removes_every_url() -> None:
    finalized = policy_from_urls(FALLBACK, ()).finalize(
        Response("Acesse http://localhost:8000 no navegador", ResponseSource.ANSWERER)
    )
    assert finalized == ("Acesse no navegador",)


def test_an_allowed_url_survives_the_bold_a_model_wrapped_it_in() -> None:
    finalized = policy_from_urls(FALLBACK, ("http://localhost:8000",)).finalize(
        Response("Abra **http://localhost:8000** no navegador", ResponseSource.ANSWERER)
    )
    assert finalized == ("Abra *http://localhost:8000* no navegador",)


def test_a_removed_url_leaves_no_orphaned_emphasis() -> None:
    finalized = policy().finalize(
        Response("Veja **https://evil.example/x**, depois volte.", ResponseSource.ANSWERER)
    )
    assert finalized == ("Veja, depois volte.",)
