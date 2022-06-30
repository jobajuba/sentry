import logging
from typing import Any, MutableMapping

from sentry import ratelimits, tsdb
from sentry.api.serializers import serialize
from sentry.eventstore.models import Event
from sentry.plugins.base import Plugin
from sentry.plugins.base.configuration import react_plugin_config
from sentry.plugins.status import PluginStatus

logger = logging.getLogger(__name__)


class DataForwardingPlugin(Plugin):
    status = PluginStatus.BETA

    def configure(self, project, request):
        return react_plugin_config(self, project, request)

    def has_project_conf(self):
        return True

    def get_rate_limit(self):
        """
        Returns a tuple of (Number of Requests, Window in Seconds)
        """
        return (50, 1)

    def forward_event(self, event: Event, payload: MutableMapping[str, Any]) -> bool:
        """Forward the event and return a boolean if it was successful."""
        raise NotImplementedError

    def get_event_payload(self, event):
        return serialize(event)

    def get_plugin_type(self):
        return "data-forwarding"

    def get_rl_key(self, event):
        return f"{self.conf_key}:{event.project.organization_id}"

    def initialize_variables(self, event):
        return

    def is_ratelimited(self, event):
        self.initialize_variables(event)
        rl_key = self.get_rl_key(event)
        # limit segment to 50 requests/second
        limit, window = self.get_rate_limit()
        if limit and window and ratelimits.is_limited(rl_key, limit=limit, window=window):
            logger.info(
                "data_forwarding.skip_rate_limited",
                extra={
                    "event_id": event.event_id,
                    "issue_id": event.group_id,
                    "project_id": event.project_id,
                    "organization_id": event.project.organization_id,
                },
            )
            return True
        return False

    def post_process(self, event, **kwargs):
        if self.is_ratelimited(event):
            return

        payload = self.get_event_payload(event)
        success = self.forward_event(event, payload)
        if success is False:
            # TODO(dcramer): record failure
            pass
        tsdb.incr(tsdb.models.project_total_forwarded, event.project.id, count=1)
