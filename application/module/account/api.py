# -*- coding: utf-8 -*-
import hashlib
import hmac
import time
import datetime
from oauth import oauth
from oauth.oauth import escape

from django.conf import settings

from horizontalpartitioning import transaction_commit_on_success_hp
from module.ngword.models import NgwordValidator

from module.account.models import (
    IDENTITY_TYPE,
    Account,
    UUID2PlayerID,
    Identity2PlayerID,
    IdentifierPairLog,
    PlayerName
)

from module.player2.api import get_player

from django.db import IntegrityError

INVALID_MAC_ADDRESS = '02:00:00:00:00:00'
INVALID_IDENTIFIER_FOR_VENDOR = '00000000-0000-0000-0000-000000000000'


def create_uuid(str1, str2):
    message = '&'.join((oauth.escape(str1), oauth.escape(str2),oauth.escape(str(time.time()))))
    shared_key = oauth.escape(settings.UUID_SECRET)
    return hmac.new(shared_key, message, hashlib.sha1).hexdigest()

def get_account(player_id):
    try:
        return Account.objects.partition(player_id).get(player_id=player_id)
    except Account.DoesNotExist:
        return None

invalid_chars = [
    "\\",
    "~",
    "$",
    "/",
    ":",
    ",",
    "'",
    ";",
    "*",
    "?",
    "<",
    ">",
    "|",
    "`",
    "[",
    "]",
    "=",
    "+",
    ".",
    "@",
    "(",
    ")",
    "#",
    "%",
    "^",
    " "
]

MAX_NAME_LENGTH = 10
class valid_status():
    def __init__(self, flag, status=0):
        self.flag = flag
        self.status = status
    def __nonzero__(self):
        return self.flag

def is_valid_name(name):
    if name is None or not 0 < len(name) <= MAX_NAME_LENGTH:
        return valid_status(False, 1000)

    if name == u'سمَـَّوُوُحخ ̷̴̐خ ̷̴̐خ ̷̴̐خ امارتيخ ̷̴̐خ':
        return valid_status(False, 1000)

    for invalid_char in invalid_chars:
        if invalid_char in name:
            return valid_status(False, 1000)

    ngword_validator = NgwordValidator.Instance()
    if not ngword_validator.is_valid(name):
        return valid_status(False, 1003)
    return valid_status(True)

def insert_identifier_for_vendor_and_mac(player_id, identifier_for_vendor, mac_address, identifier_for_vendor_native):
    if identifier_for_vendor_native is not None and identifier_for_vendor_native != identifier_for_vendor:
        try:
            IdentifierPairLog.objects.partition(player_id).create(
                player_id=player_id,
                identifier_for_vendor=identifier_for_vendor,
                identifier_for_vendor_native=identifier_for_vendor_native
            )
        except IntegrityError:
            pass

def insert_player_name(player_id, name):
    try:
        PlayerName.objects.partition(player_id).create(player_id=player_id, name=name)
    except:
        # 暂时不支持4字节的表情字符(仅仅survey用，需要改线上mysql参数)
        pass

def update_player_name(player_id, name):
    try:
        player_name_data = PlayerName.objects.partition(player_id).get(player_id=player_id)
        player_name_data.name = name
        player_name_data.save()
    except PlayerName.DoesNotExist:
        insert_player_name(player_id, name)
    except:
        # 暂时不支持4字节的表情字符(仅仅survey用，需要改线上mysql参数)
        pass


def search_player_name(pattern):
    all_data = []

    if not pattern:
        return all_data

    for i in range(settings.HORIZONTAL_PARTITIONING_PARTITION_NUMBER):
        database_name = settings.HORIZONTAL_PARTITIONING_DB_NAME_FORMAT % i
        data = PlayerName.objects.using(database_name).filter(name__contains=pattern)
        all_data.extend(data)

    return all_data
