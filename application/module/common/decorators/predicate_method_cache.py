# -*- coding: utf-8 -*-
from functools import wraps
from django.core.cache import get_cache

cache = get_cache('default')


def predicate_method_cache(prefix=None):
    '''
    述語関数の結果をキャッシュする
    '''
    def _(func):
        @wraps(func)
        def __(*args, **kwargs):
            if not prefix:
                pre = func.__name__
            else:
                pre = prefix
            key = _cache_key(pre, *args, **kwargs)
            value = cache.get(key)
            if value is None:
                value = func(*args, **kwargs)
                cache.set(key, value)
            return bool(value)
        return __
    return _


def predicate_method_cache_delete(prefix=None):
    '''
    述語関数のキャッシュを削除する
    '''
    def _(func):
        @wraps(func)
        def __(*args, **kwargs):
            value = func(*args, **kwargs)
            if not prefix:
                pre = func.__name__
            else:
                pre = prefix
            key = _cache_key(pre, *args, **kwargs)
            cache.delete(key)
            return bool(value)
        return __
    return _


def _cache_key(prefix, *args, **kwargs):
    import sha
    args_str = ":".join([str(arg) for arg in args])
    kwargs_str = ":".join([str(kwarg[0]) + '-' + str(kwarg[1]) for kwarg in kwargs.items()])
    return '{}:{}'.format(prefix, sha.sha(args_str + '.' + kwargs_str).hexdigest())
