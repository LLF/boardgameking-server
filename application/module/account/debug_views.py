# -*- coding: utf-8 -*-
from django.conf import settings

from module.common.decorators.api import require_player
from module.common.util import output_response

from module.account.models import (
    IDENTITY_TYPE,
    Account,
    UUID2PlayerID,
    Identity2PlayerID,
    IdentifierPairLog,
)

@require_player
def reset_account(request):
    player_id = request.player.pk

    account = Account.objects.partition(player_id).get(player_id=player_id)
    identity_type = account.identity_type
    old_uuid = account.uuid

    if identity_type == IDENTITY_TYPE.MAC:
        identity_id = account.mac_address
        after = '{}:{}'.format(account.mac_address, player_id)
        account.mac_address = after
    elif identity_type == IDENTITY_TYPE.GAME_CENTER:
        identity_id = account.identity_id
        after = '{}:{}'.format(account.identity_id, player_id)
        account.identity_id = after
    else:
        return output_response(status_code=1001, errmsg='unknow identity type')

    # 更新identity_id
    account.save()

    # 删除 uuid 到 player_id 的映射
    if old_uuid:
        UUID2PlayerID(old_uuid).delete()

    # 删除 identiy 到 player_id 的映射
    Identity2PlayerID(identity_type, identity_id).delete()

    IdentifierPairLog.objects.partition(player_id).filter(player_id=player_id).delete()

    return output_response()

@require_player
def set_tutorial_finished(request):
    player_id = request.player.pk

    from module.tutorial.models import NewbieTutorial
    NewbieTutorial(player_id).set(NewbieTutorial.PHASE_OLD_USER)

    return output_response()