# -*- coding: utf-8 -*-

import re

class QvgaSizeMiddleware(object):
    """
    
    width:60px
    height="200"
    
    などを検出して、VGA機ならサイズを2倍にする
    
    """
    
    #RE_QVGA_SIZE = re.compile(r"qvga-(width|height):(\d+)px", re.I)
    #RE_QVGA_SIZE = re.compile(r"qvga-(width|height)(\s*:\s*|=)([\"\']*)(\d+)([\"\']*)(px|)", re.I)
    RE_QVGA_SIZE = re.compile(r'(width|height)(\s*:\s*|=)([\"\']*)(\d+)([\"\']*)(px|)', re.I)
    
    def process_response(self, request, response):
        
        if not request.path.startswith("/m/"):
            return response
        
        content_type = response.get('Content-Type',"")
        if not content_type.startswith("text/html"):
            return response
        
        if not hasattr(request, 'device'):
            return response
        
        if not hasattr(request.device, 'display'):
            return response
        
        if not request.device.display.is_vga():
            return response
        
        #VGA対応端末なので適用
        content = response.content
        def qvga_width_double(m):
            width = int(m.group(4))
            return "%s%s%s%s%s%s" % (m.group(1), m.group(2), m.group(3), width * 2, m.group(5), m.group(6))
        content = self.RE_QVGA_SIZE.sub(qvga_width_double, content)
        
        response.content = content
        return response

