from tristhana.application.start import StartCommand, StartUseCase


async def test_start_negotiates_the_locale() -> None:
    result = await StartUseCase().execute(StartCommand(telegram_user_id=1, language_code="kk"))

    assert result.locale == "ru"
