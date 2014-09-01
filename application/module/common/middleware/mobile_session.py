# -*- coding: utf-8 -*-

import time
import uamobile
import hashlib

from django.conf import settings
from django.utils.cache import patch_vary_headers
from django.utils.http import cookie_date
from django.core.cache import cache


def create_hashed_debug_user_id(request):
    """
    requestから、ランダムなユーザーIDを作成する。
    HTTP_USER_AGENT と、REMOTE_ADDR から一意なIDを生成。
    opensocial ライブラリが変わったら追従すること
    """
    bulk_user_id = request.META.get('HTTP_USER_AGENT')
    hashed_debug_osuser_number = int(hashlib.sha1(bulk_user_id).hexdigest()[5:11],16)
    hashed_debug_osuser_number = hashed_debug_osuser_number % 100000000
    opensocial_debug_user_id = hashed_debug_osuser_number  + 9900000000
    return str(opensocial_debug_user_id)

def get_opensocial_owner_id(request):
    opensocial_owner_id = None
    if settings.OPENSOCIAL_DEBUG:
        if settings.OPENSOCIAL_DEBUG_USER_ID:
            opensocial_owner_id = settings.OPENSOCIAL_DEBUG_USER_ID
        else:
            # OPENSOCIAL_DEBUG_USER_ID = False とか、 "" だった場合、ユーザーエージェントとIPアドレスからユーザーIDを生成
            opensocial_owner_id = create_hashed_debug_user_id(request)
        request.opensocial_userid = str(opensocial_owner_id)
    else:
        if u'opensocial_owner_id' in request.REQUEST:
            opensocial_owner_id = request.REQUEST[u'opensocial_owner_id']
    return opensocial_owner_id


class MobileSessionMiddleware(object):
    '''
    OpenSocial用のセッションミドルウェア
    '''
    cache_key_name = 'session_key_%s'

    def get_agent(self, request):
        return getattr(request, 'agent', uamobile.detect(request.META))

    def get_cache_key(self, guid):
        return self.cache_key_name % guid

    def process_view(self, request, view_func, view_args, view_kwargs):
        pass

    def process_request(self, request):
        engine = __import__(settings.SESSION_ENGINE, {}, {}, [''])
        agent = self.get_agent(request)
        opensocial_owner_id = get_opensocial_owner_id(request)
        if opensocial_owner_id:
            # opensocial_owner_id を一意の値としてセッションに用いる
            session_key = cache.get(self.get_cache_key(opensocial_owner_id))
            request.session = engine.SessionStore(session_key)

    def process_response(self, request, response):
        # If request.session was modified, or if response.session was set, save
        # those changes and set a session cookie.
        agent = self.get_agent(request)
        try:
            accessed = request.session.accessed
            modified = request.session.modified
        except AttributeError:
            pass
        else:
            if accessed:
                patch_vary_headers(response, ('Cookie',))
            if modified or settings.SESSION_SAVE_EVERY_REQUEST:
                if request.session.get_expire_at_browser_close():
                    max_age = None
                    expires = None
                else:
                    max_age = request.session.get_expiry_age()
                    expires_time = time.time() + max_age
                    expires = cookie_date(expires_time)
                # Save the session data and refresh the client cookie.
                request.session.save()
                #request.session.modified = False  # ここでFalseにするとSessioMiddlewareで２度書きを防げるが、管理画面にログインできなくなる
                # memcacheにセッションキーをセット
                opensocial_owner_id = get_opensocial_owner_id(request)
                if opensocial_owner_id:
                    session_key = cache.set(self.get_cache_key(opensocial_owner_id), request.session.session_key, settings.SESSION_COOKIE_AGE)
        return response
