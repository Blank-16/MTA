import logging

logger = logging.getLogger(__name__)


def configure_otel(app) -> None:
    """
    Wires OpenTelemetry auto-instrumentation. Best-effort — any missing
    instrumentation package is skipped with a warning so startup never fails.
    Call this after app creation, before any middleware is added.
    """
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        
        resource = Resource.create({SERVICE_NAME: "medical-triage-backend"})
        provider = TracerProvider(resource=resource)

        # OTLP exporter — sends to Jaeger/Tempo/Honeycomb via collector
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter()  # reads OTEL_EXPORTER_OTLP_ENDPOINT from env
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("OTel OTLP exporter configured")
        except Exception as exc:
            logger.warning("OTel OTLP exporter unavailable: %s", exc)

        trace.set_tracer_provider(provider)
    except ImportError:
        logger.warning("opentelemetry-sdk not installed — tracing disabled")
        return

    # FastAPI auto-instrumentation
    _try_instrument("FastAPI", lambda: _instrument_fastapi(app))

    # psycopg auto-instrumentation
    _try_instrument("psycopg", lambda: _instrument_psycopg())

    # Redis auto-instrumentation
    _try_instrument("Redis", lambda: _instrument_redis())


def _try_instrument(name: str, fn) -> None:
    try:
        fn()
        logger.debug("OTel instrumented: %s", name)
    except Exception as exc:
        logger.warning("OTel instrumentation failed for %s (non-fatal): %s", name, exc)


def _instrument_fastapi(app) -> None:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    FastAPIInstrumentor.instrument_app(app)


def _instrument_psycopg() -> None:
    from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
    PsycopgInstrumentor().instrument()


def _instrument_redis() -> None:
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    RedisInstrumentor().instrument()
