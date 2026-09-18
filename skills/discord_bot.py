from __future__ import annotations

import os
import sys
import tempfile

import certifi

# macOS Python often needs certifi's CA bundle for SSL
os.environ.setdefault("SSL_CERT_FILE", certifi.where())

import discord
from discord.ext import commands

import gateway as _gateway_mod

_discord_bot_ref = None


class DiscordBot:
    def __init__(
        self,
        token: str,
        agent_lock: object,
        app,
    ) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        self.bot = commands.Bot(command_prefix=None, intents=intents)
        import skills.discord_bot as _db_mod
        _db_mod._discord_bot_ref = self.bot
        self.token = token
        self._agent_lock = agent_lock
        self._app = app

        @self.bot.event
        async def on_ready() -> None:
            print(f"[Discord] Connected as {self.bot.user}")

        @self.bot.event
        async def on_message(message: discord.Message) -> None:
            if message.author == self.bot.user:
                return

            prompt = message.content

            self._app.call_from_thread(
                self._app._add_discord_message,
                f"[Discord] {message.author.display_name}: {prompt}",
            )

            images: list[str] = []
            for att in message.attachments:
                if any(
                    att.filename.lower().endswith(ext)
                    for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif")
                ):
                    suffix = att.filename.rsplit(".", 1)[-1]
                    tmp = tempfile.NamedTemporaryFile(
                        delete=False, suffix=f".{suffix}"
                    )
                    await att.save(tmp.name)
                    images.append(tmp.name)

            with self._agent_lock:
                handler = _gateway_mod._permission_handler
                _gateway_mod._permission_handler = None
                try:
                    result = _gateway_mod.call_evy(
                        prompt, images=images or None
                    )
                except Exception as e:
                    print(
                        f"[Discord] Error processing message: {e}",
                        file=sys.stderr,
                    )
                    import traceback
                    traceback.print_exc()
                    result = f"Sorry, I encountered an error: {e}"
                finally:
                    _gateway_mod._permission_handler = handler

            if not result:
                result = "(no response)"

            for i in range(0, len(result), 2000):
                await message.channel.send(result[i : i + 2000])

            self._app.call_from_thread(self._app._add_evy_message, result)

    def run(self) -> None:
        try:
            self.bot.run(self.token)
        except Exception as e:
            print(
                f"[Discord] Failed to start bot: {e}",
                file=sys.stderr,
            )
            import traceback

            traceback.print_exc()
