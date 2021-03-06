"""File containing the Custom TelegramClient"""
import datetime
import logging
import time
from typing import Optional, Union

import logzero
import spamwatch
from spamwatch.types import Permission
from telethon import TelegramClient, hints
from telethon.errors import UserAdminInvalidError
from telethon.events import NewMessage, ChatAction
from telethon.tl.custom import Message
from telethon.tl.functions.channels import EditBannedRequest
from telethon.tl.types import ChatBannedRights

import config
from database.arango import ArangoDB
from utils.mdtex import FormattedBase, MDTeXDocument, Section
from utils.pluginmgr import PluginManager

logger: logging.Logger = logzero.logger

AUTOMATED_BAN_REASONS = ['Spambot', 'Vollzugsanstalt', 'Kriminalamt']


class KantekClient(TelegramClient):  # pylint: disable = R0901, W0223
    """Custom telethon client that has the plugin manager as attribute."""
    plugin_mgr: Optional[PluginManager] = None
    db: Optional[ArangoDB] = None
    kantek_version: str = ''
    sw: spamwatch.Client = None

    async def respond(self, event: NewMessage.Event,
                      msg: Union[str, FormattedBase, Section, MDTeXDocument],
                      reply: bool = True) -> Message:
        """Respond to the message an event caused or to the message that was replied to

        Args:
            event: The event of the message
            msg: The message text
            reply: If it should reply to the message that was replied to

        Returns: None

        """
        msg = str(msg)
        if reply:
            if isinstance(event, ChatAction.Event):
                reply_to = event.action_message.id
            else:
                reply_to = (event.reply_to_msg_id or event.message.id)
            return await event.respond(msg, reply_to=reply_to)
        else:
            return await event.respond(msg, reply_to=event.message.id)

    async def gban(self, uid: Union[int, str], reason: str):
        """Command to gban a user

        Args:
            uid: User ID
            reason: Ban reason

        Returns: None

        """
        # if the user account is deleted this can be None
        if uid is None:
            return
        user = self.db.query('For doc in BanList '
                             'FILTER doc._key == @uid '
                             'RETURN doc', bind_vars={'uid': str(uid)})
        for ban_reason in AUTOMATED_BAN_REASONS:
            if user and (ban_reason in user[0]['reason']) and (ban_reason not in reason):
                return False
        await self.send_message(
            config.gban_group,
            f'<a href="tg://user?id={uid}">{uid}</a>', parse_mode='html')
#         await self.send_message(
#             config.gban_group,
#             f'/gban {uid} {reason}')
        await self.send_message(
            config.gban_group,
            f'/fban {uid} {reason}')
        time.sleep(0.5)
        await self.send_read_acknowledge(config.gban_group,
                                         max_id=1000000,
                                         clear_mentions=True)
        data = {'_key': str(uid),
                'id': str(uid),
                'reason': reason}

        self.db.query('UPSERT {"_key": @ban.id} '
                      'INSERT @ban '
                      'UPDATE {"reason": @ban.reason} '
                      'IN BanList ', bind_vars={'ban': data})

        if self.sw and self.sw.permission in [Permission.Admin,
                                              Permission.Root]:
            self.sw.add_ban(int(uid), reason)

        return True

    async def ungban(self, uid: Union[int, str]):
        """Command to gban a user

        Args:
            uid: User ID

        Returns: None

        """
        await self.send_message(
            config.gban_group,
            f'<a href="tg://user?id={uid}">{uid}</a>', parse_mode='html')
#         await self.send_message(
#             config.gban_group,
#             f'/ungban {uid}')
        await self.send_message(
            config.gban_group,
            f'/unfban {uid}')
        time.sleep(0.5)
        await self.send_read_acknowledge(config.gban_group,
                                         max_id=1000000,
                                         clear_mentions=True)

        self.db.query('REMOVE {"_key": @uid} '
                      'IN BanList', bind_vars={'uid': str(uid)})
        if self.sw and self.sw.permission in [Permission.Admin,
                                              Permission.Root]:
            self.sw.delete_ban(int(uid))

    async def ban(self, chat, uid):
        """Bans a user from a chat."""
        try:
            await self(EditBannedRequest(
                chat, uid, ChatBannedRights(
                    until_date=datetime.datetime(2038, 1, 1),
                    view_messages=True
                )
            ))
        except UserAdminInvalidError as err:
            logger.error(err)

    async def get_cached_entity(self, entity: hints.EntitiesLike):
        input_entity = await self.get_input_entity(entity)
        return await self.get_entity(input_entity)
