"""OpenTelemetry optionnel — activé si OTEL_EXPORTER_OTLP_ENDPOINT est défini."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger('pinova.otel')

_initialized = False


def init_opentelemetry() -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True

    endpoint = (os.environ.get('OTEL_EXPORTER_OTLP_ENDPOINT') or '').strip()
    if not endpoint:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.django import DjangoInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.warning(
            'OTEL_EXPORTER_OTLP_ENDPOINT défini mais packages opentelemetry absents — pip install opentelemetry-*'
        )
        return

    service_name = os.environ.get('OTEL_SERVICE_NAME', 'pinova-backend')
    resource = Resource.create({'service.name': service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    DjangoInstrumentor().instrument()
    logger.info('OpenTelemetry initialisé service=%s endpoint=%s', service_name, endpoint)
