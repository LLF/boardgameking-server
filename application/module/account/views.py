# -*- coding:utf-8 -*-
from operator import attrgetter
from django.views.decorators.http import require_http_methods
from django.conf import settings

from module.common.decorators.api import require_player
from module.common.util import STATUS_CODE, output_response
from module.account.models import (
    IDENTITY_TYPE,
    Account,
    PlayerGNA,
    UUID2PlayerID,
    Identity2PlayerID,
    PlayerIDGenerator,
    IdentifierPairLog,
    IdentiyidInMaintenance,
)
from module.account.api import (
    create_uuid,
    get_account,
    is_valid_name,
    insert_identifier_for_vendor_and_mac, 
    INVALID_MAC_ADDRESS,
    INVALID_IDENTIFIER_FOR_VENDOR,
    insert_player_name
)
from module.tutorial.models import NewbieTutorial
from module.player2.models import PlayerData
from module.player2.api import player_exists
from module.card2.models import Card
from module.card2.api import get_card
from module.playercard2.api import acquire_card
from module.playerdeck2.models import PlayerDeck
from module.game_settings.models import GameSettings
from module.tutorial.models import TutorialPhase
from submodule.gamelog.api import log_daily_access

from module.actionlog.api import log_do_create_account
from module.evolution2.api import get_evolution_item_set
from module.playerevolution2.api import acquire_evolution_item_set
from module.mystery.models import MYSTERY_SLOT
from module.player_mystery.api import set_player_mystery_count

import module.i18n as T

@require_http_methods(['POST'])
def create_account(request):
    identity_type = request.REQUEST.get('identity_type', None)
    identity_id   = request.REQUEST.get('identity_id', None) #IOS7开始，macaddress无效化
    name   = request.REQUEST.get('name', None)
    init_card = request.REQUEST.get('init_card', None)
    invite_code = request.REQUEST.get('invite_code', '')
    # android上这个值就发macaddress吧,ios6以前的也是
    identifier_for_vendor = request.REQUEST.get('identifier_for_vendor', None)
    identifier_for_vendor_native = request.REQUEST.get('identifier_for_vendor_native', None)

    db_mac_address = identity_id
    db_vendor = identifier_for_vendor


    if identity_type is None or identity_id is None or identifier_for_vendor is None or \
        (identity_type != str(IDENTITY_TYPE.GAME_CENTER) and identity_type != str(IDENTITY_TYPE.MAC)):
        return output_response(STATUS_CODE.REQUIRE_IDENTITY)

    identity_type = str(IDENTITY_TYPE.MAC) #现在不支持其他类型

    if not is_valid_name(name):
        return output_response(status_code=1000, errmsg='invalid name')

    init_choose_card_num = GameSettings.get_value(GameSettings.KEY_PLAYER_INIT_CHOOSE_CARD_NUM)
    available_card_ids = []
    for i in range(init_choose_card_num):
        key = GameSettings.FORMAT_KEY_PLAYER_INIT_CARD_ID.format(i+1)
        available_card_ids.append(str(GameSettings.get_value(key)))
    if init_card is None or str(init_card) not in available_card_ids:
        return output_response(status_code=1001, errmsg='invalid initial card')



    # 验证需要注册的账户是否已经存在(先用macaddress检查一下)
    player_id = Identity2PlayerID(identity_type, identity_id).get()
    if player_id is not None:
        return output_response(STATUS_CODE.PLAYER_EXIST)

    # 如果identity_id(mac地址)和identifier_for_vendor不相同，且identifier_for_vendor合法
    # 则使用identifier_for_vendor标识用户
    if identity_id != identifier_for_vendor and identifier_for_vendor != INVALID_IDENTIFIER_FOR_VENDOR:
        identity_id = identifier_for_vendor
        player_id = Identity2PlayerID(identity_type, identity_id).get()
        if player_id is not None:
            return output_response(STATUS_CODE.PLAYER_EXIST)


    # 创建player_id
    player_id = PlayerIDGenerator().get_next_player_id()

    # 发行UUID
    uuid = create_uuid(identity_type, identity_id)

    # 关联player_id和identity
    if identity_type == str(IDENTITY_TYPE.GAME_CENTER):
        Account.objects.partition(player_id).create(player_id=player_id, 
            identity_id=identity_id, identity_type=identity_type, uuid=uuid)
    elif identity_type == str(IDENTITY_TYPE.MAC):
        Account.objects.partition(player_id).create(player_id=player_id, 
            mac_address=identity_id, identity_type=identity_type, uuid=uuid)

    # GNA对应
    PlayerGNA.objects.partition(player_id).create(osuser_id=player_id)

    # 创建Redis
    UUID2PlayerID(uuid).set(player_id)
    Identity2PlayerID(identity_type, identity_id).set(player_id)

    # 创建player数据
    # 初始化用户的Deck
    init_deck_num = GameSettings.get_value(GameSettings.KEY_PLAYER_INIT_DECK_NUM)
    player = PlayerData(player_id).create(
        name=name.encode('utf-8'),
        deck_num=init_deck_num,
        init_card=init_card,
        first_payment_reward=True,
    )

    init_card_level = GameSettings.get_value(GameSettings.KEY_PLAYER_INIT_CARD_LEVEL)
    card = Card.get_cache(init_card)
    main_card, is_new = acquire_card(player_id, card, level=init_card_level)

    # 选定了第一张卡以后，提供两张额外的卡
    for idx, c in enumerate(available_card_ids, start=1):
        if int(c) == int(init_card):
            selected_idx = idx

    init_help_card_num = GameSettings.get_value(GameSettings.KEY_PLAYER_INIT_HELP_CARD_NUM)
    init_help_card_level = GameSettings.get_value(GameSettings.KEY_PLAYER_INIT_HELP_CARD_LEVEL)
    help_cards = []
    slot_info = {}
    for i in range(init_help_card_num):
        card_id = GameSettings.get_value(GameSettings.FORMAT_KEY_PLAYER_INIT_HELP_CARD_ID.format(selected_idx, i+1))
        card = Card.get_cache(card_id)
        playercard, is_new = acquire_card(player_id, card, level=init_help_card_level)
        help_cards.append(playercard)
        slot = _get_slot_by_playercard(playercard)
        slot_info["slot{}".format(slot)] = playercard.unique_id

    # 获取主卡的类型
    default_slot = _get_slot_by_playercard(main_card)
    slot_info["slot{}".format(default_slot)] = main_card.unique_id
            
    for i in range(int(init_deck_num)):
        playerdeck = PlayerDeck(player_id, i)
        playerdeck.init_leadercard(main_card, default_slot)
        if i == 0:
            playerdeck.store(main_card.unique_id, **slot_info)


    # 赠送经验猫
    card_id = GameSettings.get_value(GameSettings.KEY_EXTRA_REWARD_FOR_FIRST_AREA_OF_NORMAL_STAGE)
    # 保存到用户
    card = get_card(card_id)
    player_card, is_new_card = acquire_card(player_id, card)

    # 赠送一套1星升2星的进化素材
    acquire_evolution_item_set(player_id, get_evolution_item_set(main_card.card.evo_item_set), 1)
    #空出最后一个slot给tutorial时用
    for i in xrange(MYSTERY_SLOT.COUNT-1):
        set_player_mystery_count(player_id, main_card.unique_id, i, 1)

    # 邀请码相关
    is_invitee = False
    from module.invitation2.api import decode_invite_code
    from module.invitation2.models import (
        PlayerInviter,
        PlayerInvitees,
    )
    from module.friend2.api import add_invitation
    is_valid, inviter_id = decode_invite_code(invite_code)
    if is_valid and player_exists(inviter_id):
        is_invitee = True
        # 记录邀请者
        PlayerInviter(player.pk).set(inviter_id)
        # 加入被邀请行列
        PlayerInvitees(inviter_id).add(player.pk)

        # 互相邀请
        add_invitation(player.pk, inviter_id)
        add_invitation(inviter_id, player.pk)

        # 标记玩家是被邀请的
        player.update(is_introduced=1)

    log_daily_access(player_id, request)

    log_do_create_account(player_id, identity_type, identity_id, is_invitee, inviter_id, init_card, name)

    insert_identifier_for_vendor_and_mac(player_id, db_vendor, db_mac_address, identifier_for_vendor_native)

    NewbieTutorial(player_id).set(NewbieTutorial.PHASE_UNA2)

    insert_player_name(player_id, name.encode('utf-8'))

    # 判断该新用户是否是在维护期间下载app的用户
    identityid_in_maintenance = IdentiyidInMaintenance()
    if identityid_in_maintenance.has_identity_id(identity_id):
        from module.gift2.api import send_official_gift
        send_official_gift(player_id, 5, 3000, 1, u'緊急メンテナンスのお詫びです。\n\n魔晶石x３０００ をお送りします。\n\n急なメンテナンスとなり、大変申し訳御座いませんでした。\n ')
        # 删除identityid防止迁移之后重新拿到补偿
        identityid_in_maintenance.delete(identity_id)

    return output_response(STATUS_CODE.OK, {'uuid': uuid, 'player_id': str(player_id), 'is_invitee': is_invitee})

def _get_slot_by_playercard(playercard):
    TYPE = Card.TYPE
    if playercard.card.type == TYPE.PA or playercard.card.type == TYPE.MA or \
        playercard.card.type == TYPE.RANGER:
        return 3
    elif playercard.card.type == TYPE.PD or playercard.card.type == TYPE.MD:
        return 1
    elif playercard.card.type == TYPE.HEALER:
        return 4
    else:
        assert False

@require_http_methods(['POST'])
def get_uuid(request):
    identity_type = request.REQUEST.get('identity_type', None)
    identity_id   = request.REQUEST.get('identity_id',None)

    # ios上现在会将IdentifierForVendor保存在keychain中
    identifier_for_vendor = request.REQUEST.get('identifier_for_vendor', None)
    # 这个依旧是原生的IdentifierForVendor
    # 两个vendor不一致的可能性为
    # 1. 用户删除app以后，IdentifierForVendor发生了变更
    # 2. 用户将数据备份到其他设备以后
    # 3. ios不确定的bug导致了IdentifierForVendor发生了变更
    identifier_for_vendor_native = request.REQUEST.get('identifier_for_vendor_native', None)

    identity_type = str(IDENTITY_TYPE.MAC) #现在不支持其他类型

    if identity_type is None or identity_id is None or identifier_for_vendor is None or \
        (identity_type != str(IDENTITY_TYPE.GAME_CENTER) and identity_type != str(IDENTITY_TYPE.MAC)):
        return output_response(STATUS_CODE.REQUIRE_IDENTITY)

    # 用来记录db
    db_mac_address = identity_id
    db_vendor = identifier_for_vendor

    # 该identity是否登录过
    if identity_id == INVALID_MAC_ADDRESS:
        # ios7传过来的无效mac地址
        player_id = None
    else:
        # 合法的mac地址
        player_id = Identity2PlayerID(identity_type, identity_id).get()

    # 如果identity_id(mac地址)和identifier_for_vendor不相同，且identifier_for_vendor合法
    # 则使用identifier_for_vendor标识用户 (转化老用户，老用户用macaddress保存的)
    if player_id is not None and identity_id != identifier_for_vendor and identifier_for_vendor != INVALID_IDENTIFIER_FOR_VENDOR:
        account = Account.objects.partition(player_id).get(player_id = player_id)
        account.mac_address = identifier_for_vendor
        account.save()
        Identity2PlayerID(identity_type, identity_id).delete()
        Identity2PlayerID(identity_type, identifier_for_vendor).set(player_id)

    if player_id is None:
        # 无法使用macaddress找到账户，尝试使用IdentifierForVendor
        player_id = Identity2PlayerID(identity_type, identifier_for_vendor).get()
        if player_id is None:
            # 根据vendor_native去找
            # 实际情况可以是vendor_native发生了变化（这个会记录在IdentifierPairLog里）
            # 然后持久化下来的vendor也丢了，到这里试着根据以前的记录看看能不能找到
            result = IdentifierPairLog.objects.all_partition_filter(identifier_for_vendor_native=identifier_for_vendor_native)
            if len(result) > 0:
                player_id = result[0].player_id
                account = Account.objects.partition(player_id).get(player_id = player_id)
                account.mac_address = identifier_for_vendor
                account.save()
                Identity2PlayerID(identity_type, identity_id).delete()
                Identity2PlayerID(identity_type, identifier_for_vendor).set(player_id)


    if player_id is None:
        return output_response(STATUS_CODE.PLAYER_NOT_EXIST)
    else:
        # 已有用户，重新发行UUID
        uuid = create_uuid(identity_type, player_id)

        # 更新DB uuid
        account = Account.objects.partition(player_id).get(player_id = player_id)
        old_uuid = account.uuid
        account.uuid = uuid
        account.save()

        # 更新redis uuid
        if old_uuid:
            UUID2PlayerID(old_uuid).delete()
        UUID2PlayerID(uuid).set(player_id)

        player = PlayerData(player_id)

        if settings.USER_DEBUG:
            player_id = settings.OPENSOCIAL_DEBUG_USER_ID

        log_daily_access(player_id, request)

        insert_identifier_for_vendor_and_mac(player_id, db_vendor, db_mac_address, identifier_for_vendor_native)

        if player.ban:
            return output_response(status_code=STATUS_CODE.PLAYER_BAN, errmsg=u"player ban...")
        else:
            return output_response(STATUS_CODE.OK, {'uuid': uuid, 'player_id': str(player_id)})


def get_account_info(request):
    identity_type = request.REQUEST.get('identity_type', None)
    identity_id   = request.REQUEST.get('identity_id',None)
    identifier_for_vendor = request.REQUEST.get('identifier_for_vendor', None)

    identity_type = str(IDENTITY_TYPE.MAC) #现在不支持其他类型

    if identity_id is None or not IDENTITY_TYPE.is_valid(int(identity_type)):
        return output_response(STATUS_CODE.REQUIRE_IDENTITY)

    player_id = Identity2PlayerID(identity_type, identity_id).get()

    if identity_id != identifier_for_vendor:
        # IOS设备
        if player_id is not None:
            # 根据macadress能够找到账户
            # IOS7以前的设备，有效账户，需要将mac地址改绑定到IdentifierForVendor上
            Identity2PlayerID(identity_type, identity_id).delete()
            Identity2PlayerID(identity_type, identifier_for_vendor).set(player_id)
            account = Account.objects.partition(player_id).get(player_id = player_id)
            account.mac_address = identifier_for_vendor
            account.save()
        else:
            # 无法使用macaddress找到账户，尝试使用IdentifierForVendor
            identity_id = identifier_for_vendor
            player_id = Identity2PlayerID(identity_type, identity_id).get()
    else:
        # android设备，不用特别处理
        pass

    if player_id is None:
        # 这里不用全局的PLAYER_NOT_EXIST状态码，使用局部状态码
        return output_response(status_code=1002, errmsg='player not exists')
    else:
        return output_response(STATUS_CODE.OK)
