import re
from urllib.parse import urlparse


def extract_url(text):
    for match in re.findall(r"https?://[^\s<>]+", text):
        url = match.rstrip(".,;!?，。；！）)]}>'\"")
        host = (urlparse(url).hostname or "").lower()
        if host in {
            "douyin.com",
            "www.douyin.com",
            "v.douyin.com",
            "iesdouyin.com",
            "www.iesdouyin.com",
        }:
            return url
    raise ValueError("链接不合法：请粘贴抖音分享链接或完整分享文案")
