from io import BytesIO
from typing import Optional

from soundfile import read
from karuha import MessageSession, on_command
from karuha.text import Head, Audio


@on_command
async def asr(session: MessageSession, reply: Head[Optional[int]] = None) -> None:
    if reply is None:
        await session.finish("No reply message")
    message = await session.get_data(seq_id=reply)
    if not isinstance(message.text, Audio):
        await session.finish("No an audio")
    buffer = BytesIO()
    await session.download_attachment(message.text, buffer)
    try:
        data, samplerate = read(buffer)
        await session.send(f"{data.shape[0]} samples, {samplerate} Hz")
    except Exception as e:
        await session.finish(f"Error: {e}")
    ...
