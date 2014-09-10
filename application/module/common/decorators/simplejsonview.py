# -*- coding: utf-8 -*-
from functools import wraps
import json

from django.http import HttpResponse
from django.conf import settings

def simplejsonview(view_func):
    @wraps(view_func)
    def decorate(request, *args, **kwargs):
        result = view_func(request, *args, **kwargs)
        if isinstance(result, HttpResponse):
            return result
        elif isinstance(result, dict):
            if settings.DEBUG:
                return HttpResponse(json.dumps(result, indent=4), mimetype="application/json")
            else:
                return HttpResponse(json.dumps(result), mimetype="application/json")
        else:
            return result

    return decorate

