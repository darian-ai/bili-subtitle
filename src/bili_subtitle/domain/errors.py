"""阶段二向应用层暴露的稳定错误分类。"""


class MetadataError(Exception):
    """输入与元数据流程的预期失败。"""


class InputError(MetadataError):
    """用户输入无法解析或不在支持范围内。"""


class InvalidPageError(MetadataError):
    """请求的分集不存在。"""


class VideoNotFoundError(MetadataError):
    """投稿不存在或已删除。"""


class AccessDeniedError(MetadataError):
    """平台拒绝当前访问。"""


class NetworkError(MetadataError):
    """访问平台时发生网络错误。"""


class RedirectError(MetadataError):
    """短链未能安全解析到受支持的视频页。"""


class PlatformResponseError(MetadataError):
    """平台响应不符合当前支持的结构。"""
