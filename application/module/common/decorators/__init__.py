# -*- coding: utf-8 -*-
import datetime
from functools import wraps

from django.conf import settings
from django.core.cache import get_cache
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from module.common.redirector.redirector import Redirector
from module.common.redirector.utils import mask
from submodule.gsocial.http import HttpResponseOpensocialRedirect

import warnings

_keep_request = None

def keep_request(view_func):
    def decorate(request, *args, **kwds):

        # do something
        global _keep_request
        _keep_request = request

        return view_func(request, *args, **kwds)
        decorate.__doc__ = view_func.__doc__
        decorate.__dict__ = view_func.__dict__
    return decorate

def get_kept_request():
    global _keep_request
    return _keep_request


class RedirectHandler(object):

    urlpattern = r'(?P<redirector_token>@[^/]+\/)?'

    def __init__(self, default, function, recv_url, redirector):
        redirector.handler = self
        self.redirector = redirector
        self.recv_url = recv_url
        self.function = function
        self.default = default

    def __call__(self, token, request, *args, **kwargs):
        request.redirector = self.redirector
        if token:
            return self.dispatch(request, token)
        return self.start(request, *args, **kwargs)

    def dispatch(self, request, token):
        callback = self.redirector.recv(token[1:-1])
        if callback:
            request.next_url = self.redirector.finish_url
            next_token = self.redirector.next_stack()
            if next_token:
                request.next_url = self.token_compact_to_url(self.recv_url, next_token)
            return callback(request)
        return HttpResponseOpensocialRedirect(self.redirector.finish_url)

    def start(self, request, *args, **kwargs):
        response = self.function(request, *args, **kwargs)
        if type(response) == bool:
            return response
        if response is None:
            return HttpResponseOpensocialRedirect(reverse(self.default))
        if request.is_ajax() and response["Content-Type"] == "text/json":
            return response
        if not isinstance(response, HttpResponseRedirect):
            raise TypeError('%s is not HttpResponseRedirect object.' % response)

        finish_url = response["Location"]
        if finish_url.startswith('http://'):
            finish_url = finish_url[len('http://' + settings.SITE_DOMAIN):]

        if not self.redirector.stack:
            return HttpResponseOpensocialRedirect(finish_url)

        return HttpResponseOpensocialRedirect(self.redirector(self.token_compact_to_url(self.recv_url, self.redirector.first_stack()), finish_url))

    @classmethod
    def token_compact_to_url(cls, url, token, params=None):
        url = url.rstrip('/')
        token = token.rstrip('/')
        url = '%s/@%s/' % (url, token)
        # if params:
            # url += '?%s' % params
        return url

    @classmethod
    def token_extract_from_url(cls, url):
        token = url.rstrip('/')
        token = token[token.rfind('/') + 1:]
        if token.startswith('@'):
            return token
        return None

class form_keeper(object):
    def __init__(self, updated=()):
        self.updated = updated

    def __call__(self, view_func):
        self.session_key = 'form_keeper:%s.%s' % (view_func.__module__, view_func.__name__)

        @wraps(view_func)
        def _form_keeper(request, *args, **kwargs):
            params = request.session.get(self.session_key, {})

            params.update(dict((x, request.REQUEST[x]) for x in self.updated if x in request.REQUEST))
            request.session[self.session_key] = params

            params = params.copy()
            params.update(request.REQUEST)
            request.form_keeper = params
            return view_func(request, *args, **kwargs)

        def clear(request, keys=()):
            if keys:
                params = request.session.get(self.session_key, {})
                for key in keys:
                    if key in params:
                        del params[key]

                request.session[self.session_key] = params
            else:
                if self.session_key in request.session:
                    del request.session[self.session_key]

        def update(request, update):
            if type(update) == dict:
                params = request.session.get(self.session_key, {})
                params.update(update)
                request.session[self.session_key] = params

        def get(request, key, default=None):
            return request.session.get(self.session_key, {}).get(key, default)

        _form_keeper.clear = clear
        _form_keeper.update = update
        _form_keeper.get = get
        return _form_keeper


def deprecated(func):
    '''This is a decorator which can be used to mark functions
    as deprecated. It will result in a warning being emitted
    when the function is used.'''
    
    @wraps(func)
    def new_func(*args, **kwargs):
        warnings.warn_explicit(
            "Call to deprecated function {}.".format(func.__name__),
            category=DeprecationWarning,
            filename=func.func_code.co_filename,
            lineno=func.func_code.co_firstlineno + 1
        )
        return func(*args, **kwargs)

    return new_func