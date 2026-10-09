import json
from datetime import datetime, timedelta, timezone

from aiohttp import web
from azure.storage.blob.aio import ContainerClient, BlobServiceClient
from azure.storage.blob import generate_blob_sas, BlobSasPermissions


class CitationFilesHandler:
    def __init__(
        self,
        blob_service_client: BlobServiceClient,
        samples_container_client: ContainerClient,
    ):
        self.container_client = samples_container_client
        self.blob_service_client = blob_service_client

    async def handle(self, request):
        try:
            data = await request.json()
        except json.JSONDecodeError as error:
            raise web.HTTPBadRequest(text="Invalid JSON") from error
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("fileName"), str)
            or not data["fileName"].strip()
        ):
            raise web.HTTPBadRequest(text="A fileName is required")
        return web.json_response(await self._get_file_url(data["fileName"]))

    async def _get_file_url(self, blob_name: str):
        blob_client = self.container_client.get_blob_client(
            blob_name.replace("\\", "/")
        )
        now = datetime.now(timezone.utc)
        expiry_time = now + timedelta(minutes=5)

        # Create the user delegation key
        user_delegation_key = await self.blob_service_client.get_user_delegation_key(
            key_start_time=now - timedelta(minutes=5), key_expiry_time=expiry_time
        )
        sas_token = generate_blob_sas(
            account_name=blob_client.account_name or "",
            container_name=self.container_client.container_name,
            blob_name=blob_name.replace("\\", "/"),
            user_delegation_key=user_delegation_key,
            permission=BlobSasPermissions(read=True),
            expiry=expiry_time,
        )

        signed_url = f"{blob_client.url}?{sas_token}"
        return signed_url
