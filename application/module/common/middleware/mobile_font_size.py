# -*- coding: utf-8 -*-

import re

RE_MOBILE_FONT_SIZE = re.compile(r'MOBILE-FONT-SIZE-(\w+)')

class MobileFontSizeMiddleware(object):
    """
    携帯により文字サイズを変更するミドルウェア
    MOBILE-FONT-SIZE-NORMAL
    MOBILE-FONT-SIZE-LARGE
    """
    
    
    def process_response(self, request, response):
        
        if request.path.startswith("/m/") or \
            request.path.startswith("/debugroom/") or request.path.startswith("/promo/"):
            pass
        else:
            return response
        
        content_type = response.get('Content-Type',"")
        if not content_type.startswith("text/html"):
            return response
        
        if not hasattr(request, 'device'):
            return response
        
        if not hasattr(request.device, 'display'):
            return response
        
        content = response.content
        def change_font_size(m):
            size_id = m.group(1)
            if size_id == 'NORMAL':
                if request.device.is_softbank():
                    if request.device.display.is_vga():
                        return 'medium'
                    else:
                        return 'x-small'
                elif request.device.is_docomo():
                    return 'xx-small'
                else:
                    return '10px'
            elif size_id == 'LARGE':
                if request.device.is_softbank():
                    if request.device.display.is_vga():
                        return 'large'
                    else:
                        return 'medium'
                else:
                    return 'medium'
            else:
                return m.group(0)
        content = RE_MOBILE_FONT_SIZE.sub(change_font_size, content)
        
        response.content = content
        return response

