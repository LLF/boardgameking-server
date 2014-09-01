# -*- coding: utf-8 -*-
from threading import local

thread_local = local()


def set_smartphone(is_smartphone):
    global thread_local
    if thread_local is None:
        thread_local = local()
    thread_local.is_smartphone = is_smartphone


def set_featurephone(is_featurephone):
    global thread_local
    if thread_local is None:
        thread_local = local()
    thread_local.is_featurephone = is_featurephone


def is_smartphone(): 
    global thread_local
    if thread_local is None:
        return False
    if not hasattr(thread_local, 'is_smartphone'):
        return False
    return thread_local.is_smartphone


def is_featurephone():
    global thread_local
    if thread_local is None:
        return False
    if not hasattr(thread_local, 'is_featurephone'):
        return False
    return thread_local.is_featurephone


class DeviceEnvironmentMiddleware(object):
    '''
    device環境に合わせる
    '''
    def process_request(self, request):
        if hasattr(request, 'is_smartphone'):
            set_smartphone(request.is_smartphone)
        if hasattr(request, 'is_featurephone'):
            set_featurephone(request.is_featurephone)
