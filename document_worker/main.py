from fastapi import FastAPI

from document_worker.api.routes import router


def create_app() -> FastAPI:
    application = FastAPI(
        title="DDOKBOT Document Worker",
        version="0.1.0",
        description="DDOKBOT Document Processing Worker API",
    )

    application.include_router(router)

    return application


app = create_app()