# -*- coding:utf-8 -*-

"""

クラスメソッド結果をキャッシュするデコレータ

"""

import hashlib
import base64
from functools import wraps
import logging

from django.db import models
from django.core.cache import cache as django_cache
from django.utils.encoding import smart_str

def _logging_verbose(message):
    pass
    #logging.debug('[METHOD_CACHE] %s' % message)


def _execute(method, obj, args, kwargs, cache_timeout=None, cache_backend=None, ignore_request=None):
    """
    メソッドを実行する
    実行結果がキャッシュされていれば、実行せずにそれを返す
    """
    cache_key = _generate_cache_key(obj, method, ignore_request, args, kwargs)
    #logging.debug('[METHOD_CACHE] cache_key=%s' % cache_key)
    if cache_backend is None:
        cache_backend = django_cache
    
    result = cache_backend.get(cache_key, None)
    if result is None:
        #メソッド実施!
        result = method(obj, *args, **kwargs)
        if cache_timeout is None:
            cache_backend.set(cache_key, result)
        else:
            cache_backend.set(cache_key, result, cache_timeout)
        _logging_verbose('cache NO hit. key=%s' % cache_key)
    else:
        _logging_verbose('cache hit. key=%s' % cache_key)
    return result


def _generate_cache_key(obj, method, ignore_request=False, args=[], kwargs={}):
    """
    キャッシュのキーを作成
    オブジェクト名, メソッド名, 引数を連結して作成。
    250文字を超えそうだったら、引数をハッシュ化する
    @param
        (class|instance) obj: クラスかインスタンス
        (function|str) method: メソッド自体か、そのメソッドの名前の文字列
        (bool)ignore_request: Trueの場合、'request'というパラメータ名があったら無視する
        (list) args: 引数リスト
        (dict) kw: キーワード引数のディクショナリ
    """
    KEY_LENGTH_LIMIT = 250
    o_name = obj.__name__ if hasattr(obj,'__name__') else obj.__class__.__name__
    if hasattr(method, '_original_method'):
        method = method._original_method
    f_name = method.func_name
    arg_names = method.func_code.co_varnames[1:method.func_code.co_argcount] 
    #↑引数の名前のリスト0には cls か self が入ってくるので見ない
    if not isinstance(args, (tuple, list,)):
        args = [args,]
    arg_nv_list = []
    for i in range(len(arg_names)):
        arg_name = arg_names[i]
        if ignore_request and arg_name == 'request':
            continue
        if len(args) > i:
            arg_nv_list.append((arg_name, args[i]))
        elif arg_name in kwargs:
            arg_nv_list.append((arg_name, kwargs[arg_name]))
        else:
            arg_nv_list.append((arg_name, ''))
    args_str = ','.join([ repr(arg_name) + ":" + _get_arg_value_unique_name(arg_value) for arg_name, arg_value in arg_nv_list ])
    approach_1 = "MC/%s/%s/%s" % (o_name, f_name, args_str)
    approach_1 = approach_1.replace(' ', '') #memcachedではスペース使えない 変に置換するより除去でいいか
    if len(approach_1) < KEY_LENGTH_LIMIT:
        return approach_1
    else:
        # キーが長すぎたので一部ハッシュ化
        hashed = hashlib.md5(args_str)
        hashed_key_part = base64.b64encode(hashed.digest())
        approach_2 = "MC/%s/%s/*%s" % (o_name, f_name, hashed_key_part)
        return approach_2[:KEY_LENGTH_LIMIT]


def _get_arg_value_unique_name(arg_value):
    """
    arg_value を、他のと区別できるような文字列を作る
    キャッシュのキーに使うため
    """
    if hasattr(arg_value, 'pk'):
        return str(arg_value.pk)
    else:
        return smart_str(arg_value, errors='ignore') #reprのほうがいい？


def method_cache(*args, **kwargs):
    """
    デコレータ本体
    
    基本的にクラスメソッドに使う。
    インスタンスメソッドでも使えるが、インスタンスが異なっても同じキャッシュのキーなので、
    期待してない結果が返ると思うので基本的に使わない。
    第一引数にクラスかインスタンスがくることを想定しているのでstaticmethodでは使えない。
    
    デコレータの一番下に書くこと推奨。(そうしないと対象メソッドの引数名が正しくとれない。多分。)
    
    @see: training/models.py TrainingStory
    
    from common.decorators.method_cache import method_cache, delete_method_cache
    
    class Hoge(object):
        
        @classmethod
        @method_cache
        def heavy_method(cls, arg1):
            ...
            ...
        
        def save(self):
            delete_method_cache(self, self.heavy_method, args=(self.arg1,))
            ...
            ...
        
    """
    cache_timeout = kwargs.pop('cache_timeout', None)
    cache_backend = kwargs.pop('cache_backend', None)
    ignore_request = kwargs.pop('ignore_request', None)
    assert not kwargs, "Keyword argument accepted is cache_backend or cache_timeout"
    if any((cache_timeout, cache_backend, ignore_request)):
        params = {}
        if cache_timeout is not None:
            params['cache_timeout'] = cache_timeout
        if cache_backend is not None:
            params['cache_backend'] = cache_backend
        if ignore_request is not None:
            params['ignore_request'] = ignore_request
        def _internal_params(method):
            @wraps(method)
            def decorate(obj, *args, **kwargs):
                return _execute(method, obj, args, kwargs, **params)
            decorate._original_method = method #デコレートされててもメソッド引数が参照できるように
            return decorate
        return _internal_params
    else:
        method = args[0]
        @wraps(method)
        def decorate(obj, *args, **kwargs):
            return _execute(method, obj, args, kwargs)
        decorate._original_method = method #デコレートされててもメソッド引数が参照できるように
        return decorate



def delete_method_cache(obj, method, args=[], kwargs={}, cache_backend=None, ignore_request=False):
    """
    キャッシュを削除。
    各モデルの save() なんかに仕込む。
    パラメータは、名前なし引数でも名前付き引数でもらっても大丈夫
    """
    cache_key = _generate_cache_key(obj, method, ignore_request, args=args, kwargs=kwargs)
    if cache_backend is None:
        cache_backend = django_cache
    cache_backend.delete(cache_key)
    _logging_verbose('cache delete. key=%s' % cache_key)


# 
# サンプル
# 
#class MethodCacheModel(models.Model):
#    """
#    method_cache デコレータを使うときには、必ず消すメソッドを各必要がある。
#    拡張先でdelete_cacheメソッドをオーバーライドすることで対応する。
#    """
#    class Meta:
#        abstract = True
#
#    def save(self, *args, **kwargs):
#        super(MethodCacheModel, self).save(*args, **kwargs)
#        self.delete_cache()
#
#    def delete(self, *args, **kwargs):
#        self.delete_cache()
#        super(MethodCacheModel, self).delete(*args, **kwargs)
#
#    def delete_cache(self):
#        super(MethodCacheModel, self).delete_cache()
#        delete_method_cache(self, self.get, args=(self.pk, ))
#        delete_method_cache(self, self.get_all)
#
#    @classmethod
#    @method_cache
#    def get_all(cls):
#        return list(cls.objects.all())
#
#    @classmethod
#    @method_cache
#    def get(cls, pk):
#        return cls.objects.get(pk = pk)
#

