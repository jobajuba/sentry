from abc import ABC
from enum import Enum
from typing import Any, Optional, Sequence

from sentry.integrations.notifications import AbstractMessageBuilder
from sentry.templatetags.sentry_helpers import absolute_uri
from sentry.utils.assets import get_asset_url

URL_FORMAT_STR = "[{text}]({url})"


class TextSize(Enum):
    SMALL = "Small"
    MEDIUM = "Medium"
    LARGE = "Large"


class TextWeight(Enum):
    BOLDER = "Bolder"
    LIGHTER = "Lighter"


class MSTeamsMessageBuilder(AbstractMessageBuilder, ABC):
    def build(self) -> Any:
        """Abstract `build` method that all inheritors must implement."""
        raise NotImplementedError

    @staticmethod
    def get_text_block(text: str, size: Optional[TextSize] = None) -> Any:
        return {
            "type": "TextBlock",
            "text": text,
            "wrap": True,
            "size": size.value if size else None,
        }

    def get_logo_block(self) -> Any:
        self.get_image_block(get_asset_url("sentry", "images/sentry-glyph-black.png"))

    @staticmethod
    def get_image_block(url: str) -> Any:
        return {
            "type": "Image",
            "url": absolute_uri(url),
            "size": "Large",
        }

    @staticmethod
    def get_column_block(*columns: Any) -> Any:
        return {
            "type": "ColumnSet",
            "columns": [
                {"type": "Column", "items": [column], "width": "auto"} for column in columns
            ],
        }

    def _build(
        self,
        text: Any,
        title: Optional[Any] = None,
        footer: Optional[Any] = None,
        actions: Optional[Sequence[Any]] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Helper to DRY up MS Teams specific fields.
        :param string text: Body text.
        :param [string] title: Title text.
        :param [string] footer: Footer text.
        :param kwargs: Everything else.
        """
        body = []
        if title:
            body.append(title)
        if text:
            body.append(text)

        body.extend(kwargs.get("fields"))

        if footer:
            body.append(footer)

        # TODO MARCOS should this be the buttons instead?
        for action in actions or []:
            body.append(action)

        return {
            "body": body,
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.2",
        }
