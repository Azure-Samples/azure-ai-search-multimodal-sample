import logging
import os
from pathlib import Path
from aiohttp import web
from rich.logging import RichHandler
from openai import AsyncAzureOpenAI
from azure.identity.aio import (
    DefaultAzureCredential,
    get_bearer_token_provider,
)
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient
from azure.search.documents.agent.aio import KnowledgeAgentRetrievalClient
from azure.core.pipeline.policies import UserAgentPolicy

from azure.storage.blob.aio import BlobServiceClient

from search_grounding import SearchGroundingRetriever
from knowledge_agent import KnowledgeAgentGrounding
from constants import USER_AGENT
from multimodalrag import MultimodalRag
from data_model import DocumentPerChunkDataModel
from citation_file_handler import CitationFilesHandler


logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)],
)


async def list_indexes(index_client: SearchIndexClient):
    indexes = []
    async for index in index_client.list_indexes():
        indexes.append({"name": index.name})
    return web.json_response([index["name"] for index in indexes])


async def create_app():
    tokenCredential = DefaultAzureCredential()
    tokenProvider = get_bearer_token_provider(
        tokenCredential,
        "https://cognitiveservices.azure.com/.default",
    )

    chatcompletions_model_name = os.environ["AZURE_OPENAI_MODEL_NAME"]
    openai_endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    search_endpoint = os.environ["SEARCH_SERVICE_ENDPOINT"]
    search_index_name = os.environ["SEARCH_INDEX_NAME"]
    knowledge_agent_name = os.environ["KNOWLEDGE_AGENT_NAME"]
    openai_deployment_name = os.environ["AZURE_OPENAI_DEPLOYMENT"]

    search_client = SearchClient(
        endpoint=search_endpoint,
        index_name=search_index_name,
        credential=tokenCredential,
        user_agent_policy=UserAgentPolicy(base_user_agent=USER_AGENT),
    )
    data_model = DocumentPerChunkDataModel()

    index_client = SearchIndexClient(
        endpoint=search_endpoint,
        credential=tokenCredential,
        user_agent_policy=UserAgentPolicy(base_user_agent=USER_AGENT),
    )

    ka_retrieval_client = KnowledgeAgentRetrievalClient(
        agent_name=knowledge_agent_name,
        endpoint=search_endpoint,
        credential=tokenCredential,
    )

    knowledge_agent = KnowledgeAgentGrounding(
        ka_retrieval_client,
        search_client,
        index_client,
        data_model,
        search_index_name,
        knowledge_agent_name,
        openai_endpoint,
        openai_deployment_name,
        chatcompletions_model_name,
    )

    openai_client = AsyncAzureOpenAI(
        azure_ad_token_provider=tokenProvider,
        api_version="2024-08-01-preview",
        azure_endpoint=openai_endpoint,
        timeout=30,
    )

    search_grounding = SearchGroundingRetriever(
        search_client,
        openai_client,
        data_model,
        chatcompletions_model_name,
    )

    blob_service_client = BlobServiceClient(
        account_url=os.environ["ARTIFACTS_STORAGE_ACCOUNT_URL"],
        credential=tokenCredential,
    )
    artifacts_container_client = blob_service_client.get_container_client(
        os.environ["ARTIFACTS_STORAGE_CONTAINER"]
    )
    samples_container_client = blob_service_client.get_container_client(
        os.environ["SAMPLES_STORAGE_CONTAINER"]
    )

    app = web.Application(middlewares=[])

    mmrag = MultimodalRag(
        knowledge_agent,
        search_grounding,
        openai_client,
        chatcompletions_model_name,
        artifacts_container_client,
    )
    mmrag.attach_to_app(app, "/chat")

    citation_files_handler = CitationFilesHandler(
        blob_service_client, samples_container_client
    )

    current_directory = Path(__file__).parent
    app.add_routes(
        [
            web.get(
                "/", lambda _: web.FileResponse(current_directory / "static/index.html")
            ),
            web.get("/list_indexes", lambda _: list_indexes(index_client)),
            web.post("/get_citation_doc", citation_files_handler.handle),
        ]
    )
    app.router.add_static("/", path=current_directory / "static", name="static")

    return app


if __name__ == "__main__":
    host = os.environ.get("HOST", "localhost")
    port = int(os.environ.get("PORT", 5000))
    web.run_app(create_app(), host=host, port=port)
