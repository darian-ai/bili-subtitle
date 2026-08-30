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


class UnsupportedVideoType(MetadataError):
    """视频使用当前版本不支持的内容或播放器模型。"""


class VideoNotReadyError(MetadataError):
    """视频尚未进入普通投稿的稳定可处理状态。"""


class NetworkError(MetadataError):
    """访问平台时发生网络错误。"""


class RedirectError(MetadataError):
    """短链未能安全解析到受支持的视频页。"""


class PlatformResponseError(MetadataError):
    """平台响应不符合当前支持的结构。"""


class SubtitleError(Exception):
    """单轨道字幕流程的稳定错误基类。"""


class NoSubtitles(SubtitleError):
    """分集具有合法但为空的字幕集合。"""


class AuthenticationRequired(SubtitleError):
    """当前会话无效。"""


class SubtitleAccessDenied(SubtitleError):
    """当前账号无权访问字幕。"""


class SubtitleNetworkError(SubtitleError):
    """字幕请求发生网络故障。"""


class SubtitlePlatformResponseError(SubtitleError):
    """字幕平台响应不符合支持的结构。"""


class ExportError(SubtitleError):
    """字幕文件无法安全发布。"""
