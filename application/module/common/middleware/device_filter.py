# -*- coding: utf-8 -*-


from django.http import HttpResponse

HTML_ERROR = u"""\
<html> 
<head> 
<meta http-equiv="Content-Type" content="text/html;charset=Shift_JIS" /> 
<meta http-equiv="pragma" content="no-cache" /> 
<meta http-equiv="cache-control" content="no-cache" /> 
<meta http-equiv="expires" content="0" />
<meta name="viewport" content="width=240,user-scalable=no,maximum-scale=2" /> 
</head> 
<body> 
申し訳ございません｡<br /> 
お使いの端末には対応しておりません｡ 
</div> 
</body> 
</html> 
"""

def _error_response():
    response = HttpResponse(HTML_ERROR, mimetype="text/html", status=200)
    return response




class DeviceFilterMiddleware(object):
    """
    Willcomで接続した時などにエラーメッセージを表示
    mobilejpのミドルウェア群の後の実施すること
    """
    def process_request(self, request):
        if hasattr(request, 'device'):
            if request.device.is_willcom():
                return _error_response()
