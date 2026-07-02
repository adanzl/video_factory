from app.services.render.text_render import split_phrase_chunks


def test_short_opener_merges_into_question():
    text = "哇，你知道吗？欧洲好多房子都没空调，"
    phrases = split_phrase_chunks(text)
    assert len(phrases) >= 2
    first_tts, first_display = phrases[0]
    assert first_tts == "哇，你知道吗？"
    assert first_display == "哇，你知道吗"


def test_display_keeps_middle_punctuation():
    phrases = split_phrase_chunks("你看，不是他们不怕热，而是太贵啦！")
    assert phrases[0][1].startswith("你看，")
    assert "不是他们不怕热" in phrases[0][1]

    phrases2 = split_phrase_chunks("1902年，威利斯·开利为纽约一家印刷厂设计了第一台现代空调。")
    joined = "".join(d for _, d in phrases2)
    assert "威利斯·开利" in joined
