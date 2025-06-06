import asyncio
import datetime
import os
import json
import uuid
from azure.ai.documentintelligence.aio import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import (
    AnalyzeResult,
    AnalyzeOutputOption,
    AnalyzeDocumentRequest,
    DocumentParagraph,
)
from azure.ai.inference.aio import EmbeddingsClient, ImageEmbeddingsClient
from azure.ai.inference.models import EmbeddingInput
from azure.core.exceptions import ResourceNotFoundError, HttpResponseError
from instructor import AsyncInstructor
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SimpleField,
    SearchableField,
    ComplexField,
    SearchFieldDataType,
    CorsOptions,
    VectorSearch,
    VectorSearchProfile,
    HnswAlgorithmConfiguration,
    SemanticSearch,
    SemanticConfiguration,
    SemanticPrioritizedFields,
    SemanticField,
    AzureMachineLearningVectorizer,
    AzureMachineLearningParameters,
)
from azure.storage.blob.aio import BlobServiceClient
from helpers import get_blob_as_base64
from collections import defaultdict


class ProcessFile:
    def __init__(
        self,
        document_client: DocumentIntelligenceClient,
        text_model: EmbeddingsClient,
        image_model: ImageEmbeddingsClient,
        search_client: SearchClient,
        index_client: SearchIndexClient,
        instructor_openai_client: AsyncInstructor,
        blob_service_client: BlobServiceClient,
        chatcompletions_model_name: str,
    ):
        self.document_client = document_client
        self.text_model = text_model
        self.image_model = image_model
        self.search_client = search_client
        self.index_client = index_client
        self.instructor_openai_client = instructor_openai_client
        self.blob_service_client = blob_service_client
        self.chatcompletions_model_name = chatcompletions_model_name
        self.container_client = self.blob_service_client.get_container_client(
            os.environ["ARTIFACTS_STORAGE_CONTAINER"]
        )
        self.sample_container_client = self.blob_service_client.get_container_client(
            os.environ["SAMPLES_STORAGE_CONTAINER"]
        )

    async def process_file(
        self,
        file_bytes: bytes,
        file_name: str,
        index_name: str,
    ):
        try:
            await self.sample_container_client.create_container()
        except Exception as e:
            print(f"Error creating samples container: {e}")
        try:
            await self.container_client.create_container()
        except Exception as e:
            print(f"Error creating knowledgeStore container: {e}")
        
        try:
            fields = [
                SimpleField(
                    name="content_id", type=SearchFieldDataType.String, key=True
                ),
                SimpleField(
                    name="text_document_id",
                    type=SearchFieldDataType.String,
                    searchable=False,
                    filterable=True,
                    hidden=False,
                    sortable=False,
                    facetable=False,
                ),
                SimpleField(
                    name="image_document_id",
                    type=SearchFieldDataType.String,
                    searchable=False,
                    filterable=True,
                    hidden=False,
                    sortable=False,
                    facetable=False,
                ),
                SearchableField(
                    name="document_title",
                    type=SearchFieldDataType.String,
                    searchable=True,
                    filterable=True,
                    hidden=False,
                    sortable=True,
                    facetable=True,
                ),
                SearchableField(
                    name="content_text",
                    type=SearchFieldDataType.String,
                    searchable=True,
                    filterable=True,
                    hidden=False,
                    sortable=True,
                    facetable=True,
                ),
                SearchField(
                    name="content_embedding",
                    hidden=False,
                    type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                    vector_search_dimensions=1024,
                    searchable=True,
                    vector_search_profile_name="hnsw",
                ),
                SimpleField(
                    name="content_path",
                    type=SearchFieldDataType.String,
                    searchable=False,
                    filterable=True,
                    hidden=False,
                    sortable=False,
                    facetable=False,
                ),
                ComplexField(
                    name="locationMetadata",
                    fields=[
                        SimpleField(
                            name="pageNumber",
                            type=SearchFieldDataType.Int32,
                            searchable=False,
                            filterable=True,
                            hidden=False,
                            sortable=True,
                            facetable=True,
                        ),
                        SimpleField(
                            name="boundingPolygons",
                            type=SearchFieldDataType.String,
                            searchable=False,
                            hidden=False,
                            filterable=False,
                            sortable=False,
                            facetable=False,
                        ),
                    ],
                ),
            ]

            vector_search = VectorSearch(
                algorithms=[
                    HnswAlgorithmConfiguration(
                        name="defaulthnsw",
                        kind="hnsw",
                        parameters={
                            "m": 4,
                            "efConstruction": 400,
                            "metric": "cosine",
                        },
                    )
                ],
                profiles=[
                    VectorSearchProfile(
                        name="hnsw",
                        algorithm_configuration_name="defaulthnsw",
                        vectorizer_name="cohere-vectorizer",
                    )
                ],
                vectorizers=[
                    AzureMachineLearningVectorizer(
                        vectorizer_name="cohere-vectorizer",
                        aml_parameters=AzureMachineLearningParameters(
                            scoring_uri=os.environ["AZURE_INFERENCE_EMBED_ENDPOINT"],
                            model_name=os.environ["AZURE_INFERENCE_EMBED_MODEL_NAME"],
                            authentication_key=os.environ[
                                "AZURE_INFERENCE_EMBED_API_KEY"
                            ],
                        ),
                    )
                ],
            )

            semantic_search = SemanticSearch(
                default_configuration_name="semanticconfig",
                configurations=[
                    SemanticConfiguration(
                        name="semanticconfig",
                        prioritized_fields=SemanticPrioritizedFields(
                            title_field=SemanticField(field_name="document_title"),
                            content_fields=[SemanticField(field_name="content_text")],
                        ),
                    )
                ],
            )

            cors_options = CorsOptions(allowed_origins=["*"], max_age_in_seconds=60)
            search_index = SearchIndex(
                name=index_name,
                fields=fields,
                cors_options=cors_options,
                vector_search=vector_search,
                semantic_search=semantic_search,
            )

            await self.index_client.create_index(search_index)

            print(f"Index {index_name} created successfully")
        except Exception as e:
            print(f"Error creating index: {e}")
        ext = file_name.split(".")[-1].lower()
        if ext == "pdf":
            await self._process_pdf(file_bytes, file_name, index_name)
        else:
            print(f"Unsupported file type: {file_name}")

    async def _process_pdf(self, file_bytes: bytes, file_name: str, index_name: str):
        """Processes PDF documents for text, layout, and image embeddings."""

        await self.sample_container_client.upload_blob(file_name, file_bytes, overwrite=True)

        paragraphs, images = await self.analyze_document(file_bytes, file_name)

        documents = []

        page_dict = defaultdict(list)
        for paragraph in paragraphs:
            for region in paragraph.bounding_regions:
                page_dict[region["pageNumber"]].append(paragraph)

        for page_number, paragraphs in list(page_dict.items()):
            print(f"Processing page {page_number} of {file_name}.")
            document_id = str(uuid.uuid4())

            text_chunks, text_metadata = self._chunk_text_with_metadata(
                page_number, paragraphs
            )

            print(f"Extracted {len(text_chunks)} text chunks.")
            if text_chunks:
                text_embeddings = (
                    await self.text_model.embed(
                        input=text_chunks,
                        model=os.environ["AZURE_INFERENCE_EMBED_MODEL_NAME"],
                    )
                ).data

                await asyncio.sleep(2)

                for idx, chunk in enumerate(text_chunks):
                    documents.append(
                        {
                            "content_id": f"{str(uuid.uuid4())}",
                            "document_title": file_name,
                            "text_document_id": f"{document_id}",
                            "content_text": chunk,
                            "locationMetadata": text_metadata[idx],
                            "content_embedding": text_embeddings[idx].embedding,
                        }
                    )
                    await self._check_and_index_documents(
                        documents, file_name, index_name
                    )

            associated_images = [
                img for img in images if img.get("page_number") == page_number
            ]

            for img in associated_images:
                print(f"Processing image {img['blob_name']} on page {page_number}.")

                blob_name = img["blob_name"]
                blob_client = self.container_client.get_blob_client(blob_name)
                image_base64 = await get_blob_as_base64(blob_client)
                documents.append(
                    {
                        "content_id": f"{str(uuid.uuid4())}",
                        "document_title": file_name,
                        "image_document_id": f"{document_id}",
                        "content_path": blob_name,
                        "locationMetadata": {
                            "pageNumber": img["page_number"],
                            "boundingPolygons": json.dumps([img["boundingPolygons"]]),
                        },
                        "content_embedding": await self._get_image_embedding(
                            image_base64
                        ),
                    }
                )
                await asyncio.sleep(2)
                await self._check_and_index_documents(documents, file_name, index_name)

        if documents:
            print(
                f"Indexing remaining documents for {file_name} with {len(documents)} documents."
            )
            await self._index_documents(index_name, documents)
            documents.clear()

    async def analyze_document(self, file_bytes, file_name):
        print(f"Analyzing document {file_name}.")

        try:
            poller = await self.document_client.begin_analyze_document(
                "prebuilt-layout",
                body=AnalyzeDocumentRequest(bytes_source=file_bytes),
                output=[AnalyzeOutputOption.FIGURES],
            )

        except HttpResponseError as e:
            print(f"Error analyzing document {file_name}: {e}")
            return

        result: AnalyzeResult = await poller.result()

        print(f"Extracting text and images from {file_name}.")

        images = await self._extract_figures(
            file_name, result, poller.details["operation_id"]
        )

        return result.paragraphs, images

    async def _check_and_index_documents(self, documents, file_name, index_name):
        """Checks if documents collection has reached 100 elements and indexes if needed."""
        if len(documents) == 10:
            print(f"Indexing document {file_name} with {len(documents)} chunks.")
            await self._index_documents(index_name, documents)
            documents.clear()

    async def _extract_figures(self, file_name, result, result_id):
        """Extracts figures and their metadata from the analyzed result."""

        blob_folder = os.path.join(
            os.environ["SEARCH_INDEX_NAME"],
            datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
        )

        images_info = []
        total_figures = len(result.figures or [])
        for i, figure in enumerate(result.figures or [], 1):
            print(f"Processing figure {i} of {total_figures}")
            try:
                response = await self.document_client.get_analyze_result_figure(
                    model_id=result.model_id, result_id=result_id, figure_id=figure.id
                )
                file_name = f"figure_{figure.id}.png"
                blob_name = f"{blob_folder}/{file_name}"

                image_data = b""
                async for chunk in response:
                    image_data += chunk

                await self.container_client.upload_blob(
                    name=blob_name, data=image_data, overwrite=True
                )

                info = {
                    "blob_name": blob_name,
                    "page_number": figure.bounding_regions[0].page_number,
                    "boundingPolygons": self._format_polygon(
                        figure.bounding_regions[0].polygon
                    ),
                }

                print(f"Processed image {blob_name}")
                images_info.append(info)
            except ResourceNotFoundError as e:
                print(f"Figure {figure.id} not found: {e}")
                continue
        return images_info

    async def _get_image_embedding(self, image_base64: str):
        """Generates image embeddings."""
        return (
            (
                await self.image_model.embed(
                    input=[
                        EmbeddingInput(image=f"data:image/png;base64,{image_base64}")
                    ]
                )
            )
            .data[0]
            .embedding
        )

    def _chunk_text_with_metadata(
        self, page_number, paragraphs: list[DocumentParagraph]
    ):
        """Chunks text and attaches metadata for each chunk."""

        chunks, metadata = [], []
        current_chunk, current_tokens, max_tokens, overlap = "", 0, 500, 50
        current_bounding_regions = []

        for paragraph in paragraphs or []:
            tokens = paragraph.content.split()

            if current_tokens + len(tokens) > max_tokens:
                chunks.append(current_chunk.strip())
                metadata.append(
                    {
                        "pageNumber": page_number,
                        "boundingPolygons": json.dumps(current_bounding_regions),
                    }
                )
                current_chunk = " ".join(tokens[-overlap:]) + " " + paragraph.content
                current_tokens = len(current_chunk.split())
                current_bounding_regions = []

            else:
                current_chunk += " " + paragraph.content
                current_tokens += len(tokens)

            if paragraph.bounding_regions:
                for region in paragraph.bounding_regions:
                    current_bounding_regions.append(
                        self._format_polygon(region.polygon)
                    )

        if current_chunk.strip():
            chunks.append(current_chunk.strip())
            metadata.append(
                {
                    "pageNumber": page_number,
                    "boundingPolygons": json.dumps(current_bounding_regions),
                }
            )

        filtered_chunks_metadata = [
            (chunk, meta) for chunk, meta in zip(chunks, metadata) if chunk.strip()
        ]
        filtered_chunks, filtered_metadata = (
            zip(*filtered_chunks_metadata) if filtered_chunks_metadata else ([], [])
        )

        return list(filtered_chunks), list(filtered_metadata)

    def _format_polygon(self, polygon):
        """Formats polygon coordinates."""
        return [
            {"x": polygon[i], "y": polygon[i + 1]} for i in range(0, len(polygon), 2)
        ]

    async def _index_documents(self, index_name, documents):
        """Indexes documents into Azure Cognitive Search."""
        try:
            # Validate JSON before sending
            try:
                json.dumps(documents)
            except json.JSONDecodeError as e:
                print(f"Invalid JSON in documents: {e}")
                return

            await self.search_client.upload_documents(documents=documents)
            print(f"Indexed {len(documents)} documents.")
        except Exception as e:
            print(f"Error indexing documents: {e}")
