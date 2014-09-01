# -*- coding: utf-8 -*-

from threading import local

_requests = local()


def get_request():
    if hasattr(_requests, 'value'):
        return _requests.value
    else:
        return None

def set_request(request):
    _requests.value = request

class GlobalRequestMiddleware(object):
    def process_request(self, request):
        _requests.value = request

    def process_response(self, request, response):
        if hasattr(_requests, 'value'):
            del _requests.value
        return response
