"""微信公众号 API 客户端兼容门面。"""

from .wechat.base import BASE_URL, BaseWechatClient
from .wechat.comment import CommentMixin
from .wechat.datacube import DatacubeMixin
from .wechat.draft import DraftMixin
from .wechat.material import MaterialMixin
from .wechat.menu import MenuMixin
from .wechat.message import MessageMixin
from .wechat.misc import MiscMixin
from .wechat.publish import PublishMixin
from .wechat.user import UserMixin


class WechatClient(
    DraftMixin,
    PublishMixin,
    MaterialMixin,
    DatacubeMixin,
    UserMixin,
    MenuMixin,
    CommentMixin,
    MessageMixin,
    MiscMixin,
    BaseWechatClient,
):
    """组合各接口域，并保持 v1 的公开构造与方法签名。"""


__all__ = ["BASE_URL", "WechatClient"]
