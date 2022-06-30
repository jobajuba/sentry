import math
from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

from sentry import features
from sentry.api.bases.project import ProjectEndpoint, ProjectPermission
from sentry.models import Project
from sentry.snuba import discover
from sentry.utils.dates import parse_stats_period


def percentile_fn(data, percentile):
    """
    Returns the nth percentile from a sorted list

    :param percentile: A value between 0 and 1
    :param data: Sorted list of values
    """
    if len(data) == 0:
        return None
    pecentile_idx = len(data) * percentile
    if pecentile_idx.is_integer():
        return data[int(pecentile_idx)]
    else:
        return data[int(math.ceil(pecentile_idx)) - 1]


class DynamicSamplingPermission(ProjectPermission):
    # ToDo(ahmed): Revisit the permission level for Dynamic Sampling once the requirements are
    #  better defined
    scope_map = {"GET": ["project:write", "project:admin"]}


class ProjectDynamicSamplingDistributionEndpoint(ProjectEndpoint):
    private = True
    permission_classes = (DynamicSamplingPermission,)

    @staticmethod
    def _get_sample_rates_data(data):
        distribution_functions = {
            "min": lambda lst: min(lst, default=None),
            "max": lambda lst: max(lst, default=None),
            "mean": lambda lst: sum(lst) / len(lst) if len(lst) > 0 else None,
            "p50": lambda lst: percentile_fn(data, 0.5),
            "p90": lambda lst: percentile_fn(data, 0.9),
            "p95": lambda lst: percentile_fn(data, 0.95),
            "p99": lambda lst: percentile_fn(data, 0.99),
        }
        return {key: func(data) for key, func in distribution_functions.items()}

    def get(self, request: Request, project) -> Response:
        """
        Generates distribution function values for client sample rates from a random sample of
        root transactions, and provides the projects breakdown for these transaction when
        creating a dynamic sampling rule for distributed traces.
        ``````````````````````````````````````````````````

        :pparam string organization_slug: the slug of the organization the
                                          release belongs to.
        :qparam string query: If set, this parameter is used to filter root transactions.
        :qparam string sampleSize: If set, specifies the sample size of random root transactions.
        :qparam string distributedTrace: Set to distinguish the dynamic sampling creation rule
                                    whether it is for distributed trace or single transactions.
        :qparam string statsPeriod: an optional stat period (can be one of
                                    ``"24h"``, ``"14d"``, and ``""``).
        :auth: required
        """
        if not features.has(
            "organizations:filters-and-sampling", project.organization, actor=request.user
        ):
            return Response(
                {
                    "detail": [
                        "Dynamic sampling feature flag needs to be enabled before you can perform "
                        "this action."
                    ]
                },
                status=404,
            )

        query = request.GET.get("query", "")
        requested_sample_size = min(int(request.GET.get("sampleSize", 100)), 1000)
        distributed_trace = request.GET.get("distributedTrace", "1") == "1"
        stats_period = min(
            parse_stats_period(request.GET.get("statsPeriod", "1h")), timedelta(hours=24)
        )

        end_time = timezone.now()
        start_time = end_time - stats_period

        # Fetches a random sample of root transactions of size `sample_size` in the last period
        # defined by `stats_period`. The random sample is fetched by ordering by the
        # `random_number` which is generated by a `random_number` function which generates a random
        # number for every row. The goal here is to fetch the transaction ids, their sample rates
        # and their trace ids.
        root_transactions = discover.query(
            selected_columns=[
                "id",
                "trace",
                "trace.client_sample_rate",
                "random_number() AS random_number",
            ],
            query=f"{query} event.type:transaction !has:trace.parent_span_id",
            params={
                "start": start_time,
                "end": end_time,
                "project_id": [project.id],
                "organization_id": project.organization,
            },
            orderby=["-random_number"],
            offset=0,
            limit=requested_sample_size,
            equations=[],
            auto_fields=True,
            auto_aggregations=True,
            allow_metric_aggregates=True,
            use_aggregate_conditions=True,
            transform_alias_to_input_format=True,
            functions_acl=["random_number"],
            referrer="dynamic-sampling.distribution.fetch-parent-transactions",
        )["data"]

        sample_size = len(root_transactions)
        sample_rates = sorted(
            transaction.get("trace.client_sample_rate") for transaction in root_transactions
        )
        if len(sample_rates) == 0:
            return Response(
                {
                    "project_breakdown": None,
                    "sample_size": sample_size,
                    "null_sample_rate_percentage": None,
                    "sample_rate_distributions": None,
                }
            )

        non_null_sample_rates = sorted(
            float(sample_rate) for sample_rate in sample_rates if sample_rate not in {"", None}
        )

        project_breakdown = None
        if distributed_trace:
            # If the distributedTrace flag was enabled, then we are also interested in fetching
            # the project breakdown of the projects in the trace of the root transaction
            trace_id_list = [transaction.get("trace") for transaction in root_transactions]
            projects_in_org = Project.objects.filter(organization=project.organization).values_list(
                "id", flat=True
            )

            project_breakdown = discover.query(
                selected_columns=["project", "count()"],
                query=f"event.type:transaction trace:[{','.join(trace_id_list)}]",
                params={
                    "start": start_time,
                    "end": end_time,
                    "project_id": list(projects_in_org),
                    "organization_id": project.organization,
                },
                equations=[],
                orderby=[],
                offset=0,
                limit=20,
                auto_fields=True,
                auto_aggregations=True,
                allow_metric_aggregates=True,
                use_aggregate_conditions=True,
                transform_alias_to_input_format=True,
                referrer="dynamic-sampling.distribution.fetch-project-breakdown",
            )["data"]

            # If the number of the projects in the breakdown is greater than 10 projects,
            # then a question needs to be raised on the eligibility of the org for dynamic sampling
            if len(project_breakdown) > 10:
                return Response(
                    status=status.HTTP_400_BAD_REQUEST,
                    data={
                        "details": "Way too many projects in the distributed trace's project breakdown"
                    },
                )

        return Response(
            {
                "project_breakdown": project_breakdown,
                "sample_size": sample_size,
                "null_sample_rate_percentage": (
                    (sample_size - len(non_null_sample_rates)) / sample_size * 100
                ),
                "sample_rate_distributions": self._get_sample_rates_data(non_null_sample_rates),
            }
        )
