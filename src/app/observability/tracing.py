from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from src.app.core.config import Settings


def configure_tracing(app: FastAPI, settings: Settings) -> None:
    if not settings.telemetry_enabled:
        return

    provider = TracerProvider(
        resource=Resource.create({"service.name": settings.telemetry_service_name})
    )
    exporter = (
        OTLPSpanExporter(endpoint=settings.telemetry_otlp_endpoint)
        if settings.telemetry_otlp_endpoint
        else ConsoleSpanExporter()
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
