# -*- coding: utf-8 -*-
import base64
import hashlib
import urllib
import hmac
import logging
import random

from oauth import oauth
from oauth.oauth import OAuthRequest
from oauth.oauth import escape, _utf8_str

from django.conf import settings
from django.core.cache import get_cache
from django.http import HttpResponse

from module.common.util import output_response, STATUS_CODE, decrypt_message
from module.account.models import UUID2PlayerID
from module.version.models import VersionRedis
from module.version.api import is_IOS

nonce_cache = get_cache('nonce_param')
nonce_key = 'api_nonce:%s'

def get_nonce(request):
    nonce = request.REQUEST.get("nonce", "");
    key = nonce_key % (nonce)
    return nonce_cache.get(key, False)

def set_nonce(request):
    nonce = request.REQUEST.get("nonce", "");
    key = nonce_key % (nonce)
    return nonce_cache.set(key, True)


class Log(object):
    """
    ログ出力クラスを無効化するスタブ
    """
    @classmethod
    def _get_logging_res(cls, msg, obj):
        pass

    @classmethod
    def debug(cls, msg, obj):
        pass

    @classmethod
    def info(cls, msg, obj):
        pass

    @classmethod
    def error(cls, msg, obj):
        pass

    @classmethod
    def warn(cls, msg, obj):
        pass


def log_error(*msg):
    logging.error("oauth_middleware" + repr(msg))


def log_info(*msg):
    logging.info("oauth_middleware" + repr(msg))


def log_debug(*msg):
    logging.debug("oauth_middleware" + repr(msg))


class ApiAuthMiddleware(object):
    def process_request(self, request):
        """
        process_request
        """

        # 设置request的player_id属性
        set_player_id(request)

        if settings.DISABLE_AUTH:
            return None

        # 非api请求
        if not request.path.startswith('/api/'):
            return None

        nonce = request.REQUEST.get('nonce', None);
        if nonce is None:
            log_error("check nonce: no nonce")
            return output_response(STATUS_CODE.AUTHENTICATION_ERROR)

        # duplicate request check
        is_nonce_exist = get_nonce(request)
        if is_nonce_exist:
            log_error("check_duplicate nonce NG")
            return HttpResponse(status=204)

        # ignore設定
        if hasattr(settings, 'OAUTH_IGNORE_PATH'):
            ignore_path = settings.OAUTH_IGNORE_PATH
            for path in ignore_path:
                if request.path.startswith(path):
                    return None
        # version check
        is_ignore = False
        if hasattr(settings, 'IGNORE_VERSION_CHECK'):
            for path in settings.IGNORE_VERSION_CHECK:
                if request.path.startswith(path):
                    is_ignore = True

        if not is_ignore:
            app_version = request.META.get('HTTP_X_KK_APPVERSION', None)
            dlc_version = request.META.get('HTTP_X_KK_DLCVERSION', None)
            DEVICEOS = request.META.get('HTTP_X_KK_DEVICEOS', None)

            if app_version is None or dlc_version is None or DEVICEOS is None:
                return output_response(STATUS_CODE.AUTHENTICATION_ERROR)

            # 分服的version信息记录在redis里
            version = VersionRedis()

            # 如果未初始化，不验证。一般是访问localhost的情况
            if version.exists():
                # app version 不必是最新，只要满足不小于db的设定值就OK
                app_version_db = ''
                if is_IOS(DEVICEOS):
                    app_version_db = version.ios_app_version
                else:
                    app_version_db = version.android_app_version
                if cmp(app_version, app_version_db) < 0:
                    return output_response(STATUS_CODE.APP_VERSION_OLD)
                elif dlc_version != version.dlc_version:
                    return output_response(STATUS_CODE.DLC_VERSION_OLD)
            else:
                log_error("version not exists")

        if verify_sign(request):
            return None
        else:
            return output_response(STATUS_CODE.AUTHENTICATION_ERROR)

def create_message(request, params):
    """
    create_message
    """
    host = request.get_host()
    host = host.split(',')[0]
    base_url = request.is_secure() and 'https://' or 'http://' + host + request.path
    oauth_request = OAuthRequestWithDupKey(
        request.method,
        base_url,
        params)
    message = '&'.join((
        oauth.escape(oauth_request.get_normalized_http_method()),
        oauth.escape(oauth_request.get_normalized_http_url()),
        oauth.escape(oauth_request.get_normalized_parameters())))
    return message


def create_hmac_hash(request, params, oauth_token_secret):
    """
    create_hmac_hash
    """
    message = create_message(request, params)
    shared_key = oauth.escape(oauth_token_secret)
    hashed = hmac.new(shared_key, message, hashlib.sha1)
    return hashed.digest()

def verify_sign(request):
    # 获取客户端oauth_signature字符串
    remote_hash = request.GET.get('oauth_signature', None)
    if not remote_hash:
        log_error("verify_sign failed: remote_hash not found or empty", remote_hash)
        return False
    remote_hash = base64.decodestring(remote_hash)

    # 合并GET和POST参数
    params = request.GET.copy()
    params.update(request.POST)

    # 本地签名
    local_hash = create_hmac_hash(request, params, settings.API_SECRET)
    if local_hash != remote_hash:
        log_error("verify_sign_params failed: ", request.method, remote_hash, local_hash)
        return False

    set_nonce(request)

    # 把加密的数据恢复回来
    # 加密的内容在data字段里面
    # 对客户端的要求：POST必有data字段
    if request.method == 'POST' and request.POST['data']:
        data_str = decrypt_message(request.POST['data'])
        request.POST = request.POST.copy()
        del request.POST['data']
        if data_str:
            for param in data_str.split('&'):
                if param.strip() == "":
                    continue
                #(key, value) = param.strip().split('=', 1)
                key_info = param.strip().split('=', 1)
                if len(key_info) == 2:
                    (key, value) = key_info
                else:
                    continue
                request.POST.update({key: urllib.unquote(value)})
        request.REQUEST.dicts = (request.POST, request.GET)

    return True


def get_stress_user_from_cookie(request):
    # COOKIES中是否有压测用户ID
    stress_user = request.COOKIES.get(settings.STRESS_USER_COOKIE_NAME, None)
    if stress_user is None:
        # 从压测用户ID一览中随机取一个
        stress_user = random.randint(1, settings.MAX_STRESS_USER_ID)

    return stress_user


def set_stress_user_to_cookie(request, response):
    # stress_user写回cookie
    response.set_cookie(settings.STRESS_USER_COOKIE_NAME, request.player_id)


def set_player_id(request):
    # 这里只负责根据mode来取player_id，允许player_id为None
    player_id = None

    if settings.USER_DEBUG:
        # USER_DEBUG模式，无视UUID
        player_id = str(settings.OPENSOCIAL_DEBUG_USER_ID)
    elif request.path.startswith('/api/'):  # api url以外请求不设置player_id
        # 普通模式，通过UUID获取
        uuid = request.META.get('HTTP_X_KK_UUID', None)
        if uuid is not None:
            try:
                player_id = UUID2PlayerID(uuid).get()
            except:
                from module.common.maintenance import get_request_ip
                log_error("Exception because HTTP_X_KK_UUID has values: ", uuid, get_request_ip(request))

    request.player_id = player_id


class OAuthRequestWithDupKey(OAuthRequest):
    """
    支持参数里面有多个相同的key的进行签名
    """
    def get_normalized_parameters(self):
        """Return a string that contains the parameters that must be signed."""
        params = self.parameters
        try:
            # Exclude the signature if it exists.
            del params['oauth_signature']
        except:
            pass
        # Escape key values before sorting.
        key_values = []
        for k, values in params.iterlists():
            for v in values:
                key_values.append((escape(_utf8_str(k)), escape(_utf8_str(v))))

        # Sort lexicographically, first after key, then after value.
        key_values.sort()
        # Combine key value pairs into a string.
        return '&'.join(['%s=%s' % (k, v) for k, v in key_values])
