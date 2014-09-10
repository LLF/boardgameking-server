# -*- coding: utf-8 -*-
from functools import wraps
from django.conf import settings
import logging

from module.common.util import output_response, STATUS_CODE
from submodule.gamelog.api import log_event_access
from module.player2.models import (
    PlayerData
)
from module.player2.api import update_player_timestamp
from module.player2.models import PlayerOfflineChanges

def require_player(view_func):
    @wraps(view_func)
    def decorate(request, *args, **kwds):
        player_id = request.player_id
        if player_id is None:
            # 无效的UUID，需重新认证获取新的UUID
            return output_response(STATUS_CODE.INVALID_UUID)

        playerdata = PlayerData(player_id)
        if not playerdata.exists():
            return output_response(STATUS_CODE.INVALID_UUID)

        playerdata.load()
        if playerdata.ban:
            return output_response(status_code=STATUS_CODE.PLAYER_BAN, errmsg=u"player ban...")
        request.player = playerdata

        result =  view_func(request, *args, **kwds)
        # 用户offline数据清零
        PlayerOfflineChanges(playerdata.pk).reset_changes()
        # 更新用户的最后登录时间戳(必须放在请求处理完之后)
        update_player_timestamp(playerdata.pk)
        return result
    return decorate

def log_event_dau(view_func):
    @wraps(view_func)
    def _log_event_dau(request, *args, **kwargs):
        from module.quest.api import check_substage
        if hasattr(request, 'player_id'):
            player = request.player_id
            if player is not None:
                substage_id = request.REQUEST.get('substage_id', None)
                if substage_id is not None and check_substage(substage_id):
                    log_event_access(player, 'allen_eventstage_{}'.format(substage_id))
        return view_func(request, *args, **kwargs)
    return _log_event_dau

def check_ip_address(view_func):
    @wraps(view_func)
    def decorate(request, *args, **kwds):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            logging.debug("HTTP_X_FORWARDED_FOR: {}".format(x_forwarded_for))
            ip = x_forwarded_for.split(',')[-1].strip()
            logging.debug("ip: {}".format(ip))
        else:
            ip = request.META.get('REMOTE_ADDR', '-')
            logging.debug("ip: {}".format(ip))

        if not ip in settings.ENABLE_API_REMOTE_ADDR:
            return output_response(status_code=STATUS_CODE.AUTHENTICATION_ERROR, errmsg=u"IP address not permission")
        return view_func(request, *args, **kwds)
    return decorate



